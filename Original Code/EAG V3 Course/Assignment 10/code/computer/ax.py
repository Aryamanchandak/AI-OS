"""macOS accessibility tree — the OS analogue of browser/dom.py.

Deliberately mirrors dom.py's contract: an `Element` with an integer mark,
role, name and screen bbox, and a `UISnapshot` exposing `by_id()` and
`legend()`. Because the shapes match, the Layer-2b and Layer-3 drivers are
structurally the same code as the browser skill's — only the enumerator and
the dispatcher change.

Coordinates differ from the browser in one way that matters: these are
*global screen* points, not viewport-relative CSS pixels. There is no
scrolling offset to correct for, but there is a Retina scale factor, and it
applies to screenshots rather than to AX geometry — AX already reports
points, and `screen.py` is what has to divide. Keeping that conversion out
of this file is intentional: AX geometry stays in one unit system.

Requires Accessibility permission for the *controlling* process (the
terminal or IDE running this). `ax_available()` reports that up front so
the cascade can escalate instead of silently enumerating nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    kAXChildrenAttribute,
    kAXDescriptionAttribute,
    kAXFocusedAttribute,
    kAXPositionAttribute,
    kAXRoleAttribute,
    kAXSizeAttribute,
    kAXTitleAttribute,
    kAXValueAttribute,
    kAXWindowsAttribute,
)
from AppKit import NSWorkspace
import Quartz


# Roles worth handing to a model. Everything else is structure (groups,
# splitters, scroll areas) that inflates the legend without adding an
# action target. Static text is included because on macOS it carries the
# readable state — a calculator's display is AXStaticText, not a value.
INTERACTIVE_ROLES = {
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXMenuButton",
    "AXTextField", "AXTextArea", "AXSecureTextField", "AXComboBox",
    "AXSlider", "AXIncrementor", "AXLink", "AXMenuItem", "AXTabGroup",
    "AXCell", "AXRow", "AXStaticText", "AXValueIndicator", "AXDisclosureTriangle",
}


def ax_available() -> bool:
    """True when this process may read other apps' AX trees."""
    return bool(AXIsProcessTrusted())


@dataclass
class Element:
    id: int
    tag: str          # kept for legend parity with dom.Element
    role: str
    name: str
    x: int            # global screen points, top-left of bbox
    y: int
    w: int
    h: int
    value: str = ""
    focused: bool = False

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    def legend_line(self) -> str:
        """dom.py-compatible: `[id]<tag role="role">name</tag>`, with the
        AX value appended when it differs from the name — for text fields
        and displays the value *is* the state the model must reason about."""
        role = f' role="{self.role}"' if self.role else ""
        name = self.name or ""
        extra = ""
        if self.value and self.value != name:
            extra = f' value="{self.value}"'
        focus = " focused" if self.focused else ""
        return f"[{self.id}]<{self.tag}{role}{extra}{focus}>{name}</{self.tag}>"


@dataclass
class UISnapshot:
    elements: list[Element]
    app: str
    window_title: str = ""

    def by_id(self, mark: int) -> Element | None:
        for e in self.elements:
            if e.id == mark:
                return e
        return None

    def legend(self, max_chars: int = 40_000) -> str:
        text = "\n".join(e.legend_line() for e in self.elements)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[truncated]"
        return text

    def text_dump(self) -> str:
        """Layer-1 read: every readable string, no marks, no LLM. This is
        what a pure extraction answers from."""
        out = []
        for e in self.elements:
            for s in (e.name, e.value):
                if s and s not in out:
                    out.append(s)
        return "\n".join(out)


# ── raw AX plumbing ─────────────────────────────────────────────────────────
def _attr(el, name):
    """Read one AX attribute, returning None on any AX error. The API
    returns (error_code, value); a non-zero code means the attribute is
    absent or the element died mid-walk, both of which are normal during a
    live UI walk and must not raise."""
    try:
        err, val = AXUIElementCopyAttributeValue(el, name, None)
    except Exception:                                    # noqa: BLE001
        return None
    return val if err == 0 else None


def _as_str(v) -> str:
    if v is None:
        return ""
    try:
        return str(v).strip()
    except Exception:                                    # noqa: BLE001
        return ""


def _geometry(el) -> tuple[int, int, int, int] | None:
    """Returns (x, y, w, h) in global screen points, or None if the element
    has no usable geometry (offscreen, zero-sized, or not positioned)."""
    pos, size = _attr(el, kAXPositionAttribute), _attr(el, kAXSizeAttribute)
    if pos is None or size is None:
        return None
    try:
        p = Quartz.CGPoint()
        s = Quartz.CGSize()
        # AXValue boxes a CGPoint/CGSize; unbox via the AXValue API.
        from ApplicationServices import (
            AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType,
        )
        if not AXValueGetValue(pos, kAXValueCGPointType, p):
            return None
        if not AXValueGetValue(size, kAXValueCGSizeType, s):
            return None
    except Exception:                                    # noqa: BLE001
        return None
    x, y, w, h = int(p.x), int(p.y), int(s.width), int(s.height)
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def pid_for_app(app_name: str) -> int | None:
    """Resolve a running app's pid by (case-insensitive) localized name."""
    target = app_name.lower()
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        name = _as_str(a.localizedName()).lower()
        if name == target or target in name:
            return int(a.processIdentifier())
    return None


def enumerate_ui(app_name: str, *, max_elements: int = 400,
                 max_depth: int = 28) -> UISnapshot:
    """Walk the frontmost window of `app_name` and return marked elements.

    Depth- and count-capped: AX trees in Electron apps can run to tens of
    thousands of nodes, and an unbounded walk would both hang and blow past
    any sane token budget. The caps are generous enough for native apps and
    are the reason Electron targets take the CDP path instead."""
    if not ax_available():
        return UISnapshot(elements=[], app=app_name,
                          window_title="(accessibility permission not granted)")
    pid = pid_for_app(app_name)
    if pid is None:
        return UISnapshot(elements=[], app=app_name,
                          window_title=f"(app not running: {app_name})")

    app_el = AXUIElementCreateApplication(pid)
    windows = _attr(app_el, kAXWindowsAttribute) or []
    if not windows:
        return UISnapshot(elements=[], app=app_name, window_title="(no windows)")
    win = windows[0]
    title = _as_str(_attr(win, kAXTitleAttribute))

    elements: list[Element] = []
    next_id = 1

    def walk(el, depth: int) -> None:
        nonlocal next_id
        if depth > max_depth or len(elements) >= max_elements:
            return
        role = _as_str(_attr(el, kAXRoleAttribute))
        if role in INTERACTIVE_ROLES:
            geo = _geometry(el)
            if geo:
                x, y, w, h = geo
                name = (_as_str(_attr(el, kAXTitleAttribute))
                        or _as_str(_attr(el, kAXDescriptionAttribute)))
                value = _as_str(_attr(el, kAXValueAttribute))
                # Unnamed, valueless nodes are noise — they give the model
                # nothing to select on and cost tokens.
                if name or value:
                    elements.append(Element(
                        id=next_id, tag=role.replace("AX", "").lower(),
                        role=role, name=name, x=x, y=y, w=w, h=h,
                        value=value,
                        focused=bool(_attr(el, kAXFocusedAttribute)),
                    ))
                    next_id += 1
        for child in (_attr(el, kAXChildrenAttribute) or []):
            walk(child, depth + 1)

    walk(win, 0)
    return UISnapshot(elements=elements, app=app_name, window_title=title)
