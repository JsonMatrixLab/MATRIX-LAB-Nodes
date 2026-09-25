// Execute the production module graph and registration hooks. DOM sentinels stop
// at the mounting boundary; visible renderer acceptance remains a separate test.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import crypto from "node:crypto";
import {pathToFileURL} from "node:url";

const root = path.resolve(process.argv[2]);
const manifest = JSON.parse(fs.readFileSync(path.join(root, "MANIFEST.json")));
const web = path.join(root, "web");
const registrations = [];
let domAttempts = 0;
const sentinel = new Error("DOM mount boundary reached");
const application = { registerExtension(extension) { registrations.push(extension); } };
const context = vm.createContext({
  console: {warn() {}, log() {}}, Symbol, Map, Set, URL,
  document: { createElement() { domAttempts++; throw sentinel; } },
  comfyAPI: { app: {app: application}, api: {api: {fetchApi() { throw new Error("No network in regression"); }}} },
});
const modules = new Map();
const appModule = new vm.SyntheticModule(["app"], function () { this.setExport("app", application); }, {context});
const apiModule = new vm.SyntheticModule(["api"], function () { this.setExport("api", context.comfyAPI.api.api); }, {context});
async function moduleAt(filename) {
  if (modules.has(filename)) return modules.get(filename);
  let source = fs.readFileSync(filename, "utf8");
  // Expose one private pure function without replacing its production body.
  if (/[/\\]halo\.[a-f0-9]+\.mjs$/.test(filename)) source += "\nexport { parameterFieldPresentation };";
  const module = new vm.SourceTextModule(source, {context, identifier: filename, initializeImportMeta(meta) {meta.url = pathToFileURL(filename).href;}});
  modules.set(filename, module);
  await module.link(async (specifier) => {
    if (specifier.endsWith("/scripts/app.js")) return appModule;
    if (specifier.endsWith("/scripts/api.js")) return apiModule;
    assert(specifier.startsWith("./"), `Unexpected external dependency: ${specifier}`);
    return moduleAt(path.resolve(path.dirname(filename), specifier));
  });
  return module;
}
function file(prefix) {
  const names = fs.readdirSync(web).filter(name => name.startsWith(prefix + "."));
  assert.equal(names.length, 1, `Exactly one ${prefix} module`);
  return path.join(web, names[0]);
}
for (const relative of manifest.frontend_entrypoints) {
  const module = await moduleAt(path.join(root, relative));
  await module.evaluate();
}
const expectedRegistrations = manifest.frontend_entrypoints.length;
assert.equal(registrations.length, expectedRegistrations);
assert.equal(new Set(registrations.map(item => item.name)).size, expectedRegistrations);
assert(registrations.some(item => item.name === "matrix.h3-resolution.halo.classic"));
assert(registrations.some(item => item.name === "matrixlab.video-prompt"));
const pairs = [
  ["MATRIX_SpectralSampler", "MATRIXSpectralSampler", "halo.execution"],
  ["MATRIX_AIInfluencerResolution2K4K", "MATRIXLAB_AIInfluencerResolution2K4K", "resolution"],
  ["MATRIX_ImageBatchLoader", "MATRIXLAB_ImageBatchLoader", "image-collection.gallery"],
  ["MATRIX_AutoPrompter", "MATRIXLAB_PromptDirector", "prompt-director.halo"],
];
const required = ["instructions", "system_prompt", "model", "final_prompt", "generation_state", "character_trigger", "collection", "aspect_ratio", "resolution_tier"];
let hookCases = 0;
for (const [current, legacy, needle] of pairs) {
  const candidates = registrations.filter(item => item.name.includes(needle));
  const extension = needle === "resolution" ? candidates.find(item => item.name.includes("2k4k")) : candidates[0];
  assert(extension, `Registration for ${current}`);
  for (const hook of ["nodeCreated", "loadedGraphNode"]) {
    for (const key of ["comfyClass", "type"]) {
      for (const id of [current, legacy, "UnrelatedNode"]) {
        const node = { [key]: id, widgets: required.map(name => ({name, value: ""})), inputs: [], addDOMWidget() {} };
        const before = JSON.stringify(node);
        const started = domAttempts;
        try { extension[hook](node); } catch (error) { assert.equal(error, sentinel); }
        assert.equal(domAttempts - started, id === "UnrelatedNode" ? 0 : 1, `${id} ${hook} ${key}`);
        assert.equal(JSON.stringify(node), before, "No canonical state mutation before mounting");
        hookCases++;
      }
    }
  }
}
const added = registrations.find(item => item.name === "matrixlab.video-prompt");
for (const hook of ["nodeCreated", "loadedGraphNode"]) {
  for (const key of ["comfyClass", "type"]) {
    for (const id of ["MATRIX_Prompt", "MATRIX_VideoMetadataKiller", "UnrelatedNode"]) {
      const node = {[key]: id, widgets: [{name: "prompt", value: ""}, {name: "filename_prefix", value: "clean"}], inputs: [], addDOMWidget() {}};
      const started = domAttempts;
      try { added[hook](node); } catch (error) { assert.equal(error, sentinel); }
      assert.equal(domAttempts - started, id === "UnrelatedNode" ? 0 : 1, `${id} ${hook} ${key}`);
      hookCases++;
    }
  }
}
const prompt = modules.get(file("prompt_director")).namespace;
let loaderCases = 0;
for (const key of ["comfyClass", "type"]) {
  for (const id of ["MATRIX_ImageBatchLoader", "MATRIXLAB_ImageBatchLoader", "UnrelatedNode"]) {
    const collection = {name: "collection", value: JSON.stringify({version: 1, items: [{image: "fixture.png [input]"}], selected: 0})};
    const origin = {[key]: id, widgets: [collection], outputs: [{name: "images", type: "IMAGE"}]};
    const node = {inputs: [{name: "images", link: 1}], graph: {links: {1: {origin_id: 2, origin_slot: 0}}, getNodeById() {return origin;}}};
    if (id === "UnrelatedNode") assert.throws(() => prompt.resolveReferenceCollection(node), /Connect IMAGE directly/);
    else {
      const resolved = prompt.resolveReferenceCollection(node);
      assert.equal(resolved.widget, collection);
      assert.equal(resolved.collection.items[0].image, "fixture.png [input]");
    }
    loaderCases++;
  }
}
const halo = modules.get(file("halo")).namespace;
for (const scales of ["1", "0.5,1"]) {
  const policy = id => halo.parameterFieldPresentation({type: id, inputs: [], widgets: [{name: "scales", value: scales}, {name: "mode", value: "manual"}]}, {name: "delta"});
  assert.deepEqual(policy("MATRIXSpectralSampler"), policy("MATRIX_SpectralSampler"));
  assert(policy("MATRIXSpectralSampler"));
  assert.equal(policy("UnrelatedNode"), null);
}
for (const [relative, expected] of Object.entries(manifest.frontend_alias_compatibility.frontend_assets)) {
  const data = fs.readFileSync(path.join(root, relative));
  assert.equal(crypto.createHash("sha256").update(data).digest("hex"), expected);
  const match = relative.match(/\.([0-9a-f]{16})\.(?:js|mjs)$/);
  if (match) assert.equal(expected.slice(0, 16), match[1]);
}
console.log(JSON.stringify({pass: true, hookCases, loaderCases, spectralPolicies: 2, registrations: registrations.length, scope: "Production routing, loader resolution, policy, import graph and content hashes; not visible browser acceptance"}, null, 2));
