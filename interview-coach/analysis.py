"""Local analysis of a recorded answer: transcript, voice metrics, gaze.

Nothing in this file calls the network (except the one-time Whisper model
download from Hugging Face on first run).
"""
import json
import os
import re
import threading
from pathlib import Path

import numpy as np

SR = 16000

# ------------------------------------------------------------------ whisper

_whisper = None
_whisper_lock = threading.Lock()

# Whisper tends to silently drop "um"/"uh". Priming the prompt with
# disfluent text makes it far more likely to transcribe them.
FILLER_PROMPT = "Umm, so, uh, I think, like, you know, hmm... Okay, so, um, here's what I, uh, mean."
HARD_FILLERS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "hmm", "mm", "ah", "eh"}
SOFT_FILLERS = ["like", "you know", "basically", "kind of", "sort of", "i mean", "actually", "literally", "so yeah"]


def get_whisper():
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel

            size = os.getenv("WHISPER_MODEL", "small.en")
            _whisper = WhisperModel(size, device="auto", compute_type="int8")
    return _whisper


def transcribe(path):
    from faster_whisper import decode_audio

    audio = decode_audio(str(path), sampling_rate=SR)
    segments, _info = get_whisper().transcribe(
        audio,
        language="en",
        word_timestamps=True,
        initial_prompt=FILLER_PROMPT,
        condition_on_previous_text=False,
        vad_filter=False,
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            token = w.word.strip()
            if token:
                words.append({"w": token, "start": float(w.start), "end": float(w.end)})
    return audio, words


def _clean(tok):
    return re.sub(r"[^a-z']", "", tok.lower())


def voice_metrics(audio, words, answer_s):
    duration = len(audio) / SR
    m = {"recording_seconds": round(duration, 1), "answer_limit_seconds": answer_s}
    if not words:
        m["speech_detected"] = False
        return m, []

    first, last = words[0]["start"], words[-1]["end"]
    span = max(last - first, 1e-6)
    content_words = [w for w in words if _clean(w["w"]) not in HARD_FILLERS]

    pauses = []
    for a, b in zip(words, words[1:]):
        gap = b["start"] - a["end"]
        if gap >= 1.0:
            pauses.append({"at": round(a["end"], 1), "seconds": round(gap, 1), "after_word": a["w"]})

    hard = [w for w in words if _clean(w["w"]) in HARD_FILLERS]
    text = " " + " ".join(_clean(w["w"]) for w in words) + " "
    soft = {}
    for phrase in SOFT_FILLERS:
        n = len(re.findall(r"(?<= )" + re.escape(phrase) + r"(?= )", text))
        if n >= 2:
            soft[phrase] = n

    m.update(
        {
            "speech_detected": True,
            "words_spoken": len(content_words),
            "time_to_first_word_s": round(first, 1),
            "speaking_span_s": round(span, 1),
            "pace_wpm": round(len(content_words) / span * 60),
            "hesitation_fillers": len(hard),
            "hesitation_fillers_per_min": round(len(hard) / (span / 60), 1),
            "repeated_verbal_tics": soft,
            "pauses_over_1s": len(pauses),
            "pauses_over_2s": sum(1 for p in pauses if p["seconds"] >= 2.0),
            "longest_pause_s": max((p["seconds"] for p in pauses), default=0),
            "still_talking_when_time_ran_out": bool(duration >= answer_s - 1.5 and duration - last < 1.0),
            "unused_time_s": round(max(answer_s - last, 0), 1),
        }
    )

    # Pitch variability (monotone check). Heuristic only.
    try:
        import librosa

        f0, _vf, _vp = librosa.pyin(audio, fmin=65, fmax=400, sr=SR, frame_length=1024, hop_length=512)
        f0 = f0[~np.isnan(f0)]
        if len(f0) > 30:
            semis = 12 * np.log2(f0 / np.median(f0))
            m["pitch_variability_semitones"] = round(float(np.std(semis)), 2)
            m["pitch_note"] = "below ~2 semitones tends to sound flat/monotone (heuristic)"
    except Exception as e:  # noqa: BLE001
        m["pitch_variability_semitones"] = None
        m["pitch_error"] = str(e)[:200]

    return m, pauses


# --------------------------------------------------------------------- gaze
# Webcam gaze via MediaPipe Face Mesh (iris landmarks) + head-pose proxies.
# Heuristic. Works best after calibration (look into the lens for 4 s).

BASELINE_PATH = Path(__file__).parent / "data" / "gaze_baseline.json"

# Minimum deviation from baseline that counts as "looking away".
# Tune these if feedback flags too much / too little.
MIN_THRESH = {"h": 0.07, "v": 0.09, "yaw": 0.06, "pitch": 0.05}
MIN_AWAY_SECONDS = 0.8
SAMPLE_FPS = 6


def _ratio(p, a, b):
    dx, dy = b.x - a.x, b.y - a.y
    L = dx * dx + dy * dy
    return ((p.x - a.x) * dx + (p.y - a.y) * dy) / L if L else 0.5


def _features(lm):
    # Iris centres: 468 (subject's right eye, image-left), 473 (subject's left eye).
    h = (_ratio(lm[468], lm[33], lm[133]) + _ratio(lm[473], lm[362], lm[263])) / 2  # grows -> iris to image-right
    v = (_ratio(lm[468], lm[159], lm[145]) + _ratio(lm[473], lm[386], lm[374])) / 2  # grows -> iris down
    yaw = _ratio(lm[1], lm[234], lm[454])  # grows -> nose to image-right
    pitch = _ratio(lm[1], lm[10], lm[152])  # grows -> head tilted down
    return {"h": h, "v": v, "yaw": yaw, "pitch": pitch}


def _extract(path):
    import av
    import mediapipe as mp

    fm = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    samples = []
    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        t0, next_t = None, 0.0
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            if t0 is None:
                t0 = float(frame.time)
            t = float(frame.time) - t0
            if t < next_t:
                continue
            next_t = t + 1.0 / SAMPLE_FPS
            img = frame.to_ndarray(format="rgb24")
            res = fm.process(img)
            if res.multi_face_landmarks:
                samples.append((t, _features(res.multi_face_landmarks[0].landmark)))
            else:
                samples.append((t, None))
    finally:
        container.close()
        fm.close()
    return samples


def calibrate(path):
    samples = [f for _, f in _extract(path) if f]
    if len(samples) < 5:
        raise RuntimeError("Face not detected clearly enough. Sit facing the camera in good light and retry.")
    base = {}
    for k in ("h", "v", "yaw", "pitch"):
        vals = np.array([s[k] for s in samples])
        base[k] = {"median": float(np.median(vals)), "sd": float(np.std(vals))}
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(base, indent=2))
    return base


def _direction(d, th):
    # Camera image is NOT mirrored: iris/nose moving to image-left = candidate looking to THEIR right.
    horiz = max(abs(d["h"]) / th["h"], abs(d["yaw"]) / th["yaw"])
    vert = max(abs(d["v"]) / th["v"], abs(d["pitch"]) / th["pitch"])
    if horiz >= vert:
        lr = d["h"] if abs(d["h"]) / th["h"] >= abs(d["yaw"]) / th["yaw"] else d["yaw"]
        return "to your right" if lr < 0 else "to your left"
    up_down = d["pitch"] if abs(d["pitch"]) / th["pitch"] >= abs(d["v"]) / th["v"] else d["v"]
    return "down" if up_down > 0 else "up"


def gaze(path):
    samples = _extract(path)
    faces = [f for _, f in samples if f]
    if not samples:
        return {"available": False, "reason": "no video frames decoded"}

    calibrated = BASELINE_PATH.exists()
    if calibrated:
        b = json.loads(BASELINE_PATH.read_text())
        base = {k: b[k]["median"] for k in b}
        th = {k: max(MIN_THRESH[k], 3 * b[k]["sd"]) for k in MIN_THRESH}
    else:
        if not faces:
            return {"available": False, "reason": "face not detected"}
        base = {k: float(np.median([f[k] for f in faces])) for k in MIN_THRESH}
        th = dict(MIN_THRESH)

    labels = []
    for t, f in samples:
        if f is None:
            labels.append((t, "not in frame"))
            continue
        d = {k: f[k] - base[k] for k in base}
        away = (
            abs(d["h"]) > th["h"] or abs(d["yaw"]) > th["yaw"]
            or d["v"] > th["v"] or d["v"] < -th["v"] * 1.3
            or abs(d["pitch"]) > th["pitch"]
        )
        labels.append((t, _direction(d, th) if away else "camera"))

    # merge runs
    step = 1.0 / SAMPLE_FPS
    segments, cur = [], None
    for t, lab in labels:
        if cur and cur["dir"] == lab:
            cur["end"] = t + step
        else:
            if cur:
                segments.append(cur)
            cur = {"dir": lab, "start": t, "end": t + step}
    if cur:
        segments.append(cur)

    away_segs = [
        {"start": round(s["start"], 1), "end": round(s["end"], 1), "seconds": round(s["end"] - s["start"], 1), "direction": s["dir"]}
        for s in segments
        if s["dir"] != "camera" and s["end"] - s["start"] >= MIN_AWAY_SECONDS
    ]
    total = len(labels)
    on_cam = sum(1 for _, lab in labels if lab == "camera")
    by_dir = {}
    for s in away_segs:
        by_dir[s["direction"]] = round(by_dir.get(s["direction"], 0) + s["seconds"], 1)
    return {
        "available": True,
        "calibrated": calibrated,
        "eye_contact_pct": round(100 * on_cam / total) if total else None,
        "look_away_count": len(away_segs),
        "seconds_away_by_direction": by_dir,
        "segments": away_segs,
        "note": "Webcam gaze estimate (heuristic). 'camera' means looking at/near the lens.",
    }


# ---------------------------------------------------------------- combine

def annotate(words, pauses, gaze_segments):
    if not words:
        return ""
    pause_after = {p["at"]: p["seconds"] for p in pauses}
    gz = sorted(gaze_segments or [], key=lambda s: s["start"])
    gi, out, next_mark = 0, [], 0.0
    for w in words:
        while gi < len(gz) and gz[gi]["start"] <= w["start"]:
            s = gz[gi]
            tag = "not in frame" if s["direction"] == "not in frame" else f"looks away: {s['direction']}"
            out.append(f"[{tag} {s['seconds']}s @{s['start']}]")
            gi += 1
        if w["start"] >= next_mark:
            out.append(f"\n[{int(w['start'] // 60)}:{int(w['start'] % 60):02d}]")
            next_mark = (w["start"] // 10 + 1) * 10
        out.append(w["w"])
        p = pause_after.get(round(w["end"], 1))
        if p:
            out.append(f"[pause {p}s]")
    return " ".join(out).strip()


def analyse(path, answer_s):
    audio, words = transcribe(path)
    metrics, pauses = voice_metrics(audio, words, answer_s)
    try:
        g = gaze(path)
    except Exception as e:  # noqa: BLE001
        g = {"available": False, "reason": f"gaze analysis failed: {str(e)[:200]}"}
    metrics["gaze"] = {k: v for k, v in g.items() if k != "segments"}
    transcript = " ".join(w["w"] for w in words)
    annotated = annotate(words, pauses, g.get("segments") if g.get("available") else [])
    return {
        "transcript": transcript,
        "annotated_transcript": annotated,
        "metrics": metrics,
        "pauses": pauses,
        "gaze_segments": g.get("segments", []),
    }
