"""app_planner.py — Web frontend for the Session 7 agent.

Serves a simple chat UI at / and routes messages to agent7.run().
No planner, calendar, or reminder code — just the agent loop.

Run:
    uv run app_planner.py
Then open http://127.0.0.1:8000
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import agent7

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger(__name__)

SANDBOX = Path(__file__).parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)

session: dict = {
    "messages": [{"role": "ai", "content": "Hi! What can I help you with today?"}],
}


def _gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY to upload files.")
    return key


def _upload_to_gemini(path: Path) -> str:
    """Upload a sandbox file to Gemini Files API and return its URI."""
    from google import genai as _genai

    client = _genai.Client(api_key=_gemini_api_key())
    f = client.files.upload(file=str(path))
    while f.state.name != "ACTIVE":
        time.sleep(1)
        f = client.files.get(name=f.name)
    return f.uri


app = FastAPI()

# ── Inline HTML ───────────────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Agent 7</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: #1a1a2e;
    color: #fff;
    box-shadow: 0 2px 6px rgba(0,0,0,.3);
    flex-shrink: 0;
  }
  header h1 { font-size: 1.1rem; font-weight: 600; letter-spacing: .5px; }
  header h1 span { color: #7c83fd; }

  #new-session-btn {
    background: transparent;
    border: 1px solid rgba(255,255,255,.35);
    color: #fff;
    padding: 5px 14px;
    border-radius: 6px;
    font-size: .8rem;
    cursor: pointer;
    transition: background .15s;
  }
  #new-session-btn:hover { background: rgba(255,255,255,.12); }

  /* ── Message list ── */
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .msg {
    display: flex;
    max-width: 78%;
  }
  .msg.user { align-self: flex-end; }
  .msg.ai   { align-self: flex-start; }

  .bubble {
    padding: 10px 15px;
    border-radius: 16px;
    font-size: .92rem;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg.user .bubble {
    background: #7c83fd;
    color: #fff;
    border-bottom-right-radius: 4px;
  }
  .msg.ai .bubble {
    background: #fff;
    color: #1a1a2e;
    border-bottom-left-radius: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,.1);
  }

  /* ── Typing indicator ── */
  .typing .bubble {
    display: flex;
    gap: 5px;
    align-items: center;
    padding: 14px 18px;
  }
  .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #7c83fd;
    animation: blink 1.2s infinite;
  }
  .dot:nth-child(2) { animation-delay: .2s; }
  .dot:nth-child(3) { animation-delay: .4s; }
  @keyframes blink {
    0%, 80%, 100% { opacity: .15; }
    40% { opacity: 1; }
  }

  /* ── Input area ── */
  #input-area {
    background: #fff;
    border-top: 1px solid #dde1e9;
    flex-shrink: 0;
  }

  /* File attachment chip */
  #file-chip {
    display: none;
    align-items: center;
    gap: 6px;
    padding: 6px 16px 0;
  }
  #file-chip-inner {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #eef0ff;
    border: 1px solid #c5c9fd;
    border-radius: 20px;
    padding: 3px 10px 3px 8px;
    font-size: .8rem;
    color: #4a4fbf;
    max-width: 320px;
  }
  #file-chip-inner svg { flex-shrink: 0; }
  #file-chip-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  #file-chip-remove {
    background: none;
    border: none;
    color: #7c83fd;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0;
    flex-shrink: 0;
  }
  #file-chip-remove:hover { color: #e74c3c; }
  #file-chip-uri {
    font-size: .72rem;
    color: #888;
    margin-left: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
  }

  /* Upload progress */
  #upload-status {
    display: none;
    align-items: center;
    gap: 6px;
    padding: 6px 16px 0;
    font-size: .8rem;
    color: #7c83fd;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  #upload-spinner {
    width: 14px; height: 14px;
    border: 2px solid #dde1e9;
    border-top-color: #7c83fd;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }

  #input-bar {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    padding: 10px 16px 12px;
  }

  #upload-btn {
    background: transparent;
    border: 1px solid #dde1e9;
    color: #888;
    width: 40px; height: 40px;
    border-radius: 10px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: border-color .15s, color .15s;
  }
  #upload-btn:hover { border-color: #7c83fd; color: #7c83fd; }
  #upload-btn svg { width: 18px; height: 18px; }

  #user-input {
    flex: 1;
    resize: none;
    border: 1px solid #dde1e9;
    border-radius: 10px;
    padding: 9px 13px;
    font-size: .92rem;
    font-family: inherit;
    line-height: 1.45;
    max-height: 140px;
    overflow-y: auto;
    outline: none;
    transition: border-color .15s;
  }
  #user-input:focus { border-color: #7c83fd; }

  #send-btn {
    background: #7c83fd;
    border: none;
    color: #fff;
    width: 40px; height: 40px;
    border-radius: 10px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: background .15s;
  }
  #send-btn:hover:not(:disabled) { background: #5a63f5; }
  #send-btn:disabled { opacity: .4; cursor: default; }
  #send-btn svg { width: 18px; height: 18px; }
</style>
</head>
<body>

<header>
  <h1>Agent <span>7</span></h1>
  <button id="new-session-btn">New session</button>
</header>

<div id="messages"></div>

<input type="file" id="file-input" hidden />

<div id="input-area">
  <!-- File attachment chip (shown after successful upload) -->
  <div id="file-chip">
    <div id="file-chip-inner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
        <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
      </svg>
      <span id="file-chip-name"></span>
      <span id="file-chip-uri" title=""></span>
      <button id="file-chip-remove" title="Remove attachment">&times;</button>
    </div>
  </div>

  <!-- Upload progress indicator -->
  <div id="upload-status">
    <div id="upload-spinner"></div>
    <span id="upload-status-text">Uploading to Gemini…</span>
  </div>

  <div id="input-bar">
    <!-- Attach file button -->
    <button id="upload-btn" title="Attach a file">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
      </svg>
    </button>

    <textarea id="user-input" rows="1" placeholder="Ask anything…"></textarea>

    <button id="send-btn" title="Send">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
           stroke-linecap="round" stroke-linejoin="round">
        <line x1="22" y1="2" x2="11" y2="13"/>
        <polygon points="22 2 15 22 11 13 2 9 22 2"/>
      </svg>
    </button>
  </div>
</div>

<script>
const msgList    = document.getElementById('messages');
const input      = document.getElementById('user-input');
const sendBtn    = document.getElementById('send-btn');
const newSessBtn = document.getElementById('new-session-btn');
const uploadBtn  = document.getElementById('upload-btn');
const fileInput  = document.getElementById('file-input');
const fileChip   = document.getElementById('file-chip');
const chipName   = document.getElementById('file-chip-name');
const chipUri    = document.getElementById('file-chip-uri');
const chipRemove = document.getElementById('file-chip-remove');
const uploadStatus     = document.getElementById('upload-status');
const uploadStatusText = document.getElementById('upload-status-text');

let attachedFileUri  = null;
let attachedFileName = null;

// ── Rendering ────────────────────────────────────────────────────────────────

function appendMsg(role, text) {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  wrap.appendChild(bubble);
  msgList.appendChild(wrap);
  msgList.scrollTop = msgList.scrollHeight;
  return wrap;
}

function showTyping() {
  const wrap = document.createElement('div');
  wrap.className = 'msg ai typing';
  wrap.innerHTML = '<div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
  msgList.appendChild(wrap);
  msgList.scrollTop = msgList.scrollHeight;
  return wrap;
}

function loadHistory(messages) {
  msgList.innerHTML = '';
  messages.forEach(m => appendMsg(m.role === 'user' ? 'user' : 'ai', m.content));
}

// ── File attachment UI ────────────────────────────────────────────────────────

function showFileChip(filename, uri) {
  chipName.textContent = filename;
  chipUri.textContent = uri;
  chipUri.title = uri;
  fileChip.style.display = 'flex';
}

function clearAttachment() {
  attachedFileUri  = null;
  attachedFileName = null;
  fileChip.style.display = 'none';
  fileInput.value = '';
}

chipRemove.addEventListener('click', clearAttachment);

// ── File upload ───────────────────────────────────────────────────────────────

uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  // Show uploading indicator, hide any prior chip
  fileChip.style.display = 'none';
  uploadStatusText.textContent = `Uploading ${file.name} to Gemini…`;
  uploadStatus.style.display = 'flex';
  uploadBtn.disabled = true;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const r = await fetch('/upload_file', { method: 'POST', body: formData });
    const data = await r.json();
    uploadStatus.style.display = 'none';
    uploadBtn.disabled = false;

    if (data.uri) {
      attachedFileUri  = data.uri;
      attachedFileName = data.filename;
      showFileChip(data.filename, data.uri);
    } else {
      appendMsg('ai', `File upload failed: ${data.error || 'unknown error'}`);
    }
  } catch (err) {
    uploadStatus.style.display = 'none';
    uploadBtn.disabled = false;
    appendMsg('ai', 'File upload failed — please try again.');
  }

  fileInput.value = '';
});

// ── State ────────────────────────────────────────────────────────────────────

async function fetchState() {
  const r = await fetch('/state');
  const data = await r.json();
  loadHistory(data.messages);
}

// ── Send ─────────────────────────────────────────────────────────────────────

async function send() {
  const text = input.value.trim();
  if (!text && !attachedFileUri) return;

  const messageText = text || 'Please analyze the attached file.';

  input.value = '';
  input.style.height = '';
  input.disabled = true;
  sendBtn.disabled = true;

  // Show in UI: if file attached, prepend a small label
  const displayText = attachedFileName
    ? `📎 ${attachedFileName}\n${messageText}`
    : messageText;
  appendMsg('user', displayText);
  const typingEl = showTyping();

  const body = { message: messageText };
  if (attachedFileUri) {
    body.file_uri  = attachedFileUri;
    body.file_name = attachedFileName;
  }

  // Clear attachment immediately so it's not re-sent
  clearAttachment();

  try {
    const r = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    typingEl.remove();
    appendMsg('ai', data.reply || '(no response)');
  } catch (err) {
    typingEl.remove();
    appendMsg('ai', 'Something went wrong — please try again.');
  }

  input.disabled = false;
  sendBtn.disabled = false;
  input.focus();
}

// ── New session ───────────────────────────────────────────────────────────────

async function newSession() {
  clearAttachment();
  await fetch('/new_session', { method: 'POST' });
  await fetchState();
}

// ── Events ───────────────────────────────────────────────────────────────────

sendBtn.addEventListener('click', send);
newSessBtn.addEventListener('click', newSession);

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

input.addEventListener('input', () => {
  input.style.height = '';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
});

fetchState();
</script>
</body>
</html>
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    return _HTML


@app.get("/state")
def get_state():
    return {"messages": session["messages"]}


class ChatRequest(BaseModel):
    message: str
    file_uri: str | None = None
    file_name: str | None = None


@app.post("/chat")
def chat(req: ChatRequest):
    msg = req.message.strip()
    if not msg:
        return {"reply": "", "messages": session["messages"]}

    session["messages"].append({"role": "user", "content": msg})

    agent_msg = msg
    if req.file_uri:
        agent_msg = (
            f"[Attached file: {req.file_name or 'file'} — Gemini URI: {req.file_uri}]\n\n"
            + msg
        )

    try:
        reply = asyncio.run(agent7.run(agent_msg))
    except Exception as e:
        log.exception("agent7.run failed")
        reply = f"Error: {e}"

    session["messages"].append({"role": "ai", "content": reply})
    return {"reply": reply, "messages": session["messages"]}


@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...)):
    """Receive a browser-uploaded file, save to sandbox, upload to Gemini Files API."""
    raw_name = file.filename or ""
    safe_name = Path(raw_name).name  # strip any directory traversal components
    if not safe_name:
        return {"error": "Invalid filename"}
    dest = SANDBOX / safe_name
    contents = await file.read()
    dest.write_bytes(contents)
    try:
        uri = _upload_to_gemini(dest)
    except Exception as e:
        log.exception("Gemini upload failed")
        return {"error": str(e)}
    return {"uri": uri, "filename": safe_name}


@app.post("/new_session")
def new_session():
    session["messages"] = [{"role": "ai", "content": "Hi! What can I help you with today?"}]
    return {"messages": session["messages"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
