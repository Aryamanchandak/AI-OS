import { build } from "esbuild";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

for (const file of ["manifest.json", "src/reader/reader.html"]) {
  await cp(resolve(root, file), resolve(dist, file.split("/").at(-1)));
}

await Promise.all([
  build({
    entryPoints: [resolve(root, "src/background.js")],
    bundle: true,
    outfile: resolve(dist, "background.js"),
    format: "esm",
    target: "chrome120",
    minify: false
  }),
  build({
    entryPoints: [resolve(root, "src/capture.js")],
    bundle: true,
    outfile: resolve(dist, "capture.js"),
    format: "iife",
    target: "chrome120",
    minify: false
  }),
  build({
    entryPoints: [resolve(root, "src/live-overlay.js")],
    bundle: true,
    outfile: resolve(dist, "live-overlay.js"),
    format: "iife",
    target: "chrome120",
    minify: false
  }),
  build({
    entryPoints: [resolve(root, "src/reader/reader.js")],
    bundle: true,
    outfile: resolve(dist, "reader.js"),
    format: "iife",
    target: "chrome120",
    minify: false
  })
]);

const manifest = JSON.parse(await readFile(resolve(dist, "manifest.json"), "utf8"));
manifest.version = JSON.parse(await readFile(resolve(root, "package.json"), "utf8")).version;
await writeFile(resolve(dist, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

console.log(`Built unpacked extension at ${dist}`);
