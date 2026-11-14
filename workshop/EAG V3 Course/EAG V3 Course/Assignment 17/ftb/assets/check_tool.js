#!/usr/bin/env node
/**
 * check_tool — does this generated calculator give the agreed answers?
 *
 *   node checks/check_tool.js index.html
 *
 * This file is the judge. It lives under checks/, which the engine refuses to
 * edit, next to checks/cases.json: the examples the user confirmed, with the
 * answers they expect.
 *
 * The page must keep its arithmetic in one block:
 *
 *   <script id="calc">function calculate(input) { ...; return {...}; }</script>
 *
 * That block is run here on its own, with no page, no network and no globals,
 * against every confirmed example. Exit 0 only if every example matches.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const file = process.argv[2];
if (!file) { console.error("usage: node checks/check_tool.js <file.html>"); process.exit(2); }
if (!fs.existsSync(file)) { console.error(`FAIL\n  ${file} does not exist yet`); process.exit(1); }

const html = fs.readFileSync(file, "utf8");
const suite = JSON.parse(fs.readFileSync(path.join(__dirname, "cases.json"), "utf8"));
const tolerance = typeof suite.tolerance === "number" ? suite.tolerance : 0.005;
const problems = [];

// ---- the page must be one self-contained file ------------------------------
for (const m of html.matchAll(/<(script|link|img|iframe)\b[^>]*\b(?:src|href)\s*=\s*["']?\s*(https?:)?\/\//gi))
  problems.push(`[standalone] <${m[1].toLowerCase()}> loads an external file; the tool must work offline`);
if (/\b(fetch|XMLHttpRequest|WebSocket|sendBeacon|EventSource)\b/.test(html))
  problems.push("[standalone] the page uses a network API; a calculator has no reason to");
if (!/<(input|select|textarea)\b/i.test(html))
  problems.push("[interface] the page has no input fields");

// ---- the arithmetic must be in exactly one <script id="calc"> --------------
const blocks = [...html.matchAll(/<script\b[^>]*\bid\s*=\s*["']calc["'][^>]*>([\s\S]*?)<\/script>/gi)];
let calculate = null;
if (blocks.length !== 1) {
  problems.push(`[contract] expected exactly one <script id="calc"> block, found ${blocks.length}`);
} else {
  try {
    const sandbox = vm.createContext(Object.create(null));
    vm.runInContext(blocks[0][1], sandbox, { timeout: 1000 });
    calculate = vm.runInContext("typeof calculate === 'function' ? calculate : null", sandbox);
    if (!calculate) problems.push("[contract] the calc block does not define function calculate(input)");
  } catch (e) {
    problems.push(`[contract] the calc block threw while loading: ${e.message}. ` +
                  "It must not touch document or window.");
  }
}

// ---- every confirmed example must come out right ---------------------------
function differences(expected, actual, where, out) {
  if (typeof expected === "number") {
    if (typeof actual !== "number" || !Number.isFinite(actual) || Math.abs(actual - expected) > tolerance)
      out.push(`${where}: expected ${expected}, got ${JSON.stringify(actual)}`);
  } else if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) { out.push(`${where}: expected a list, got ${JSON.stringify(actual)}`); return; }
    if (actual.length !== expected.length)
      out.push(`${where}: expected ${expected.length} rows, got ${actual.length}`);
    expected.forEach((item, i) => { if (i < actual.length) differences(item, actual[i], `${where}[${i}]`, out); });
  } else if (expected && typeof expected === "object") {
    if (!actual || typeof actual !== "object") { out.push(`${where}: expected an object, got ${JSON.stringify(actual)}`); return; }
    for (const key of Object.keys(expected)) differences(expected[key], actual[key], `${where}.${key}`, out);
  } else if (expected !== actual) {
    out.push(`${where}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

let passed = 0;
const cases = Array.isArray(suite.cases) ? suite.cases : [];
if (!cases.length) problems.push("[examples] there are no confirmed examples, so no answer was checked");
if (calculate) {
  for (const example of cases) {
    const found = [];
    try {
      const input = JSON.parse(JSON.stringify(example.input));
      const result = vm.runInNewContext("f(i)", { f: calculate, i: input }, { timeout: 2000 });
      differences(example.expected, JSON.parse(JSON.stringify(result === undefined ? null : result)), "result", found);
    } catch (e) {
      found.push(`calculate threw: ${e.message}`);
    }
    if (found.length) for (const line of found) problems.push(`[example: ${example.name}] ${line}`);
    else { passed++; console.log(`ok   ${example.name}`); }
  }
}

console.log(`examples passed: ${passed} of ${cases.length}`);
if (problems.length) {
  console.error("\nFAIL");
  for (const p of problems) console.error("  " + p);
  process.exit(1);
}
console.log("PASS");
process.exit(0);
