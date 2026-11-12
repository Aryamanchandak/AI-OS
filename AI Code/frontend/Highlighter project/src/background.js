import { getValue, setValues } from "./db.js";

const compactUrl = value => {
  try {
    const url = new URL(value);
    url.hash = "";
    return url.href;
  } catch {
    return value || "";
  }
};

const hash = value => {
  let result = 5381;
  for (let index = 0; index < value.length; index++) {
    result = ((result << 5) + result + value.charCodeAt(index)) | 0;
  }
  return (result >>> 0).toString(36);
};

const uid = () =>
  `${Date.now().toString(36)}${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}`;

function validateCapture(payload) {
  if (!payload || typeof payload !== "object") throw new Error("Capture payload is missing");
  if (typeof payload.html !== "string" || !payload.html.trim()) throw new Error("The captured article is empty");
  if (payload.html.length > 10_000_000) throw new Error("The captured article is larger than 10 MB");
  let url;
  try {
    url = new URL(payload.url);
  } catch {
    throw new Error("The source URL is invalid");
  }
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("Marginal only captures HTTP pages");
}

async function saveCapture(payload) {
  validateCapture(payload);
  const docs = (await getValue("docs:index")) || [];
  const normalizedUrl = compactUrl(payload.url);
  const revisionHash = hash(payload.html);
  const duplicate = docs.find(
    item => compactUrl(item.url) === normalizedUrl && item.revisionHash === revisionHash
  );

  if (duplicate) {
    return { id: duplicate.id, duplicate: true };
  }

  const documentRecord = {
    id: uid(),
    title: payload.title?.trim() || "Untitled",
    byline: payload.byline?.trim() || "",
    excerpt: payload.excerpt?.trim() || "",
    siteName: payload.siteName?.trim() || "",
    url: normalizedUrl,
    capturedAt: new Date().toISOString(),
    html: payload.html,
    revisionHash
  };
  const summary = {
    id: documentRecord.id,
    title: documentRecord.title,
    url: documentRecord.url,
    capturedAt: documentRecord.capturedAt,
    revisionHash,
    excerpt: documentRecord.excerpt,
    siteName: documentRecord.siteName
  };

  await setValues([
    [`doc:${documentRecord.id}`, documentRecord],
    [`hls:${documentRecord.id}`, []],
    ["docs:index", [...docs, summary]]
  ]);

  return { id: documentRecord.id, duplicate: false };
}

let captureQueue = Promise.resolve();
function queueCapture(payload) {
  const operation = captureQueue.then(() => saveCapture(payload));
  captureQueue = operation.catch(() => {});
  return operation;
}

async function overlayForUrl(url) {
  const docs = (await getValue("docs:index")) || [];
  const matching = docs
    .filter(item => compactUrl(item.url) === compactUrl(url))
    .sort((left, right) => right.capturedAt.localeCompare(left.capturedAt));
  const summary = matching[0];
  if (!summary) return null;

  const highlights = (await getValue(`hls:${summary.id}`)) || [];
  const attached = highlights.filter(item => item.status === "attached" && item.quote?.exact);
  if (!attached.length) return null;

  return {
    document: summary,
    highlights: attached.map(item => ({
      id: item.id,
      quote: item.quote,
      position: item.position,
      note: item.note || "",
      tags: item.tags || []
    }))
  };
}

chrome.action.onClicked.addListener(async tab => {
  if (!tab.id || !/^https?:/i.test(tab.url || "")) {
    if (tab.id) {
      await chrome.action.setBadgeText({ tabId: tab.id, text: "×" });
      await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color: "#B4531B" });
    }
    return;
  }

  await chrome.action.setBadgeText({ tabId: tab.id, text: "…" });
  await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color: "#2C6E9B" });
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["capture.js"]
    });
  } catch (error) {
    console.error("Marginal capture injection failed", error);
    await chrome.action.setBadgeText({ tabId: tab.id, text: "×" });
    await chrome.action.setBadgeBackgroundColor({ tabId: tab.id, color: "#B4531B" });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "MARGINAL_SAVE_CAPTURE") {
    queueCapture(message.payload)
      .then(async result => {
        try {
          if (sender.tab?.id) {
            await chrome.action.setBadgeText({ tabId: sender.tab.id, text: "✓" });
            await chrome.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: "#4D7C4A" });
            setTimeout(() => chrome.action.setBadgeText({ tabId: sender.tab.id, text: "" }).catch(() => {}), 1800);
          }
        } catch (error) {
          console.warn("Marginal could not update its action badge", error);
        }
        let warning = "";
        try {
          await chrome.tabs.create({
            url: chrome.runtime.getURL(`reader.html?doc=${encodeURIComponent(result.id)}`)
          });
        } catch (error) {
          warning = "Saved, but the reader tab could not be opened";
          console.warn("Marginal could not open the saved document", error);
        }
        sendResponse({ ok: true, ...result, warning });
      })
      .catch(error => {
        console.error("Marginal capture failed", error);
        sendResponse({ ok: false, error: error.message });
      });
    return true;
  }

  if (message?.type === "MARGINAL_GET_OVERLAY") {
    overlayForUrl(message.url)
      .then(result => sendResponse({ ok: true, result }))
      .catch(error => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "MARGINAL_OVERLAY_RESULT") {
    if (sender.tab?.id) {
      const refused = Number(message.refused) || 0;
      const placed = Number(message.placed) || 0;
      chrome.action.setBadgeText({
        tabId: sender.tab.id,
        text: refused ? "!" : placed ? String(placed) : ""
      });
      chrome.action.setBadgeBackgroundColor({
        tabId: sender.tab.id,
        color: refused ? "#B4531B" : "#4D7C4A"
      });
    }
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === "MARGINAL_OPEN_READER") {
    chrome.tabs.create({
      url: chrome.runtime.getURL(`reader.html?doc=${encodeURIComponent(message.docId || "")}`)
    });
    sendResponse({ ok: true });
    return false;
  }

  return false;
});
