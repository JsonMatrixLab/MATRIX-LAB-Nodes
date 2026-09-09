import {
  applyHaloSelect,
  createHaloWidgetHost,
  haloMinimumNodeHeight,
  haloWidgetLayoutHeight,
  measureHaloContentHeight,
  mountHaloSurface,
  setHaloNodeSize,
} from "./halo.d64a9a13ccfeb9ce.mjs";

const { app } = globalThis.comfyAPI?.app || {};
const { api } = globalThis.comfyAPI?.api || {};

const NODE_TYPE = "MATRIX_AutoPrompter";
const LOADER_TYPE = "MATRIX_ImageBatchLoader";
const PRESENTATION_WIDGET = "matrixlab_prompt_director_ui";
const CREDENTIAL_PATH = "/matrixlab/prompt-director/v1/credential";
const MODELS_PATH = "/matrixlab/prompt-director/v1/models";
const SESSION_HEADER = "X-Matrix-Credential-Session";
const SESSION_CACHE_KEY = Symbol.for("matrixlab.prompt-director.credential-sessions");
const EMPTY_COLLECTION = Object.freeze({ version: 1, items: Object.freeze([]), selected: null });
const WATCHED_WIDGETS = new Set(["instructions", "system_prompt", "model", "character_trigger"]);
const REQUIRED_WIDGETS = [
  "instructions", "system_prompt", "model", "final_prompt", "generation_state", "character_trigger",
];
const MIN_WIDTH = 430;
const DEFAULT_HEIGHT = 560;
const MAX_CATALOGUE_MODELS = 256;
const COLLECTION_OBSERVER = Symbol.for("matrixlab.prompt-director.collection-observer");
export const CONTROL = Symbol.for("matrixlab.prompt-director.control");

function sessionCache() {
  globalThis[SESSION_CACHE_KEY] ||= new Map();
  return globalThis[SESSION_CACHE_KEY];
}

function sessionStorageKey(host) {
  return `matrixlab.prompt-director.session:${host}`;
}

function readSession(host, storage) {
  const cached = sessionCache().get(host);
  if (typeof cached === "string" && cached) return cached;
  try {
    const value = storage?.getItem?.(sessionStorageKey(host));
    if (typeof value === "string" && value) {
      sessionCache().set(host, value);
      return value;
    }
  } catch {}
  return "";
}

function writeSession(host, storage, value) {
  if (typeof value === "string" && value) {
    sessionCache().set(host, value);
    try { storage?.setItem?.(sessionStorageKey(host), value); } catch {}
  } else {
    sessionCache().delete(host);
    try { storage?.removeItem?.(sessionStorageKey(host)); } catch {}
  }
}

function withSession(headers, session) {
  return session ? { ...headers, [SESSION_HEADER]: session } : { ...headers };
}

export function parseModelCatalogue(payload) {
  if (!payload || !Array.isArray(payload.models) || payload.models.length < 1 ||
      payload.models.length > MAX_CATALOGUE_MODELS) {
    throw new Error(`Model catalogue must contain 1–${MAX_CATALOGUE_MODELS} models.`);
  }
  const ids = payload.models.map((entry) => {
    if (!entry || Array.isArray(entry) || Object.keys(entry).join(",") !== "id" ||
        typeof entry.id !== "string" || !entry.id.trim() || entry.id !== entry.id.trim()) {
      throw new Error("Model catalogue contains an invalid canonical ID.");
    }
    return entry.id;
  });
  if (new Set(ids).size !== ids.length) throw new Error("Model catalogue contains duplicate IDs.");
  if ([...ids].sort().join("\n") !== ids.join("\n")) throw new Error("Model catalogue is not canonical-sorted.");
  if (typeof payload.catalogue_fingerprint !== "string" || !payload.catalogue_fingerprint) {
    throw new Error("Model catalogue fingerprint is missing.");
  }
  return { ids, fingerprint: payload.catalogue_fingerprint };
}

function widgetByName(node, name) {
  return (node?.widgets || []).find((widget) => widget?.name === name);
}

function snapshotWidget(widget) {
  return {
    widget,
    draw: widget.draw,
    computeSize: widget.computeSize,
    callback: widget.callback,
    hadOptions: Object.prototype.hasOwnProperty.call(widget, "options"),
    options: widget.options,
    hidden: widget.options?.hidden,
    hadNativeHidden: Object.prototype.hasOwnProperty.call(widget, "hidden"),
    nativeHidden: widget.hidden,
  };
}

function hideWidget(snapshot) {
  snapshot.widget.options ||= {};
  snapshot.widget.options.hidden = true;
  // Classic's DOM bridge reads widget.hidden, not options.hidden.
  snapshot.widget.hidden = true;
  snapshot.widget.draw = () => {};
  snapshot.widget.computeSize = () => [0, -4];
}

function restoreWidget(snapshot) {
  const { widget } = snapshot;
  widget.draw = snapshot.draw;
  widget.computeSize = snapshot.computeSize;
  if (snapshot.hadNativeHidden) widget.hidden = snapshot.nativeHidden;
  else delete widget.hidden;
  if (widget.callback === snapshot.ownedCallback) widget.callback = snapshot.callback;
  if (snapshot.hadOptions) {
    widget.options = snapshot.options;
    if (widget.options) widget.options.hidden = snapshot.hidden;
  } else delete widget.options;
}

function removePresentation(node, beforeWidgets, presentation) {
  if (!Array.isArray(node?.widgets)) return;
  for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
    const widget = node.widgets[index];
    if (!beforeWidgets.has(widget) &&
        (widget === presentation || widget?.name === PRESENTATION_WIDGET)) node.widgets.splice(index, 1);
  }
}

function inputLink(node, name) {
  return (node?.inputs || []).find((input) => input?.name === name)?.link;
}

function isWidgetLinked(node, name) {
  return (node?.inputs || []).some((input) =>
    (input?.name === name || input?.widget?.name === name) && input.link != null
  );
}

function graphLink(graph, linkId) {
  return graph?.links instanceof Map ? graph.links.get(linkId) : graph?.links?.[linkId];
}

function graphNode(graph, id) {
  return graph?.getNodeById?.(id) || graph?._nodes_by_id?.[id] ||
    (graph?._nodes || []).find((node) => node?.id === id);
}

export function parseReferenceCollection(value) {
  if (typeof value !== "string") throw new Error("Reference collection is not saved JSON.");
  let data;
  try { data = JSON.parse(value); }
  catch { throw new Error("Reference collection is invalid JSON."); }
  if (!data || Array.isArray(data) || typeof data !== "object" ||
      Object.keys(data).sort().join(",") !== "items,selected,version" || data.version !== 1 ||
      !Array.isArray(data.items)) throw new Error("Reference collection has an unsupported shape.");
  if (data.items.length > 10) throw new Error("Auto Prompter accepts at most 10 reference images.");
  const seen = new Set();
  const items = data.items.map((item, index) => {
    if (!item || Array.isArray(item) || typeof item !== "object" ||
        Object.keys(item).join(",") !== "image" || typeof item.image !== "string" ||
        !item.image.endsWith(" [input]") || !item.image.slice(0, -8)) {
      throw new Error(`Reference ${index + 1} has an invalid image identity.`);
    }
    if (seen.has(item.image)) throw new Error(`Reference ${index + 1} is duplicated.`);
    seen.add(item.image);
    return { image: item.image };
  });
  if (data.selected !== null &&
      (!Number.isInteger(data.selected) || data.selected < 0 || data.selected >= items.length)) {
    throw new Error("Reference collection selection is invalid.");
  }
  return { version: 1, items, selected: data.selected };
}

export function resolveReferenceCollection(node, application = app) {
  const linkId = inputLink(node, "images");
  if (linkId == null) return { collection: EMPTY_COLLECTION, widget: null };
  const graph = node?.graph || application?.graph;
  const link = graphLink(graph, linkId);
  const originId = link?.origin_id ?? link?.originId;
  const originSlot = link?.origin_slot ?? link?.originSlot;
  const origin = graphNode(graph, originId);
  if ((origin?.comfyClass || origin?.type) === "LoadImage") {
    if (Number(originSlot) !== 0 || origin.outputs?.[originSlot]?.type === "MASK") {
      throw new Error("Connect the Load Image IMAGE output, not its mask.");
    }
    const imageWidget = widgetByName(origin, "image");
    if (!imageWidget || isWidgetLinked(origin, "image")) {
      throw new Error("Choose a local file in Load Image before generating.");
    }
    const filename = String(imageWidget.value ?? "").replace(/\\/g, "/");
    if (!filename || / \[(?:output|temp)\]$/.test(filename)) {
      throw new Error("Choose an input image in Load Image before generating.");
    }
    const identity = filename.endsWith(" [input]") ? filename : `${filename} [input]`;
    return {
      collection: parseReferenceCollection(JSON.stringify({version: 1, items: [{image: identity}], selected: 0})),
      widget: imageWidget,
    };
  }
  if (!origin || (origin.comfyClass || origin.type) !== LOADER_TYPE) {
    throw new Error("Connect IMAGE directly from Load Image or MATRIX IMAGE BATCH LOADER. Other upstream images must first be saved as input files.");
  }
  const output = origin.outputs?.[originSlot];
  if (output?.name && output.name !== "images") {
    throw new Error("Connect the Image Batch Loader images output.");
  }
  const collectionWidget = widgetByName(origin, "collection");
  if (!collectionWidget) throw new Error("Connected Image Batch Loader has no collection state.");
  return { collection: parseReferenceCollection(collectionWidget.value), widget: collectionWidget };
}

function observeCollection(widget, listener) {
  if (!widget || typeof listener !== "function") return () => {};
  let state = widget[COLLECTION_OBSERVER];
  if (!state) {
    state = { original: widget.callback, listeners: new Set(), dispatcher: null };
    state.dispatcher = function (...args) {
      let result;
      try { result = state.original?.apply(this, args); }
      finally { for (const callback of [...state.listeners]) callback(); }
      return result;
    };
    widget[COLLECTION_OBSERVER] = state;
    widget.callback = state.dispatcher;
  }
  state.listeners.add(listener);
  return () => {
    state.listeners.delete(listener);
    if (state.listeners.size) return;
    if (widget.callback === state.dispatcher) widget.callback = state.original;
    if (widget[COLLECTION_OBSERVER] === state) delete widget[COLLECTION_OBSERVER];
  };
}

function generationState(value) {
  try {
    const state = JSON.parse(String(value || "{}"));
    return state && !Array.isArray(state) && typeof state === "object" ? state : {};
  } catch { return {}; }
}

function requestSnapshot(collection, widgets) {
  return JSON.stringify({
    collection,
    instructions: String(widgets.instructions.value ?? ""),
    system_prompt: String(widgets.system_prompt.value ?? ""),
    model: String(widgets.model.value ?? ""),
    character_trigger: String(widgets.character_trigger.value ?? ""),
  });
}

async function textFingerprint(value) {
  const text = String(value ?? "");
  const subtle = globalThis.crypto?.subtle;
  if (!subtle?.digest || typeof TextEncoder !== "function") {
    let first = 0x811c9dc5;
    let second = 0x9e3779b9;
    for (let index = 0; index < text.length; index += 1) {
      const unit = text.charCodeAt(index);
      first = Math.imul(first ^ unit, 0x01000193) >>> 0;
      second = Math.imul(second ^ unit, 0x85ebca6b) >>> 0;
    }
    return `revision:${text.length}:${first.toString(16).padStart(8, "0")}${second.toString(16).padStart(8, "0")}`;
  }
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(text));
  return `sha256:${[...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

function responseError(payload, response, fallback) {
  if (typeof payload?.error === "string" && payload.error) return payload.error;
  if (typeof payload?.error?.message === "string" && payload.error.message) return payload.error.message;
  if (typeof payload?.message === "string" && payload.message) return payload.message;
  return response?.status ? `${fallback} (${response.status})` : fallback;
}

function addStyle(doc, root) {
  const style = doc.createElement("style");
  style.textContent = `
.matrixlab-director [hidden]{display:none!important}
.matrixlab-director__output-header{display:flex;align-items:center;gap:8px}.matrixlab-director__output-header>span:first-child{flex:1}.matrixlab-director .matrixlab-director__copy{display:inline-flex;align-items:center;justify-content:center;flex:0 0 28px;width:28px;min-height:28px;padding:4px;border-radius:6px;letter-spacing:0}.matrixlab-director__copy-status{font-size:10px;line-height:14px;max-width:65%;overflow-wrap:anywhere}
.matrixlab-director{position:relative;z-index:2;display:grid;grid-auto-rows:max-content;align-content:start;margin:0 7px;padding:18px 16px;gap:8px;color:#EDF8F0;font:400 13px/19.5px "Cascadia Mono","Cascadia Code",Consolas,"Liberation Mono",monospace;font-variant-ligatures:none;box-sizing:border-box}
.matrixlab-director *{box-sizing:border-box;font:inherit}.matrixlab-director__eyebrow{color:#ABC0B1;font-size:9px;line-height:13.5px;letter-spacing:1px;text-transform:uppercase}.matrixlab-director__references{display:flex;justify-content:space-between;gap:8px;color:#97AA9C;font-size:10px;line-height:16px}.matrixlab-director__count{color:#5CF2A5}
.matrixlab-director label{display:grid;gap:5px;color:#ABC0B1;font-size:11px;line-height:16.5px}.matrixlab-director label[data-linked="true"]::after{content:"LINKED";color:#97AA9C;font-size:9px;line-height:13.5px}.matrixlab-director textarea,.matrixlab-director input{width:100%;min-height:38px;border:1px solid #31543C;border-radius:9px;padding:8px 10px;background:linear-gradient(125deg,#172B1EDF 0%,#0B1710ED 100%);color:#EDF8F0;text-align:left;direction:ltr}.matrixlab-director .matrixlab-halo-select{width:100%;min-height:38px;padding:8px 10px}.matrixlab-director textarea:disabled,.matrixlab-director input:disabled{border-color:#34513E;background:#0C1710;color:#97AA9C}.matrixlab-director textarea{resize:vertical;min-height:76px}.matrixlab-director__output textarea{min-height:116px}.matrixlab-director textarea:focus-visible,.matrixlab-director input:focus-visible,.matrixlab-director button:focus-visible,.matrixlab-director summary:focus-visible{outline:2px solid #FFCA6B;outline-offset:4px}
.matrixlab-director button{min-height:40px;border:1px solid #00FF41;border-radius:10px;padding:0 12px;background:linear-gradient(180deg,#173E24 0%,#0B2113 100%);color:#BDFFD0;letter-spacing:1px;text-transform:uppercase;cursor:pointer}.matrixlab-director button:disabled{opacity:.38;cursor:default}.matrixlab-director__actions{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.matrixlab-director__recover{min-width:96px;border-color:#31543C;text-transform:none;letter-spacing:0}
.matrixlab-director__credential{display:grid;gap:8px;padding:10px;border:1px solid #21492B;border-radius:9px;background:#08170BDE}.matrixlab-director__credential-status{color:#97AA9C;font-size:10px;line-height:16px;overflow-wrap:anywhere}.matrixlab-director__key-row,.matrixlab-director__model-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:8px}.matrixlab-director__credential-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.matrixlab-director__key-row button,.matrixlab-director__model-row button,.matrixlab-director__change{min-height:38px;border-color:#31543C;text-transform:none;letter-spacing:0}.matrixlab-director__change{width:100%;min-width:0}.matrixlab-director__model-error{color:#FF6B5A;font-size:10px;line-height:16px}.matrixlab-director__model-row label[data-invalid="true"] select{border-color:#FF6B5A;background:#26110F}
.matrixlab-director details{border:1px solid #21492B;border-radius:9px;padding:8px 10px;background:#08170BDE}.matrixlab-director summary{cursor:pointer;color:#97AA9C;font-size:10px;line-height:16px}.matrixlab-director__advanced{display:grid;gap:8px;padding-top:10px}.matrixlab-director__status{min-height:30px;padding:7px 9px;border:1px solid #24462E;border-radius:8px;background:#08170BDE;color:#94C69E;font-size:10px;line-height:16px;overflow-wrap:anywhere}.matrixlab-director__status[data-error="true"]{border-color:#FF6B5A;background:#26110F;color:#FF6B5A}.matrixlab-director__status[data-stale="true"]{border-color:#FFCA6B;background:#241B0D;color:#FFCA6B}
`;
  root.appendChild(style);
}

function makeLabel(doc, text, control, className = "") {
  const label = doc.createElement("label");
  if (className) label.className = className;
  const span = doc.createElement("span");
  span.textContent = text;
  label.append(span, control);
  return label;
}

function uuid(randomUUID) {
  const value = randomUUID?.() || globalThis.crypto?.randomUUID?.();
  if (typeof value !== "string" || !value) throw new Error("A request ID could not be created.");
  return value;
}

export function mountPromptDirector(node, options = {}) {
  if (node?.[CONTROL]) { node[CONTROL].render(); return node[CONTROL]; }
  if ((node?.comfyClass || node?.type) !== NODE_TYPE || typeof node?.addDOMWidget !== "function") return null;
  const doc = options.document || globalThis.document;
  const service = options.api || api;
  const application = options.app || app;
  if (!doc?.createElement || typeof service?.fetchApi !== "function") return null;
  const widgets = Object.fromEntries(REQUIRED_WIDGETS.map((name) => [name, widgetByName(node, name)]));
  if (REQUIRED_WIDGETS.some((name) => !widgets[name])) return null;

  const beforeWidgets = new Set(node.widgets || []);
  const snapshots = REQUIRED_WIDGETS.map((name) => snapshotWidget(widgets[name]));
  const previousResize = node.onResize;
  const previousRemoved = node.onRemoved;
  const previousConfigure = node.onConfigure;
  const previousConnectionsChange = node.onConnectionsChange;
  const root = doc.createElement("div");
  root.className = "matrixlab-director";
  root.style.width = `${MIN_WIDTH}px`;
  root.style.maxWidth = "100%";
  root.style.minWidth = "0";
  const host = createHaloWidgetHost(root, doc);
  if (!host) return null;
  host.style.alignItems = "center";
  host.style.justifyContent = "center";
  addStyle(doc, root);

  const eyebrow = doc.createElement("div");
  eyebrow.className = "matrixlab-director__eyebrow";
  eyebrow.textContent = node.title;
  const references = doc.createElement("div");
  references.className = "matrixlab-director__references";
  const referenceLabel = doc.createElement("span");
  referenceLabel.textContent = "1–10 reference images";
  const referenceCount = doc.createElement("span");
  referenceCount.className = "matrixlab-director__count";
  references.append(referenceLabel, referenceCount);
  const credentialPanel = doc.createElement("section");
  credentialPanel.className = "matrixlab-director__credential";
  const credentialStatus = doc.createElement("div");
  credentialStatus.className = "matrixlab-director__credential-status";
  credentialStatus.setAttribute("aria-live", "polite");
  const keyRow = doc.createElement("div");
  keyRow.className = "matrixlab-director__key-row";
  const keyInput = doc.createElement("input");
  keyInput.type = "password";
  keyInput.autocomplete = "off";
  keyInput.spellcheck = false;
  keyInput.setAttribute("aria-label", "xAI API key");
  const connect = doc.createElement("button");
  connect.type = "button";
  connect.dataset.action = "connect-key";
  connect.textContent = "Connect / Verify";
  keyRow.append(keyInput, connect);
  const changeKey = doc.createElement("button");
  changeKey.type = "button";
  changeKey.dataset.action = "change-key";
  changeKey.className = "matrixlab-director__change";
  changeKey.textContent = "Change";
  const disconnect = doc.createElement("button");
  disconnect.type = "button";
  disconnect.dataset.action = "disconnect-key";
  disconnect.className = "matrixlab-director__change";
  disconnect.textContent = "Disconnect";
  const credentialActions = doc.createElement("div");
  credentialActions.className = "matrixlab-director__credential-actions";
  credentialActions.append(changeKey, disconnect);
  credentialPanel.append(credentialStatus, keyRow, credentialActions);
  const instructions = doc.createElement("textarea");
  const instructionLabel = makeLabel(doc, "Instructions", instructions);
  const actions = doc.createElement("div");
  actions.className = "matrixlab-director__actions";
  const generate = doc.createElement("button");
  generate.type = "button";
  generate.dataset.action = "generate";
  generate.textContent = "Generate Prompt";
  const recover = doc.createElement("button");
  recover.type = "button";
  recover.dataset.action = "recover";
  recover.className = "matrixlab-director__recover";
  recover.textContent = "Recover";
  actions.append(generate, recover);
  const finalPrompt = doc.createElement("textarea");
  const finalLabel = makeLabel(doc, "Final prompt", finalPrompt, "matrixlab-director__output");
  const finalHeader = doc.createElement("div");
  finalHeader.className = "matrixlab-director__output-header";
  const copyPrompt = doc.createElement("button");
  copyPrompt.type = "button";
  copyPrompt.dataset.action = "copy-prompt";
  copyPrompt.className = "matrixlab-director__copy";
  copyPrompt.title = "Copy final prompt";
  copyPrompt.setAttribute("aria-label", "Copy final prompt");
  copyPrompt.innerHTML = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>';
  const copyStatus = doc.createElement("span");
  copyStatus.className = "matrixlab-director__copy-status";
  copyStatus.setAttribute("role", "status");
  copyStatus.setAttribute("aria-live", "polite");
  const finalTitle = finalLabel.firstChild;
  finalLabel.removeChild(finalTitle);
  finalHeader.append(finalTitle, copyStatus, copyPrompt);
  finalLabel.replaceChildren(finalHeader, finalPrompt);
  const modelRow = doc.createElement("div");
  modelRow.className = "matrixlab-director__model-row";
  const model = applyHaloSelect(doc.createElement("select"));
  const modelLabel = makeLabel(doc, "Model", model);
  const refreshModelsButton = doc.createElement("button");
  refreshModelsButton.type = "button";
  refreshModelsButton.dataset.action = "refresh-models";
  refreshModelsButton.textContent = "Refresh Models";
  modelRow.append(modelLabel, refreshModelsButton);
  const modelErrorRow = doc.createElement("div");
  modelErrorRow.className = "matrixlab-director__model-error";
  const advanced = doc.createElement("details");
  const summary = doc.createElement("summary");
  summary.textContent = "Advanced";
  const advancedBody = doc.createElement("div");
  advancedBody.className = "matrixlab-director__advanced";
  const systemPrompt = doc.createElement("textarea");
  const characterTrigger = doc.createElement("input");
  characterTrigger.type = "text";
  const systemLabel = makeLabel(doc, "System prompt", systemPrompt);
  const triggerLabel = makeLabel(doc, "Character trigger", characterTrigger);
  advancedBody.append(systemLabel, triggerLabel);
  advanced.append(summary, advancedBody);
  const status = doc.createElement("div");
  status.className = "matrixlab-director__status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  root.append(eyebrow, references, credentialPanel, instructionLabel, modelRow, modelErrorRow,
    actions, finalLabel, advanced, status);

  let presentation = null;
  let halo = null;
  let destroyed = false;
  let pending = null;
  let resizeTimer = null;
  let sizingObserver = null;
  let unobserveCollection = () => {};
  let observedWidget = null;
  let suppressStale = false;
  let collectionError = "";
  let actionError = "";
  let copying = false;
  let copiedText = null;
  let copyNoticeTimer = null;
  const textPreviews = new Map();
  let credentialError = "";
  let modelError = "";
  let credential = { configured: false, verified: false, source: "", tail: "", persistence: "none" };
  let credentialEditing = true;
  let modelIds = [];
  let catalogueFingerprint = "";
  let credentialController = null;
  let catalogueController = null;
  let credentialEpoch = 0;
  let catalogueEpoch = 0;
  const browserStorage = options.sessionStorage || globalThis.sessionStorage;
  const comfyHost = String(options.comfyHost || globalThis.location?.origin || service.apiURL?.("/") || "comfyui");
  let credentialSession = readSession(comfyHost, browserStorage);

  const acceptCredential = (payload) => {
    if (!payload || typeof payload.configured !== "boolean" || typeof payload.verified !== "boolean" ||
        typeof payload.source !== "string" || typeof payload.tail !== "string" ||
        typeof payload.session !== "string") throw new Error("Credential service returned an invalid status.");
    credential = {
      configured: payload.configured,
      verified: payload.verified,
      source: payload.source,
      tail: payload.tail,
      persistence: typeof payload.persistence === "string" ? payload.persistence : "none",
    };
    credentialSession = payload.session;
    writeSession(comfyHost, browserStorage, credentialSession);
    credentialEditing = !(credential.configured && credential.verified);
  };

  const invokeWidget = (widget, value, event) => {
    widget.value = value;
    widget.callback?.call(widget, value, application?.canvas || null, node, node.pos, event);
  };
  const writeState = (value, event) => {
    suppressStale = true;
    try { invokeWidget(widgets.generation_state, JSON.stringify(value), event); }
    finally { suppressStale = false; }
  };
  const markStale = (reason = "Inputs changed") => {
    if (destroyed || suppressStale) return;
    const prior = generationState(widgets.generation_state.value);
    if (!prior.request_id && !String(widgets.final_prompt.value || "")) return;
    const unresolved = ["submitting", "pending", "indeterminate"].includes(prior.state);
    writeState({ version: 1, ...prior, state: unresolved ? prior.state : "stale", reason });
  };
  const bindCollectionObserver = (widget) => {
    if (widget === observedWidget) return;
    unobserveCollection();
    observedWidget = widget;
    unobserveCollection = observeCollection(widget, () => {
      actionError = "";
      markStale("Reference images changed");
      render();
    });
  };
  const currentCollection = () => {
    const resolved = resolveReferenceCollection(node, application);
    bindCollectionObserver(resolved.widget);
    return resolved.collection;
  };
  const syncControl = (control, widget) => {
    if (doc.activeElement !== control) control.value = String(widget.value ?? "");
  };
  let modelOptionsKey = "";
  const rebuildModelOptions = () => {
    const selected = String(widgets.model.value ?? "");
    const optionsKey = JSON.stringify([modelIds, modelIds.includes(selected) ? "" : selected]);
    if (optionsKey === modelOptionsKey) { model.value = selected; return; }
    modelOptionsKey = optionsKey;
    while (model.firstChild) model.removeChild(model.firstChild);
    if (!model.firstChild && Array.isArray(model.children)) model.children.splice(0, model.children.length);
    if (selected && !modelIds.includes(selected)) {
      const missing = doc.createElement("option");
      missing.value = selected;
      missing.textContent = `Unavailable: ${selected}`;
      model.appendChild(missing);
    }
    for (const id of modelIds) {
      const option = doc.createElement("option");
      option.value = id;
      option.textContent = id;
      model.appendChild(option);
    }
    model.value = selected;
  };
  const render = () => {
    if (destroyed) return;
    copyPrompt.disabled = copying || !String(widgets.final_prompt.value ?? "").trim();
    if (copiedText !== String(widgets.final_prompt.value ?? "")) copyStatus.textContent = "";
    syncControl(instructions, widgets.instructions);
    syncControl(systemPrompt, widgets.system_prompt);
    syncControl(characterTrigger, widgets.character_trigger);
    syncControl(finalPrompt, widgets.final_prompt);
    // Project saved text into the native text viewer without executing downstream work.
    // Other STRING consumers receive the exact same value on normal graph execution.
    const connectedPreviews = new Set();
    for (const linkId of node.outputs?.[0]?.links || []) {
      const link = graphLink(node.graph || application?.graph, linkId);
      const target = graphNode(node.graph || application?.graph, link?.target_id ?? link?.targetId);
      if ((target?.comfyClass || target?.type) !== "PreviewAny" || typeof target.onExecuted !== "function") continue;
      connectedPreviews.add(target);
      const text = String(widgets.final_prompt.value ?? "");
      if (textPreviews.get(target) === text) continue;
      textPreviews.set(target, text);
      try { target.onExecuted({text: [text]}); }
      catch { textPreviews.delete(target); }
    }
    for (const target of textPreviews.keys()) if (!connectedPreviews.has(target)) textPreviews.delete(target);
    rebuildModelOptions();
    let count = null;
    try { count = currentCollection().items.length; collectionError = ""; }
    catch (error) { collectionError = error?.message || String(error); bindCollectionObserver(null); }
    referenceCount.textContent = count == null ? "Invalid source" : count ? `${count} connected` : "0 connected · at least 1 required";
    const state = generationState(widgets.generation_state.value);
    const busy = Boolean(pending);
    const credentialReady = credential.configured && credential.verified;
    const modelReady = modelIds.includes(String(widgets.model.value ?? ""));
    const actionLinked = REQUIRED_WIDGETS.some((name) => isWidgetLinked(node, name));
    const blockedOutcome = ["submitting", "pending", "indeterminate"].includes(state.state);
    const linkedControls = [
      [instructions, instructionLabel, "instructions"], [systemPrompt, systemLabel, "system_prompt"],
      [model, modelLabel, "model"], [finalPrompt, finalLabel, "final_prompt"],
      [characterTrigger, triggerLabel, "character_trigger"],
    ];
    for (const [element, label, name] of linkedControls) {
      const linked = isWidgetLinked(node, name);
      element.disabled = linked;
      label.dataset.linked = String(linked);
    }
    model.disabled = Boolean(catalogueController) || !credentialReady || isWidgetLinked(node, "model");
    modelLabel.dataset.invalid = String(credentialReady && !modelReady);
    modelErrorRow.textContent = modelError || (credentialReady && !modelReady
      ? `Selected model is unavailable: ${String(widgets.model.value ?? "")}` : "");
    refreshModelsButton.disabled = Boolean(catalogueController) || !credential.configured;
    connect.disabled = busy || blockedOutcome || Boolean(credentialController) || !String(keyInput.value || "").trim();
    changeKey.disabled = busy || blockedOutcome || Boolean(credentialController);
    disconnect.disabled = changeKey.disabled;
    disconnect.hidden = !credential.configured;
    const connected = credentialReady;
    keyRow.hidden = connected && !credentialEditing;
    changeKey.hidden = !connected || credentialEditing;
    credentialStatus.textContent = credentialError || (connected
      ? `Connected · ••••${credential.tail || ""} · ${credential.source || "credential"} · ${credential.persistence}`
      : "Enter an xAI API key or use a configured environment key.");
    generate.disabled = busy || Boolean(credentialController) || Boolean(catalogueController) || count == null || count === 0 || actionLinked || blockedOutcome ||
      !credentialReady || !modelReady;
    recover.hidden = !state.request_id || !["submitting", "pending", "indeterminate"].includes(state.state);
    recover.disabled = busy || isWidgetLinked(node, "final_prompt") || isWidgetLinked(node, "generation_state");
    status.dataset.error = String(Boolean(collectionError || actionError || ["failed", "indeterminate"].includes(state.state)));
    status.dataset.stale = String(state.state === "stale");
    if (collectionError) status.textContent = collectionError;
    else if (credentialError) status.textContent = credentialError;
    else if (modelError) status.textContent = modelError;
    else if (actionError) status.textContent = actionError;
    else if (busy) status.textContent = pending.kind === "recover" ? "Checking saved request…" : "Generating prompt…";
    else if (state.state === "complete") status.textContent = state.manual_edit_preserved ? "Complete · manual prompt preserved" : "Prompt ready";
    else if (state.state === "stale") status.textContent = state.reason || "Prompt is stale; generate when ready.";
    else if (state.state === "failed") status.textContent = state.error || "The provider definitively rejected or could not complete the request.";
    else if (state.state === "indeterminate") status.textContent = state.error || "Request outcome is uncertain. Recover it explicitly.";
    else if (state.state === "pending" || state.state === "submitting") status.textContent = "Request may still be pending. Recover it explicitly.";
    else status.textContent = "A normal graph run reuses the saved final prompt.";
  };

  const jsonResponse = async (response, fallback) => {
    const payload = await response?.json?.();
    if (!response?.ok) throw new Error(responseError(payload, response, fallback));
    return payload;
  };

  const refreshModels = async () => {
    if (destroyed || catalogueController || !credential.configured) return;
    const epoch = ++catalogueEpoch;
    const credentialEpochAtStart = credentialEpoch;
    const credentialSessionAtStart = credentialSession;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    catalogueController = controller || { abort() {} };
    modelError = "";
    render();
    try {
      const response = await service.fetchApi(MODELS_PATH, {
        method: "GET",
        headers: withSession({ "X-Matrix-Prompt-Intent": "generate-v1" }, credentialSession),
        signal: controller?.signal,
      });
      const payload = await jsonResponse(response, "Model catalogue could not be loaded");
      if (destroyed || epoch !== catalogueEpoch || credentialEpochAtStart !== credentialEpoch ||
          credentialSessionAtStart !== credentialSession) return;
      acceptCredential(payload.credential);
      const parsed = parseModelCatalogue(payload);
      modelIds = parsed.ids;
      catalogueFingerprint = parsed.fingerprint;
    } catch (error) {
      if (destroyed || error?.name === "AbortError" || epoch !== catalogueEpoch) return;
      modelIds = [];
      catalogueFingerprint = "";
      modelError = error?.message || String(error);
    } finally {
      if (epoch === catalogueEpoch) catalogueController = null;
      render();
    }
  };

  const refreshCredentialStatus = async () => {
    if (destroyed) return;
    credentialController?.abort?.();
    const epoch = ++credentialEpoch;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    credentialController = controller || { abort() {} };
    credentialError = "";
    render();
    try {
      const response = await service.fetchApi(CREDENTIAL_PATH, {
        method: "GET",
        headers: withSession({ "X-Matrix-Credential-Intent": "status-v1" }, credentialSession),
        signal: controller?.signal,
      });
      const payload = await jsonResponse(response, "Credential status could not be loaded");
      if (destroyed || epoch !== credentialEpoch) return;
      acceptCredential(payload);
      if (credential.configured) await refreshModels();
      else { modelIds = []; catalogueFingerprint = ""; }
    } catch (error) {
      if (destroyed || error?.name === "AbortError" || epoch !== credentialEpoch) return;
      credentialError = error?.message || String(error);
      modelIds = [];
      catalogueFingerprint = "";
    } finally {
      if (epoch === credentialEpoch) credentialController = null;
      render();
    }
  };

  const connectCredential = async () => {
    if (destroyed || credentialController) return;
    if (pending || ["submitting", "pending", "indeterminate"].includes(generationState(widgets.generation_state.value).state)) {
      credentialError = "Recover the prior request before changing credentials.";
      render();
      return;
    }
    const key = String(keyInput.value || "").trim();
    if (!key) { credentialError = "Enter an API key before connecting."; render(); return; }
    catalogueEpoch += 1;
    catalogueController?.abort?.();
    catalogueController = null;
    const epoch = ++credentialEpoch;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    credentialController = controller || { abort() {} };
    credentialError = "";
    const body = JSON.stringify({ key });
    keyInput.value = "";
    render();
    try {
      const response = await service.fetchApi(CREDENTIAL_PATH, {
        method: "POST",
        headers: withSession({
          "Content-Type": "application/json",
          "X-Matrix-Credential-Intent": "set-v1",
        }, credentialSession),
        body,
        signal: controller?.signal,
      });
      const payload = await jsonResponse(response, "API key verification failed");
      if (destroyed || epoch !== credentialEpoch) return;
      acceptCredential(payload);
      if (!(credential.configured && credential.verified)) throw new Error("API key was not verified.");
      modelIds = [];
      catalogueFingerprint = "";
      await refreshModels();
    } catch (error) {
      if (destroyed || error?.name === "AbortError" || epoch !== credentialEpoch) return;
      credentialEditing = true;
      credentialError = error?.message || String(error);
    } finally {
      if (epoch === credentialEpoch) credentialController = null;
      render();
    }
  };

  const disconnectCredential = async () => {
    if (destroyed || pending || credentialController ||
        ["submitting", "pending", "indeterminate"].includes(generationState(widgets.generation_state.value).state)) return;
    catalogueEpoch += 1;
    catalogueController?.abort?.();
    catalogueController = null;
    const epoch = ++credentialEpoch;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    credentialController = controller || { abort() {} };
    credentialError = "";
    keyInput.value = "";
    render();
    try {
      const response = await service.fetchApi(`${CREDENTIAL_PATH}/disconnect`, {
        method: "POST",
        headers: withSession({ "X-Matrix-Credential-Intent": "disconnect-v1" }, credentialSession),
        signal: controller?.signal,
      });
      const payload = await jsonResponse(response, "Credential could not be disconnected");
      if (destroyed || epoch !== credentialEpoch) return;
      acceptCredential(payload);
      modelIds = [];
      catalogueFingerprint = "";
      modelError = "";
    } catch (error) {
      if (destroyed || error?.name === "AbortError" || epoch !== credentialEpoch) return;
      credentialError = error?.message || String(error);
    } finally {
      if (epoch === credentialEpoch) credentialController = null;
      render();
    }
  };

  const commitText = (element, widget, event, stale = false) => {
    actionError = "";
    invokeWidget(widget, element.value, event);
    if (stale) markStale();
    render();
  };
  const listeners = [
    [instructions, "change", (event) => commitText(instructions, widgets.instructions, event, true)],
    [systemPrompt, "change", (event) => commitText(systemPrompt, widgets.system_prompt, event, true)],
    [model, "change", (event) => commitText(model, widgets.model, event, true)],
    [characterTrigger, "change", (event) => commitText(characterTrigger, widgets.character_trigger, event, true)],
    [finalPrompt, "input", (event) => commitText(finalPrompt, widgets.final_prompt, event, false)],
    [keyInput, "input", render],
    [copyPrompt, "click", async (event) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      const text = String(widgets.final_prompt.value ?? "");
      if (destroyed || copying || !text.trim()) return;
      copying = true;
      copiedText = text;
      clearTimeout(copyNoticeTimer);
      copyNoticeTimer = null;
      copyStatus.textContent = "";
      render();
      try {
        const clipboard = options.clipboard || globalThis.navigator?.clipboard;
        if (!clipboard?.writeText) throw new Error("Clipboard unavailable");
        await clipboard.writeText(text);
        if (!destroyed && text === String(widgets.final_prompt.value ?? "")) {
          copyStatus.textContent = "Copied";
          copyNoticeTimer = setTimeout(() => {
            copyNoticeTimer = null;
            if (!destroyed) copyStatus.textContent = "";
          }, 3000);
        }
      } catch {
        if (!destroyed && text === String(widgets.final_prompt.value ?? "")) copyStatus.textContent = "Copy failed — select text and copy manually";
      } finally {
        copying = false;
        if (!destroyed) render();
      }
    }],
  ];
  for (const [element, type, listener] of listeners) element.addEventListener(type, listener);
  const changeCredential = () => {
    if (destroyed || pending || credentialController ||
        ["submitting", "pending", "indeterminate"].includes(generationState(widgets.generation_state.value).state)) return;
    credentialEditing = true; credentialError = ""; render(); keyInput.focus?.();
  };
  connect.addEventListener("click", connectCredential);
  changeKey.addEventListener("click", changeCredential);
  disconnect.addEventListener("click", disconnectCredential);
  refreshModelsButton.addEventListener("click", refreshModels);

  const applyCompleted = async (payload, requestId, requestMeta, event) => {
    const prompt = payload?.prompt ?? payload?.final_prompt;
    if (!payload || payload.request_id !== requestId || typeof prompt !== "string") {
      throw new Error("Prompt service returned an invalid response.");
    }
    let capturedInputs = "";
    try { capturedInputs = requestSnapshot(currentCollection(), widgets); }
    catch {}
    const capturedOutput = String(widgets.final_prompt.value ?? "");
    const currentInputs = await textFingerprint(capturedInputs);
    const currentOutput = await textFingerprint(capturedOutput);
    if (destroyed || pending?.requestId !== requestId ||
        isWidgetLinked(node, "final_prompt") || isWidgetLinked(node, "generation_state")) return;
    let inputsUnchanged = false;
    try { inputsUnchanged = capturedInputs === requestSnapshot(currentCollection(), widgets); }
    catch {}
    const inputChanged = !inputsUnchanged || !requestMeta.input_fingerprint || currentInputs !== requestMeta.input_fingerprint;
    const preserveManual = String(widgets.final_prompt.value ?? "") !== capturedOutput ||
      !requestMeta.output_fingerprint || currentOutput !== requestMeta.output_fingerprint;
    const fingerprint = typeof payload.fingerprint === "string" ? payload.fingerprint : "";
    if (inputChanged) {
      writeState({ version: 1, request_id: requestId, state: "stale", fingerprint,
        input_fingerprint: requestMeta.input_fingerprint, output_fingerprint: requestMeta.output_fingerprint,
        reason: "Inputs changed while this request was running" }, event);
      return;
    }
    if (!preserveManual) invokeWidget(widgets.final_prompt, prompt, event);
    writeState({ version: 1, request_id: requestId, state: "complete", fingerprint,
      input_fingerprint: requestMeta.input_fingerprint, output_fingerprint: requestMeta.output_fingerprint,
      manual_edit_preserved: preserveManual }, event);
  };

  const submit = async (event) => {
    if (pending || destroyed || credentialController || catalogueController) return;
    const savedBeforeSubmit = generationState(widgets.generation_state.value);
    if (["submitting", "pending", "indeterminate"].includes(savedBeforeSubmit.state)) {
      actionError = "Recover the prior request before starting another paid request.";
      render();
      return;
    }
    if (!(credential.configured && credential.verified)) {
      credentialError = "Connect and verify an xAI credential before generating.";
      render();
      return;
    }
    if (!modelIds.includes(String(widgets.model.value ?? ""))) {
      modelError = `Selected model is unavailable: ${String(widgets.model.value ?? "")}`;
      render();
      return;
    }
    pending = { kind: "preparing", controller: null, requestId: null };
    render();
    let collection;
    let requestId;
    try {
      collection = currentCollection();
      if (!collection.items.length) throw new Error("Add 1–10 reference images before generating.");
      if (REQUIRED_WIDGETS.some((name) => isWidgetLinked(node, name))) {
        throw new Error("Disconnect linked Auto Prompter fields before generating.");
      }
      requestId = uuid(options.randomUUID);
    }
    catch (error) {
      pending = null;
      actionError = error?.message || String(error);
      render();
      return;
    }
    const capturedInputs = requestSnapshot(collection, widgets);
    const capturedOutput = String(widgets.final_prompt.value ?? "");
    let requestMeta;
    try {
      requestMeta = {
        input_fingerprint: await textFingerprint(capturedInputs),
        output_fingerprint: await textFingerprint(capturedOutput),
      };
    } catch (error) {
      pending = null;
      if (!destroyed) {
        actionError = error?.message || String(error);
        render();
      }
      return;
    }
    let unchanged = false;
    try { unchanged = capturedInputs === requestSnapshot(currentCollection(), widgets); }
    catch {}
    if (destroyed) return;
    if (!unchanged || REQUIRED_WIDGETS.some((name) => isWidgetLinked(node, name))) {
      pending = null;
      actionError = "Inputs changed before the request could be submitted.";
      render();
      return;
    }
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    pending = { kind: "generate", controller, requestId };
    actionError = "";
    writeState({ version: 1, request_id: requestId, state: "submitting", ...requestMeta }, event);
    render();
    try {
      const response = await service.fetchApi("/matrixlab/prompt-director/v1/generate", {
        method: "POST",
        headers: withSession({
          "Content-Type": "application/json",
          "X-Matrix-Prompt-Intent": "generate-v1",
        }, credentialSession),
        body: JSON.stringify({
          request_id: requestId,
          collection,
          instructions: String(widgets.instructions.value ?? ""),
          system_prompt: String(widgets.system_prompt.value ?? ""),
          model: String(widgets.model.value ?? ""),
          character_trigger: String(widgets.character_trigger.value ?? ""),
          allow_paid: true,
        }),
        signal: controller?.signal,
      });
      const payload = await response?.json?.();
      if (!response?.ok) throw new Error(responseError(payload, response, "Prompt generation failed"));
      if (destroyed || pending?.requestId !== requestId) return;
      await applyCompleted(payload, requestId, requestMeta, event);
      actionError = "";
    } catch (error) {
      if (destroyed || error?.name === "AbortError" || pending?.requestId !== requestId) return;
      writeState({ version: 1, request_id: requestId, state: "indeterminate", ...requestMeta,
        error: error?.message || String(error) }, event);
    } finally {
      if (pending?.requestId === requestId) pending = null;
      render();
    }
  };

  const recoverRequest = async (event) => {
    if (pending || destroyed) return;
    const saved = generationState(widgets.generation_state.value);
    if (typeof saved.request_id !== "string" || !saved.request_id ||
        !["submitting", "pending", "indeterminate"].includes(saved.state)) return;
    const requestId = saved.request_id;
    if (isWidgetLinked(node, "final_prompt") || isWidgetLinked(node, "generation_state")) return;
    const requestMeta = {
      input_fingerprint: saved.input_fingerprint,
      output_fingerprint: saved.output_fingerprint,
    };
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    pending = { kind: "recover", controller, requestId };
    actionError = "";
    render();
    try {
      const response = await service.fetchApi(`/matrixlab/prompt-director/v1/requests/${encodeURIComponent(requestId)}`, {
        method: "GET", headers: withSession({}, credentialSession), signal: controller?.signal,
      });
      const payload = await response?.json?.();
      if (!response?.ok) throw new Error(responseError(payload, response, "Request recovery failed"));
      if (destroyed || pending?.requestId !== requestId) return;
      if (["complete", "completed"].includes(payload?.state)) await applyCompleted(payload, requestId, requestMeta, event);
      else if (["pending", "claimed", "submitted"].includes(payload?.state)) {
        writeState({ version: 1, request_id: requestId, state: "pending", ...requestMeta }, event);
      }
      else if (payload?.state === "failed") {
        writeState({ version: 1, request_id: requestId, state: "failed", ...requestMeta,
          error: typeof payload?.error === "string" ? payload.error : "Request failed definitively." }, event);
      }
      else writeState({ version: 1, request_id: requestId, state: "indeterminate",
        ...requestMeta, error: typeof payload?.error === "string" ? payload.error :
          typeof payload?.message === "string" ? payload.message : "Request outcome is indeterminate." }, event);
      actionError = "";
    } catch (error) {
      if (destroyed || error?.name === "AbortError" || pending?.requestId !== requestId) return;
      writeState({ version: 1, request_id: requestId, state: "indeterminate", ...requestMeta,
        error: error?.message || String(error) }, event);
    } finally {
      if (pending?.requestId === requestId) pending = null;
      render();
    }
  };
  generate.addEventListener("click", submit);
  recover.addEventListener("click", recoverRequest);

  const measuredHeight = () => haloWidgetLayoutHeight(measureHaloContentHeight(root, DEFAULT_HEIGHT), presentation);
  const scheduleMinimum = () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      resizeTimer = null;
      if (destroyed) return;
      const width = Number(node.size?.[0]) || 0;
      const margin = Number(presentation?.margin);
      const nativeNode = root.closest?.("[data-node-id]");
      const nativeSlot = root.parentElement;
      const horizontalInsets = nativeNode?.offsetWidth > 0 && nativeSlot?.offsetWidth > 0
        ? Math.max(0, nativeNode.offsetWidth - nativeSlot.offsetWidth)
        : 2 * (Number.isFinite(margin) && margin >= 0 ? margin : 10);
      const minimumNodeWidth = MIN_WIDTH + horizontalInsets;
      const requiredHeight = haloMinimumNodeHeight(node, measuredHeight());
      const nextWidth = Math.max(width, minimumNodeWidth);
      if (nextWidth !== width || Math.abs(requiredHeight - Number(node.size?.[1])) > 0.5) {
        setHaloNodeSize(node, [nextWidth, requiredHeight]);
      }
      halo?.renderStatic?.();
    }, 0);
  };
  const destroy = () => {
    if (destroyed) return;
    destroyed = true;
    clearTimeout(copyNoticeTimer);
    copyNoticeTimer = null;
    textPreviews.clear();
    clearTimeout(resizeTimer);
    sizingObserver?.disconnect();
    pending?.controller?.abort?.();
    pending = null;
    credentialEpoch += 1;
    catalogueEpoch += 1;
    credentialController?.abort?.();
    catalogueController?.abort?.();
    credentialController = null;
    catalogueController = null;
    unobserveCollection();
    for (const [element, type, listener] of listeners) element.removeEventListener(type, listener);
    generate.removeEventListener("click", submit);
    recover.removeEventListener("click", recoverRequest);
    connect.removeEventListener("click", connectCredential);
    changeKey.removeEventListener("click", changeCredential);
    disconnect.removeEventListener("click", disconnectCredential);
    refreshModelsButton.removeEventListener("click", refreshModels);
    halo?.destroy?.();
    snapshots.forEach(restoreWidget);
    removePresentation(node, beforeWidgets, presentation);
    root.remove?.(); host.remove?.();
    if (node.onResize === wrappedResize) node.onResize = previousResize;
    if (node.onRemoved === wrappedRemoved) node.onRemoved = previousRemoved;
    if (node.onConfigure === wrappedConfigure) node.onConfigure = previousConfigure;
    if (node.onConnectionsChange === wrappedConnectionsChange) node.onConnectionsChange = previousConnectionsChange;
    if (node[CONTROL] === control) delete node[CONTROL];
  };
  const wrappedResize = function (...args) { const result = previousResize?.apply(this, args); scheduleMinimum(); return result; };
  const wrappedRemoved = function (...args) { destroy(); return previousRemoved?.apply(this, args); };
  const wrappedConfigure = function (...args) { const result = previousConfigure?.apply(this, args); render(); return result; };
  const wrappedConnectionsChange = function (...args) {
    const result = previousConnectionsChange?.apply(this, args);
    actionError = ""; bindCollectionObserver(null); markStale("Reference connection changed"); render(); return result;
  };
  const control = { node, root, host, render, submit, recover: recoverRequest,
    connectCredential, disconnectCredential, refreshModels, refreshCredentialStatus, destroy,
    get credential() { return { ...credential }; },
    get modelIds() { return [...modelIds]; },
    get catalogueFingerprint() { return catalogueFingerprint; },
    get pending() { return pending; }, get destroyed() { return destroyed; } };

  try {
    presentation = node.addDOMWidget(PRESENTATION_WIDGET, "matrixlab-prompt-director", host, {
      serialize: false, hideOnZoom: false, getMinHeight: measuredHeight, getHeight: measuredHeight,
    });
    if (!presentation) throw new Error("ComfyUI did not create the Auto Prompter DOM widget");
    presentation.serialize = false;
    presentation.options ||= {};
    presentation.options.serialize = false;
    halo = mountHaloSurface(root, node, { app: application, document: doc, profile: "ui" });
    if (!halo) throw new Error("HALO surface mount failed");
    for (const snapshot of snapshots) {
      const widget = snapshot.widget;
      snapshot.ownedCallback = widget.callback = function (...args) {
        let result;
        try { result = snapshot.callback?.apply(this, args); }
        finally { if (!suppressStale && WATCHED_WIDGETS.has(widget.name)) markStale(); render(); }
        return result;
      };
      hideWidget(snapshot);
    }
    node[CONTROL] = control;
    node.onResize = wrappedResize;
    node.onRemoved = wrappedRemoved;
    node.onConfigure = wrappedConfigure;
    node.onConnectionsChange = wrappedConnectionsChange;
    const SizingObserver = doc.defaultView?.ResizeObserver || globalThis.ResizeObserver;
    if (typeof SizingObserver === "function") {
      sizingObserver = new SizingObserver(scheduleMinimum);
      sizingObserver.observe(root);
    }
    render(); scheduleMinimum();
    void refreshCredentialStatus();
    return control;
  } catch (error) {
    sizingObserver?.disconnect();
    unobserveCollection();
    credentialEpoch += 1;
    catalogueEpoch += 1;
    credentialController?.abort?.();
    catalogueController?.abort?.();
    for (const [element, type, listener] of listeners) element.removeEventListener(type, listener);
    generate.removeEventListener("click", submit);
    recover.removeEventListener("click", recoverRequest);
    connect.removeEventListener("click", connectCredential);
    changeKey.removeEventListener("click", changeCredential);
    disconnect.removeEventListener("click", disconnectCredential);
    refreshModelsButton.removeEventListener("click", refreshModels);
    halo?.destroy?.();
    snapshots.forEach(restoreWidget);
    removePresentation(node, beforeWidgets, presentation);
    root.remove?.(); host.remove?.();
    node.onResize = previousResize;
    node.onRemoved = previousRemoved;
    node.onConfigure = previousConfigure;
    node.onConnectionsChange = previousConnectionsChange;
    options.onError?.(error);
    return null;
  }
}

app?.registerExtension?.({
  name: "matrix.prompt-director.halo",
  nodeCreated: mountPromptDirector,
  loadedGraphNode: mountPromptDirector,
});
