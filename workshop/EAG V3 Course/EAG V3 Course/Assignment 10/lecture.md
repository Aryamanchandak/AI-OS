
Session 10: Computer-Use Agent
1. What this session is
A charter to make a Computer-Use Agent. No code release.

This session tells you how to build a computer-use skill, an agent that drives real desktop applications and what will silently break on the way. The code samples in this document are shapes of code you will write. The assignment is yours to build.

Two reasons it reads that way. First, computer-use is more OS-dependent than browser-use; what works on your Mac may work differently on your colleague's Windows machine. A single shipped skill cannot cover that. Second, the lessons here are the kind you only learn by hitting the traps. We can map the traps; you still have to walk through them.


2. How the world changed
A computer-use agent in 2024 needed a custom perception pipeline: icon detection, OCR, button classifiers, a VLM on top. That path worked and was expensive, brittle, and slow. I built that from scratch hoping, people would need to learn that, but I was wrong (which was good!).

Three things changed by 2026. OS accessibility APIs got mature Python bindings on every major platform. Frontier VLMs got reliable on UI screenshots. A unified driver cua-driver exposes all three OS accessibility APIs behind one JSON tool surface. The 2024 perception stack collapses into two paths: read the accessibility tree and ask a cheap text model what to click, or screenshot and ask a vision model. Everything between is gone.

3. Tools and terms
A one-line reference. Things we should know before we proceed.

Term	What it is
AX tree	The accessibility tree. A semantic, screen-reader-shaped view of a window's UI elements.
cua-driver	A Rust binary that reads AX trees and synthesises clicks/keystrokes on macOS, Linux, Windows.
Daemon	A long-running cua-driver serve process that holds the element-index cache.
element_index	A turn-scoped integer the daemon assigns to each actionable AX node.
TCC	macOS Transparency, Consent, Control — the system that gates Accessibility and Screen Recording grants.
UAC	Windows User Account Control — the elevation prompt some apps require.
Portal	Linux org.freedesktop.portal.* services — how Wayland gates input.
CDP	Chrome DevTools Protocol. Lets you drive any Chromium window through CSS selectors.
Electron	Apps that ship a Chromium runtime as their UI (VS Code, Slack, Notion, Discord, Cursor).
Set-of-marks	A screenshot with numbered boxes drawn over UI regions for a vision model to pick from (Session 9).
AppleScript activation	A one-line osascript call that brings a macOS app to the foreground.
4. What cua-driver gives you
cua-driver is the core library that launches apps, walks AX trees, synthesises clicks, keystrokes, drags, scrolls, hotkeys, screenshots, and records trajectories. It speaks JSON over a Unix socket. 34 tools with same control mechanisms on macOS, Linux, Windows. The full reference guide is shared in CUA_DRIVER_GUIDE.md.

What it does not do: planning, goal decomposition, perception interpretation, error recovery, vision. That is your job.

You always talk to a running daemon — cua-driver serve. The daemon holds the per-window element-index cache. You need to start it once per session.

def ensure_daemon():
    if subprocess.run(["cua-driver", "status"]).returncode != 0:
        subprocess.Popen(["cua-driver", "serve"])
        time.sleep(0.5)

5. What you can drive, what you cannot
Before picking an assignment target, look at this table.

Target category	Driveable?	Through what
Native productivity apps (Calculator, Notes, Mail, file pickers, Settings, Office)	Yes	AX tree
Electron apps (VS Code, Slack, Discord, Notion, Cursor, Obsidian, Linear, 1Password)	Yes — with a flag	CDP, by relaunching with electron_debugging_port
Chrome / Safari / Firefox (the rendered page)	Yes — with a flag	CDP / Safari Remote Automation
Games (anything OpenGL / Metal / Vulkan / DirectX)	Vision only	Screenshot + click by coordinate
Canvas-rendered web (Figma, Google Maps, Photopea)	Vision only	Same
DRM-protected players, banking apps, login screen, Touch ID prompt	No	These deliberately disable AX and forbid synthetic input
Anything elevated (installers, system settings on Windows)	Only if the agent runs elevated too	Match the privilege level
Two general rules fall out of this table. Apps built with standard platform UI toolkits expose a full AX tree. Anything that paints its own pixels — games, canvas, custom renderers — does not. Pick your assignment knowing which side of that line your target application sits on.

6. The four layers
The browser cascade from Session 9 transfers to the desktop wholesale. Same shape, different logic at each layer.

nothing useful in tree

no known sequence

tree empty or target missing

tree never readable

Layer 1: extract
AX text / clipboard / file contents
$0

Layer 2a: deterministic
known hotkeys, fixed sequences
$0

Layer 2b: a11y
AX tree + cheap text LLM
cents

Layer 3: vision
screenshot + set-of-marks + vision LLM
dollars

Precondition: permissions
TCC / Wayland portal / UAC
app activated

error: precondition_blocked

Layer 1 — extract
Read content directly from the AX tree (or the clipboard, or a file). For "what does this email say" or "what is in cell B3" no click is needed. The text is already in the tree. Zero LLM cost. Try this first.

Layer 2a — deterministic
When the goal is "compute 42 × 18 in Calculator" and you know Calculator's hotkeys, the whole interaction is a sequence of press_key calls. No LLM in the loop. This is the path students skip because writing hotkey sequences is boring; it is also the path that keeps assignments cheap. Of course you'd need to build a skill where some LLM is pushing these hotkeys in order.

Layer 2b — a11y tree
get_window_state returns the AX tree as Markdown with every actionable element tagged [element_index N]. A cheap text LLM (free-tier Gemini 3.1 Flash-Lite through the V9 gateway from Session 9) reads the markdown plus the goal and emits a JSON action. You dispatch the action by element_index. The loop repeats.

This is the workhorse layer. Most assignment runs should land here.

Layer 3 — vision
When the AX tree comes back empty after activation, when the target element is missing from the tree, or when the goal is inherently visual ("click the button that looks like a triangle"), capture a screenshot, draw numbered marks over UI regions, send to V9's /v1/vision endpoint, click by (x, y).

Vision is roughly 10× the per-turn cost of Layer 2b. Use it as the genuine last resort. The most common cost mistake on this assignment is escalating to vision when AX would have worked.


7. The scan-act-verify loop
Every turn, for every window, runs three phases.

scan   → get_window_state(pid, window_id)        builds element index cache
act    → click / type_text / press_key / hotkey  addresses by element_index
verify → get_window_state(pid, window_id)        confirms state changed
Two invariants to be careful about. If either of them breaks, the agent will silently misbehave.

Invariant 1. Call get_window_state once per turn per window before any element-indexed action. That call builds the element_index → AX node cache. With no cache, every click fails with "element_index N not found in cache for pid=...".

Invariant 2. Every new get_window_state snapshot replaces the previous index map. UIs reflow: a dialog opens, a menu pops up, a list re-sorts, and the AX walk visits nodes in a different order. An element_index from snapshot N is a turn-scoped token. Re-scan after every state-changing action.

The verify step is the most important pattern in the loop. A click that returns success does not mean the action achieved its intent. The button might have been disabled. The form might have rejected the input silently. The window might have backgrounded between scan and act. Re-read the AX tree after every action and check one post-condition: did the expected element appear, did the field update, did the title change.


8. The Traps that look the same
Four different causes produce the same surface symptom: element_count: 0, or a cache miss on a click that should have worked. A student debugging linearly will mistake one for another and lose hours.

Symptom	Likely cause	One-line guard
element_count: 0 on first scan	Permissions not granted (TCC / portal / UAC)	Raise a PermissionsError immediately, link to grant command
element_count: 0 after launching an app on macOS	App was launched in the background, window not realised yet	AppleScript activation, sleep 0.5s, re-scan
element_count: 0 on a Qt app on Linux	QT_ACCESSIBILITY=1 not set when the app launched	Launch the app with that env var set
Cache miss on a click that worked last turn	UI reflowed, indices shifted	Re-scan before any element-indexed action
element_count: 0 on Electron apps	Window is one opaque AXWebArea to AX	Relaunch with electron_debugging_port, use page tool (Layer 2 special case)
element_count: 0 on a game, Figma, Photopea	Renderer paints its own pixels, no AX nodes	Layer 3 vision, no recovery available
The single guard that saves the most time:

state = call("get_window_state", {...})
if state["element_count"] == 0:
    raise PreconditionError(
        "cua-driver returned an empty AX tree. "
        "Check: (1) permissions granted, (2) app activated, "
        "(3) QT_ACCESSIBILITY=1 if Linux/Qt, (4) Electron debugging port if Electron."
    )
8.1 Permissions, briefly
macOS. Two TCC grants — Accessibility and Screen Recording — attach to cua-driver's bundle ID. Run cua-driver permissions grant and accept both system dialogs. Granting through the terminal binds the grant to the terminal; the driver silently fails later.

Linux. X11 sessions need nothing. Wayland sessions need a portal grant per session — interactive, not persistent. Most production setups default to X11 until the portal flow matures.

Windows. Most apps need no special setup. Apps that elevate (installers, system settings) require the agent to run elevated too.

8.2 The background-launch trap (macOS)
launch_app uses LaunchServices and explicitly does not steal focus from the user's foreground app. The response field self_activation_suppressed: true confirms this. A backgrounded app's main window is not yet built in the AX hierarchy, so the first get_window_state returns the system menu bar and zero app buttons.

bring_to_front would seem to fix this. Read its schema: Windows-only, errors on macOS.

The workaround:

subprocess.run(
    ["osascript", "-e", f'tell application "{app_name}" to activate'],
    check=True,
)
time.sleep(0.5)
After activation, the same get_window_state call returns the full UI (e.g. 237 elements for Calculator). One-time per session.


9. The Electron escape hatch
A large fraction of modern desktop apps are Chromium browsers in disguise: VS Code, Cursor, Slack, Discord, Notion, Linear desktop, 1Password, Obsidian. To AX they look like a single opaque AXWebArea.

cua-driver's answer: launch the app with a debugging port and drive its DOM through Chrome DevTools Protocol directly.

cua-driver call launch_app '{
  "bundle_id": "com.microsoft.VSCode",
  "electron_debugging_port": 9222
}'

cua-driver call page '{
  "pid": <vscode_pid>,
  "action": "click",
  "selector": ".tabs-container .tab.active"
}'
The page tool gives you the full CDP surface: CSS selectors, JavaScript evaluation, element waiting, navigation. For Tauri or WebKit-based apps use webkit_inspector_port instead. Without these flags, the apps are pixel-only.

Useful planner pattern: read list_apps, pattern-match against a known list of Electron apps, and when the target matches, relaunch with the debugging port. One branch unlocks the entire CDP path. The Browser cascade from Session 9 already understands CDP, so the desktop-Electron path borrows it directly.

For browsers themselves the same trick applies: Chrome supports --remote-debugging-port natively, Safari needs Develop → Allow Remote Automation, recent Firefox builds support CDP.

10. The five layers that you will build
cua-driver gives you perception and action. Five layers above it are yours. Each has a cost-quality knob you control.

Layer	What it does	Cost knob
Goal decomposition	Maps natural-language goal to ordered app-level subgoals	Frontier vs cheap model for the planner
Perception interpretation	Filters the AX tree markdown into something an LLM can act on	Pre-filter with query arg, summarise with cheap model, regex-extract structured rows. Biggest knob.
Action sequencing	Translates subgoals into the scan-act-verify loop, respecting the re-scan invariant	How aggressively you re-scan vs cache
Error recovery	Element gone after re-scan, permission denied, unexpected modal, app crashed	How much state you carry across the failure
Vision fallback	Captures screenshot, draws set-of-marks, calls V9 vision, parses verdict	Trigger threshold for escalation
The Layer 2b judgment LLM emits a structured action with one of two verdicts: act with an element_index, or escalate with a reason. Your dispatch reads the verdict and routes. This mirrors Browser's output.path field from Session 9, and the replay viewer surfaces it the same way.


11. Recording and replay
cua-driver ships start_recording and replay_trajectory. Use them.

Every run records to a turn-numbered directory of (tool, args) pairs. When the agent fails, the trajectory is the evidence. When it succeeds, the trajectory is a regression test.

call("start_recording", {"output_dir": f"/tmp/run-{session_id}"})
try:
    run_agent(goal)
finally:
    call("stop_recording", {})
Replay against the same starting UI state:

call("replay_trajectory", {"trajectory_dir": f"/tmp/run-{session_id}"})
The assignment requires recording every submitted run. The trajectory directory plus the YouTube demo are the submission's evidence.


12. Wiring into the Session 9 runtime
Your Computer-Use skill drops into the catalogue alongside Browser. The S9 code does not change. The catalogue entry has the same shape as Browser's: a prompt file, a description, no provider pin. The dispatch branch in skills.py adds one if skill.name == "computer" line. The V9 gateway from Session 9 handles every LLM and vision call — no new gateway. The replay viewer shows your chosen layer the same way it shows Browser's. The cost ledger tags calls under agent: computer.

The takeaway: integration is one line. The interesting work is the five layers above the driver.

13. Running safely on your real machine (enterprise)
cua-driver runs on the real host. The agent controls your actual apps, sees your files, can read clipboard contents, can navigate to authenticated sites in your browser. An agent bug that closes the wrong file or sends the wrong email has real consequences.

The full sandbox path is the cua Python SDK with Sandbox.ephemeral(Image.macos()), which boots a macOS VM through Apple's Virtualization framework. Heavyweight (gigabytes of disk, slow startup), macOS-only. In Session 12 we will cover proper container isolation.

For any enterprise effort, the recommended setup:

A fresh user account on the machine for the any run. Grant permissions to cua-driver under that account. The agent operates only on test files inside that account's home directory.
A backup of any data the agent might touch.
The verify step on every action, especially destructive ones.
kill_app and Cmd-Z are the two recovery primitives. Test them before recording. If a run goes wrong, cua-driver shutdown kills the daemon and the agent stops within a second.

14. Assignment
Build a Computer-Use skill that drops into the Session 9 catalogue and solves three real tasks on your primary OS. Respect the five-layer architecture so the cascade discipline is visible in the code. Record every run with start_recording and submit the trajectory directory as evidence.

Pick three tasks from this list:

A Calculator or simple-arithmetic task using deterministic hotkeys (Layer 2a).
A spreadsheet or notes-app task using the AX tree and cheap text LLM judgment (Layer 2b).
A task in an Electron app (VS Code, Slack, Cursor, Notion, Discord) using the page tool with electron_debugging_port.
A task in a canvas-rendered or game-style target that forces Layer 3 vision (a small browser game, Figma desktop, a sketching app with no ARIA).
An email or message draft composition that exercises Layer 2b with strong verification.
A multi-app workflow that switches between two apps and moves data between them.
Constraints:

At least one task uses vision.
At least one task uses the Electron page path.
At least one task completes with zero vision calls.
Submission: a GitHub repository README and a YouTube demo. The README covers the architecture (the five layers), the three tasks, the cascade decisions, and any failure modes encountered. The YouTube demo shows the agent operating live for at least one task with the agent-cursor overlay visible.

Constraints on the path: no paid APIs, no third-party agentic frameworks. V9 gateway from Session 9 for all LLM and vision calls. cua-driver as the substrate. Read CUA_DRIVER_GUIDE.md before starting.

Safety: read §13 before any run that touches important data. A fresh user account is the recommended setup.

15. Coming up!
Session 11 introduces channels. Your Computer-Use skill becomes one input among many to an agent that reads from WhatsApp, Slack, voice, and email, and writes back through the same channels. From Session 10 onwards, you own your own code! 🙃