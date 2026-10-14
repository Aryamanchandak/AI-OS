import { Readability } from "@mozilla/readability";
import DOMPurify from "dompurify";

const ALLOWED_TAGS = [
  "p", "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "pre", "code",
  "em", "i", "strong", "b", "u", "s", "sup", "sub", "br", "hr", "figure",
  "figcaption", "a", "img", "table", "thead", "tbody", "tr", "th", "td"
];
const ALLOWED_ATTR = ["href", "src", "alt", "title"];
const MIN_ARTICLE_LENGTH = 400;

if (!globalThis.__marginalCaptureActive) {
  globalThis.__marginalCaptureActive = true;
  capture().finally(() => {
    globalThis.__marginalCaptureActive = false;
  });
}

async function capture() {
  dismissExistingPanel();
  const parsed = parseArticle();
  const html = parsed?.content ? sanitizeArticle(parsed.content) : "";
  const textLength = textOf(html).length;

  if (parsed && textLength >= MIN_ARTICLE_LENGTH) {
    await persist({
      title: parsed.title || document.title,
      byline: parsed.byline || "",
      excerpt: parsed.excerpt || "",
      siteName: parsed.siteName || location.hostname,
      url: location.href,
      html
    });
    return;
  }

  await chooseFallback({
    parsed,
    extractedLength: textLength,
    extractedHtml: html
  });
}

function parseArticle() {
  try {
    const clone = document.cloneNode(true);
    clone.querySelectorAll("[data-marginal-ui], rw-live-highlight").forEach(node => node.remove());
    return new Readability(clone, {
      charThreshold: 200,
      keepClasses: false
    }).parse();
  } catch (error) {
    console.warn("Marginal: Readability could not parse this page", error);
    return null;
  }
}

function sanitizeArticle(rawHtml) {
  const template = document.createElement("template");
  template.innerHTML = rawHtml;

  template.content.querySelectorAll("a[href], img[src]").forEach(element => {
    const attr = element.localName === "a" ? "href" : "src";
    const value = element.getAttribute(attr);
    try {
      const absolute = new URL(value, document.baseURI);
      if (!["http:", "https:"].includes(absolute.protocol)) element.removeAttribute(attr);
      else element.setAttribute(attr, absolute.href);
    } catch {
      element.removeAttribute(attr);
    }
  });

  return DOMPurify.sanitize(template.innerHTML, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "svg", "canvas", "form"],
    FORBID_ATTR: ["srcset", "style", "class", "id"],
    RETURN_TRUSTED_TYPE: false
  });
}

function textOf(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  return (template.content.textContent || "").replace(/\s+/g, " ").trim();
}

function selectedHtml() {
  const selection = getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return "";
  const container = document.createElement("div");
  for (let index = 0; index < selection.rangeCount; index++) {
    container.append(selection.getRangeAt(index).cloneContents());
  }
  return sanitizeArticle(container.innerHTML);
}

function fullBodyHtml() {
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll(
    "script,style,noscript,iframe,object,embed,svg,canvas,form,nav,footer,[data-marginal-ui],rw-live-highlight"
  ).forEach(node => node.remove());
  return sanitizeArticle(clone.innerHTML);
}

function chooseFallback({ parsed, extractedLength, extractedHtml }) {
  return new Promise(resolve => {
    const selected = selectedHtml();
    const body = fullBodyHtml();
    const host = document.createElement("div");
    host.dataset.marginalUi = "capture";
    const shadow = host.attachShadow({ mode: "open" });
    document.documentElement.append(host);

    shadow.innerHTML = `
      <style>
        :host{all:initial;position:fixed;inset:0;z-index:2147483647;font-family:"Avenir Next","Segoe UI",sans-serif;color:#171815}
        .shade{position:absolute;inset:0;background:rgba(13,14,12,.46);backdrop-filter:blur(2px)}
        .panel{position:absolute;right:24px;top:24px;width:min(390px,calc(100vw - 32px));background:#F7F5EE;border:1px solid #D8D2C3;border-radius:14px;box-shadow:0 24px 70px rgba(0,0,0,.28);padding:22px}
        .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#847D6D;margin-bottom:9px}
        h2{font:600 25px/1.12 Georgia,serif;letter-spacing:-.02em;margin:0 0 10px}
        p{font:14px/1.55 "Avenir Next","Segoe UI",sans-serif;color:#625D52;margin:0 0 18px}
        .count{font-family:ui-monospace,monospace;color:#8B6711}
        .actions{display:grid;gap:8px}
        button{appearance:none;border:1px solid #D8D2C3;border-radius:9px;background:#fffdf8;color:#171815;text-align:left;padding:12px 13px;cursor:pointer;font:600 13px/1.25 "Avenir Next","Segoe UI",sans-serif;transition:transform .15s ease,border-color .15s ease}
        button:hover{transform:translateY(-1px);border-color:#9F8C55}
        button:focus-visible{outline:3px solid rgba(200,155,31,.35);outline-offset:2px}
        button[disabled]{opacity:.42;cursor:not-allowed;transform:none}
        button.primary{background:#F2CB43;border-color:#D4A90C}
        small{display:block;font-weight:400;color:#777064;margin-top:3px}
        .cancel{margin-top:10px;border:0;background:transparent;text-align:center;color:#777064;padding:8px}
        @media(max-width:500px){.panel{right:16px;top:16px}}
      </style>
      <div class="shade"></div>
      <section class="panel" role="dialog" aria-modal="true" aria-labelledby="marginal-fallback-title" aria-describedby="marginal-fallback-description">
        <div class="eyebrow">Marginal capture</div>
        <h2 id="marginal-fallback-title">This page did not resolve cleanly.</h2>
        <p id="marginal-fallback-description">Readability found <span class="count">${extractedLength.toLocaleString()} characters</span>. Choose an explicit fallback so a broken article is never saved silently.</p>
        <div class="actions">
          <button class="primary" data-choice="selection" ${textOf(selected).length ? "" : "disabled"}>
            Save selected passage
            <small>${textOf(selected).length ? `${textOf(selected).length.toLocaleString()} selected characters` : "Select text on the page first"}</small>
          </button>
          <button data-choice="body">
            Save cleaned page body
            <small>${textOf(body).length.toLocaleString()} characters after sanitizing</small>
          </button>
          ${extractedHtml ? `<button data-choice="readability">Save Readability result anyway<small>${extractedLength.toLocaleString()} extracted characters</small></button>` : ""}
        </div>
        <button class="cancel" data-choice="cancel">Cancel</button>
      </section>
    `;

    const finish = () => {
      host.remove();
      resolve();
    };

    shadow.addEventListener("click", async event => {
      const button = event.target.closest("[data-choice]");
      if (!button || button.disabled) return;
      const choice = button.dataset.choice;
      if (choice === "cancel") return finish();

      const choiceHtml =
        choice === "selection" ? selected :
        choice === "readability" ? extractedHtml :
        body;
      shadow.querySelectorAll("button").forEach(item => {
        item.disabled = true;
      });
      button.querySelector("small").textContent = "Saving…";

      try {
        await persist({
          title: parsed?.title || document.title || "Untitled",
          byline: parsed?.byline || "",
          excerpt: parsed?.excerpt || "",
          siteName: parsed?.siteName || location.hostname,
          url: location.href,
          html: choiceHtml
        });
        finish();
      } catch {
        shadow.querySelectorAll("button").forEach(item => {
          item.disabled = item.dataset.choice === "selection" && !textOf(selected).length;
        });
        button.querySelector("small").textContent = "Save failed — try again";
      }
    });

    shadow.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        finish();
        return;
      }
      if (event.key !== "Tab") return;
      const buttons = Array.from(shadow.querySelectorAll("button:not([disabled])"));
      if (!buttons.length) return;
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && shadow.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && shadow.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    (shadow.querySelector(".primary:not([disabled])") || shadow.querySelector("[data-choice='cancel']")).focus();
  });
}

function persist(payload) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      { type: "MARGINAL_SAVE_CAPTURE", payload },
      response => {
        const error = chrome.runtime.lastError;
        if (error || !response?.ok) {
          const message = error?.message || response?.error || "Could not save this page";
          showToast(message, true);
          reject(new Error(message));
          return;
        }
        showToast(
          response.warning || (response.duplicate ? "Already in Marginal — opening it" : "Saved to Marginal"),
          Boolean(response.warning)
        );
        resolve(response);
      }
    );
  });
}

function showToast(message, isError = false) {
  document.querySelector("[data-marginal-ui='toast']")?.remove();
  const toast = document.createElement("div");
  toast.dataset.marginalUi = "toast";
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  Object.assign(toast.style, {
    position: "fixed",
    right: "22px",
    bottom: "22px",
    zIndex: "2147483647",
    padding: "11px 16px",
    borderRadius: "999px",
    background: isError ? "#8E3E1D" : "#171815",
    color: "#F8F5EC",
    font: "600 13px/1.2 Avenir Next, Segoe UI, sans-serif",
    boxShadow: "0 12px 35px rgba(0,0,0,.24)"
  });
  toast.textContent = message;
  document.documentElement.append(toast);
  setTimeout(() => toast.remove(), 2600);
}

function dismissExistingPanel() {
  document.querySelector("[data-marginal-ui='capture']")?.remove();
}
