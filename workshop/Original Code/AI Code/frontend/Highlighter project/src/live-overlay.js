const BLOCK_SELECTOR = "h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,figcaption,tr";
const SKIP_SELECTOR = "script,style,noscript,textarea,input,select,option,button,[contenteditable='true'],[data-marginal-ui],rw-live-highlight";
const CTX = 40;

if (!globalThis.__marginalOverlayLoaded) {
  globalThis.__marginalOverlayLoaded = true;
  chrome.runtime.sendMessage(
    { type: "MARGINAL_GET_OVERLAY", url: location.href },
    response => {
      if (chrome.runtime.lastError || !response?.ok || !response.result) return;
      applyOverlay(response.result);
    }
  );
}

function buildIndex() {
  const entries = [];
  const blocks = Array.from(document.body.querySelectorAll(BLOCK_SELECTOR))
    .filter(element => !element.matches(SKIP_SELECTOR))
    .filter(element => !element.querySelector(BLOCK_SELECTOR));
  let text = "";
  let position = 0;

  for (const block of blocks) {
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue || node.parentElement?.closest(SKIP_SELECTOR)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    let node;
    while ((node = walker.nextNode())) {
      const normalized = node.nodeValue.replace(/\u00a0/g, " ");
      if (!normalized.length) continue;
      entries.push({
        node,
        start: position,
        end: position + normalized.length
      });
      text += normalized;
      position += normalized.length;
    }
    text += "\n";
    position += 1;
  }

  return { entries, text };
}

function allIndices(haystack, needle) {
  const matches = [];
  let index = haystack.indexOf(needle);
  while (index !== -1 && matches.length < 200) {
    matches.push(index);
    index = haystack.indexOf(needle, index + 1);
  }
  return matches;
}

function contextScore(text, start, end, highlight) {
  const prefix = text.slice(Math.max(0, start - CTX), start);
  const suffix = text.slice(end, end + CTX);
  const expectedPrefix = highlight.quote.prefix || "";
  const expectedSuffix = highlight.quote.suffix || "";
  let prefixHit = 0;
  let suffixHit = 0;

  while (
    prefixHit < Math.min(prefix.length, expectedPrefix.length) &&
    prefix[prefix.length - 1 - prefixHit] === expectedPrefix[expectedPrefix.length - 1 - prefixHit]
  ) prefixHit++;
  while (
    suffixHit < Math.min(suffix.length, expectedSuffix.length) &&
    suffix[suffixHit] === expectedSuffix[suffixHit]
  ) suffixHit++;

  const prefixScore = expectedPrefix ? prefixHit / expectedPrefix.length : 0.5;
  const suffixScore = expectedSuffix ? suffixHit / expectedSuffix.length : 0.5;
  return 0.55 + 0.22 * prefixScore + 0.22 * suffixScore;
}

function bigrams(value) {
  const result = new Map();
  for (let index = 0; index < value.length - 1; index++) {
    const gram = value.slice(index, index + 2);
    result.set(gram, (result.get(gram) || 0) + 1);
  }
  return result;
}

function dice(left, right) {
  if (!left.size || !right.size) return 0;
  let intersection = 0;
  let leftTotal = 0;
  let rightTotal = 0;
  for (const [gram, count] of left) {
    leftTotal += count;
    intersection += Math.min(count, right.get(gram) || 0);
  }
  for (const count of right.values()) rightTotal += count;
  return (2 * intersection) / (leftTotal + rightTotal);
}

function resolveHighlight(text, highlight) {
  const exact = highlight.quote.exact;
  const matches = allIndices(text, exact);
  if (matches.length) {
    const ranked = matches
      .map(start => ({
        start,
        end: start + exact.length,
        score: contextScore(text, start, start + exact.length, highlight),
        strategy: "quote"
      }))
      .sort((left, right) => right.score - left.score);
    if (ranked.length === 1 || ranked[0].score - ranked[1].score >= 0.05) return ranked[0];
  }

  if (exact.length < 12 || text.length > 400000) return null;
  const target = bigrams(exact);
  const length = exact.length;
  const step = Math.max(1, Math.floor(length / 6));
  let best = null;
  let second = 0;

  for (let start = 0; start + length <= text.length; start += step) {
    const score = dice(bigrams(text.slice(start, start + length)), target);
    if (!best || score > best.score) {
      second = best?.score || 0;
      best = { start, end: start + length, score, strategy: "fuzzy" };
    } else if (score > second) {
      second = score;
    }
  }

  return best && best.score >= 0.82 && best.score - second >= 0.04 ? best : null;
}

function partsFor(entries, start, end) {
  return entries
    .filter(entry => entry.end > start && entry.start < end)
    .map(entry => ({
      node: entry.node,
      start: Math.max(0, start - entry.start),
      end: Math.min(entry.end - entry.start, end - entry.start)
    }))
    .filter(part => part.end > part.start);
}

function paint(entries, resolution, highlight, docId) {
  const parts = partsFor(entries, resolution.start, resolution.end);
  let painted = 0;
  for (let index = parts.length - 1; index >= 0; index--) {
    const part = parts[index];
    if (!part.node.isConnected) continue;
    const range = document.createRange();
    range.setStart(part.node, part.start);
    range.setEnd(part.node, part.end);
    const mark = document.createElement("rw-live-highlight");
    mark.dataset.highlightId = highlight.id;
    mark.dataset.marginalDocId = docId;
    if (index === 0) {
      mark.tabIndex = 0;
      mark.setAttribute("role", "link");
      mark.setAttribute("aria-label", `Open in Marginal: ${highlight.quote.exact.slice(0, 120)}`);
    }
    mark.title = [highlight.note, ...(highlight.tags || []).map(tag => `#${tag}`)]
      .filter(Boolean)
      .join(" · ");
    try {
      range.surroundContents(mark);
      painted++;
    } catch {
      // A refused fragment is safer than mutating an unexpected host structure.
    }
  }
  return painted === parts.length && painted > 0;
}

function injectStyles() {
  if (document.getElementById("marginal-live-style")) return;
  const style = document.createElement("style");
  style.id = "marginal-live-style";
  style.dataset.marginalUi = "overlay-style";
  style.textContent = `
    rw-live-highlight{
      background:rgba(255,213,0,.25)!important;
      box-shadow:inset 0 -2px 0 #E5B900!important;
      border-radius:1px!important;
      color:inherit!important;
      cursor:pointer!important;
    }
    rw-live-highlight:hover{background:rgba(255,213,0,.42)!important}
    rw-live-highlight:focus-visible{outline:2px solid #2C6E9B!important;outline-offset:2px!important}
  `;
  document.documentElement.append(style);
}

function showStatus(docId, placed, refused) {
  document.querySelector("[data-marginal-ui='overlay-status']")?.remove();
  const host = document.createElement("div");
  host.dataset.marginalUi = "overlay-status";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host{all:initial;position:fixed;right:18px;bottom:18px;z-index:2147483646;font-family:"Avenir Next","Segoe UI",sans-serif}
      .pill{display:flex;align-items:center;gap:9px;background:#171815;color:#F8F5EC;border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:8px 9px 8px 13px;box-shadow:0 10px 35px rgba(0,0,0,.24);font-size:12px}
      b{color:#F2CB43;font-weight:700}
      .warn{color:#E8A06D}
      button{appearance:none;border:0;background:rgba(255,255,255,.1);color:inherit;border-radius:999px;padding:5px 9px;cursor:pointer;font:inherit}
      button:hover{background:rgba(255,255,255,.18)}
      button:focus-visible{outline:2px solid #F2CB43;outline-offset:2px}
      .close{padding:3px 7px;color:#B9B5AB}
      @media(max-width:520px){:host{right:10px;bottom:10px;left:10px}.pill{justify-content:center;flex-wrap:wrap;border-radius:14px}}
      @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
    </style>
    <div class="pill" role="region" aria-label="Marginal overlay status">
      <b>Marginal</b>
      <span>${placed} placed${refused ? ` · <span class="warn">${refused} refused</span>` : ""}</span>
      <button data-open>Reader</button>
      <button class="close" data-close aria-label="Dismiss">×</button>
    </div>
  `;
  shadow.querySelector("[data-open]").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "MARGINAL_OPEN_READER", docId });
  });
  shadow.querySelector("[data-close]").addEventListener("click", () => host.remove());
  document.documentElement.append(host);
}

function applyOverlay(result) {
  const { entries, text } = buildIndex();
  if (!entries.length || !text) {
    const refused = result.highlights.length;
    showStatus(result.document.id, 0, refused);
    chrome.runtime.sendMessage({ type: "MARGINAL_OVERLAY_RESULT", placed: 0, refused });
    return;
  }
  const resolved = [];
  let refused = 0;

  for (const highlight of result.highlights) {
    const resolution = resolveHighlight(text, highlight);
    if (resolution) resolved.push({ highlight, resolution });
    else refused++;
  }

  injectStyles();
  let placed = 0;
  resolved
    .sort((left, right) => right.resolution.start - left.resolution.start)
    .forEach(item => {
      if (paint(entries, item.resolution, item.highlight, result.document.id)) placed++;
      else refused++;
    });
  if (placed || refused) showStatus(result.document.id, placed, refused);
  chrome.runtime.sendMessage({
    type: "MARGINAL_OVERLAY_RESULT",
    placed,
    refused
  });

  document.addEventListener("click", event => {
    const mark = event.target.closest?.("rw-live-highlight");
    if (!mark) return;
    chrome.runtime.sendMessage({
      type: "MARGINAL_OPEN_READER",
      docId: mark.dataset.marginalDocId
    });
  });
  document.addEventListener("keydown", event => {
    const mark = event.target.closest?.("rw-live-highlight");
    if (!mark || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    chrome.runtime.sendMessage({
      type: "MARGINAL_OPEN_READER",
      docId: mark.dataset.marginalDocId
    });
  });
}
