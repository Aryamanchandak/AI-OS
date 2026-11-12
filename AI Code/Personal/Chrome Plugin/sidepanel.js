// ── Folder persistence (IndexedDB) ────────────────────────────────────────────
const DB_NAME = "sharpen-db", DB_STORE = "settings", DB_VERSION = 1;

function openDB() {
  return new Promise((res, rej) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = e => e.target.result.createObjectStore(DB_STORE);
    req.onsuccess = e => res(e.target.result);
    req.onerror   = e => rej(e.target.error);
  });
}

async function idbGet(key) {
  const db = await openDB();
  return new Promise((res, rej) => {
    const req = db.transaction(DB_STORE).objectStore(DB_STORE).get(key);
    req.onsuccess = e => res(e.target.result);
    req.onerror   = e => rej(e.target.error);
  });
}

async function idbPut(key, value) {
  const db = await openDB();
  return new Promise((res, rej) => {
    const req = db.transaction(DB_STORE, "readwrite").objectStore(DB_STORE).put(value, key);
    req.onsuccess = () => res();
    req.onerror   = e => rej(e.target.error);
  });
}

async function pickSaveFolder() {
  const handle = await window.showDirectoryPicker({ mode: "readwrite" });
  await idbPut("saveFolder", handle);
  updateFolderLabel(handle.name);
  return handle;
}

function updateFolderLabel(name) {
  el("tldr-folder-label").innerHTML = `Save folder: <strong>${name}</strong>`;
}

async function getSaveFolderHandle() {
  const handle = await idbGet("saveFolder");
  if (!handle) return null;
  const perm = await handle.queryPermission({ mode: "readwrite" });
  if (perm === "granted") return handle;
  const req = await handle.requestPermission({ mode: "readwrite" });
  return req === "granted" ? handle : null;
}

// ── Model config ──────────────────────────────────────────────────────────────
const MODEL = "gpt-4o-mini";
const TLDR_MODEL = "gpt-5";

// ── Prompts ───────────────────────────────────────────────────────────────────
function buildCounterPrompt(page) {
  return `You are helping someone sharpen their thinking about an article they're reading. Read the content below, identify its core claims, and provide steelmanned counterarguments.

Page title: ${page.title}
URL: ${page.url}
Content (first 6000 chars):
${page.text}

Respond with ONLY a JSON object (no prose, no markdown fences) in this schema:

{
  "main_claims": ["claim 1", "claim 2", "claim 3"],
  "counterarguments": [
    {
      "target_claim": "which claim this addresses",
      "counter": "the counterargument, steelmanned — 2-3 sentences",
      "strength": "strong | moderate | weak"
    }
  ],
  "weakest_points": ["a point in the original argument that's vulnerable, 1 sentence", "..."],
  "missing_context": ["important context the page omits that a reader should seek out, 1 sentence", "..."]
}

Include 3-5 counterarguments. Steelman them — present the strongest version of the opposing view, not strawmen. Label strength honestly. If the page has no substantive argument (e.g. it's a product page), say so in a single counterargument with target_claim "N/A".`;
}

function buildBiasPrompt(page) {
  return `You are analyzing the rhetorical and structural patterns of a webpage to help a reader notice framing choices. You are NOT fact-checking. You are NOT assessing whether claims are true. You are identifying how the argument is constructed and what framing choices shape the reader's interpretation.

Page title: ${page.title}
URL: ${page.url}
Content (first 6000 chars):
${page.text}

Respond with ONLY a JSON object (no prose, no markdown fences) in this schema:

{
  "framing_summary": "one sentence describing the overall rhetorical stance/framing",
  "loaded_language": [
    {"phrase": "exact or near-exact phrase from the text", "note": "why this word choice carries rhetorical weight, 1 sentence"}
  ],
  "whats_emphasized": ["what the page foregrounds, 1 sentence each"],
  "whats_backgrounded_or_missing": ["perspectives, voices, counterarguments, or context that are absent or minimized, 1 sentence each"],
  "implicit_assumptions": ["premises the argument takes for granted without justifying, 1 sentence each"],
  "rhetorical_devices": ["appeals to emotion, authority, consensus, fear, etc. as they appear here, 1 sentence each"]
}

Rules:
- Focus on STRUCTURE and RHETORIC, not truth. Do not say anything is "false" or "misleading."
- Include 2-5 items per array. If a category genuinely doesn't apply, use an empty array.
- Quote exact phrases where possible for loaded_language.
- Be even-handed. Every piece of writing has framing; your job is to surface it, not condemn it.`;
}

function buildTLDRPrompt(page) {
  return `Summarize the following webpage for someone who wants the gist in 30 seconds.

Page title: ${page.title}
URL: ${page.url}
Content (first 6000 chars):
${page.text}

Respond with ONLY a JSON object (no prose, no markdown fences) in this schema:

{
  "bottom_line": "one sentence — what this page is really saying or trying to do",
  "summary": "2-3 sentences covering the who, what, and why",
  "key_points": ["the most important point", "second most important", "third if needed"],
  "worth_reading_if": "one sentence describing who would benefit most from reading the full page"
}`;
}

function buildTopicExtractionPrompt(page) {
  return `Read the following webpage and return the central debatable topic in one sentence.

Page title: ${page.title}
URL: ${page.url}
Content: ${page.text.slice(0, 3000)}

Respond with ONLY a JSON object: {"topic": "one sentence"}`;
}

function buildDebateSystemPrompt() {
  return `You are a debate partner. The user has stated a position; you argue the DIRECT OPPOSITE.

Topic: ${debateState.topic}
User's position: ${debateState.userPosition}
Your role: Argue the direct negation of the user's position. Do not reframe, soften, or shift scope — if the user says "X is good", you argue "X is not good" or "X is harmful". Never agree with the user's premise.

Rules:
- Argue your side genuinely. Steelman the opposition; do not strawman the user.
- Keep each response to 3-5 sentences. This is a real-time exchange, not an essay.
- Press weak points in the user's reasoning. Ask pointed questions when useful.
- Do not capitulate just because the user pushes back. Only concede a specific sub-point if they've genuinely made a strong case, and say so explicitly when you do.
- If the user makes a novel argument you hadn't considered, engage with it directly rather than redirecting.
- Stay on topic. Don't drift into meta-commentary about the debate itself unless the user asks.`;
}

// ── Debate state ─────────────────────────────────────────────────────────────
let debateState = {
  topic: null,
  userPosition: null,
  pageTitle: null,
  pageUrl: null,
  messages: []
};

// ── OpenAI API wrapper ────────────────────────────────────────────────────────
async function callOpenAI({ systemPrompt, messages, maxTokens = 1500, model = MODEL }) {
  const serverUrl = await getServerUrl();
  let response;

  try {
    response = await fetch(`${serverUrl}/openai/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        system_prompt: systemPrompt || null,
        messages,
        max_tokens: maxTokens,
        model
      })
    });
  } catch (err) {
    throw new Error("Server offline — run: ./run.sh");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.detail || `Server error ${response.status}`);
  }

  return data.content;
}

async function callOpenAIStream({ messages, model = MODEL, maxTokens = 1500, onChunk }) {
  const serverUrl = await getServerUrl();
  let response;

  try {
    response = await fetch(`${serverUrl}/openai/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        messages,
        model,
        max_tokens: maxTokens
      })
    });
  } catch (err) {
    throw new Error("Server offline — run: ./run.sh");
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err?.detail || `Server error ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let accumulated = "";
  let emitted = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    accumulated += decoder.decode(value, { stream: true });
    emitted = accumulated;
    onChunk(accumulated);
  }

  accumulated += decoder.decode();
  if (accumulated !== emitted) onChunk(accumulated);

  return accumulated;
}

function normalizeExtractedPage(page, fallbackUrl = "") {
  if (!page || typeof page !== "object") return null;

  const title = typeof page.title === "string" ? page.title.trim() : "";
  const url = typeof page.url === "string" ? page.url.trim() : fallbackUrl;
  const text = typeof page.text === "string" ? page.text.trim() : "";

  if (!title || !url || !text) return null;
  return { title, url, text };
}

// ── Page content extractor ────────────────────────────────────────────────────
async function extractPageContent() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const blockedPrefixes = [
    "chrome://", "chrome-extension://", "edge://", "about:",
    "https://chrome.google.com/webstore"
  ];
  if (!tab.url || blockedPrefixes.some(p => tab.url.startsWith(p))) {
    throw new Error("Can't analyze browser system pages. Try a regular website.");
  }

  if (!tab.id) {
    throw new Error("Could not access the active tab. Reload the page and try again.");
  }

  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => ({
      title: document.title,
      url: location.href,
      text: document.body.innerText.slice(0, 6000)
    })
  });

  if (!result || result.error) {
    throw new Error(result?.error?.message || "Failed to read the current page.");
  }

  const page = normalizeExtractedPage(result.result, tab.url);
  if (!page) {
    throw new Error("The page content could not be read. Reload the page and try again.");
  }

  return page;
}

// ── Smart content extractor — transcript on YouTube, body text elsewhere ───────
async function extractSmartContent() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const blockedPrefixes = [
    "chrome://", "chrome-extension://", "edge://", "about:",
    "https://chrome.google.com/webstore"
  ];
  if (!tab.url || blockedPrefixes.some(p => tab.url.startsWith(p))) {
    throw new Error("Can't analyze browser system pages. Try a regular website.");
  }

  if (!tab.id) {
    throw new Error("Could not access the active tab. Reload the page and try again.");
  }

  if (!tab.url.includes('youtube.com/watch')) {
    return extractPageContent();
  }

  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      let segs = document.querySelectorAll('ytd-transcript-segment-renderer yt-formatted-string');

      if (segs.length === 0) {
        let btn = document.querySelector('button[aria-label="Open transcript"]');
        if (!btn) {
          const expand = document.querySelector('#expand, tp-yt-paper-button#expand');
          if (expand) { expand.click(); await sleep(400); }
          btn = document.querySelector('button[aria-label="Open transcript"]');
        }
        if (!btn) {
          const more = document.querySelector('ytd-menu-renderer yt-button-shape button');
          if (more) {
            more.click(); await sleep(400);
            btn = document.querySelector('[aria-label="Open transcript"]') ||
                  Array.from(document.querySelectorAll('tp-yt-paper-item'))
                    .find(el => el.textContent.toLowerCase().includes('transcript'));
          }
        }
        if (btn) { btn.click(); await sleep(1100); }
        segs = document.querySelectorAll('ytd-transcript-segment-renderer yt-formatted-string');
      }

      if (segs.length === 0) throw new Error(
        'Transcript not found. Open it manually (… > Open transcript) then try again.'
      );

      return {
        title: document.title.replace(' - YouTube', '').trim(),
        url: location.href,
        text: Array.from(segs).map(s => s.innerText).filter(Boolean).join(' ')
      };
    }
  });

  if (result.error) throw new Error(result.error.message);

  const page = normalizeExtractedPage(result?.result, tab.url);
  if (page) return page;

  return extractPageContent();
}

// ── JSON extraction helper ────────────────────────────────────────────────────
function extractJSON(text) {
  const cleaned = text.trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "");
  return JSON.parse(cleaned);
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
function el(id) { return document.getElementById(id); }

function makeEl(tag, className) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  return e;
}

function setText(node, text) {
  node.textContent = text;
  return node;
}

// ── Tab switching ─────────────────────────────────────────────────────────────
const tabs = ["counter", "bias", "debate", "tldr", "socratic", "cards"];

function switchTab(name) {
  tabs.forEach(t => {
    el(`tab-${t}`).classList.toggle("active", t === name);
    el(`${t}-panel`).hidden = (t !== name);
  });
}

// ── TLDR renderer ─────────────────────────────────────────────────────────────
function renderTLDR(data, container) {
  container.innerHTML = "";

  const addTitle = (text) => {
    const d = makeEl("div", "result-section-title");
    d.textContent = text;
    container.appendChild(d);
  };

  const addBullet = (text) => {
    const d = makeEl("div", "result-bullet");
    d.textContent = text;
    container.appendChild(d);
  };

  // Bottom line
  addTitle("Bottom Line");
  const bl = makeEl("div");
  bl.style.cssText = "font-weight:600;color:#1a1a1a;font-size:13px;margin-bottom:4px;line-height:1.5;";
  bl.textContent = data.bottom_line || "";
  container.appendChild(bl);

  // Summary
  addTitle("Summary");
  const sum = makeEl("div");
  sum.style.cssText = "color:#333;font-size:12px;line-height:1.6;";
  sum.textContent = data.summary || "";
  container.appendChild(sum);

  // Key points
  if ((data.key_points || []).length) {
    addTitle("Key Points");
    data.key_points.forEach(p => addBullet(p));
  }

  // Worth reading if
  if (data.worth_reading_if) {
    addTitle("Worth Reading If…");
    const wri = makeEl("div");
    wri.style.cssText = "color:#555;font-size:12px;font-style:italic;";
    wri.textContent = data.worth_reading_if;
    container.appendChild(wri);
  }
}

// ── TLDR save ─────────────────────────────────────────────────────────────────
async function saveTLDRAsMarkdown(data, page) {
  const date = new Date().toISOString().slice(0, 10);
  const slug = (page.title || "summary")
    .toLowerCase()
    .split(/\s+/).slice(0, 6).join('-')
    .replace(/[^a-z0-9-]/g, '');
  const filename = `tldr-${slug}-${date}.md`;

  let md = `# TLDR: ${page.title}\n\n`;
  md += `**Date:** ${date}  \n`;
  md += `**Source:** [${page.url}](${page.url})\n\n---\n\n`;
  md += `## Bottom Line\n${data.bottom_line || ""}\n\n`;
  md += `## Summary\n${data.summary || ""}\n\n`;
  if ((data.key_points || []).length) {
    md += `## Key Points\n`;
    data.key_points.forEach(p => { md += `- ${p}\n`; });
    md += "\n";
  }
  if (data.worth_reading_if) {
    md += `## Worth Reading If\n${data.worth_reading_if}\n`;
  }

  let dirHandle = await getSaveFolderHandle();
  if (!dirHandle) dirHandle = await pickSaveFolder();

  const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(md);
  await writable.close();
}

// ── TLDR mode ─────────────────────────────────────────────────────────────────
async function runTLDR() {
  const btn = el("tldr-analyze-btn");
  const status = el("tldr-status");
  const results = el("tldr-results");

  btn.disabled = true;
  results.innerHTML = "";

  // Live streaming preview element
  const preview = makeEl("pre");
  preview.style.cssText = "font-size:11px;color:#555;white-space:pre-wrap;word-break:break-word;margin:0;line-height:1.5;";
  results.appendChild(preview);

  try {
    status.textContent = "Reading page…";
    const page = await extractSmartContent();

    status.textContent = "Summarizing…";
    const raw = await callOpenAIStream({
      messages: [{ role: "user", content: buildTLDRPrompt(page) }],
      model: TLDR_MODEL,
      onChunk: (text) => { preview.textContent = text; }
    });

    const data = extractJSON(raw);
    status.textContent = "";
    results.innerHTML = "";
    renderTLDR(data, results);

    // Save button
    const saveBtn = makeEl("button");
    saveBtn.textContent = "Save as Markdown";
    saveBtn.style.cssText = "margin-top:12px;padding:6px 14px;font-size:12px;cursor:pointer;border:1px solid #ccc;border-radius:6px;background:#f9f9f9;";
    saveBtn.addEventListener("click", () => saveTLDRAsMarkdown(data, page));
    results.appendChild(saveBtn);
  } catch (err) {
    results.innerHTML = "";
    status.textContent = "Error: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Counter renderer ──────────────────────────────────────────────────────────
function renderCounter(data, container) {
  container.innerHTML = "";

  const addTitle = (text) => {
    const d = makeEl("div", "result-section-title");
    d.textContent = text;
    container.appendChild(d);
  };

  const addBullet = (text) => {
    const d = makeEl("div", "result-bullet");
    d.textContent = text;
    container.appendChild(d);
  };

  // Main claims
  addTitle("Main Claims of the Page");
  (data.main_claims || []).forEach(c => addBullet(c));

  // Counterarguments
  addTitle("Counterarguments");
  (data.counterarguments || []).forEach(item => {
    const wrap = makeEl("div", "counter-item");

    const header = makeEl("div", "counter-item-header");

    const strength = (item.strength || "weak").toLowerCase();
    const badge = makeEl("span", `strength-badge strength-${strength}`);
    badge.textContent = strength;
    header.appendChild(badge);

    const target = makeEl("span", "counter-target");
    target.textContent = `Against: "${item.target_claim || ""}"`;
    header.appendChild(target);

    wrap.appendChild(header);

    const body = makeEl("div", "counter-text");
    body.textContent = item.counter || "";
    wrap.appendChild(body);

    container.appendChild(wrap);
  });

  // Weakest points
  if ((data.weakest_points || []).length) {
    addTitle("Weakest Points in the Original");
    data.weakest_points.forEach(p => addBullet(p));
  }

  // Missing context
  if ((data.missing_context || []).length) {
    addTitle("What's Missing");
    data.missing_context.forEach(p => addBullet(p));
  }
}

// ── Bias renderer ─────────────────────────────────────────────────────────────
function renderBias(data, container) {
  container.innerHTML = "";

  const addTitle = (text) => {
    const d = makeEl("div", "result-section-title");
    d.textContent = text;
    container.appendChild(d);
  };

  const addBullet = (text) => {
    const d = makeEl("div", "result-bullet");
    d.textContent = text;
    container.appendChild(d);
  };

  // Framing summary
  addTitle("Framing");
  const framing = makeEl("div");
  framing.style.cssText = "font-style:italic;color:#555;font-size:12px;margin-bottom:4px;";
  framing.textContent = data.framing_summary || "";
  container.appendChild(framing);

  // Loaded language
  if ((data.loaded_language || []).length) {
    addTitle("Loaded Language");
    data.loaded_language.forEach(item => {
      const wrap = makeEl("div", "bias-loaded-item");
      const phrase = makeEl("span", "bias-phrase");
      phrase.textContent = `"${item.phrase || ""}"`;
      wrap.appendChild(phrase);
      const note = makeEl("div", "bias-note");
      note.textContent = item.note || "";
      wrap.appendChild(note);
      container.appendChild(wrap);
    });
  }

  // Emphasized
  if ((data.whats_emphasized || []).length) {
    addTitle("Emphasized");
    data.whats_emphasized.forEach(p => addBullet(p));
  }

  // Backgrounded / missing
  if ((data.whats_backgrounded_or_missing || []).length) {
    addTitle("Backgrounded / Missing");
    data.whats_backgrounded_or_missing.forEach(p => addBullet(p));
  }

  // Implicit assumptions
  if ((data.implicit_assumptions || []).length) {
    addTitle("Implicit Assumptions");
    data.implicit_assumptions.forEach(p => addBullet(p));
  }

  // Rhetorical devices
  if ((data.rhetorical_devices || []).length) {
    addTitle("Rhetorical Devices");
    data.rhetorical_devices.forEach(p => addBullet(p));
  }

  // Disclaimer — always shown
  const disc = makeEl("div", "disclaimer");
  disc.textContent = "⚠ This tool surfaces framing patterns, not truth. This tool has its own priors about what counts as \"loaded\" language — treat this as prompts for your own reading, not a verdict.";
  container.appendChild(disc);
}

// ── Counter mode ──────────────────────────────────────────────────────────────
async function runCounter() {
  const btn = el("counter-analyze-btn");
  const status = el("counter-status");
  const results = el("counter-results");

  btn.disabled = true;
  results.innerHTML = "";

  try {
    status.textContent = "Reading page…";
    const page = await extractSmartContent();

    status.textContent = "Thinking…";
    const raw = await callOpenAI({
      messages: [{ role: "user", content: buildCounterPrompt(page) }],
      maxTokens: 1500
    });

    const data = extractJSON(raw);
    status.textContent = "";
    renderCounter(data, results);
  } catch (err) {
    status.textContent = "Error: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Bias mode ─────────────────────────────────────────────────────────────────
async function runBias() {
  const btn = el("bias-analyze-btn");
  const status = el("bias-status");
  const results = el("bias-results");

  btn.disabled = true;
  results.innerHTML = "";

  try {
    status.textContent = "Reading page…";
    const page = await extractSmartContent();

    status.textContent = "Thinking…";
    const raw = await callOpenAI({
      messages: [{ role: "user", content: buildBiasPrompt(page) }],
      maxTokens: 1500
    });

    const data = extractJSON(raw);
    status.textContent = "";
    renderBias(data, results);
  } catch (err) {
    status.textContent = "Error: " + err.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Debate mode ───────────────────────────────────────────────────────────────
function appendMessage(role, text) {
  const messages = el("debate-messages");

  // Remove thinking placeholder if present
  const thinking = messages.querySelector(".msg-thinking");
  if (thinking) thinking.remove();

  const cls = role === "user" ? "msg-user"
    : role === "assistant" ? "msg-assistant"
    : role === "system-error" ? "msg-system"
    : "msg-thinking";

  const msg = makeEl("div", `msg ${cls}`);
  msg.textContent = text;
  messages.appendChild(msg);
  messages.scrollTop = messages.scrollHeight;
  return msg;
}

function showThinking() {
  const messages = el("debate-messages");
  const msg = makeEl("div", "msg msg-thinking");
  msg.textContent = "Thinking…";
  messages.appendChild(msg);
  messages.scrollTop = messages.scrollHeight;
}

// User submits position → extract topic → start debate immediately
async function startDebate() {
  const positionInput = el("debate-position-input");
  const errEl = el("debate-setup-error");
  const startBtn = el("debate-start-btn");

  const userPosition = positionInput.value.trim();
  if (!userPosition) {
    errEl.textContent = "Please enter your position first.";
    return;
  }

  errEl.textContent = "";
  startBtn.disabled = true;
  startBtn.textContent = "Reading page…";

  try {
    const page = await extractSmartContent();
    startBtn.textContent = "Starting…";

    const raw = await callOpenAI({
      messages: [{ role: "user", content: buildTopicExtractionPrompt(page) }],
      maxTokens: 150
    });

    const data = extractJSON(raw);

    debateState.topic = data.topic;
    debateState.userPosition = userPosition;
    debateState.pageTitle = page.title;
    debateState.pageUrl = page.url;
    debateState.messages = [];

    el("debate-setup").hidden = true;
    el("debate-chat").hidden = false;
    el("debate-topic-label").textContent = debateState.topic;
    el("debate-messages").innerHTML = "";

    const systemPrompt = buildDebateSystemPrompt() +
      "\n\nOpen with your strongest challenge to the user's position in 3-4 sentences, ending with a pointed question.";

    showThinking();

    const reply = await callOpenAI({
      systemPrompt,
      messages: [{ role: "user", content: "Begin." }],
      maxTokens: 600
    });

    debateState.messages = [
      { role: "user", content: "Begin." },
      { role: "assistant", content: reply }
    ];

    appendMessage("assistant", reply);

  } catch (err) {
    errEl.textContent = "Error: " + err.message;
    el("debate-setup").hidden = false;
    el("debate-chat").hidden = true;
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = "Start Debate";
  }
}

async function sendDebateMessage() {
  const input = el("debate-user-input");
  const sendBtn = el("debate-send-btn");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  appendMessage("user", text);

  debateState.messages.push({ role: "user", content: text });

  // Cap history at 30 messages
  if (debateState.messages.length > 30) {
    debateState.messages = debateState.messages.slice(-30);
  }

  showThinking();

  try {
    const reply = await callOpenAI({
      systemPrompt: buildDebateSystemPrompt(),
      messages: debateState.messages,
      maxTokens: 600
    });

    debateState.messages.push({ role: "assistant", content: reply });
    appendMessage("assistant", reply);
  } catch (err) {
    appendMessage("system-error", "Error: " + err.message);
  } finally {
    sendBtn.disabled = false;
    el("debate-user-input").focus();
  }
}

function saveDebateAsMarkdown() {
  if (!debateState.topic || debateState.messages.length <= 1) return;

  const date = new Date().toISOString().slice(0, 10);
  const slug = debateState.topic
    .toLowerCase()
    .split(/\s+/).slice(0, 6).join('-')
    .replace(/[^a-z0-9-]/g, '');
  const filename = `debate-${slug}-${date}.md`;

  let md = `# Debate: ${debateState.topic}\n\n`;
  md += `**Date:** ${date}  \n`;
  md += `**Article:** [${debateState.pageTitle}](${debateState.pageUrl})  \n`;
  md += `**Your position:** ${debateState.userPosition}\n\n---\n\n`;

  for (const msg of debateState.messages.slice(1)) {
    const label = msg.role === 'user' ? '**You:**' : '**Claude:**';
    md += `${label} ${msg.content}\n\n---\n\n`;
  }

  const blob = new Blob([md], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function resetDebate() {
  saveDebateAsMarkdown();
  debateState = { topic: null, userPosition: null, pageTitle: null, pageUrl: null, messages: [] };
  el("debate-chat").hidden = true;
  el("debate-setup").hidden = false;
  el("debate-position-input").value = "";
  el("debate-setup-error").textContent = "";
  el("debate-messages").innerHTML = "";
}

async function getServerUrl() {
  return new Promise(resolve => chrome.storage.local.get('serverUrl', d => resolve(d.serverUrl || 'http://localhost:8765')));
}

async function saveServerUrl(url) {
  return new Promise(resolve => chrome.storage.local.set({ serverUrl: url.trim().replace(/\/$/, '') }, resolve));
}

// ── Socratic — transcript extraction ─────────────────────────────────────────
async function extractContent() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const isYouTube = tab.url && tab.url.includes('youtube.com/watch');
  const page = await extractSmartContent();
  if (!page) {
    throw new Error('Could not extract content from this page. Reload the tab and try again.');
  }
  return {
    type: isYouTube ? 'youtube' : 'article',
    videoId: isYouTube ? (new URL(tab.url).searchParams.get('v') || '') : '',
    title: page.title,
    url: page.url,
    text: page.text
  };
}

// ── Socratic — prompts ────────────────────────────────────────────────────────
const SYSTEM_QUESTIONS = `You are a Socratic tutor. Generate exactly 3 questions about the provided content that:
- Cannot be answered by recalling a single sentence verbatim
- Require synthesis, application, or critical evaluation
- Are ordered: conceptual first, then applied, then critical

Return ONLY valid JSON — no prose, no fences:
{"questions": ["question 1", "question 2", "question 3"]}`;

const SYSTEM_EVALUATE = `You are a Socratic tutor evaluating a student's answer.

Classify it as one of:
- shallow: restated words from the text, no genuine understanding shown
- partial: right direction but missing a key dimension
- solid: demonstrates genuine understanding

Then respond:
- shallow: ask a pointed follow-up that exposes the specific gap. Be direct, not encouraging.
- partial: name exactly what's missing in one sentence, then ask them to fill that gap.
- solid: confirm in exactly one sentence, then say "Ready for the next question." (or "Session complete." if this was Q3).

Return ONLY valid JSON — no prose, no fences:
{"verdict": "shallow|partial|solid", "response": "your response text"}`;

const SYSTEM_EXPORT = `You are extracting structured study material from a Socratic learning session.
Produce output compatible with the study_system extraction schema.

Valid relation types: RELATES_TO, PREREQUISITE_OF, COMPONENT_OF, CONTRASTS_WITH, APPLIES_TO, TESTED_TOGETHER

Return ONLY valid JSON — no prose, no fences:
{
  "concepts": [
    {"canonical_name": "...", "domain": "...", "summary": "...", "aliases": [], "tags": []}
  ],
  "triplets": [
    {"subject": "...", "relation": "RELATES_TO", "object": "..."}
  ],
  "flashcards": [
    {"front": "...", "back": "..."}
  ],
  "open_question": "A worthwhile question to research further"
}
Include 3-5 concepts, 3-5 triplets, exactly 4 flashcard pairs.`;

// ── Socratic — state ──────────────────────────────────────────────────────────
let socraticState = {
  content: null,       // {type, title, videoId, url, text}
  questions: [],
  currentQ: 0,
  solidHistory: [],    // [{q, a}] — only solid-verdict answers, one per question
  phase: 'idle',       // idle | questioning | complete
  exportData: null
};

// ── Socratic — UI helpers ─────────────────────────────────────────────────────
function setSocraticPhase(phase) {
  socraticState.phase = phase;
  el('socratic-idle').hidden   = phase !== 'idle';
  el('socratic-chat').hidden   = phase !== 'questioning';
  el('socratic-export').hidden = phase !== 'complete';
}

function updateSocraticProgress() {
  const dots = el('socratic-progress').querySelectorAll('.progress-dot');
  dots.forEach((dot, i) => {
    dot.classList.remove('active', 'done');
    if (i < socraticState.currentQ) dot.classList.add('done');
    else if (i === socraticState.currentQ) dot.classList.add('active');
  });
}

function appendSocraticMsg(role, text) {
  const messages = el('socratic-messages');
  const thinking = messages.querySelector('.msg-thinking');
  if (thinking) thinking.remove();
  const cls = role === 'user' ? 'msg-user' : role === 'error' ? 'msg-system' : 'msg-assistant';
  const msg = makeEl('div', `msg ${cls}`);
  msg.textContent = text;
  messages.appendChild(msg);
  messages.scrollTop = messages.scrollHeight;
}

function showSocraticThinking() {
  const messages = el('socratic-messages');
  const msg = makeEl('div', 'msg msg-thinking');
  msg.textContent = 'Thinking…';
  messages.appendChild(msg);
  messages.scrollTop = messages.scrollHeight;
}

// ── Socratic — load flow ──────────────────────────────────────────────────────
async function loadSocraticContent() {
  const loadBtn = el('socratic-load-btn');
  const status  = el('socratic-load-status');
  loadBtn.disabled = true;
  status.textContent = 'Extracting content…';

  try {
    const content = await extractContent();
    if (!content.text || content.text.length < 80) {
      throw new Error('Content too short to generate meaningful questions.');
    }

    status.textContent = 'Generating questions…';
    const raw = await callOpenAI({
      systemPrompt: SYSTEM_QUESTIONS,
      messages: [{ role: "user", content: `Content: ${content.text.slice(0, 5000)}` }],
      maxTokens: 700
    });
    const { questions } = extractJSON(raw);

    if (!Array.isArray(questions) || questions.length < 3) {
      throw new Error('Could not generate 3 questions from this content.');
    }

    socraticState = {
      content,
      questions,
      currentQ: 0,
      solidHistory: [],
      phase: 'questioning',
      exportData: null
    };

    el('socratic-video-title').textContent = content.title;
    el('socratic-messages').innerHTML = '';
    updateSocraticProgress();
    setSocraticPhase('questioning');
    appendSocraticMsg('tutor', questions[0]);
    el('socratic-user-input').focus();

  } catch (err) {
    status.textContent = 'Error: ' + err.message;
  } finally {
    loadBtn.disabled = false;
  }
}

// ── Socratic — answer handling ────────────────────────────────────────────────
async function sendSocraticAnswer() {
  const input   = el('socratic-user-input');
  const sendBtn = el('socratic-send-btn');
  const text    = input.value.trim();
  if (!text || socraticState.phase !== 'questioning') return;

  input.value = '';
  input.style.height = 'auto';
  sendBtn.disabled = true;

  appendSocraticMsg('user', text);
  showSocraticThinking();

  const currentQuestion = socraticState.questions[socraticState.currentQ];

  try {
    const raw = await callOpenAI({
      systemPrompt: SYSTEM_EVALUATE,
      messages: [{ role: "user", content: `Question: ${currentQuestion}\nStudent answer: ${text}` }],
      maxTokens: 500
    });
    const { verdict, response } = extractJSON(raw);

    if (verdict === 'solid') {
      socraticState.solidHistory.push({ q: currentQuestion, a: text });

      if (socraticState.currentQ < 2) {
        socraticState.currentQ++;
        updateSocraticProgress();
        appendSocraticMsg('tutor', response);
        appendSocraticMsg('tutor', socraticState.questions[socraticState.currentQ]);
      } else {
        appendSocraticMsg('tutor', response);
        await generateSocraticExport();
      }
    } else {
      appendSocraticMsg('tutor', response);
    }

  } catch (err) {
    appendSocraticMsg('error', 'Error: ' + err.message);
  } finally {
    sendBtn.disabled = false;
    el('socratic-user-input').focus();
  }
}

// ── Socratic — export ─────────────────────────────────────────────────────────
async function generateSocraticExport() {
  setSocraticPhase('complete');
  const genStatus = el('socratic-export-generating');
  const jsonEl    = el('socratic-export-json');
  genStatus.textContent = 'Generating study materials…';
  jsonEl.textContent = '';

  const sessionLog = socraticState.solidHistory
    .map((h, i) => `Q${i + 1}: ${h.q}\nAnswer: ${h.a}`)
    .join('\n\n');

  const userMsg = `Video: "${socraticState.content.title}"\n\nSession:\n${sessionLog}`;

  try {
    const raw = await callOpenAI({
      systemPrompt: SYSTEM_EXPORT,
      messages: [{ role: "user", content: userMsg }],
      maxTokens: 1200
    });
    const payload = extractJSON(raw);

    const ts = new Date().toISOString();
    socraticState.exportData = {
      schema_version: '1.0',
      source: {
        type: socraticState.content.type,
        video_id: socraticState.content.videoId,
        title: socraticState.content.title,
        url: socraticState.content.url,
        captured_at: ts
      },
      extraction: {
        file_path: socraticState.content.videoId
          ? `youtube://${socraticState.content.videoId}`
          : socraticState.content.url,
        concepts:  payload.concepts  || [],
        triplets:  payload.triplets  || [],
        atomic_facts: []
      },
      flashcards:    payload.flashcards    || [],
      open_question: payload.open_question || ''
    };

    genStatus.textContent = '';
    jsonEl.textContent = JSON.stringify(socraticState.exportData, null, 2);

  } catch (err) {
    genStatus.textContent = 'Export error: ' + err.message;
  }
}

async function pushToKgVecDb() {
  if (!socraticState.exportData) return;

  const pushBtn   = el('socratic-push-btn');
  const statusEl  = el('socratic-push-status');
  const serverUrl = await getServerUrl();

  pushBtn.disabled = true;
  statusEl.style.color = '#888';
  statusEl.textContent = 'Connecting…';

  try {
    const res = await fetch(`${serverUrl}/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(socraticState.exportData)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err?.detail || `Server error ${res.status}`);
    }

    const d = await res.json();
    statusEl.style.color = '#10b981';
    statusEl.textContent = `✓ ${d.nodes_upserted} nodes · ${d.edges_upserted} edges · ${d.flashcards_vectorised} flashcards`;
    pushBtn.textContent = 'Pushed ✓';

  } catch (err) {
    statusEl.style.color = '#dc2626';
    statusEl.textContent = err.message.toLowerCase().includes('fetch') || err.message.toLowerCase().includes('failed')
      ? '× Server offline — run: python server.py'
      : '× ' + err.message;
    pushBtn.disabled = false;
  }
}

function copySocraticJSON() {
  if (!socraticState.exportData) return;
  navigator.clipboard.writeText(JSON.stringify(socraticState.exportData, null, 2));
  const btn = el('socratic-copy-btn');
  const orig = btn.textContent;
  btn.textContent = 'Copied!';
  setTimeout(() => { btn.textContent = orig; }, 1500);
}

function downloadSocraticJSON() {
  if (!socraticState.exportData) return;
  const ts  = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
  const vid = socraticState.content.videoId || 'session';
  const blob = new Blob(
    [JSON.stringify(socraticState.exportData, null, 2)],
    { type: 'application/json' }
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `socratic-${vid}-${ts}.json`; a.click();
  URL.revokeObjectURL(url);
}

function resetSocratic() {
  socraticState = { content: null, questions: [], currentQ: 0, solidHistory: [], phase: 'idle', exportData: null };
  el('socratic-messages').innerHTML = '';
  el('socratic-load-status').textContent = '';
  el('socratic-export-json').textContent = '';
  el('socratic-export-generating').textContent = '';
  el('socratic-push-status').textContent = '';
  el('socratic-push-btn').textContent = 'Push to KG + VecDB';
  el('socratic-push-btn').disabled = false;
  setSocraticPhase('idle');
}

// ── Flashcards ────────────────────────────────────────────────────────────────
function buildFlashcardsPrompt(page) {
  return `Generate study flashcards from the content below.

Page title: ${page.title}
URL: ${page.url}
Content (first 6000 chars):
${page.text}

Respond with ONLY a JSON object (no prose, no markdown fences):
{
  "flashcards": [
    {"front": "question or term", "back": "answer or explanation"}
  ]
}

Generate 6-8 flashcards. Each front should be a clear question or key term. Each back should be a concise explanation (1-3 sentences). Cover the most important concepts from the content.`;
}

let cardsState = { cards: [], current: 0, flipped: false };

function renderCard() {
  if (!cardsState.cards.length) return;
  const card = cardsState.cards[cardsState.current];
  el('card-front-text').textContent = card.front;
  el('card-back-text').textContent = card.back;
  el('card-counter').textContent = `${cardsState.current + 1} / ${cardsState.cards.length}`;
  el('card-counter-mobile').textContent = `${cardsState.current + 1} / ${cardsState.cards.length}`;
  el('card-progress-fill').style.width = `${((cardsState.current + 1) / cardsState.cards.length) * 100}%`;
  el('flashcard-inner').classList.remove('flipped');
  el('flashcard-wrap').classList.remove('is-flipped');
  cardsState.flipped = false;
}

function flipCard() {
  cardsState.flipped = !cardsState.flipped;
  el('flashcard-inner').classList.toggle('flipped', cardsState.flipped);
  el('flashcard-wrap').classList.toggle('is-flipped', cardsState.flipped);
}

function prevCard() {
  if (!cardsState.cards.length) return;
  cardsState.current = (cardsState.current - 1 + cardsState.cards.length) % cardsState.cards.length;
  renderCard();
}

function nextCard() {
  if (!cardsState.cards.length) return;
  cardsState.current = (cardsState.current + 1) % cardsState.cards.length;
  renderCard();
}

async function runFlashcards() {
  const btn = el('cards-generate-btn');
  const status = el('cards-status');
  const area = el('cards-area');

  btn.disabled = true;
  area.hidden = true;
  status.textContent = 'Reading page…';

  try {
    const page = await extractSmartContent();
    status.textContent = 'Generating flashcards…';
    const raw = await callOpenAI({
      messages: [{ role: 'user', content: buildFlashcardsPrompt(page) }],
      maxTokens: 1200
    });
    const data = extractJSON(raw);
    if (!data.flashcards?.length) throw new Error('No flashcards generated.');
    cardsState = { cards: data.flashcards, current: 0, flipped: false };
    renderCard();
    status.textContent = '';
    area.hidden = false;
  } catch (err) {
    status.textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Wire everything up on DOM load ────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Tab clicks
  el("tab-counter").addEventListener("click",   () => switchTab("counter"));
  el("tab-bias").addEventListener("click",      () => switchTab("bias"));
  el("tab-debate").addEventListener("click",    () => switchTab("debate"));
  el("tab-tldr").addEventListener("click",      () => switchTab("tldr"));
  el("tab-socratic").addEventListener("click",  () => switchTab("socratic"));

  // TLDR
  el("tldr-analyze-btn").addEventListener("click", runTLDR);
  el("tldr-set-folder-btn").addEventListener("click", pickSaveFolder);
  idbGet("saveFolder").then(h => { if (h) updateFolderLabel(h.name); });

  // Counter
  el("counter-analyze-btn").addEventListener("click", runCounter);

  // Bias
  el("bias-analyze-btn").addEventListener("click", runBias);

  // Debate
  el("debate-start-btn").addEventListener("click", startDebate);

  // Debate chat — send button
  el("debate-send-btn").addEventListener("click", sendDebateMessage);

  // Debate chat — Enter to send, Shift+Enter for newline
  el("debate-user-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendDebateMessage();
    }
  });

  // Auto-resize textarea
  el("debate-user-input").addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 120) + "px";
  });

  // Debate reset
  el("debate-reset-btn").addEventListener("click", resetDebate);

  // Save debate when sidepanel is closed
  window.addEventListener("beforeunload", saveDebateAsMarkdown);

  // ── Settings overlay ────────────────────────────────────────────────────────
  el("settings-btn").addEventListener("click", async () => {
    const url = await getServerUrl();
    el("server-url-input").value = url;
    el("settings-overlay").hidden = false;
    el("server-url-input").focus();
  });

  el("settings-close-btn").addEventListener("click", () => {
    el("settings-overlay").hidden = true;
    el("settings-status").textContent = '';
  });

  el("settings-save-btn").addEventListener("click", async () => {
    const url = el("server-url-input").value.trim() || 'http://localhost:8765';
    await saveServerUrl(url);
    el("settings-status").textContent = 'Saved!';
    setTimeout(() => {
      el("settings-status").textContent = '';
      el("settings-overlay").hidden = true;
    }, 900);
  });

  // Close overlay on backdrop click
  el("settings-overlay").addEventListener("click", (e) => {
    if (e.target === el("settings-overlay")) el("settings-overlay").hidden = true;
  });

  // ── Socratic wiring ─────────────────────────────────────────────────────────
  el("socratic-load-btn").addEventListener("click", loadSocraticContent);

  el("socratic-send-btn").addEventListener("click", sendSocraticAnswer);

  el("socratic-user-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendSocraticAnswer();
    }
  });

  el("socratic-user-input").addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 120) + "px";
  });

  el("socratic-reset-btn").addEventListener("click", resetSocratic);
  el("socratic-new-session-btn").addEventListener("click", resetSocratic);

  el("socratic-copy-btn").addEventListener("click", copySocraticJSON);
  el("socratic-download-btn").addEventListener("click", downloadSocraticJSON);
  el("socratic-push-btn").addEventListener("click", pushToKgVecDb);

  // ── Flashcards wiring ────────────────────────────────────────────────────────
  el("tab-cards").addEventListener("click", () => switchTab("cards"));
  el("cards-generate-btn").addEventListener("click", runFlashcards);
  el("flashcard-wrap").addEventListener("click", flipCard);
  el("card-prev-btn").addEventListener("click", (e) => { e.stopPropagation(); prevCard(); });
  el("card-next-btn").addEventListener("click", (e) => { e.stopPropagation(); nextCard(); });
});
