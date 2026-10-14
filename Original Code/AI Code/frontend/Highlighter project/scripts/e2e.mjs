import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import puppeteer from "puppeteer-core";

const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const extensionPath = resolve("dist");
const profilePath = await mkdtemp(join(tmpdir(), "marginal-e2e-"));
let ambiguous = false;

const sentence = "A missing overlay is recoverable.";
const surround = "A deliberately stable prefix gives this passage enough context. ";
const suffix = " A deliberately stable suffix makes ambiguity measurable.";
const hostileSentence = "Nested emphasis and linked text stay exact across 中文, العربية, and 🙂 emoji.";
const hostileFixture = await readFile(resolve("tests/fixtures/hostile-article.html"), "utf8");

const server = createServer((request, response) => {
  if (request.url !== "/article") {
    response.writeHead(404);
    response.end("Not found");
    return;
  }
  const passage = `<p>${surround}<strong>${sentence}</strong>${suffix}</p>`;
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(
    hostileFixture
      .replace("{{PASSAGE}}", passage)
      .replace("{{AMBIGUOUS_PASSAGE}}", ambiguous ? passage : "")
  );
});

await new Promise(resolveReady => server.listen(0, "127.0.0.1", resolveReady));
const { port } = server.address();
const articleUrl = `http://127.0.0.1:${port}/article`;

let browser;
try {
  browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    userDataDir: profilePath,
    enableExtensions: true,
    args: [
      "--no-first-run",
      "--no-default-browser-check"
    ]
  });

  const extensionId = await browser.installExtension(extensionPath);
  const workerTarget = await browser.waitForTarget(
    target => target.type() === "service_worker" && target.url() === `chrome-extension://${extensionId}/background.js`,
    { timeout: 15000 }
  );
  const worker = await workerTarget.worker();

  const reader = await browser.newPage();
  await reader.goto(`chrome-extension://${extensionId}/reader.html`, { waitUntil: "networkidle0" });
  await reader.waitForSelector("#doc h1");
  const seedTitle = await reader.$eval("#doc h1", node => node.textContent);
  assert(seedTitle === "What a highlight actually is", "reader boots with the seed document");

  const article = await browser.newPage();
  await article.goto(articleUrl, { waitUntil: "networkidle0" });
  await article.bringToFront();
  await worker.evaluate(async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["capture.js"]
    });
  });

  const capturedTarget = await browser.waitForTarget(
    target => target.type() === "page" && /reader\.html\?doc=/.test(target.url()),
    { timeout: 15000 }
  );
  const captured = await capturedTarget.page();
  await captured.waitForSelector("#doc h1");
  assert(
    await captured.$eval("#doc h1", node => node.textContent) === "A Durable Test Article",
    "Readability capture opens the frozen article"
  );
  assert(
    await captured.$eval("#doc", node => !node.textContent.includes("Site navigation")),
    "Readability excludes surrounding navigation"
  );

  await captured.evaluate(exact => {
    const walker = document.createTreeWalker(document.querySelector("#doc"), NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const start = node.nodeValue.indexOf(exact);
      if (start === -1) continue;
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, start + exact.length);
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
      return;
    }
    throw new Error("Test sentence was not found in the captured reader");
  }, sentence);
  await captured.waitForFunction(() => document.querySelectorAll("rw-highlight").length > 0);

  await article.reload({ waitUntil: "networkidle0" });
  await article.waitForFunction(() => document.querySelectorAll("rw-live-highlight").length > 0);
  assert(
    await article.$eval("rw-live-highlight", (node, exact) => node.textContent === exact, sentence),
    "live-page overlay reattaches the exact quote"
  );

  ambiguous = true;
  await article.reload({ waitUntil: "networkidle0" });
  await article.waitForFunction(() => document.querySelector("[data-marginal-ui='overlay-status']"));
  assert(
    await article.$$eval("rw-live-highlight", nodes => nodes.length) === 0,
    "ambiguous live-page matches are refused"
  );
  const refusedStatus = await article.$eval(
    "[data-marginal-ui='overlay-status']",
    host => host.shadowRoot.textContent
  );
  assert(/1 refused/.test(refusedStatus), "overlay reports the refused highlight");

  await captured.bringToFront();
  const frozenText = await captured.$eval("#doc", node => node.textContent);
  const scrollBeforeHighlight = await captured.evaluate(() => scrollY);
  await selectExact(captured, hostileSentence);
  await captured.waitForFunction(() => document.querySelectorAll("rw-highlight").length >= 2);
  assert(
    Math.abs(await captured.evaluate(() => scrollY) - scrollBeforeHighlight) <= 1,
    "creating a highlight does not move the reading position"
  );
  assert(
    await captured.$eval("#doc", (node, expected) => node.textContent === expected, frozenText),
    "painting across nested inline, CJK, RTL and emoji preserves exact visible text"
  );
  await captured.keyboard.press("z");
  await captured.waitForFunction(() => document.querySelectorAll("rw-highlight").length === 1);
  assert(
    await captured.$eval("#doc", (node, expected) => node.textContent === expected, frozenText),
    "undo removes wrappers without changing the frozen text"
  );
  await selectExact(captured, hostileSentence);
  await captured.waitForFunction(() => document.querySelectorAll("rw-highlight").length >= 2);
  await captured.reload({ waitUntil: "networkidle0" });
  await captured.waitForFunction(() => document.querySelectorAll("rw-highlight").length >= 2);
  assert(
    await captured.$eval("#doc", (node, expected) => node.textContent === expected, frozenText),
    "hostile highlights persist across reload with canonical text unchanged"
  );
  assert(
    await hasPaintedQuote(captured, sentence) && await hasPaintedQuote(captured, hostileSentence),
    "reload returns each highlight to the same exact passage"
  );
  assert(
    await captured.$$eval("rw-highlight[tabindex='0'][role='button']", nodes => nodes.length) >= 2,
    "persisted highlights are keyboard operable"
  );

  await captured.evaluate(value => {
    const mark = Array.from(document.querySelectorAll("rw-highlight"))
      .find(node => node.textContent === value);
    if (!mark) throw new Error("Resizable test highlight was not found");
    mark.click();
    mark.querySelector(".grip.e").focus();
  }, sentence);
  await captured.keyboard.down("Shift");
  await captured.keyboard.press("ArrowRight");
  await captured.keyboard.up("Shift");
  await captured.waitForFunction(
    exact => {
      const nodes = Array.from(document.querySelectorAll("rw-highlight"));
      const ids = new Set(nodes.map(node => node.dataset.highlightId));
      return Array.from(ids).some(id => {
        const text = nodes.filter(node => node.dataset.highlightId === id)
          .map(node => node.textContent).join("");
        return text.startsWith(exact) && text.length > exact.length;
      });
    },
    {},
    sentence
  );
  assert(
    await captured.$$eval("rw-highlight", (nodes, exact) => {
      const ids = new Set(nodes.map(node => node.dataset.highlightId));
      return Array.from(ids).some(id => {
        const text = nodes.filter(node => node.dataset.highlightId === id)
          .map(node => node.textContent).join("");
        return text.startsWith(exact) && text.length > exact.length;
      });
    },
    sentence),
    "keyboard resize moves only the chosen boundary"
  );
  await captured.keyboard.press("z");
  await captured.waitForFunction(
    exact => Array.from(document.querySelectorAll("rw-highlight")).some(node => node.textContent === exact),
    {},
    sentence
  );

  await captured.click("#btnJson");
  await captured.waitForSelector("#exportValue");
  const documentExport = JSON.parse(await captured.$eval("#exportValue", node => node.value));
  assert(
    documentExport.document.url === articleUrl &&
      documentExport.highlights.some(highlight => highlight.quote.exact === hostileSentence),
    "portable document export includes the exact quote and source"
  );
  await captured.click("[data-modal-close]");

  await captured.click("#btnLibrary");
  await captured.waitForSelector("#libraryQuery");
  await captured.waitForFunction(() =>
    !document.querySelector("#libraryList")?.textContent.includes("Loading local library")
  );
  await captured.$eval("#libraryQuery", (node, value) => {
    node.value = value;
    node.dispatchEvent(new Event("input", { bubbles: true }));
  }, sentence);
  await captured.waitForFunction(
    title => {
      const items = Array.from(document.querySelectorAll(".library-item"));
      return items.some(item => item.textContent.includes(title));
    },
    {},
    "A Durable Test Article"
  );
  assert(true, "library search finds words inside exact quotes");

  await captured.$eval("#libraryBackup", node => node.click());
  await captured.waitForSelector("#backupValue");
  const backupValue = await captured.$eval("#backupValue", node => node.value);
  const backup = JSON.parse(backupValue);
  const backedUpArticle = backup.documents.find(record => record.document.title === "A Durable Test Article");
  assert(
    backup.format === "marginal-backup" && backup.version === 1,
    "whole-library backup has a versioned recovery format"
  );
  assert(
    backedUpArticle?.highlights.length === 2 &&
      backedUpArticle.highlights.some(highlight => highlight.quote.exact === hostileSentence),
    "whole-library backup includes frozen content and every highlight anchor"
  );
  await captured.click("[data-modal-close]");
  await captured.click("#btnLibrary");
  await captured.waitForSelector("[data-delete-doc]");
  await captured.click("[data-delete-doc]");
  await captured.waitForSelector("#confirmDelete");
  await captured.click("#confirmDelete");
  await captured.waitForFunction(
    title => !Array.from(document.querySelectorAll("#docpick option")).some(option => option.textContent === title),
    {},
    "A Durable Test Article"
  );
  assert(true, "library deletion removes the document and its highlights");

  await captured.waitForSelector("#libraryRestore");
  await captured.click("#libraryRestore");
  await captured.waitForSelector("#restoreValue");
  await captured.$eval("#restoreValue", node => {
    node.value = '{"format":"marginal-backup","version":999,"documents":[]}';
  });
  await captured.click("#restoreLibrary");
  await captured.waitForFunction(() => {
    const button = document.querySelector("#restoreLibrary");
    return button && !button.disabled && document.querySelector("#veil").classList.contains("show");
  });
  assert(
    !await captured.$$eval("#docpick option", (options, title) =>
      options.some(option => option.textContent === title),
    "A Durable Test Article"),
    "invalid backups are refused before changing the library"
  );
  await captured.$eval("#restoreValue", (node, value) => {
    node.value = value;
    node.dispatchEvent(new Event("input", { bubbles: true }));
  }, backupValue);
  await captured.click("#restoreLibrary");
  await captured.waitForFunction(() => !document.querySelector("#veil").classList.contains("show"));
  await chooseDocument(captured, "A Durable Test Article");
  await captured.waitForFunction(
    title => document.querySelector("#doc h1")?.textContent === title &&
      document.querySelectorAll("rw-highlight").length >= 2,
    {},
    "A Durable Test Article"
  );
  assert(
    await captured.$eval("#doc", (node, expected) => node.textContent === expected, frozenText),
    "validated restore recovers the frozen document and hostile highlights"
  );

  console.log("M7 release-readiness browser flow passed");
} finally {
  await browser?.close();
  server.close();
  await rm(profilePath, { recursive: true, force: true });
}

function assert(condition, message) {
  if (!condition) throw new Error(`Assertion failed: ${message}`);
  console.log(`✓ ${message}`);
}

async function selectExact(page, exact) {
  await page.evaluate(value => {
    const root = document.querySelector("#doc");
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return node.parentElement?.closest(".glyph,.marginnote,.grip")
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = [];
    let text = "";
    let node;
    while ((node = walker.nextNode())) {
      nodes.push({ node, start: text.length, end: text.length + node.nodeValue.length });
      text += node.nodeValue;
    }
    const start = text.indexOf(value);
    if (start === -1) throw new Error(`Test text was not found: ${value}`);
    const end = start + value.length;
    const first = nodes.find(entry => entry.end > start);
    const last = [...nodes].reverse().find(entry => entry.start < end);
    const range = document.createRange();
    range.setStart(first.node, start - first.start);
    range.setEnd(last.node, end - last.start);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  }, exact);
}

async function chooseDocument(page, title) {
  await page.evaluate(value => {
    const select = document.querySelector("#docpick");
    const option = Array.from(select.options).find(item => item.textContent === value);
    if (!option) throw new Error(`Document was not restored: ${value}`);
    select.value = option.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }, title);
}

async function hasPaintedQuote(page, exact) {
  return page.$$eval("rw-highlight", (nodes, value) => {
    const ids = Array.from(new Set(nodes.map(node => node.dataset.highlightId)));
    return ids.some(id => {
      const parts = nodes.filter(node => node.dataset.highlightId === id);
      return parts.map(node => {
        const copy = node.cloneNode(true);
        copy.querySelectorAll(".grip,.glyph").forEach(item => item.remove());
        return copy.textContent;
      }).join("") === value;
    });
  }, exact);
}
