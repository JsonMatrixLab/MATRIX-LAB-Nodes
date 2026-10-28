import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("FLAT entrypoint targets only MATRIX_SCAILWindow", () => {
  const entry = fs.readFileSync(path.join(root, "web/flat_entry.0f3c3ed2942d4b44.js"), "utf8");
  assert.match(entry, /const ids = \["MATRIX_SCAILWindow"\]/);
  assert.doesNotMatch(entry, /MATRIX_Wan3|MATRIX_H3Resolution|MATRIX_Resolution/);
});

test("shared renderer detector follows LiteGraph.vueNodesMode", async () => {
  const renderer = await import(pathToFileURL(path.join(root, "web/renderer.2c53217d2a7c4360.mjs")));
  assert.equal(renderer.isVueNodesMode({ LiteGraph: { vueNodesMode: true } }), true);
  assert.equal(renderer.isVueNodesMode({ LiteGraph: { vueNodesMode: false } }), false);
});

test("mixed pack contains one FLAT runtime and retains one HALO runtime", () => {
  const names = fs.readdirSync(path.join(root, "web"));
  assert.equal(names.filter((name) => /^flat\.[0-9a-f]{16}\.mjs$/.test(name)).length, 1);
  assert.equal(names.filter((name) => /^renderer\.[0-9a-f]{16}\.mjs$/.test(name)).length, 1);
  assert.equal(names.filter((name) => /^halo\.[0-9a-f]{16}\.mjs$/.test(name)).length, 1);
});
