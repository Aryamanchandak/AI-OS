import json
import os
import re
import sys
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import (
    annual_report_analysis,
    meeting_recorder,
    podcast_agent,
    report_chatbot,
    us_result_note,
)
import server as routing

TOOL_MAP = {
    "report_chatbot":         report_chatbot,
    "meeting_recorder":       meeting_recorder,
    "podcast_agent":          podcast_agent,
    "us_result_note":         us_result_note,
    "annual_report_analysis": annual_report_analysis,
}

AGENT_LABELS = {
    "report_chatbot":         "Report ChatBot",
    "meeting_recorder":       "Meeting Recorder",
    "podcast_agent":          "Podcast Agent",
    "us_result_note":         "US Result Note",
    "annual_report_analysis": "Annual Report Analysis",
}

AGENT_REPLIES = {
    "report_chatbot":         "Opening Report ChatBot. Select a company or upload PDFs to begin analysis.",
    "meeting_recorder":       "Opening Meeting Recorder. You can start recording or upload an existing audio file.",
    "podcast_agent":          "Opening Podcast Agent. Here are the available sector-wise podcasts.",
    "us_result_note":         "Opening US Result Note. Upload your Morningstar PDFs to generate earnings notes.",
    "annual_report_analysis": "Opening Annual Report Analysis. Paste an annual report URL to get started.",
}

# ── CSS + font injection for Prefab tool pages ────────────────────────────────
TOOL_THEME_CSS = """
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Mulish:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { font-family: 'Mulish', sans-serif !important; box-sizing: border-box; }
    body { background: #fbfbf5 !important; color: #2f2f2f !important; }

    /* Terracotta palette — override Prefab Tailwind orange */
    .bg-orange-500                     { background-color: #c97c5d !important; }
    .bg-orange-400                     { background-color: #c97c5d !important; }
    .bg-orange-300                     { background-color: #d49080 !important; }
    .bg-orange-200                     { background-color: #e8c4b8 !important; }
    .bg-orange-100                     { background-color: #f3e1da !important; }
    .bg-orange-50                      { background-color: #f3f2ea !important; }
    .hover\\:bg-orange-600:hover        { background-color: #b06848 !important; }
    .hover\\:bg-orange-500:hover        { background-color: #c97c5d !important; }
    .hover\\:bg-orange-400:hover        { background-color: #c97c5d !important; }
    .text-orange-500                   { color: #c97c5d !important; }
    .text-orange-400                   { color: #c97c5d !important; }
    .border-orange-500                 { border-color: #c97c5d !important; }

    /* Slate → warm cream */
    .bg-slate-100                      { background-color: #f3f2ea !important; }
    .bg-slate-50                       { background-color: #fbfbf5 !important; }

    /* Blue for recording buttons → muted steel */
    .bg-blue-500                       { background-color: #6b8cae !important; }
    .hover\\:bg-blue-600:hover          { background-color: #5a7d9f !important; }
    .border-blue-500                   { border-color: #6b8cae !important; }
    .text-blue-600                     { color: #6b8cae !important; }

    /* Green → muted sage */
    .bg-green-500                      { background-color: #5a8a6a !important; }
    .hover\\:bg-green-600:hover         { background-color: #4a7a5a !important; }
    .text-green-500                    { color: #5a8a6a !important; }

    /* Red stays red but slightly muted */
    .bg-red-500                        { background-color: #c05c5c !important; }
    .hover\\:bg-red-600:hover           { background-color: #a84f4f !important; }

    /* Teal → warm teal */
    .bg-teal-500                       { background-color: #4a8a80 !important; }
    .hover\\:bg-teal-600:hover          { background-color: #3a7a70 !important; }

    /* Borders and backgrounds */
    .border                            { border-color: #e6e4da !important; }
    .border-gray-200, .border-gray-300 { border-color: #e6e4da !important; }
    .bg-white                          { background-color: #ffffff !important; }
    .bg-gray-50, .bg-gray-100          { background-color: #f3f2ea !important; }

    /* DataTable header orange */
    th.bg-orange-200, [class*="bg-orange-200"] { background-color: #e8c4b8 !important; }

    /* Scrollbars */
    ::-webkit-scrollbar               { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track         { background: transparent; }
    ::-webkit-scrollbar-thumb         { background: #e6e4da; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover   { background: #c97c5d; }
  </style>
"""

# ── Meeting Recorder JS (injected when serving that tool) ─────────────────────
MEETING_RECORDER_JS = """
<script>
(function() {
  // Wait for Prefab UI to render, then wire up buttons
  function wire() {
    const allBtns = Array.from(document.querySelectorAll('button'));
    const findBtn = (label) => allBtns.find(b => b.textContent.trim().includes(label));

    const startBtn  = findBtn('Start Recording');
    const pauseBtn  = findBtn('pause') || allBtns.find(b => b.querySelector('[data-lucide="pause"]'));
    const stopBtn   = findBtn('Stop Recording');
    const submitBtn = findBtn('Submit Recording');
    const clearBtn  = findBtn('Clear Recording');
    const uploadBtn = findBtn('Upload Recording');

    const statusEl  = document.querySelector('.text-green-500, .text-green-600');

    let mediaStream = null;
    let recorder    = null;
    let chunks      = [];

    function setStatus(text, colorClass) {
      if (!statusEl) return;
      statusEl.textContent = text;
      statusEl.className   = statusEl.className.replace(/text-\\S+/g, '') + ' ' + colorClass;
    }

    if (startBtn) startBtn.addEventListener('click', async () => {
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder    = new MediaRecorder(mediaStream);
        chunks      = [];
        recorder.ondataavailable = e => chunks.push(e.data);
        recorder.start();
        setStatus('Recording…', 'text-red-500');
        startBtn.disabled = true;
        if (stopBtn)  stopBtn.disabled  = false;
        if (pauseBtn) pauseBtn.disabled = false;
      } catch (e) {
        setStatus('Microphone access denied', 'text-red-400');
      }
    });

    if (pauseBtn) pauseBtn.addEventListener('click', () => {
      if (!recorder) return;
      if (recorder.state === 'recording') {
        recorder.pause();
        setStatus('Paused', 'text-amber-500');
      } else if (recorder.state === 'paused') {
        recorder.resume();
        setStatus('Recording…', 'text-red-500');
      }
    });

    if (stopBtn) stopBtn.addEventListener('click', () => {
      if (!recorder) return;
      recorder.stop();
      mediaStream.getTracks().forEach(t => t.stop());
      setStatus('Stopped — ready to submit', 'text-blue-500');
      if (startBtn) startBtn.disabled = false;
    });

    if (clearBtn) clearBtn.addEventListener('click', () => {
      chunks = [];
      recorder = null;
      if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
      setStatus('Not Recording', 'text-green-500');
      if (startBtn) startBtn.disabled = false;
    });

    if (uploadBtn) uploadBtn.addEventListener('click', () => {
      const inp = document.createElement('input');
      inp.type   = 'file';
      inp.accept = 'audio/*';
      inp.onchange = e => {
        const file = e.target.files[0];
        if (file) setStatus('Loaded: ' + file.name, 'text-blue-500');
      };
      inp.click();
    });
  }

  // Retry wiring after Prefab renders
  let tries = 0;
  const poll = setInterval(() => {
    if (document.querySelector('button') || ++tries > 20) {
      clearInterval(poll);
      wire();
    }
  }, 200);
})();
</script>
"""

# ── US Result Note JS (native file picker for Choose Files button) ─────────────
US_RESULT_JS = """
<script>
(function() {
  function wire() {
    const allBtns  = Array.from(document.querySelectorAll('button'));
    const chooseBtn = allBtns.find(b => b.textContent.trim().includes('Choose Files'));
    const uploadBtn = allBtns.find(b => b.textContent.trim().includes('Upload') && !b.textContent.includes('Choose'));
    const mutedEl  = document.querySelector('.text-muted-foreground, [class*="muted"]');

    if (chooseBtn) {
      const inp = document.createElement('input');
      inp.type     = 'file';
      inp.accept   = '.pdf';
      inp.multiple = true;
      inp.style.display = 'none';
      document.body.appendChild(inp);

      inp.onchange = () => {
        const names = Array.from(inp.files).map(f => f.name).join(', ');
        if (mutedEl) mutedEl.textContent = names || 'No file chosen';
        if (uploadBtn) uploadBtn.disabled = inp.files.length === 0;
      };

      chooseBtn.addEventListener('click', () => inp.click());
    }
  }

  let tries = 0;
  const poll = setInterval(() => {
    if (document.querySelector('button') || ++tries > 20) {
      clearInterval(poll);
      wire();
    }
  }, 200);
})();
</script>
"""

# ── Annual Report Analysis JS (wires Analyze button to /analyze endpoint) ────
ANNUAL_ANALYSIS_JS = """
<script>
(function() {
  function wire() {
    const urlInput  = document.querySelector('input[name="ar_url"]') || document.querySelector('input[type="text"]');
    const allBtns   = Array.from(document.querySelectorAll('button'));
    const analyzeBtn = allBtns.find(b => b.textContent.trim() === 'Analyze');
    if (!analyzeBtn) return;

    analyzeBtn.addEventListener('click', async () => {
      const url = urlInput ? urlInput.value.trim() : '';
      if (!url) { urlInput && urlInput.focus(); return; }

      const origText = analyzeBtn.textContent;
      analyzeBtn.disabled  = true;
      analyzeBtn.textContent = 'Analyzing…';

      try {
        const res  = await fetch('/analyze', {
          method:  'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body:    'url=' + encodeURIComponent(url),
        });
        const html = await res.text();
        document.open();
        document.write(html);
        document.close();
      } catch (e) {
        analyzeBtn.disabled  = false;
        analyzeBtn.textContent = origText;
        alert('Analysis failed. Check your URL and try again.');
      }
    });
  }

  let tries = 0;
  const poll = setInterval(() => {
    if (document.querySelector('button') || ++tries > 20) {
      clearInterval(poll);
      wire();
    }
  }, 200);
})();
</script>
"""

TOOL_EXTRA_JS = {
    "meeting_recorder":       MEETING_RECORDER_JS,
    "us_result_note":         US_RESULT_JS,
    "annual_report_analysis": ANNUAL_ANALYSIS_JS,
}

# ── Welcome screen ────────────────────────────────────────────────────────────

WELCOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Mulish:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Mulish', sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #fbfbf5;
      color: #2f2f2f;
      padding: 2rem;
    }
    .wrap { text-align: center; max-width: 520px; width: 100%; }

    .logo {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 56px; height: 56px;
      background: linear-gradient(135deg, #c97c5d, #b06848);
      border-radius: 14px;
      font-size: 1.5rem;
      color: white;
      margin-bottom: 1.25rem;
      box-shadow: 0 6px 20px rgba(201,124,93,0.28);
    }
    h1 {
      font-size: 1.25rem;
      font-weight: 700;
      color: #2f2f2f;
      margin-bottom: 0.35rem;
      letter-spacing: -0.02em;
    }
    .sub {
      color: #7a7060;
      font-size: 0.85rem;
      line-height: 1.65;
      margin-bottom: 1.75rem;
      font-weight: 400;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.5rem;
      margin-bottom: 1.5rem;
      text-align: left;
    }
    .card {
      background: #ffffff;
      border: 1px solid #e6e4da;
      border-radius: 10px;
      padding: 0.875rem 1rem;
      display: flex;
      align-items: flex-start;
      gap: 0.625rem;
      cursor: pointer;
      transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;
      user-select: none;
    }
    .card:hover {
      border-color: #c97c5d;
      box-shadow: 0 3px 12px rgba(201,124,93,0.14);
      transform: translateY(-1px);
    }
    .card:active { transform: translateY(0); }
    .card-icon { font-size: 1.15rem; line-height: 1; flex-shrink: 0; margin-top: 0.1rem; }
    .card-name { font-size: 0.78rem; font-weight: 600; color: #2f2f2f; }
    .card-desc { font-size: 0.7rem; color: #7a7060; margin-top: 0.2rem; line-height: 1.45; font-weight: 400; }

    .hint {
      font-size: 0.75rem;
      color: #7a7060;
      background: #ffffff;
      border: 1px dashed #e6e4da;
      border-radius: 8px;
      padding: 0.7rem 1rem;
      line-height: 1.7;
    }
    .hint strong { color: #c97c5d; font-weight: 600; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo">◆</div>
    <h1>ICICI Prudential AI Agents</h1>
    <p class="sub">Your intelligent workspace for financial analysis.<br>Describe what you need in the chat — the right agent opens here.</p>

    <div class="grid">
      <div class="card" data-query="Analyze an annual report" data-label="Annual Report Analysis">
        <span class="card-icon">📊</span>
        <div>
          <div class="card-name">Annual Report Analysis</div>
          <div class="card-desc">Analyze reports via URL, YoY &amp; peer comparisons</div>
        </div>
      </div>
      <div class="card" data-query="Chat with company documents" data-label="Report ChatBot">
        <span class="card-icon">🤖</span>
        <div>
          <div class="card-name">Report ChatBot</div>
          <div class="card-desc">Chat with company documents and PDFs</div>
        </div>
      </div>
      <div class="card" data-query="Record a meeting" data-label="Meeting Recorder">
        <span class="card-icon">🎙</span>
        <div>
          <div class="card-name">Meeting Recorder</div>
          <div class="card-desc">Record, upload, and transcribe meetings</div>
        </div>
      </div>
      <div class="card" data-query="Show sector podcasts" data-label="Podcast Agent">
        <span class="card-icon">🎧</span>
        <div>
          <div class="card-name">Podcast Agent</div>
          <div class="card-desc">AI-generated sector-wise financial podcasts</div>
        </div>
      </div>
      <div class="card" style="grid-column: span 2; max-width: 252px; margin: 0 auto; width: 100%;"
           data-query="Upload Morningstar PDFs for US earnings" data-label="US Result Note">
        <span class="card-icon">📄</span>
        <div>
          <div class="card-name">US Result Note</div>
          <div class="card-desc">Upload Morningstar PDFs for earnings notes</div>
        </div>
      </div>
    </div>

    <p class="hint">
      Try: <strong>"Analyze HDFC's annual report"</strong> &nbsp;·&nbsp;
      <strong>"Record a meeting"</strong> &nbsp;·&nbsp;
      <strong>"Show sector podcasts"</strong>
    </p>
  </div>

  <script>
    document.querySelectorAll('.card').forEach(card => {
      card.addEventListener('click', () => {
        window.parent.postMessage({
          action: 'send',
          text:   card.dataset.query,
        }, '*');
      });
    });
  </script>
</body>
</html>"""


# ── Shell HTML — persistent split-panel SPA ───────────────────────────────────

SHELL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ICICI Prudential Intelligence</title>
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <link href="https://fonts.googleapis.com/css2?family=Mulish:wght@300;400;600;700&display=swap" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
  <script id="tailwind-config">
    tailwind.config = {
      darkMode: "class",
      theme: {
        extend: {
          colors: {
            "surface-warm":              "#fff8f6",
            "surface-container-lowest":  "#ffffff",
            "surface-container-low":     "#fff1ec",
            "surface-container":         "#f9ebe6",
            "surface-container-high":    "#f4e5e1",
            "surface-container-highest": "#eee0db",
            "surface-variant":           "#eee0db",
            "on-surface":                "#211a18",
            "on-surface-variant":        "#53433d",
            "primary":                   "#6f331a",
            "primary-container":         "#8c4a2f",
            "on-primary":                "#ffffff",
            "on-primary-container":      "#ffc9b5",
            "outline-variant":           "#d9c2ba",
            "glass-bg":                  "rgba(255,255,255,0.75)",
          },
          fontFamily: { sans: ["Mulish","sans-serif"] }
        }
      }
    }
  </script>
  <style>
    body { font-family: 'Mulish', sans-serif; }
    .material-symbols-outlined { font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; user-select: none; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #d9c2ba; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #86736c; }
    @keyframes msgIn { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
    .msg-in { animation: msgIn .15s ease; }
    @keyframes tdot { 0%,80%,100% { opacity:.25; transform:scale(.85); } 40% { opacity:1; transform:scale(1.05); } }
  </style>
</head>
<body class="bg-surface-warm text-on-surface h-screen overflow-hidden flex flex-col">

  <!-- Global App Bar -->
  <header class="fixed top-0 left-0 w-full h-16 bg-glass-bg backdrop-blur-md border-b border-outline-variant/30 flex justify-between items-center px-6 z-50 shrink-0">
    <span class="text-lg font-bold text-primary tracking-tight">ICICI Prudential Intelligence</span>
    <div class="flex items-center gap-2">
      <nav id="agent-nav" class="flex gap-0.5 mr-2">
        <button class="nav-btn p-2 rounded-full hover:bg-surface-container-highest transition-colors" title="Annual Report Analysis" data-agent="annual_report_analysis">📊</button>
        <button class="nav-btn p-2 rounded-full hover:bg-surface-container-highest transition-colors" title="Report ChatBot"         data-agent="report_chatbot">🤖</button>
        <button class="nav-btn p-2 rounded-full hover:bg-surface-container-highest transition-colors" title="Meeting Recorder"       data-agent="meeting_recorder">🎙</button>
        <button class="nav-btn p-2 rounded-full hover:bg-surface-container-highest transition-colors" title="Podcast Agent"          data-agent="podcast_agent">🎧</button>
        <button class="nav-btn p-2 rounded-full hover:bg-surface-container-highest transition-colors" title="US Result Note"         data-agent="us_result_note">📄</button>
      </nav>
      <div class="w-px h-5 bg-outline-variant/50 mx-1"></div>
      <button class="p-2 rounded-full hover:bg-surface-container-highest transition-colors">
        <span class="material-symbols-outlined text-on-surface-variant" style="font-size:20px">notifications</span>
      </button>
      <button class="p-2 rounded-full hover:bg-surface-container-highest transition-colors">
        <span class="material-symbols-outlined text-on-surface-variant" style="font-size:20px">cloud_done</span>
      </button>
      <div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center ml-1">
        <span class="material-symbols-outlined text-on-primary-container" style="font-size:16px">person</span>
      </div>
    </div>
  </header>

  <!-- Main split below header -->
  <div id="split" class="flex mt-16 flex-1 overflow-hidden relative">

    <!-- Sidebar collapse handle -->
    <button id="collapse-btn" class="absolute top-1/2 -translate-y-1/2 z-30 w-5 h-10 bg-surface-container-lowest border border-outline-variant rounded-full flex items-center justify-center text-on-surface-variant hover:border-primary hover:text-primary hover:bg-surface-container transition-colors" style="left:400px">
      <span id="collapse-icon" class="material-symbols-outlined" style="font-size:14px">chevron_left</span>
    </button>

    <!-- Left Panel: Chat -->
    <aside id="sidebar" class="w-[400px] shrink-0 border-r border-outline-variant/30 flex flex-col bg-surface-container-lowest z-10 transition-all duration-200 overflow-hidden">

      <!-- Chat Header -->
      <div class="px-6 py-4 border-b border-outline-variant/20 flex flex-col gap-3 bg-surface-container-low/50 shrink-0">
        <div class="flex justify-between items-center">
          <div>
            <h3 class="text-base font-bold text-on-surface">Research Assistant</h3>
            <p class="text-xs text-on-surface-variant mt-0.5">Session Active</p>
          </div>
          <button class="p-2 rounded-full hover:bg-surface-variant transition-colors">
            <span class="material-symbols-outlined text-on-surface-variant" style="font-size:18px">more_vert</span>
          </button>
        </div>
        <div class="flex gap-2">
          <button id="new-chat-btn" class="flex-1 bg-primary text-on-primary py-2 rounded-lg flex items-center justify-center gap-1.5 text-xs font-bold hover:opacity-90 transition-opacity">
            <span class="material-symbols-outlined" style="font-size:15px">add</span> New Chat
          </button>
          <button class="flex-1 bg-surface-container-highest text-on-surface py-2 rounded-lg flex items-center justify-center gap-1.5 text-xs font-bold hover:bg-surface-variant border border-outline-variant/50 transition-colors">
            <span class="material-symbols-outlined" style="font-size:15px">history</span> Archive
          </button>
        </div>
      </div>

      <!-- Chat History -->
      <div id="chat-history" class="flex-1 overflow-y-auto p-5 flex flex-col gap-4"></div>

      <!-- Chat Input -->
      <div class="p-4 border-t border-outline-variant/20 bg-surface-container-lowest shrink-0">
        <div class="bg-surface-container-high rounded-2xl p-2 border border-outline-variant/30 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
          <textarea id="chat-input" class="w-full bg-transparent border-none focus:ring-0 resize-none text-sm text-on-surface placeholder:text-on-surface-variant/60 p-2 outline-none min-h-[36px] max-h-[110px]" placeholder="Ask anything… (Enter to send)" rows="1"></textarea>
          <div class="flex justify-between items-center px-2 pb-1 mt-1">
            <div class="flex gap-0.5">
              <button class="p-1.5 rounded-full hover:bg-surface-variant text-on-surface-variant transition-colors">
                <span class="material-symbols-outlined" style="font-size:18px">attach_file</span>
              </button>
              <button class="p-1.5 rounded-full hover:bg-surface-variant text-on-surface-variant transition-colors">
                <span class="material-symbols-outlined" style="font-size:18px">mic</span>
              </button>
            </div>
            <button id="send-btn" class="bg-primary text-on-primary p-2 rounded-full hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed">
              <span class="material-symbols-outlined" style="font-size:18px">send</span>
            </button>
          </div>
        </div>
        <p class="text-center text-[10px] font-semibold tracking-widest text-on-surface-variant/50 mt-2.5 uppercase">AI Generated Content May Be Inaccurate</p>
      </div>
    </aside>

    <!-- Right Panel: Sandbox -->
    <main id="tool-panel" class="flex-1 bg-surface-warm overflow-hidden flex flex-col">

      <!-- Panel header (shown when a tool is active) -->
      <div id="panel-header" class="sticky top-0 bg-surface-warm/90 backdrop-blur-md border-b border-outline-variant/20 px-8 py-4 flex justify-between items-center z-20 transition-opacity duration-200 opacity-0 shrink-0">
        <div class="flex items-center gap-3">
          <div id="panel-icon" class="bg-surface-container-high p-2 rounded-lg border border-outline-variant/30 text-base leading-none">📊</div>
          <h2 id="panel-title" class="text-base font-bold text-on-surface"></h2>
        </div>
        <span id="active-badge" class="text-xs font-bold text-primary bg-primary/10 border border-primary/20 px-3 py-1 rounded-full hidden"></span>
      </div>

      <!-- Tool iframe -->
      <iframe id="tool-frame" src="/tool/welcome" title="Agent Workspace"
              sandbox="allow-scripts allow-same-origin allow-forms allow-pointer-lock allow-popups"
              class="flex-1 w-full border-none block"></iframe>
    </main>

  </div>

  <script>
    const histEl_      = document.getElementById('chat-history');
    const inputEl_     = document.getElementById('chat-input');
    const sendBtn_     = document.getElementById('send-btn');
    const frameEl_     = document.getElementById('tool-frame');
    const badgeEl_     = document.getElementById('active-badge');
    const panelHdr_    = document.getElementById('panel-header');
    const panelTitle_  = document.getElementById('panel-title');
    const panelIcon_   = document.getElementById('panel-icon');
    const collapseBtn_ = document.getElementById('collapse-btn');
    const collapseIcon_= document.getElementById('collapse-icon');
    const splitEl_     = document.getElementById('split');
    const sidebarEl_   = document.getElementById('sidebar');
    const newChatBtn_  = document.getElementById('new-chat-btn');
    let   busy_        = false;

    const AGENT_LABELS = {
      report_chatbot:         'Report ChatBot',
      meeting_recorder:       'Meeting Recorder',
      podcast_agent:          'Podcast Agent',
      us_result_note:         'US Result Note',
      annual_report_analysis: 'Annual Report Analysis',
    };
    const AGENT_REPLIES = {
      report_chatbot:         'Opening Report ChatBot. Select a company or upload PDFs to begin analysis.',
      meeting_recorder:       'Opening Meeting Recorder. You can start recording or upload an existing audio file.',
      podcast_agent:          'Opening Podcast Agent. Here are the available sector-wise podcasts.',
      us_result_note:         'Opening US Result Note. Upload your Morningstar PDFs to generate earnings notes.',
      annual_report_analysis: 'Opening Annual Report Analysis. Paste an annual report URL to get started.',
    };
    const AGENT_ICONS = {
      report_chatbot: '🤖', meeting_recorder: '🎙', podcast_agent: '🎧',
      us_result_note: '📄', annual_report_analysis: '📊',
    };

    function ts() {
      const d = new Date();
      return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
    }

    function addMsg(role, text, artifactLabel) {
      const wrap = document.createElement('div');
      wrap.className = 'msg-in flex flex-col gap-1 ' + (role === 'user' ? 'items-end' : 'items-start');

      if (role === 'user') {
        const bubble = document.createElement('div');
        bubble.className = 'bg-surface-variant text-on-surface px-4 py-3 rounded-2xl rounded-tr-sm max-w-[85%] text-sm leading-relaxed';
        bubble.textContent = text;
        wrap.appendChild(bubble);
      } else {
        const row = document.createElement('div');
        row.className = 'flex gap-3 w-full';
        const avatar = document.createElement('div');
        avatar.className = 'w-7 h-7 rounded-full bg-primary-container flex items-center justify-center shrink-0 mt-0.5';
        avatar.innerHTML = '<span class="material-symbols-outlined text-on-primary-container" style="font-size:14px">smart_toy</span>';
        const col = document.createElement('div');
        col.className = 'flex flex-col gap-2 min-w-0';
        const bubble = document.createElement('div');
        bubble.className = 'bg-surface-container-low text-on-surface px-4 py-3 rounded-2xl rounded-tl-sm max-w-[90%] border border-outline-variant/30 text-sm leading-relaxed';
        bubble.textContent = text;
        col.appendChild(bubble);
        if (artifactLabel) {
          const chip = document.createElement('div');
          chip.className = 'flex items-center gap-2 p-3 bg-surface-container-highest rounded-xl border border-outline-variant/50 cursor-pointer hover:border-primary/50 transition-colors w-fit';
          chip.innerHTML = '<div class="bg-surface-container-lowest p-1.5 rounded-lg"><span class="material-symbols-outlined text-primary" style="font-size:16px">insert_chart</span></div><div><p class="text-xs font-bold text-on-surface">' + artifactLabel + '</p><p style="font-size:10px" class="text-on-surface-variant">Interactive Sandbox opened</p></div>';
          col.appendChild(chip);
        }
        row.appendChild(avatar);
        row.appendChild(col);
        wrap.appendChild(row);
      }

      const timeEl = document.createElement('p');
      timeEl.className = 'text-[10px] text-on-surface-variant/60 px-1';
      timeEl.textContent = ts();
      wrap.appendChild(timeEl);
      histEl_.appendChild(wrap);
      histEl_.scrollTop = histEl_.scrollHeight;
    }

    function showTyping() {
      const el = document.createElement('div');
      el.id = 'typing';
      el.className = 'msg-in flex gap-3';
      el.innerHTML = '<div class="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center shrink-0"><span class="material-symbols-outlined text-on-primary-container" style="font-size:14px">smart_toy</span></div><div class="flex items-center gap-1 px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-2xl rounded-tl-sm"><span class="w-1.5 h-1.5 rounded-full bg-primary inline-block" style="animation:tdot 1.3s infinite 0s"></span><span class="w-1.5 h-1.5 rounded-full bg-primary inline-block" style="animation:tdot 1.3s infinite .2s"></span><span class="w-1.5 h-1.5 rounded-full bg-primary inline-block" style="animation:tdot 1.3s infinite .4s"></span></div>';
      histEl_.appendChild(el);
      histEl_.scrollTop = histEl_.scrollHeight;
    }

    function hideTyping() {
      const el = document.getElementById('typing');
      if (el) el.remove();
    }

    function setActiveNav(key) {
      document.querySelectorAll('.nav-btn').forEach(b => {
        b.classList.toggle('bg-primary/10', b.dataset.agent === key);
      });
    }

    function loadTool(key, label) {
      frameEl_.style.transition = 'opacity .18s ease';
      frameEl_.style.opacity = '0';
      setTimeout(() => {
        frameEl_.src = '/tool/' + key;
        panelTitle_.textContent = label;
        panelIcon_.textContent  = AGENT_ICONS[key] || '🔧';
        panelHdr_.style.opacity = '1';
        badgeEl_.textContent    = label;
        badgeEl_.classList.remove('hidden');
        setActiveNav(key);
        frameEl_.style.opacity = '1';
      }, 160);
    }

    async function send(queryOverride) {
      if (busy_) return;
      const q = (queryOverride || inputEl_.value).trim();
      if (!q) return;
      busy_ = true;
      sendBtn_.disabled = true;
      if (!queryOverride) { inputEl_.value = ''; inputEl_.style.height = 'auto'; }
      addMsg('user', q);
      showTyping();
      try {
        const res  = await fetch('/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: 'q=' + encodeURIComponent(q),
        });
        const data = await res.json();
        hideTyping();
        addMsg('agent', data.reply, data.label);
        loadTool(data.agent, data.label);
      } catch (e) {
        hideTyping();
        addMsg('agent', 'Something went wrong. Please try again.');
      } finally {
        busy_ = false;
        sendBtn_.disabled = false;
        inputEl_.focus();
      }
    }

    window.addEventListener('message', e => {
      if (e.data && e.data.action === 'send') send(e.data.text);
    });

    newChatBtn_.addEventListener('click', () => {
      histEl_.innerHTML = '';
      panelHdr_.style.opacity = '0';
      badgeEl_.classList.add('hidden');
      frameEl_.src = '/tool/welcome';
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('bg-primary/10'));
      addMsg('agent', "Hello! Describe what you need and I'll open the right agent for you.");
    });

    let sidebarOpen = true;
    collapseBtn_.addEventListener('click', () => {
      sidebarOpen = !sidebarOpen;
      sidebarEl_.style.width   = sidebarOpen ? '400px' : '0';
      sidebarEl_.style.opacity = sidebarOpen ? '1' : '0';
      collapseBtn_.style.left  = sidebarOpen ? '400px' : '0';
      collapseIcon_.textContent = sidebarOpen ? 'chevron_left' : 'chevron_right';
    });

    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.agent;
        addMsg('user', AGENT_LABELS[key]);
        addMsg('agent', AGENT_REPLIES[key], AGENT_LABELS[key]);
        loadTool(key, AGENT_LABELS[key]);
      });
    });

    inputEl_.addEventListener('input', () => {
      inputEl_.style.height = 'auto';
      inputEl_.style.height = Math.min(inputEl_.scrollHeight, 110) + 'px';
    });
    inputEl_.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    document.addEventListener('keydown', e => {
      if (e.key === '/' && document.activeElement.tagName !== 'TEXTAREA' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault(); inputEl_.focus();
      }
    });
    sendBtn_.addEventListener('click', () => send());

    addMsg('agent', "Hello! Describe what you need and I'll open the right agent for you. You can also click any agent card below, or use the quick-nav icons above.");
    inputEl_.focus();
  </script>
</body>
</html>"""


# ── Annual Report Analysis helpers ───────────────────────────────────────────

def _analyze_url(url: str) -> dict:
    """Fetch URL content (best-effort) and ask Gemini for structured financial analysis."""
    page_text = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            ct = resp.headers.get("Content-Type", "")
            if "pdf" not in ct and "html" in ct:
                raw = resp.read(200_000)
                page_text = raw.decode("utf-8", errors="replace")
                # strip tags
                page_text = re.sub(r"<[^>]+>", " ", page_text)
                page_text = re.sub(r"\s+", " ", page_text).strip()[:30_000]
    except Exception:
        pass

    context = f"Annual report URL: {url}\n\n"
    if page_text:
        context += f"Page content (excerpt):\n{page_text}\n\n"

    prompt = (
        context +
        "You are a senior equity analyst. Based on the above, provide a structured financial analysis. "
        "Respond ONLY with a JSON object (no markdown, no extra text) in this exact format:\n"
        '{"company":"<name>","fiscal_year":"<e.g. FY24>","revenue":"<e.g. ₹10,00,000 Cr>","revenue_growth":"<e.g. +2.6%>",'
        '"ebitda":"<value>","ebitda_growth":"<e.g. +16.1%>","net_profit":"<value>","net_profit_growth":"<e.g. +8.1%>",'
        '"capex":"<value>","capex_note":"<short note e.g. Focus on 5G & Green>",'
        '"summary":"<2-3 sentence executive summary of financial performance>",'
        '"key_insights":[{"title":"<UPPERCASE TITLE>","body":"<2-3 sentence insight>"},'
        '{"title":"...","body":"..."},{"title":"...","body":"..."}]}'
    )

    try:
        response = routing._gemini_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        print(f"[analyze] Gemini error: {exc}")
        return {
            "company": url.split("/")[2] if "/" in url else url,
            "fiscal_year": "—",
            "revenue": "—", "revenue_growth": "—",
            "ebitda": "—", "ebitda_growth": "—",
            "net_profit": "—", "net_profit_growth": "—",
            "capex": "—", "capex_note": "—",
            "summary": "Analysis could not be generated. Please check the URL and try again.",
            "key_insights": [],
        }


def _render_analysis_html(data: dict) -> str:
    kpis = [
        ("GROSS REVENUE",  data.get("revenue","—"),     data.get("revenue_growth",""),     ""),
        ("EBITDA",         data.get("ebitda","—"),      data.get("ebitda_growth",""),      "Record High" if "record" in data.get("ebitda_growth","").lower() else ""),
        ("NET PROFIT",     data.get("net_profit","—"),  data.get("net_profit_growth",""),  ""),
        ("CAPEX",          data.get("capex","—"),       "",                               data.get("capex_note","")),
    ]

    def kpi_card(label, val, growth, note):
        growth_html = ""
        if growth:
            color = "#4a8a6a" if growth.startswith("+") else "#c05c5c"
            growth_html = f'<span style="font-size:12px;color:{color};margin-left:6px">{growth}</span>'
        note_html = f'<p style="font-size:11px;color:#7a7060;margin-top:6px">{note}</p>' if note else ""
        return f"""
        <div style="background:#fff;border:1px solid #e6e4da;border-radius:12px;padding:18px 20px;flex:1;min-width:140px">
          <p style="font-size:10px;font-weight:700;letter-spacing:.1em;color:#7a7060;text-transform:uppercase;margin-bottom:8px">{label}</p>
          <div style="display:flex;align-items:flex-end">
            <span style="font-size:26px;font-weight:700;color:#211a18;line-height:1">{val}</span>
            {growth_html}
          </div>
          {note_html}
        </div>"""

    kpi_cards = "".join(kpi_card(*k) for k in kpis)

    insights_html = ""
    for ins in data.get("key_insights", []):
        insights_html += f"""
        <div style="position:relative;padding-left:18px;border-left:2px solid rgba(111,51,26,.25);margin-bottom:22px">
          <div style="position:absolute;width:8px;height:8px;background:#6f331a;border-radius:50%;left:-5px;top:4px"></div>
          <h4 style="font-size:11px;font-weight:700;letter-spacing:.08em;color:#211a18;text-transform:uppercase;margin-bottom:4px">{ins.get("title","")}</h4>
          <p style="font-size:13px;color:#53433d;line-height:1.6">{ins.get("body","")}</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Mulish:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Mulish',sans-serif;background:#fbfbf5;color:#211a18;padding-bottom:40px}}
    ::-webkit-scrollbar{{width:5px}}::-webkit-scrollbar-thumb{{background:#d9c2ba;border-radius:4px}}
  </style>
</head>
<body>
  <!-- Back bar -->
  <div style="position:sticky;top:0;background:rgba(255,248,246,.92);backdrop-filter:blur(8px);border-bottom:1px solid #e6e4da;padding:12px 28px;display:flex;align-items:center;justify-content:space-between;z-index:10">
    <button onclick="window.location.href='/tool/annual_report_analysis'"
            style="display:flex;align-items:center;gap:6px;font-family:inherit;font-size:12px;font-weight:700;color:#6f331a;background:none;border:1px solid rgba(111,51,26,.3);border-radius:8px;padding:6px 14px;cursor:pointer">
      ← Back to Analysis Tool
    </button>
    <div>
      <span style="font-size:13px;font-weight:700;color:#211a18">{data.get("company","")}</span>
      <span style="font-size:11px;font-weight:700;color:#53433d;margin-left:8px;background:#f4e5e1;padding:2px 8px;border-radius:4px">{data.get("fiscal_year","")}</span>
    </div>
  </div>

  <div style="padding:28px;max-width:1000px;margin:0 auto">
    <!-- KPI row -->
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:26px">
      {kpi_cards}
    </div>

    <!-- Two-column layout: summary + insights -->
    <div style="display:grid;grid-template-columns:1fr 340px;gap:20px">

      <!-- Summary card -->
      <div style="background:#fff;border:1px solid #e6e4da;border-radius:12px;padding:24px">
        <h3 style="font-size:15px;font-weight:700;color:#211a18;margin-bottom:14px">Executive Summary</h3>
        <p style="font-size:13px;color:#53433d;line-height:1.7">{data.get("summary","")}</p>
      </div>

      <!-- AI Insights sidebar -->
      <div style="background:#fff;border:1px solid #e6e4da;border-radius:12px;padding:24px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #e6e4da">
          <span style="font-size:18px">✦</span>
          <h3 style="font-size:15px;font-weight:700;color:#211a18">AI Strategy Extraction</h3>
        </div>
        {insights_html if insights_html else '<p style="font-size:13px;color:#7a7060">No insights available.</p>'}
      </div>
    </div>
  </div>
</body>
</html>"""


# ── HTTP handler ──────────────────────────────────────────────────────────────

class DemoHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self._send_html(200, SHELL_HTML)
        elif self.path.startswith("/tool/"):
            key = self.path[len("/tool/"):]
            if key == "welcome":
                self._send_html(200, WELCOME_HTML)
            elif key in TOOL_MAP:
                html = TOOL_MAP[key].build_ui().html()
                html = self._inject_theme(html, key)
                self._send_html(200, html)
            else:
                self._send_html(404, "<h1>Unknown tool</h1>")
        else:
            self._send_html(200, SHELL_HTML)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode()
        params = parse_qs(body)

        if self.path == "/analyze":
            url = params.get("url", [""])[0].strip()
            if not url:
                self._send_html(400, "<h1>Missing URL</h1>")
                return
            print(f"[analyze] Fetching and analyzing: {url}")
            data = _analyze_url(url)
            self._send_html(200, _render_analysis_html(data))
            return

        query = params.get("q", [""])[0].strip()
        if not query:
            self._send_json(400, {"error": "empty query"})
            return

        system_key = routing._classify_intent(query)
        print(f"[demo] '{query}'  ->  {system_key}")

        self._send_json(200, {
            "agent": system_key,
            "label": AGENT_LABELS[system_key],
            "reply": AGENT_REPLIES[system_key],
        })

    def _inject_theme(self, html: str, key: str) -> str:
        html = html.replace('</head>', TOOL_THEME_CSS + '</head>', 1)
        extra_js = TOOL_EXTRA_JS.get(key, "")
        if extra_js:
            html = html.replace('</body>', extra_js + '</body>', 1)
        return html

    def _send_html(self, code: int, html: str) -> None:
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = 8080
    print(f"\nAI Agents Platform  →  http://localhost:{port}")
    print("Ctrl+C to stop\n")
    webbrowser.open(f"http://localhost:{port}")
    HTTPServer(("127.0.0.1", port), DemoHandler).serve_forever()
