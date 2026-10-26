# Rehearsal — one-way interview practice (runs locally)

Claude writes the question (and the data for chart questions). You get a prep timer, then your webcam records the answer. Speech, voice and eye contact are analysed **on your machine**. Only the transcript and metrics are sent to Claude for grading. Raw video never leaves your computer.

## One-time setup (~10 min)

You need **Python 3.10, 3.11 or 3.12**. 3.13 won't work because mediapipe has no wheels for it. Check with `python3 --version` (Mac) or `python --version` (Windows).

**Mac / Linux**
```bash
cd interview-coach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Windows (PowerShell)**
```powershell
cd interview-coach
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` in a text editor and paste your Anthropic API key after `ANTHROPIC_API_KEY=`. Don't paste keys into any chat.

## Run

- Mac/Linux: `./run.sh`
- Windows: double-click `run.bat`

Open **http://localhost:5050** in **Chrome**. Allow camera and microphone.

The first run downloads the Whisper speech model (~500 MB for `small.en`). Your first answer will wait for that download to finish.

## First session

1. Write what you're preparing for in the context box: firm, role, programme, the format you've been told, and your background. Every question and every piece of feedback uses it.
2. Click **Calibrate eye contact** once. Look straight into the lens for 4 s. Redo it if you move your laptop or seating position.
3. Pick a question type, set the prep and answer seconds to match your real interview, and click **Get a question**.
4. Click **Start**. The prep timer runs, then recording starts automatically. Click **Finish answer** to stop early.
5. Feedback appears in 30–90 s. Use **Redo this question** to drill the same question with the "next attempt" fix. That redo loop is where most of the improvement comes from.

Everything is saved in `data/`. Use **Past attempts** to replay any answer with its feedback.

## What's measured

| Signal | How | Reliability |
|---|---|---|
| Transcript, pace, pauses, time to first word, cut-off | faster-whisper word timestamps | Good |
| Fillers (um/uh) | Whisper primed to keep disfluencies | Decent. Some still get dropped, so counts are a floor. |
| Pitch variation (monotone) | librosa pYIN | Rough heuristic |
| Eye contact + look-away direction with timestamps | MediaPipe iris + head-pose vs your calibration | Heuristic. Spot-check by clicking the timestamps to replay. |
| Answer quality | Claude, type-specific rubric, strict calibration, evidence-cited | Main signal |

The delivery target ranges are coaching heuristics, not validated standards: 130–170 wpm, <3 fillers/min, first word <3 s, eye contact >80%.

## Tuning

- `.env` → `WHISPER_MODEL=base.en` for faster transcription, `medium.en` for better accuracy.
- `.env` → `CLAUDE_MODEL` to switch Claude model.
- Gaze flags too much or too little: edit `MIN_THRESH` at the top of the gaze section in `analysis.py`. Higher values mean less sensitive.
- If look-away **left/right is reversed**, your camera driver mirrors video. Swap the two strings in `_direction()` in `analysis.py`.

## Troubleshooting

- **"Camera/mic unavailable"**: close Zoom/Teams and other apps using the camera, then check Chrome's site permissions.
- **Port in use**: change `port=5050` at the bottom of `app.py`.
- **`pip install` fails on mediapipe**: wrong Python version. Use 3.10–3.12.
- **Error mentioning `ANTHROPIC_API_KEY`**: `.env` is missing, or the key wasn't pasted into it.
