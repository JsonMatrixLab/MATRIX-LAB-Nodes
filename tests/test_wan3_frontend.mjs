import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";
import { randomUUID } from "node:crypto";

const source = (await readFile(new URL("../web/wan3.966d9792a941c4af.js", import.meta.url), "utf8"))
  .replace(/^import\s+\{\s*app\s*\}\s+from\s+["'][^"']+["'];\s*/m, "")
  .replace(/^import\s+\{\s*HALO_TOKENS,\s*haloWidgetLayoutHeight,\s*mountHaloSurface\s*\}\s+from\s+["'][^"']+["'];\s*/m, "");
const legacyFixture = JSON.parse(await readFile(new URL("./fixtures/wan3/legacy-native-workflow.json", import.meta.url), "utf8"));
const linkedLegacyFixture = JSON.parse(await readFile(new URL("./fixtures/wan3/legacy-linked-image-migration.json", import.meta.url), "utf8"));
const extensions = [];
const app = { graph: { _nodes: [] }, registerExtension(extension) { extensions.push(extension); } };
class TestElement {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.dataset = {}; this.style = {}; this.listeners = {}; this.isConnected = false; this.textContent = ""; this.innerHTML = ""; }
  append(...items) { for (const item of items) { this.children.push(item); item.parentNode = this; item.isConnected = this.isConnected; } }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((item) => item !== this); this.isConnected = false; }
  setAttribute() {}
  focus() {}
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  findButton(label) { for (const child of this.children) { if (child.tagName === "button" && child.textContent === label) return child; const found = child.findButton?.(label); if (found) return found; } return null; }
}
const body = new TestElement("body");
const document = { body, createElement: (tagName) => new TestElement(tagName) };
const window = { addEventListener() {}, removeEventListener() {} };
const HALO_TOKENS = { errorText: "#ff6b5a", green: "#00ff41", fieldBorder: "#31543c", parameterLabel: "#abc0b1", primaryText: "#edf8f0", headerDivider: "#204b2b", instanceId: "#7fb58b", secondaryText: "#97aa9c" };
const haloWidgetLayoutHeight = (height, widget) => height + (widget?.margin ?? 10) * 2;
const haloSurfaces = [];
const fetchCalls = [];
const fetchResponses = [];
const fetch = async (url, init) => { fetchCalls.push({ url, init }); const data = fetchResponses.shift() || { ok: true }; return { ok: true, status: 200, async json() { return await data; } }; };
const context = { app, console, URL, document, window, fetch, crypto: { randomUUID }, HALO_TOKENS, haloWidgetLayoutHeight, mountHaloSurface: (root, node) => {
  const previousRemoved = node.onRemoved;
  const surface = { root, node, destroyed: false, destroy() { this.destroyed = true; root.isConnected = false; } };
  haloSurfaces.push(surface);
  node.onRemoved = function (...args) { surface.destroy(); return previousRemoved?.apply(this, args); };
  return surface;
}, requestAnimationFrame: () => 0, setTimeout, clearTimeout };
const testApiSource = "globalThis.__matrixWan3Tests = { MODE_WIDGETS, applyProjection, installSeedProjection, preserveLegacyFixedSeed, incompatibleInputs, installModeProjection, configureModeState, modeDialog, modal, mediaRole, dynamicInputName, migrateLegacyWorkflow, syncOperationChoices, migrateLegacyGraphData, ownedWidgetName, installKeyControl, installHalo, installNativeLayout, keyStatus, fitNodeHeight, request };";
runInNewContext(`${source}\n${testApiSource}`, context);
const api = context.__matrixWan3Tests;

function makeNode(operation = "Text to Video") {
  const widgetNames = ["operation", "tier", "image_variant", "prompt", "resolution", "duration", "aspect_ratio", "enable_audio", "generate_audio", "enable_prompt_expansion", "seed_mode", "seed", "edit_duration", "allow_video_materialization", "acknowledge_provider_trimming", "intent_nonce", "credential_scope", "billing_activation"];
  const widgets = widgetNames.map((name) => ({
    name,
    type: name === "operation" || name === "tier" || name === "image_variant" || name === "resolution" || name === "aspect_ratio" || name === "seed_mode" || name === "edit_duration" ? "combo" : "text",
    value: ({ operation, tier: "Standard", image_variant: "Regular", resolution: "720p", duration: 5, aspect_ratio: "16:9", edit_duration: "Auto", seed_mode: "Random", seed: 1, intent_nonce: "fresh-id", credential_scope: "scope", billing_activation: "wavespeed_v1" })[name] ?? false,
  }));
  return {
    type: "MATRIX_Wan3",
    widgets,
    inputs: [
      { name: "operation", link: null }, { name: "aspect_ratio", link: null }, { name: "image_variant", link: null },
      { name: "operation.image", link: null }, { name: "operation.last_image", link: null }, { name: "operation.video", link: null },
      ...Array.from({ length: 10 }, (_, i) => ({ name: `operation.reference_images.image_${String(i + 1).padStart(2, "0")}`, link: null })),
      ...Array.from({ length: 5 }, (_, i) => ({ name: `operation.reference_videos.video_${String(i + 1).padStart(2, "0")}`, link: null })),
      ...Array.from({ length: 5 }, (_, i) => ({ name: `operation.reference_audios.audio_${String(i + 1).padStart(2, "0")}`, link: null })),
    ],
    properties: {},
    graph: { beforeChange() {}, afterChange() {} },
    setDirtyCanvas() {},
    disconnectInput(index) { this.inputs[index].link = null; },
  };
}

test("tier is visible in every mode; image variant only in I2V; route-specific advanced controls are projected", () => {
  const node = makeNode();
  for (const mode of ["Text to Video", "Image to Video", "Reference to Video", "Edit Video", "Extend Video"]) {
    api.applyProjection(node, mode);
    const type = (name) => node.widgets.find((widget) => widget.name === name).type;
    const widget = (name) => node.widgets.find((item) => item.name === name);
    assert.notEqual(type("tier"), "hidden", `${mode}: tier`);
    assert.equal(widget("tier").hidden, false, `${mode}: native visible tier`);
    assert.equal(type("image_variant") === "hidden", mode !== "Image to Video", `${mode}: image variant`);
    assert.equal(widget("image_variant").hidden, mode !== "Image to Video", `${mode}: image route visibility`);
    assert.equal(type("allow_video_materialization") !== "hidden", mode === "Reference to Video" || mode === "Edit Video" || mode === "Extend Video");
    assert.equal(widget("generate_audio").hidden, mode !== "Edit Video", `${mode}: edit-only audio control`);
    assert.equal(widget("acknowledge_provider_trimming").hidden, mode !== "Edit Video" && mode !== "Extend Video", `${mode}: trim consent`);
    assert.equal(widget("enable_prompt_expansion").hidden, false, `${mode}: expansion control`);
    assert.equal(widget("credential_scope").hidden, true, `${mode}: internal credential scope`);
    assert.equal(widget("intent_nonce").hidden, true, `${mode}: internal request intent`);
    assert.equal(node.inputs.some((input) => Object.hasOwn(input, "hidden")), false, `${mode}: native dynamic inputs are not projection-controlled`);
  }
});

test("first I2V entry uses Auto and Regular, then restores its saved local preferences", () => {
  const node = makeNode();
  api.installModeProjection(node);
  const controls = Object.fromEntries(node.widgets.map((widget) => [widget.name, widget]));
  controls.operation.callback("Image to Video", {}, node, null, {});
  assert.equal(controls.aspect_ratio.value, "Auto");
  assert.equal(controls.image_variant.value, "Regular");
  controls.aspect_ratio.value = "9:16";
  controls.image_variant.value = "Spicy";
  controls.operation.callback("Text to Video", {}, node, null, {});
  assert.equal(controls.aspect_ratio.value, "9:16");
  assert.equal(controls.image_variant.value, "Regular");
  controls.operation.callback("Image to Video", {}, node, null, {});
  assert.equal(controls.aspect_ratio.value, "9:16");
  assert.equal(controls.image_variant.value, "Spicy");
});

test("Auto aspect normalizes to 16:9 when leaving I2V", () => {
  const node = makeNode("Image to Video");
  const controls = Object.fromEntries(node.widgets.map((widget) => [widget.name, widget]));
  controls.aspect_ratio.value = "Auto";
  api.installModeProjection(node);
  controls.operation.callback("Text to Video", {}, node, null, {});
  assert.equal(controls.aspect_ratio.value, "16:9");
});

test("safe I2V preferences persist through namespaced node properties and reload", () => {
  const original = makeNode("Image to Video");
  const originalControls = Object.fromEntries(original.widgets.map((widget) => [widget.name, widget]));
  originalControls.aspect_ratio.value = "Auto";
  originalControls.image_variant.value = "Spicy";
  original.properties.matrixWan3 = { imageToVideo: { api_key: "must-not-persist", aspect_ratio: "Auto", image_variant: "Spicy" }, extra: "discard" };
  api.installModeProjection(original);
  originalControls.operation.callback("Text to Video", {}, original, null, {});
  assert.deepEqual(JSON.parse(JSON.stringify(original.properties.matrixWan3)), {
    imageToVideo: { aspect_ratio: "Auto", image_variant: "Spicy" },
  });

  const restored = makeNode("Text to Video");
  restored.properties = JSON.parse(JSON.stringify(original.properties));
  api.configureModeState(restored);
  const controls = Object.fromEntries(restored.widgets.map((widget) => [widget.name, widget]));
  api.installModeProjection(restored);
  controls.operation.callback("Image to Video", {}, restored, null, {});
  assert.equal(controls.aspect_ratio.value, "Auto");
  assert.equal(controls.image_variant.value, "Spicy");
  assert.equal(Object.keys(restored.properties.matrixWan3).join(","), "imageToVideo");
});

test("mode normalization reports linked aspect and variant controls as explicit conflicts", () => {
  const node = makeNode("Image to Video");
  const controls = Object.fromEntries(node.widgets.map((widget) => [widget.name, widget]));
  controls.aspect_ratio.value = "Auto";
  controls.image_variant.value = "Spicy";
  node.inputs.find((input) => input.name === "aspect_ratio").link = 11;
  node.inputs.find((input) => input.name === "image_variant").link = 12;
  assert.deepEqual(api.incompatibleInputs(node, "Text to Video").map((input) => input.name).sort(), ["aspect_ratio", "image_variant"]);
});

const MODES = ["Text to Video", "Image to Video", "Reference to Video", "Edit Video", "Extend Video"];
const ACTIVE_MEDIA = {
  "Text to Video": new Set(),
  "Image to Video": new Set(["image", "last_image"]),
  "Reference to Video": new Set(["reference_images", "reference_videos", "reference_audios"]),
  "Edit Video": new Set(["video", "reference_images", "reference_audios"]),
  "Extend Video": new Set(["video", "last_image"]),
};
const TRANSITIONS = MODES.flatMap((from) => MODES.filter((to) => from !== to).map((to) => [from, to]));
const linkedMediaNames = ["operation.image", "operation.last_image", "operation.video", "operation.reference_images.image_01", "operation.reference_videos.video_01", "operation.reference_audios.audio_01"];
function linkedNode(from) {
  const node = makeNode(from);
  node.inputs.find((input) => input.name === "operation").link = 1;
  for (const [index, name] of linkedMediaNames.entries()) node.inputs.find((input) => input.name === name).link = index + 2;
  api.installModeProjection(node);
  return node;
}
function modeWidget(node) { return node.widgets.find((widget) => widget.name === "operation"); }
function invokeModeChange(node, nextMode) {
  modeWidget(node).callback(nextMode, { emitBeforeChange() {}, emitAfterChange() {} }, node, null, {});
}
function dialogButton(label) {
  const dialog = body.children.find((item) => item.dataset.matrixWan3ModeDialog === "1");
  assert.ok(dialog, "expected the transition confirmation dialog");
  const button = dialog.findButton(label);
  assert.ok(button, `missing dialog button ${label}`);
  return button;
}

test("all 20 directed mode changes commit directly when no sockets are connected", async (t) => {
  for (const [from, to] of TRANSITIONS) await t.test(`${from} -> ${to}`, () => {
    const node = makeNode(from);
    api.installModeProjection(node);
    invokeModeChange(node, to);
    assert.equal(modeWidget(node).value, to);
    assert.equal(node._matrixWan3Operation, to);
    assert.equal(body.children.some((item) => item.dataset.matrixWan3ModeDialog === "1"), false);
  });
});

test("all 20 directed mode changes can be cancelled without changing mode or wires", async (t) => {
  for (const [from, to] of TRANSITIONS) await t.test(`${from} -> ${to}`, () => {
    const node = linkedNode(from);
    const before = Object.fromEntries(node.inputs.map((input) => [input.name, input.link]));
    invokeModeChange(node, to);
    dialogButton("Cancel").onclick();
    assert.equal(modeWidget(node).value, from);
    assert.equal(node._matrixWan3Operation, from);
    assert.deepEqual(Object.fromEntries(node.inputs.map((input) => [input.name, input.link])), before);
  });
});

test("all 20 directed mode changes disconnect only incompatible linked inputs and preserve shared wires", async (t) => {
  for (const [from, to] of TRANSITIONS) await t.test(`${from} -> ${to}`, () => {
    const node = linkedNode(from);
    const before = Object.fromEntries(node.inputs.map((input) => [input.name, input.link]));
    invokeModeChange(node, to);
    dialogButton("Disconnect listed inputs and switch").onclick();
    assert.equal(modeWidget(node).value, to);
    assert.equal(node._matrixWan3Operation, to);
    for (const input of node.inputs) {
      const shouldPreserve = input.name !== "operation" && ACTIVE_MEDIA[to].has(api.mediaRole(input.name));
      assert.equal(input.link, shouldPreserve ? before[input.name] : null, `${from} -> ${to}: ${input.name}`);
    }
    assert.equal(node.inputs.find((input) => input.name === "aspect_ratio").link, null);
    assert.equal(node.inputs.find((input) => input.name === "image_variant").link, null);
  });
});

test("normalization conflicts can be cancelled without changing widget values", () => {
  const node = makeNode("Image to Video");
  const controls = Object.fromEntries(node.widgets.map((widget) => [widget.name, widget]));
  controls.aspect_ratio.value = "Auto";
  controls.image_variant.value = "Spicy";
  for (const name of ["operation.image", "operation.last_image", "aspect_ratio", "image_variant"]) node.inputs.find((input) => input.name === name).link = name;
  api.installModeProjection(node);
  invokeModeChange(node, "Extend Video");
  dialogButton("Cancel").onclick();
  assert.equal(controls.operation.value, "Image to Video");
  assert.equal(controls.aspect_ratio.value, "Auto");
  assert.equal(controls.image_variant.value, "Spicy");
  assert.deepEqual(Object.fromEntries(node.inputs.filter((input) => input.link != null).map((input) => [input.name, input.link])), {
    "operation.image": "operation.image", "operation.last_image": "operation.last_image", aspect_ratio: "aspect_ratio", image_variant: "image_variant",
  });
});

test("normalization acceptance disconnects only changed controls and inactive media, preserving shared media", () => {
  const node = makeNode("Image to Video");
  const controls = Object.fromEntries(node.widgets.map((widget) => [widget.name, widget]));
  controls.aspect_ratio.value = "Auto";
  controls.image_variant.value = "Spicy";
  for (const name of ["operation.image", "operation.last_image", "aspect_ratio", "image_variant"]) node.inputs.find((input) => input.name === name).link = name;
  api.installModeProjection(node);
  invokeModeChange(node, "Extend Video");
  dialogButton("Disconnect listed inputs and switch").onclick();
  assert.equal(controls.operation.value, "Extend Video");
  assert.equal(controls.aspect_ratio.value, "16:9");
  assert.equal(controls.image_variant.value, "Regular");
  assert.equal(node.inputs.find((input) => input.name === "operation.last_image").link, "operation.last_image");
  for (const name of ["operation.image", "aspect_ratio", "image_variant"]) assert.equal(node.inputs.find((input) => input.name === name).link, null);
});

test("actual legacy native workflow restores named values and removes unconnected inactive flat media ports", () => {
  const serialized = legacyFixture.nodes.find((item) => item.type === "MATRIX_Wan3");
  assert.ok(serialized);
  const node = makeNode();
  node.inputs = node.inputs.filter((input) => !api.mediaRole(input.name));
  node.inputs.push(...serialized.inputs.filter((input) => api.mediaRole(input.name)).map((input) => ({ name: input.name, link: input.link })));
  assert.equal(api.migrateLegacyWorkflow(node, serialized), true);
  const controls = Object.fromEntries(node.widgets.map((widget) => [widget.name, widget]));
  assert.equal(controls.billing_activation.value, "blocked");
  assert.equal(controls.operation.value, serialized.widgets_values_named.operation);
  assert.equal(controls.tier.value, serialized.widgets_values_named.tier);
  assert.equal(controls.seed.value, serialized.widgets_values_named.seed);
  assert.equal(controls.intent_nonce.value, serialized.widgets_values_named.intent_nonce);
  assert.equal(node.properties.matrixWan3.schemaVersion, 3);
  assert.deepEqual(node.inputs.filter((input) => api.mediaRole(input.name)), []);
});

test("legacy migration deduplicates current-route ports already supplied by DynamicCombo", () => {
  const serialized = JSON.parse(JSON.stringify(legacyFixture.nodes.find((item) => item.type === "MATRIX_Wan3")));
  serialized.widgets_values_named.operation = "Image to Video";
  const node = makeNode();
  node.inputs.push(...serialized.inputs.filter((input) => api.mediaRole(input.name)).map((input) => ({ name: input.name, link: input.link })));
  api.migrateLegacyWorkflow(node, serialized);
  const mediaNames = node.inputs.filter((input) => api.mediaRole(input.name)).map((input) => input.name);
  assert.equal(new Set(mediaNames).size, mediaNames.length);
  assert.deepEqual(mediaNames.sort(), ["operation.image", "operation.last_image"]);
});

test("native DynamicCombo control is locked while media is connected and restored after unlink", () => {
  const node = makeNode("Reference to Video");
  const operation = modeWidget(node);
  operation._matrixWan3BaseType = operation.type;
  node.inputs.find((input) => input.name === "operation.reference_images.image_01").link = 31;
  api.syncOperationChoices(node);
  assert.equal(operation.type, "hidden");
  assert.equal(operation.hidden, true);
  assert.equal(operation.options.hidden, true);
  node.inputs.find((input) => input.name === "operation.reference_images.image_01").link = null;
  api.syncOperationChoices(node);
  assert.equal(operation.type, "combo");
  assert.equal(operation.hidden, false);
  assert.equal(operation.options.hidden, false);
});

test("beforeConfigureGraph remaps an active legacy I2V wire by semantic input name", () => {
  const graph = JSON.parse(JSON.stringify(linkedLegacyFixture));
  const node = graph.nodes.find((item) => item.type === "MATRIX_Wan3");
  assert.equal(api.migrateLegacyGraphData(graph), true);
  assert.deepEqual(JSON.parse(JSON.stringify(node.inputs.slice(0, 3).map((input) => input.name))), ["operation", "operation.image", "operation.last_image"]);
  assert.deepEqual(graph.links[0], [101, 7, 0, 1, 1, "IMAGE"]);
  assert.equal(node.widgets_values_named.billing_activation, "blocked");
});

test("old Demo stays blocked even with an inconsistent activation marker; old billed choice migrates explicitly", () => {
  const demo = JSON.parse(JSON.stringify(legacyFixture));
  demo.nodes[0].widgets_values_named.billing_activation = "wavespeed_v1";
  api.migrateLegacyGraphData(demo);
  assert.equal(demo.nodes[0].widgets_values_named.billing_activation, "blocked");
  assert.equal("provider" in demo.nodes[0].widgets_values_named, false);
  assert.equal(demo.nodes[0].inputs.some((input) => input.name === "provider"), false);
  const billed = JSON.parse(JSON.stringify(legacyFixture));
  billed.nodes[0].widgets_values_named.provider = "WaveSpeed (billed)";
  billed.nodes[0].widgets_values[0] = "WaveSpeed (billed)";
  api.migrateLegacyGraphData(billed);
  assert.equal(billed.nodes[0].widgets_values_named.billing_activation, "wavespeed_v1");
});

test("unknown legacy provider is blocked and a linked provider fails before graph mutation", () => {
  const unknown = JSON.parse(JSON.stringify(legacyFixture));
  unknown.nodes[0].widgets_values_named.provider = "Unknown provider";
  api.migrateLegacyGraphData(unknown);
  assert.equal(unknown.nodes[0].widgets_values_named.billing_activation, "blocked");
  const linked = JSON.parse(JSON.stringify(legacyFixture));
  const provider = linked.nodes[0].inputs.find((input) => input.name === "provider");
  provider.link = 41;
  const before = JSON.stringify(linked);
  assert.throws(() => api.migrateLegacyGraphData(linked), /linked legacy Provider/);
  assert.equal(JSON.stringify(linked), before);
});

function legacyReferenceGraph(operation, connected) {
  const graph = JSON.parse(JSON.stringify(linkedLegacyFixture));
  const node = graph.nodes.find((item) => item.type === "MATRIX_Wan3");
  node.widgets_values_named.operation = operation;
  node.widgets_values[1] = operation;
  graph.links = [];
  for (const input of node.inputs) input.link = null;
  for (const [offset, [name, type]] of connected.entries()) {
    const input = node.inputs.find((candidate) => candidate.name === name);
    assert.ok(input, `legacy fixture has ${name}`);
    const id = 300 + offset;
    input.link = id;
    graph.links.push([id, 100 + offset, 0, node.id, node.inputs.indexOf(input), type]);
  }
  return { graph, node };
}

test("beforeConfigureGraph migrates Reference Autogrow wires in role and slot order, preserving gaps", () => {
  const { graph, node } = legacyReferenceGraph("Reference to Video", [
    ["reference_image_01", "IMAGE"], ["reference_image_10", "IMAGE"],
    ["reference_video_02", "VIDEO"], ["reference_audio_03", "AUDIO"],
  ]);
  assert.equal(api.migrateLegacyGraphData(graph), true);
  const names = JSON.parse(JSON.stringify(node.inputs.slice(1, 16).map((input) => input.name)));
  assert.deepEqual(names, [
    ...Array.from({ length: 10 }, (_, i) => `operation.reference_images.image_${String(i + 1).padStart(2, "0")}`),
    "operation.reference_videos.video_01", "operation.reference_videos.video_02",
    "operation.reference_audios.audio_01", "operation.reference_audios.audio_02", "operation.reference_audios.audio_03",
  ]);
  assert.deepEqual(graph.links.map((link) => [link[0], link[4]]), [[300, 1], [301, 10], [302, 12], [303, 15]]);
});

test("beforeConfigureGraph migrates Edit image/audio references but rejects video references", () => {
  const supported = legacyReferenceGraph("Edit Video", [["reference_image_02", "IMAGE"], ["reference_audio_04", "AUDIO"]]);
  assert.equal(api.migrateLegacyGraphData(supported.graph), true);
  assert.deepEqual(JSON.parse(JSON.stringify(supported.node.inputs.slice(1, 8).map((input) => input.name))), [
    "operation.video",
    "operation.reference_images.image_01", "operation.reference_images.image_02",
    "operation.reference_audios.audio_01", "operation.reference_audios.audio_02", "operation.reference_audios.audio_03", "operation.reference_audios.audio_04",
  ]);
  assert.deepEqual(supported.graph.links.map((link) => [link[0], link[4]]), [[300, 3], [301, 7]]);

  const unsupported = legacyReferenceGraph("Edit Video", [["reference_image_02", "IMAGE"], ["reference_video_01", "VIDEO"]]);
  const originalInputs = JSON.stringify(unsupported.node.inputs);
  const originalLinks = JSON.stringify(unsupported.graph.links);
  assert.throws(() => api.migrateLegacyGraphData(unsupported.graph), /Cannot safely migrate the linked legacy MATRIX_Wan3 input.*Edit Video/);
  assert.equal(JSON.stringify(unsupported.node.inputs), originalInputs);
  assert.equal(JSON.stringify(unsupported.graph.links), originalLinks);
});

test("beforeConfigureGraph refuses a linked legacy socket that has no safe current-route mapping", () => {
  const graph = JSON.parse(JSON.stringify(linkedLegacyFixture));
  const node = graph.nodes.find((item) => item.type === "MATRIX_Wan3");
  node.widgets_values_named.operation = "Text to Video";
  node.widgets_values[1] = "Text to Video";
  const originalInputs = JSON.stringify(node.inputs);
  assert.throws(() => api.migrateLegacyGraphData(graph), /Cannot safely migrate the linked legacy MATRIX_Wan3 input/);
  assert.equal(JSON.stringify(node.inputs), originalInputs);
  assert.equal(graph.links[0][4], 0);
});

test("key status is a native nonserialized DOM control before Operation and never exposes key material", () => {
  const node = makeNode();
  node.addDOMWidget = (name, type, element, options) => {
    const widget = { name, type, element, options };
    node.widgets.push(widget);
    return widget;
  };
  api.installKeyControl(node);
  const widget = node.widgets[0];
  assert.ok(widget.name.startsWith("matrix_wan3_key_status_"));
  assert.equal(node.widgets[1].name, "operation");
  assert.equal(widget.serialize, false);
  assert.equal(widget.options.serialize, false);
  assert.equal(widget.element.tagName, "button");
  assert.equal(widget.element.style.height, "24px");
  assert.equal(widget.element.style.maxHeight, "24px");
  assert.equal(widget.element.children[0].textContent, "WAVESPEED KEY");
  assert.equal(widget.element.children[1].textContent, "Select to manage");
  api.keyStatus(node, { present: true, source: "saved", verified: false });
  assert.equal(widget.element.children[1].textContent, "•••• · saved · unchecked");
  assert.equal(widget.options.getHeight(), 44, "the native widget reserves DOM height plus both margins");
  assert.equal(node.widgets.some((item) => item.name === "api_key" || item.value === "secret"), false);
});

test("key row loads an existing saved key without opening the dialog", async () => {
  fetchCalls.length = 0;
  fetchResponses.push({ present: true, source: "saved" });
  const node = makeNode();
  node.addDOMWidget = (name, type, element, options) => { const widget = { name, type, element, options }; node.widgets.push(widget); return widget; };
  api.installKeyControl(node);
  await new Promise((resolve) => setTimeout(resolve, 0));
  const control = node.widgets.find((item) => item.name.startsWith("matrix_wan3_key_status_")).element;
  assert.equal(control.children[1].textContent, "•••• · saved · unchecked");
  assert.equal(fetchCalls[0].init.method, "GET");
});

test("late key-row status cannot overwrite a newer saved key", async () => {
  fetchCalls.length = 0;
  let releaseMountStatus;
  fetchResponses.push(new Promise((resolve) => { releaseMountStatus = resolve; }), { present: false, source: null }, { saved: true });
  const node = makeNode();
  node.widgets.find((item) => item.name === "billing_activation").value = "blocked";
  node.addDOMWidget = (name, type, element, options) => { const widget = { name, type, element, options }; node.widgets.push(widget); return widget; };
  api.installKeyControl(node);
  api.modal(node);
  const dialog = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  await new Promise((resolve) => setTimeout(resolve, 0));
  dialog.children[0].children[3].value = "test-only-secret";
  dialog.findButton("Save key").onclick();
  await new Promise((resolve) => setTimeout(resolve, 0));
  releaseMountStatus({ present: false, source: null });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const control = node.widgets.find((item) => item.name.startsWith("matrix_wan3_key_status_")).element;
  assert.equal(control.children[1].textContent, "•••• · saved · unchecked");
  assert.equal(node.widgets.find((item) => item.name === "billing_activation").value, "wavespeed_v1", "explicit key save activates a migrated Demo node");
  dialog.findButton("Close").onclick();
});

test("legacy excess node height is reduced to current widgets while preserving width", () => {
  const node = { size: [520, 1000], computeSize: () => [430, 420], setSize(size) { this.size = size; } };
  assert.equal(api.fitNodeHeight(node), true);
  assert.deepEqual(Array.from(node.size), [520, 420]);
  assert.equal(api.fitNodeHeight(node), false);
});

test("native prompt retains a resize handle, grows the node, and follows node resizing", () => {
  let observed;
  const documentListeners = {};
  context.ResizeObserver = class { constructor(callback) { this.callback = callback; } observe(element) { observed = { element, callback: this.callback }; } disconnect() {} };
  const head = new TestElement("head");
  document.head = head;
  document.getElementById = () => null;
  const row = new TestElement("div");
  let textareaHeight = 64;
  const textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  Object.defineProperty(textarea, "offsetHeight", { get: () => textareaHeight });
  textarea.getBoundingClientRect = () => ({ right: 100, bottom: 100 });
  textarea.closest = () => row;
  const root = new TestElement("div");
  root.classList = { add() {} };
  root.querySelector = () => textarea;
  document.querySelector = () => root;
  document.addEventListener = (name, callback) => { (documentListeners[name] ||= []).push(callback); };
  document.removeEventListener = () => {};
  const node = makeNode();
  node.id = 1;
  node.size = [430, 556];
  node.computeSize = () => [430, 556];
  node.setSize = function (size) { this.size = size; this.onResize?.(size); };
  api.installNativeLayout(node);
  const prompt = node.widgets.find((item) => item.name === "prompt");
  assert.equal(prompt.options.getMinHeight(), 140);
  assert.equal(prompt.options.getHeight(), 140);
  assert.match(head.children[0].textContent, /\.lg-node:has\(\[node-type="MATRIX_Wan3"\]\)/);
  assert.match(head.children[0].textContent, /align-content: start/);
  assert.match(head.children[0].textContent, /resize: vertical/);
  assert.equal(node.size[1], 556);
  textareaHeight = 120;
  textarea.listeners.pointerdown[0]({ clientX: 95, clientY: 95 });
  textareaHeight = 160;
  observed.callback();
  assert.equal(row.style.height, "120px", "Vue ResizeObserver does not also write prompt geometry");
  documentListeners.pointermove[0]({ clientY: 135 });
  assert.equal(row.style.height, "160px");
  assert.equal(node.size[1], 596);
  assert.equal(node.properties.matrixWan3PromptHeight, 160);
  assert.equal(prompt.options.getMinHeight(), 180);
  documentListeners.pointerup[0]({});
  textareaHeight = 220;
  textarea.listeners.pointerdown[0]({ clientX: 95, clientY: 95 });
  textareaHeight = 250;
  observed.callback();
  documentListeners.pointermove[0]({ clientY: 125 });
  assert.equal(node.size[1], 626, "only the actual drag delta expands a flex-allocated Classic prompt");
  root.listeners.pointerdown[0]({ target: { closest: () => ({ dataset: { corner: "SE" } }) }, clientY: 100, pointerId: 1 });
  node.setSize([430, 676]);
  assert.equal(node.properties.matrixWan3PromptHeight, 250, "Vue native size callback does not grow the prompt");
  textareaHeight = 250;
  documentListeners.pointermove[1]({ clientY: 150, pointerId: 1 });
  assert.equal(textarea.style.height, "300px");
  assert.equal(node.properties.matrixWan3PromptHeight, 300);
  documentListeners.pointerup[0]({ pointerId: 1 });
  textareaHeight = 300;
  textarea.listeners.mousedown[0]({ clientX: 95, clientY: 95, preventDefault() {}, stopPropagation() {} });
  documentListeners.mousemove[0]({ clientY: 135 });
  assert.equal(textarea.style.height, "340px", "Vue mouse grip movement sets a real pixel height");
  assert.equal(row.style.height, "340px");
  assert.equal(node.size[1], 716);
  assert.equal(node.properties.matrixWan3PromptHeight, 340);
  documentListeners.mouseup[0]({});
  delete document.head;
  delete document.getElementById;
  delete document.querySelector;
  delete document.addEventListener;
  delete document.removeEventListener;
  delete context.ResizeObserver;
});

test("late Vue textarea creation binds prompt sizing after native DOM insertion", () => {
  let mutation;
  context.MutationObserver = class { constructor(callback) { mutation = callback; } observe() {} disconnect() {} };
  context.ResizeObserver = class { observe() {} disconnect() {} };
  context.requestAnimationFrame = (callback) => { callback(); return 0; };
  document.head = new TestElement("head");
  document.getElementById = () => null;
  const root = new TestElement("div");
  let textarea = null;
  root.querySelector = () => textarea;
  document.querySelector = () => root;
  const node = makeNode();
  node.id = 1;
  node.size = [430, 500];
  node.computeSize = () => [430, 556];
  node.setSize = function (size) { this.size = size; };
  api.installNativeLayout(node);
  textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  textarea.offsetHeight = 64;
  textarea.closest = () => new TestElement("div");
  mutation();
  assert.equal(textarea.style.height, "120px");
  assert.equal(node.size[1], 500, "Vue keeps its native DOM minimum instead of the Classic computeSize floor");
  delete document.head;
  delete document.getElementById;
  delete document.querySelector;
  delete context.MutationObserver;
  delete context.ResizeObserver;
  context.requestAnimationFrame = () => 0;
});

test("Vue remount preserves a saved prompt without inflating an already tall node", () => {
  document.head = new TestElement("head");
  document.getElementById = () => null;
  const textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  textarea.offsetHeight = 64;
  textarea.closest = () => new TestElement("div");
  const root = new TestElement("div");
  root.querySelector = () => textarea;
  document.querySelector = () => root;
  const node = makeNode();
  node.id = 1;
  node.properties.matrixWan3PromptHeight = 199;
  node.size = [225, 678];
  node.computeSize = () => [430, 805];
  node.setSize = function (size) { this.size = size; };
  api.installNativeLayout(node);
  assert.equal(textarea.style.height, "199px");
  assert.equal(root.style.minWidth, "430px", "Vue's native resize handle reads the node's inline minimum width");
  assert.equal(node.size[0], 430, "a saved narrow node is normalized to a readable width");
  assert.equal(node.size[1], 678, "Vue remount neither double-adds the prompt nor applies Classic widget minima");
  delete document.head;
  delete document.getElementById;
  delete document.querySelector;
});

test("saved oversized prompt height clamps to its maximum instead of resetting to minimum", () => {
  document.head = new TestElement("head");
  document.getElementById = () => null;
  const textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  textarea.offsetHeight = 64;
  textarea.closest = () => new TestElement("div");
  const root = new TestElement("div");
  root.querySelector = () => textarea;
  document.querySelector = () => root;
  const node = makeNode();
  node.id = 1;
  node.size = [430, 800];
  node.properties.matrixWan3PromptHeight = 1400;
  node.setSize = function (size) { this.size = size; };
  api.installNativeLayout(node);
  assert.equal(textarea.style.height, "1200px");
  assert.equal(node.properties.matrixWan3PromptHeight, 1200);
  delete document.head;
  delete document.getElementById;
  delete document.querySelector;
});

test("Vue outer resize uses the corner gesture, not native minimum-size feedback", () => {
  const listeners = {};
  const frames = [];
  let haloRedraws = 0;
  context.requestAnimationFrame = (callback) => { frames.push(callback); return frames.length; };
  document.head = new TestElement("head");
  document.getElementById = () => null;
  document.addEventListener = (name, callback) => { (listeners[name] ||= []).push(callback); };
  document.removeEventListener = () => {};
  context.ResizeObserver = class { observe() {} disconnect() {} };
  const textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  textarea.offsetHeight = 923;
  textarea.closest = () => new TestElement("div");
  textarea.getBoundingClientRect = () => ({ height: 664.56, right: 100, bottom: 100 });
  const root = new TestElement("div");
  root.querySelector = () => textarea;
  document.querySelector = () => root;
  const node = makeNode();
  node.id = 1;
  node.size = [430, 967];
  node.properties.matrixWan3PromptHeight = 923;
  node[Symbol.for("matrix.wan3.halo-control.v1")] = { renderStatic() { haloRedraws += 1; } };
  node.setSize = function (size) { this.size = size; this.onResize?.(size); };
  api.installNativeLayout(node);
  root.listeners.pointerdown[0]({ target: { closest: () => ({ dataset: { corner: "SE" } }) }, clientY: 400, pointerId: 1 });
  node.setSize([430, 1052]); // Native Vue content-minimum correction during a shrinking drag.
  assert.equal(node.properties.matrixWan3PromptHeight, 923, "native clamp must not grow the saved prompt");
  assert.equal(haloRedraws, 0, "geometry is read after Vue has committed layout");
  frames.shift()?.();
  frames.shift()?.();
  assert.equal(haloRedraws, 1, "node resize refreshes the edge after the moving brand settles");
  listeners.pointermove[1]({ clientY: 340, pointerId: 1 });
  assert.ok(node.properties.matrixWan3PromptHeight < 923, "upward corner motion can lower the prompt minimum");
  listeners.pointerup[0]({ pointerId: 1 });
  root.listeners.pointerdown[0]({ target: { closest: () => ({ dataset: { corner: "SE" } }) }, clientY: 400, pointerId: 2 });
  listeners.pointermove[1]({ clientY: 700, pointerId: 2 });
  assert.equal(node.properties.matrixWan3PromptHeight, 1200, "outer and direct prompt drags share the same height maximum");
  listeners.pointerup[0]({ pointerId: 2 });
  delete document.head;
  delete document.getElementById;
  delete document.addEventListener;
  delete document.removeEventListener;
  delete document.querySelector;
  delete context.ResizeObserver;
  context.requestAnimationFrame = () => 0;
});

test("Classic prompt fills its native widget allocation", () => {
  document.head = new TestElement("head");
  document.getElementById = () => null;
  document.querySelector = () => null;
  const textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  textarea.offsetHeight = 322;
  textarea.matches = (selector) => selector === "textarea";
  textarea.closest = () => null;
  const node = makeNode();
  node.widgets.find((item) => item.name === "prompt").element = textarea;
  node.properties.matrixWan3PromptHeight = 322;
  node.size = [430, 900];
  node.computeSize = () => [430, 900];
  node.setSize = function (size) { this.size = size; };
  api.installNativeLayout(node);
  assert.equal(textarea.style.height, "100%");
  assert.equal(node.widgets.find((item) => item.name === "prompt").options.getMinHeight(), 342);
  delete document.head;
  delete document.getElementById;
  delete document.querySelector;
});

test("Classic outer growth does not ratchet the prompt minimum and block shrinking back", () => {
  document.head = new TestElement("head");
  document.getElementById = () => null;
  document.querySelector = () => null;
  const textarea = new TestElement("textarea");
  textarea.classList = { add() {} };
  textarea.offsetHeight = 120;
  textarea.matches = (selector) => selector === "textarea";
  textarea.closest = () => null;
  const node = makeNode();
  const prompt = node.widgets.find((item) => item.name === "prompt");
  prompt.element = textarea;
  node.size = [430, 500];
  node.computeSize = () => [430, 500 + (prompt.options.getMinHeight?.() || 140) - 140];
  node.setSize = function ([width, height]) {
    this.size = [width, Math.max(height, this.computeSize()[1])];
    this.onResize?.(this.size);
  };
  app.canvas = { resizing_node: node };
  api.installNativeLayout(node);
  node.setSize([430, 600]);
  node.setSize([430, 500]);
  assert.equal(node.size[1], 500, "native minimum no longer retains the prior outer growth");
  assert.equal(prompt.options.getMinHeight(), 140);
  delete app.canvas;
  delete document.head;
  delete document.getElementById;
  delete document.querySelector;
});

test("credential verify and disconnect POSTs send their node scope as JSON", async () => {
  fetchCalls.length = 0;
  const node = makeNode();
  await api.request("verify", node);
  await api.request("disconnect", node);
  assert.equal(fetchCalls.length, 2);
  for (const { init } of fetchCalls) {
    assert.equal(init.method, "POST");
    assert.equal(init.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(init.body), { node_id: "scope" });
  }
});

test("disconnect deletes this node's saved key", async () => {
  fetchCalls.length = 0;
  fetchResponses.push({ present: true, source: "saved" }, { disconnected: true });
  const node = makeNode();
  api.modal(node);
  await Promise.resolve();
  const dialog = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  const disconnect = dialog.findButton("Disconnect this node");
  await disconnect.onclick();
  const status = dialog.children[0].children[4];
  assert.match(status.textContent, /Saved key deleted/i);
  assert.equal(fetchCalls[1].init.method, "POST");
  assert.equal(fetchCalls.length, 2);
  dialog.findButton("Close").onclick();
});

test("late initial status cannot replace a saved unverified key", async () => {
  fetchCalls.length = 0;
  let releaseStatus;
  fetchResponses.push(new Promise((resolve) => { releaseStatus = resolve; }), { saved: true });
  const node = makeNode();
  api.modal(node);
  const dialog = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  const input = dialog.children[0].children[3];
  input.value = "test-only-secret";
  dialog.findButton("Save key").onclick();
  assert.equal(input.value, "", "the secret is cleared immediately after submission");
  await Promise.resolve();
  await Promise.resolve();
  releaseStatus({ present: false, source: null });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(dialog.children[0].children[2].textContent, /SAVED.*BALANCE UNCHECKED/);
  assert.match(dialog.children[0].children[4].textContent, /Saved across restarts/);
  assert.equal(dialog.findButton("Disconnect this node").disabled, false);
  dialog.findButton("Close").onclick();
});

test("closing during save and reopening waits for the server mutation before status", async () => {
  fetchCalls.length = 0;
  let releaseSave;
  fetchResponses.push({ present: false, source: null }, new Promise((resolve) => { releaseSave = resolve; }), { present: true, source: "session" });
  const node = makeNode();
  api.modal(node);
  const first = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  await new Promise((resolve) => setTimeout(resolve, 0));
  first.children[0].children[3].value = "test-only-secret";
  first.findButton("Save key").onclick();
  first.findButton("Close").onclick();
  api.modal(node);
  const second = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  assert.equal(second.findButton("Disconnect this node").disabled, true);
  assert.equal(fetchCalls.filter(({ url }) => url.includes("/status")).length, 1, "reopen must wait for in-flight save");
  releaseSave({ saved: true });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(fetchCalls.filter(({ url }) => url.includes("/status")).length, 2);
  assert.match(second.children[0].children[2].textContent, /SAVED.*BALANCE UNCHECKED/);
  assert.equal(second.findButton("Disconnect this node").disabled, false);
  second.findButton("Close").onclick();
});

test("replacement node with the same scope waits for the old node's in-flight save", async () => {
  fetchCalls.length = 0;
  let releaseSave;
  fetchResponses.push({ present: false, source: null }, new Promise((resolve) => { releaseSave = resolve; }), { present: true, source: "session" });
  const oldNode = makeNode();
  api.modal(oldNode);
  const first = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  await new Promise((resolve) => setTimeout(resolve, 0));
  first.children[0].children[3].value = "test-only-secret";
  first.findButton("Save key").onclick();
  first.findButton("Close").onclick();
  const replacement = makeNode();
  api.modal(replacement);
  const second = body.children.find((item) => item.dataset.matrixWan3Credential === "1");
  assert.equal(second.findButton("Disconnect this node").disabled, true);
  assert.equal(fetchCalls.filter(({ url }) => url.includes("/status")).length, 1);
  releaseSave({ saved: true });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(second.children[0].children[2].textContent, /SAVED.*BALANCE UNCHECKED/);
  second.findButton("Close").onclick();
});

test("Random hides the unused numeric seed; Fixed shows the submitted value", () => {
  const node = makeNode();
  api.installSeedProjection(node);
  const mode = node.widgets.find((item) => item.name === "seed_mode");
  const seed = node.widgets.find((item) => item.name === "seed");
  assert.equal(seed.options.min, 1);
  assert.equal(seed.options.max, 9_999);
  api.applyProjection(node, "Text to Video");
  assert.equal(seed.hidden, true);
  seed.value = 0; // A legacy Random workflow may serialize an ignored zero.
  mode.value = "Fixed";
  mode.callback("Fixed");
  assert.equal(seed.hidden, false);
  assert.equal(seed.value, 1, "switching Random to Fixed does not expose an out-of-range ignored value");
  mode.value = "Random";
  mode.callback("Random");
  assert.equal(seed.hidden, true);
});

test("saved Fixed seed zero and large legacy values remain exact", () => {
  const node = makeNode();
  const mode = node.widgets.find((item) => item.name === "seed_mode");
  const seed = node.widgets.find((item) => item.name === "seed");
  mode.value = "Fixed";
  api.preserveLegacyFixedSeed(node, { widgets_values_named: { seed_mode: "Fixed", seed: 0 } });
  assert.equal(seed.value, 0);
  assert.equal(seed.options.min, 0);
  api.installSeedProjection(node);
  mode.callback("Fixed");
  assert.equal(seed.value, 0, "an explicitly saved Fixed zero is preserved");
  api.preserveLegacyFixedSeed(node, { widgets_values_named: { seed_mode: "Fixed", seed: 500_000 } });
  assert.equal(seed.value, 500_000);
  assert.equal(seed.options.max, 500_000);
});

test("current-version workflow restores named values after old seed-policy positional shift", () => {
  const node = makeNode();
  node.properties.matrixWan3 = { schemaVersion: 3 };
  node.widgets.find((item) => item.name === "seed_mode").value = "Random";
  node.widgets.find((item) => item.name === "seed").value = 1;
  node.widgets.find((item) => item.name === "edit_duration").value = false;
  api.migrateLegacyWorkflow(node, {
    widgets_values_named: {
      operation: "Edit Video", seed_mode: "Fixed", seed: 12345,
      control_after_generate: "randomize", edit_duration: 15,
      billing_activation: "wavespeed_v1",
    },
    properties: { matrixWan3: { schemaVersion: 3 } },
  });
  assert.equal(node.widgets.find((item) => item.name === "seed_mode").value, "Fixed");
  assert.equal(node.widgets.find((item) => item.name === "seed").value, 12345);
  assert.equal(node.widgets.find((item) => item.name === "edit_duration").value, 15);
  assert.equal(node.widgets.find((item) => item.name === "billing_activation").value, "wavespeed_v1");
});

test("history reconfiguration restores node-local HALO and key controls without disconnecting a reattached identity", async () => {
  fetchCalls.length = 0;
  const extension = extensions.find((item) => item.name === "matrix.wan3");
  assert.ok(extension, "the production extension is registered");
  function NodeType() {}
  NodeType.prototype.onNodeCreated = function () {};
  await extension.beforeRegisterNodeDef(NodeType, { name: "MATRIX_Wan3" });

  const node = Object.assign(Object.create(NodeType.prototype), makeNode("Reference to Video"));
  node.graph = { _nodes: [], beforeChange() {}, afterChange() {} };
  node.size = [430, 1000];
  node.computeSize = () => [430, 500];
  node.setSize = (size) => { node.size = size; };
  node.addDOMWidget = (name, type, element, options) => {
    element.isConnected = true;
    const widget = { name, type, element, options };
    node.widgets.push(widget);
    return widget;
  };
  node.addWidget = (type, name, value, callback) => {
    const widget = { type, name, value, callback };
    node.widgets.push(widget);
    return widget;
  };
  node.inputs.find((input) => input.name === "operation.reference_images.image_01").link = 77;
  node.graph._nodes.push(node);
  node.onNodeCreated();
  node.onConfigure({ widgets_values_named: { operation: "Reference to Video" }, properties: {} });

  const namedCount = (name) => node.widgets.filter((widget) => widget.name.startsWith(`${name}_`)).length;
  const activeHaloCount = () => haloSurfaces.filter((surface) => surface.node === node && !surface.destroyed).length;
  assert.equal(namedCount("matrix_wan3_halo_brand"), 1);
  assert.equal(namedCount("matrix_wan3_key_status"), 1);
  assert.equal(namedCount("matrix_wan3_new_result"), 0, "Run uses queue identity without a separate generation button");
  assert.equal(activeHaloCount(), 1);

  // LiteGraph history can detach the surviving node while rebuilding the saved graph.
  node.graph._nodes.splice(node.graph._nodes.indexOf(node), 1);
  node.onRemoved();
  node.graph._nodes.push(node);
  node.onAfterGraphConfigured?.();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(namedCount("matrix_wan3_halo_brand"), 1, "the single HALO row is mounted after history restore");
  assert.equal(namedCount("matrix_wan3_key_status"), 1, "the single key row is mounted after history restore");
  assert.equal(activeHaloCount(), 1, "the HALO animation surface is mounted after history restore");
  assert.equal(node.widgets.find((widget) => widget.name.startsWith("matrix_wan3_key_status_")).element.isConnected, true, "the key button is attached after history restore");
  assert.equal(fetchCalls.some(({ url }) => url.endsWith("/disconnect")), false, "history restoration never revokes credentials");
  assert.equal(node.inputs.find((input) => input.name === "operation.reference_images.image_01").link, 77);

  node.graph._nodes.splice(node.graph._nodes.indexOf(node), 1);
  node.onRemoved();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(fetchCalls.filter(({ url }) => url.endsWith("/disconnect")).length, 0, "node removal leaves session credentials for delayed Undo");
});

test("fresh DOM widget names remount all three controls when Vue retains graph/node render keys", () => {
  assert.match(api.ownedWidgetName("key_status"), /^matrix_wan3_key_status_[0-9a-f-]{36}$/);
  const renderReplacement = (candidateApi) => {
    const retainedByKey = new Map();
    const makeDecoratedNode = () => {
      const node = makeNode();
      node.id = 73;
      node.graph = { id: "same-graph", _nodes: [node] };
      node.addDOMWidget = (name, type, element, options) => {
        const widget = { id: randomUUID(), name, type, element, options };
        node.widgets.push(widget);
        return widget;
      };
      candidateApi.installModeProjection(node);
      candidateApi.installHalo(node);
      candidateApi.installKeyControl(node);
      return node;
    };
    const relevant = (node) => node.widgets.filter((widget) => ["operation_notice", "halo_brand", "key_status"].some((role) =>
      widget.name === `matrix_wan3_${role}` || widget.name.startsWith(`matrix_wan3_${role}_`)));
    const render = (node) => {
      for (const widget of relevant(node)) {
        const key = `${node.graph.id}:${node.id}:${widget.name}:${widget.type}`;
        if (!retainedByKey.has(key)) {
          retainedByKey.set(key, widget.element);
          widget.element.isConnected = true;
        }
      }
    };

    const oldNode = makeDecoratedNode();
    render(oldNode);
    const oldWidgets = relevant(oldNode);
    assert.equal(oldWidgets.length, 3, `operation notice, HALO brand, and key control are present (${oldNode.widgets.map((widget) => widget.name).join(", ")})`);
    oldWidgets.forEach((widget) => widget.element.remove());

    const replacement = makeDecoratedNode();
    render(replacement);
    const newWidgets = relevant(replacement);
    return { oldWidgets, newWidgets, attached: newWidgets.map((widget) => widget.element.isConnected) };
  };

  const mounted = renderReplacement(api);
  assert.equal(mounted.newWidgets.length, 3);
  assert.deepEqual(mounted.attached, [true, true, true], "fresh names create fresh graph/node/name/type Vue keys");
  for (let index = 0; index < mounted.oldWidgets.length; index += 1) {
    assert.equal(mounted.oldWidgets[index].element.isConnected, false, "the replaced widget element stays detached");
    assert.notEqual(mounted.oldWidgets[index].id, mounted.newWidgets[index].id, "registry IDs alone already differ");
    assert.notEqual(mounted.oldWidgets[index].name, mounted.newWidgets[index].name, "the render-key name must also differ");
  }

  const staticFactory = "const ownedWidgetName = (role) => `matrix_wan3_${role}_${crypto.randomUUID()}`;";
  assert.ok(source.includes(staticFactory), "counterfactual production-source replacement matches exactly");
  const staticSource = source.replace(staticFactory, "const ownedWidgetName = (role) => `matrix_wan3_${role}`;");
  const staticContext = { ...context, app: { graph: { _nodes: [] }, registerExtension() {} } };
  runInNewContext(`${staticSource}\n${testApiSource}`, staticContext);
  const staticResult = renderReplacement(staticContext.__matrixWan3Tests);
  assert.deepEqual(staticResult.attached, [false, false, false], "static names reproduce the stale Vue-key failure");
});

test("legacy socket IDs map to the DynamicCombo option's nested typed IDs", () => {
  assert.equal(api.dynamicInputName("image"), "operation.image");
  assert.equal(api.dynamicInputName("last_image"), "operation.last_image");
  assert.equal(api.dynamicInputName("video"), "operation.video");
  assert.equal(api.dynamicInputName("reference_image_10"), "operation.reference_images.image_10");
  assert.equal(api.dynamicInputName("reference_video_05"), "operation.reference_videos.video_05");
  assert.equal(api.dynamicInputName("reference_audio_03"), "operation.reference_audios.audio_03");
});
