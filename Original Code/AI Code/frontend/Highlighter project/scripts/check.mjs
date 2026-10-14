import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const manifest = JSON.parse(await readFile(resolve("dist/manifest.json"), "utf8"));
const packageJson = JSON.parse(await readFile(resolve("package.json"), "utf8"));
const required = ["background.js", "capture.js", "live-overlay.js", "reader.html", "reader.js"];
const missing = [];

for (const file of required) {
  try {
    await readFile(resolve("dist", file));
  } catch {
    missing.push(file);
  }
}

if (manifest.manifest_version !== 3) throw new Error("Manifest must be v3");
if (manifest.version !== packageJson.version) throw new Error("Manifest and package versions must match");
if (missing.length) throw new Error(`Missing build outputs: ${missing.join(", ")}`);

const reader = await readFile(resolve("dist/reader.html"), "utf8");
if (/<script(?!\s+src=)[^>]*>/i.test(reader)) throw new Error("MV3 reader contains inline script");
if (/\sonclick=/i.test(reader)) throw new Error("MV3 reader contains inline event handlers");
if (!/^<!doctype html>/i.test(reader.trim())) throw new Error("Reader must declare an HTML doctype");
if (!/<html\s+lang=/i.test(reader)) throw new Error("Reader must declare its language");
if (!/role="dialog"\s+aria-modal="true"/i.test(reader)) throw new Error("Reader modal must expose dialog semantics");
if (!/role="status"\s+aria-live="polite"/i.test(reader)) throw new Error("Reader notifications must be announced");

console.log("Extension structure, version, CSP and accessibility checks passed");
