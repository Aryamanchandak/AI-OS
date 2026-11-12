# Gesture Control — weekend POC

The dumb magic, per §11 of the brief. One camera, six gestures, a wake/sleep
gate, hard-coded actions. **No agent, no screen context, no smart path** — those
are deliberately absent, not unfinished.

```
camera → recognizer → GATE → ┬─ fast path (scroll)      → executor
                             └─ discrete (approve/…)    → executor
```

---

## Before anything: two permission grants

This is the step that silently kills these projects. Synthetic events don't
error when unauthorised — they just don't happen, which reads exactly like
broken gesture code.

Both grants attach to **the app that launches Python** (Terminal, iTerm, VS
Code), not to the script.

1. **System Settings → Privacy & Security → Accessibility** → add and tick your
   terminal app. **Then quit and reopen that app** — the grant is read at
   process start, so a running terminal won't pick it up.
2. **System Settings → Privacy & Security → Camera** → same app.

Then verify, and don't skip this:

```bash
.venv/bin/python preflight.py
```

It checks the grant, opens the camera, loads the model, and posts a real scroll
event for you to confirm with your eyes. If preflight fails, nothing downstream
will work.

---

## Setup

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

mkdir -p models && curl -sSL -o models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

### Two version traps, already hit and pinned

- **MediaPipe 1.0.x is unusable on macOS arm64 here.** Its
  `TensorsToDetectionsCalculator` forces a Metal path that aborts the whole
  process (`graph_service.h:139] Check failed: service_`), and `delegate=CPU`
  does not avoid it. Pinned to `0.10.21`.
- **`mp.solutions.hands` no longer exists** in MediaPipe 1.x. Essentially every
  tutorial online (the brief's "Bucket 2") uses that legacy API. This code uses
  the Tasks API (`HandLandmarker`), which needs the downloaded `.task` bundle.
- MediaPipe 0.10 pins `numpy<2`, so OpenCV must stay on the 4.x line. Those
  three versions move together.

---

## Run

```bash
.venv/bin/python main.py          # DRY RUN — recognises and displays, posts nothing
.venv/bin/python main.py --live   # actually drives the machine
```

Start in dry run. Watch the HUD fire correctly a few dozen times before you let
it press Return in your terminal for real.

**Keys** (HUD focused): `q` quit · `space` force-disarm · `d` toggle dry run.

---

## The gesture dictionary

The contract between hand and machine. Every entry tagged continuous or
discrete, because they behave completely differently downstream.

| Gesture | Type | When | Action |
|---|---|---|---|
| **Open palm** (5 fingers) | discrete | asleep | **Wake** — must hold 0.6 s |
| **Fist** (0 fingers) | discrete | armed | **Sleep** — instant, no dwell |
| **Two fingers** (index + middle) | **continuous** | armed | **Scroll** — trackpad metaphor |
| **Thumbs up** | discrete | armed | Approve (Return) |
| **Thumbs down** | discrete | armed | Reject (Escape) |
| **Point** (index only) | discrete | armed | Next track |

Two-finger scroll is chosen because it *already is* the trackpad gesture — it
needs no explaining, which is the §8 rule of thumb.

---

## What the build settled from §12

**Wake and sleep are different gestures, and deliberately asymmetric.**
Waking needs a sustained 0.6 s open palm; sleeping is an instant fist. The costs
are asymmetric, so the gestures should be: a false wake arms a system that can
approve a deploy, while a false sleep is merely a mild annoyance you notice
instantly. When you want out, you want out *now*.

**Segmentation — intentional flick vs. incidental motion.** Three independent
guards, since one is never enough:
- *stability window* — a pose must survive 4 consecutive frames to count at all
- *edge trigger* — discrete actions fire on entering a pose, never while held
- *refractory period* — 1 s cooldown absorbs flicker out-and-back

**Scroll mapping is accelerated, not linear.** Deadzone (a resting hand emits
exactly zero) → subtract the deadzone so motion enters from zero rather than
jumping → power curve at 1.35 → clamp at 120 px/frame so one bad landmark can't
launch the page. All in `config.py`; expect to tune them at the desk.

The scroll *direction* is unverified — no event has landed yet, so the sign
comes from the documented `CGEvent` convention rather than observation. If your
first live run scrolls backwards, swap the two branches at the end of
`fastpath.py`. One character.

**Where the context read lives** — not answered, because the smart path isn't
built. That's the right next question, not this one.

**Objective function for the POC** — proposed:

> *Scroll a page and approve a prompt without touching the trackpad, and never
> once have the system act when I didn't ask it to.*

The second clause is the hard half, and it's the one the gate and the three
segmentation guards exist to serve.

---

## An honest note on the privacy claim

The brief says cameras "are not interpreting anything until explicitly armed."
That can't be literally true — something has to watch for the wake gesture, so
hand landmarks are extracted on every frame, always.

The defensible property, which this code does enforce:

> While disarmed, no gesture is resolved into an action, no action is executed,
> no screen is captured, and nothing leaves the machine.

Landmark extraction is local, stateless, never recorded. The gate is one
structural boundary in `main.py`, not an `if armed:` inside each handler — the
next action someone adds would forget that check.

**The kill switch is a key, never a gesture.** If the only way out of the armed
state were a hand pose, a recognizer having a bad day could trap you in it.

---

## Files

| File | Role |
|---|---|
| `preflight.py` | Step 0 — permissions, camera, model, real scroll test |
| `config.py` | Every tunable. The feel of the system lives here |
| `recognizer.py` | Frame → 21 landmarks → pose label (rule-based, no training) |
| `gate.py` | Wake/sleep state machine |
| `fastpath.py` | Hand motion → scroll magnitude |
| `actions.py` | Executor — synthetic scroll and key events |
| `calibrate.py` | Live pose readout — validates the classifier against a real hand |
| `main.py` | The loop and the HUD |
| `test_logic.py` | 33 headless tests — no camera or grant needed |

```bash
.venv/bin/python test_logic.py
```

### What those 33 tests do *not* prove

`test_logic.py` builds synthetic hands using the same geometric rule the
classifier uses to read them. The gate, scroll and executor tests are real —
they cover interrupted wakes, held-pose repeats, refractory flicker, hand-loss
resets. **The seven classifier tests are not.** They prove the function agrees
with itself.

The classifier has never seen a real hand. The thumb rule in particular
(*tucked thumb ends up nearer the pinky knuckle than its own IP joint*) is a
heuristic written from reasoning, and it decides THUMBS_UP vs THUMBS_DOWN —
which is to say **approve vs reject**.

So before `--live`:

```bash
.venv/bin/python calibrate.py
```

Hold all six poses at desk height. The question that matters: *does thumbs-down
ever read as `thumbs_up`, `fist`, or `none`?* If so, the thumb rule needs
replacing (thumb-tip-to-index-MCP distance, or a wrist-relative angle) — but
observe first, don't rewrite preemptively.

---

## Deliberately not built

The smart path. No screenshot capture, no accessibility-API app detection, no
agent call, no context-dependent resolution of "up". The brief is right that
this is the novel part — and right that building it now is how this project
becomes a design document instead of a thing that works.

Ship the toy first.
