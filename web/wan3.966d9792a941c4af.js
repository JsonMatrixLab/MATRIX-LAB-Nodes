import { app } from "../../scripts/app.js";
import { HALO_TOKENS, haloWidgetLayoutHeight, mountHaloSurface } from "./halo.87ce22ea9cb20e75.mjs";

const NODE = "MATRIX_Wan3";
const BASE = "/matrix-wan3/credentials/v1";
const MODALS = new WeakMap();
const WORKFLOW_SCHEMA_VERSION = 3;
const MODE_INPUTS = {
  "Text to Video": new Set(),
  "Image to Video": new Set(["image", "last_image"]),
  "Reference to Video": new Set(["reference_images", "reference_videos", "reference_audios"]),
  "Edit Video": new Set(["video", "reference_images", "reference_audios"]),
  "Extend Video": new Set(["video", "last_image"]),
};
const LEGACY_FIXED_INPUTS = {
  "Text to Video": new Set(),
  "Image to Video": new Set(["image", "last_image"]),
  "Reference to Video": new Set(),
  "Edit Video": new Set(["video"]),
  "Extend Video": new Set(["video", "last_image"]),
};
const LEGACY_REFERENCE_MAX = { reference_images: 10, reference_videos: 5, reference_audios: 5 };
const MODE_WIDGETS = {
  "Text to Video": new Set(["tier", "prompt", "resolution", "duration", "aspect_ratio", "enable_audio", "seed_mode", "seed", "enable_prompt_expansion"]),
  "Image to Video": new Set(["tier", "image_variant", "prompt", "resolution", "duration", "aspect_ratio", "enable_audio", "seed_mode", "seed", "enable_prompt_expansion"]),
  "Reference to Video": new Set(["tier", "prompt", "resolution", "duration", "aspect_ratio", "enable_audio", "seed_mode", "seed", "enable_prompt_expansion", "allow_video_materialization"]),
  "Edit Video": new Set(["prompt", "tier", "resolution", "edit_duration", "generate_audio", "allow_video_materialization", "acknowledge_provider_trimming", "enable_prompt_expansion", "seed_mode", "seed"]),
  "Extend Video": new Set(["prompt", "tier", "resolution", "duration", "enable_audio", "allow_video_materialization", "acknowledge_provider_trimming", "enable_prompt_expansion", "seed_mode", "seed"]),
};
const KEY_CONTROL = Symbol.for("matrix.wan3.detached-key-control.v1");
const HALO_CONTROL = Symbol.for("matrix.wan3.halo-control.v1");
const REMOVAL_HOOK = Symbol.for("matrix.wan3.removal-hook.v1");
const KEY_ROW_HEIGHT = 24;
const KEY_STATUS = new WeakMap();
const KEY_REVISIONS = new WeakMap();
const KEY_MUTATIONS = new Map();
const PROMPT_LAYOUT = Symbol.for("matrix.wan3.native-prompt-layout.v1");
const PROMPT_WATCH = Symbol.for("matrix.wan3.native-prompt-watch.v1");
const PROMPT_MIN_HEIGHT = 120;
const PROMPT_MAX_HEIGHT = 1200;
const VUE_MIN_WIDTH = 430;
const clampPromptHeight = (height) => Math.max(PROMPT_MIN_HEIGHT, Math.min(PROMPT_MAX_HEIGHT, Math.round(height)));

function installNativeLayout(node) {
  if (!document.head) return;
  if (!document.getElementById?.("matrix-wan3-native-layout")) {
    const style = document.createElement("style");
    style.id = "matrix-wan3-native-layout";
    style.textContent = `
      .lg-node:has([node-type="MATRIX_Wan3"]) .lg-node-widgets[data-testid="node-widgets"] {
        grid-template-columns: min-content minmax(0, 112px) minmax(0, 1fr) !important;
        align-content: start;
      }
      .lg-node:has([node-type="MATRIX_Wan3"]) .lg-node-widgets[data-testid="node-widgets"] > * { min-width: 0; }
      [node-type="MATRIX_Wan3"] textarea { resize: vertical !important; min-height: 120px !important; max-height: 1200px !important; }
      .matrix-wan3-native-prompt { resize: vertical !important; min-height: 120px !important; max-height: 1200px !important; }
    `;
    document.head.append(style);
  }
  if (!node[PROMPT_WATCH] && typeof MutationObserver !== "undefined" && document.body) {
    const watcher = new MutationObserver(() => {
      if (node._matrixWan3Removed) return;
      if (watcher.pending) return;
      watcher.pending = true;
      requestAnimationFrame(() => { watcher.pending = false; installNativeLayout(node); });
    });
    watcher.observe(document.body, { childList: true, subtree: true });
    node[PROMPT_WATCH] = watcher;
  }
  const root = Number.isFinite(Number(node.id)) ? document.querySelector?.(`.lg-node[data-node-id="${Number(node.id)}"]`) : null;
  const savedHeight = Number(node.properties?.matrixWan3PromptHeight);
  const initialHeight = Number.isFinite(savedHeight) ? clampPromptHeight(savedHeight) : PROMPT_MIN_HEIGHT;
  if (Number.isFinite(savedHeight) && savedHeight !== initialHeight) node.properties.matrixWan3PromptHeight = initialHeight;
  if (root) {
    root.style.minWidth = `${VUE_MIN_WIDTH}px`;
    const width = Number(node.size?.[0]);
    const height = Number(node.size?.[1]);
    if (Number.isFinite(width) && width < VUE_MIN_WIDTH && Number.isFinite(height)) node.setSize?.([VUE_MIN_WIDTH, height]);
  }
  const promptWidget = widgetsFor(node).prompt;
  const native = promptWidget?.element;
  const textarea = root?.querySelector?.(`[node-type="MATRIX_Wan3"] textarea`) || (native?.matches?.("textarea") ? native : native?.querySelector?.("textarea"));
  if (promptWidget && !promptWidget._matrixWan3HeightWrapped) {
    promptWidget.options ||= {};
    const originalMinHeight = promptWidget.options.getMinHeight;
    const originalHeight = promptWidget.options.getHeight;
    const desiredHeight = () => haloWidgetLayoutHeight(clampPromptHeight(node[PROMPT_LAYOUT]?.height || Number(node.properties?.matrixWan3PromptHeight) || PROMPT_MIN_HEIGHT), promptWidget);
    promptWidget.options.getMinHeight = () => Math.max(Number(originalMinHeight?.call(promptWidget.options)) || 0, desiredHeight());
    promptWidget.options.getHeight = () => Math.max(Number(originalHeight?.call(promptWidget.options)) || 0, desiredHeight());
    promptWidget._matrixWan3HeightWrapped = true;
  }
  if (!textarea || node[PROMPT_LAYOUT]?.textarea === textarea) return;
  node[PROMPT_LAYOUT]?.observer?.disconnect();
  node[PROMPT_LAYOUT]?.release?.();
  textarea.classList?.add("matrix-wan3-native-prompt");
  const row = textarea.closest?.('[data-testid="node-widget"]');
  const measuredHeight = Math.round(textarea.offsetHeight || 0);
  const vue = !!root;
  textarea.style.height = vue ? `${initialHeight}px` : "100%";
  if (row) row.style.height = `${initialHeight}px`;
  const layout = { textarea, row, vue, height: initialHeight, dragHeight: initialHeight, observer: null, resizingPrompt: false, userResizing: false, textareaDrag: false, release: null };
  if (textarea.addEventListener && document.addEventListener) {
    let vueGrip = null;
    const beginTextareaDrag = (event) => {
      const bounds = textarea.getBoundingClientRect?.();
      if (!bounds || bounds.right - event.clientX > 24 || bounds.bottom - event.clientY > 24 || (vue && vueGrip)) return;
      layout.dragHeight = clampPromptHeight(textarea.offsetHeight || layout.height);
      layout.textareaDrag = true;
      if (vue) {
        layout.height = layout.dragHeight;
        node.properties ||= {};
        node.properties.matrixWan3PromptHeight = layout.height;
        textarea.style.height = `${layout.height}px`;
        if (row) row.style.height = `${layout.height}px`;
        const scale = bounds.height / (textarea.offsetHeight || 1);
        vueGrip = { pointerId: event.pointerId, y: event.clientY, height: layout.dragHeight, scale: scale > 0 ? scale : 1 };
        event.preventDefault?.();
        event.stopPropagation?.();
      }
    };
    const moveTextareaDrag = (event) => {
      if (!vueGrip || (event.pointerId != null && vueGrip.pointerId != null && event.pointerId !== vueGrip.pointerId)) return;
      const height = clampPromptHeight(vueGrip.height + (event.clientY - vueGrip.y) / vueGrip.scale);
      const delta = height - layout.height;
      if (!delta) return;
      layout.height = height;
      layout.dragHeight = height;
      node.properties ||= {};
      node.properties.matrixWan3PromptHeight = height;
      textarea.style.height = `${height}px`;
      if (row) row.style.height = `${height}px`;
      const width = Number(node.size?.[0]);
      const current = Number(node.size?.[1]);
      if (Number.isFinite(width) && Number.isFinite(current)) {
        layout.resizingPrompt = true;
        try { node.setSize?.([width, current + delta]); }
        finally { layout.resizingPrompt = false; }
      }
      node.setDirtyCanvas?.(true, true);
    };
    const endTextareaDrag = (event) => {
      if (vueGrip && event?.pointerId != null && vueGrip.pointerId != null && event.pointerId !== vueGrip.pointerId) return;
      vueGrip = null;
      setTimeout(() => { layout.textareaDrag = false; textarea.style.height = vue ? `${layout.height}px` : "100%"; }, 100);
    };
    textarea.addEventListener("pointerdown", beginTextareaDrag);
    document.addEventListener("pointermove", moveTextareaDrag, true);
    document.addEventListener("pointerup", endTextareaDrag, true);
    document.addEventListener("pointercancel", endTextareaDrag, true);
    if (vue) {
      textarea.addEventListener("mousedown", beginTextareaDrag);
      document.addEventListener("mousemove", moveTextareaDrag, true);
      document.addEventListener("mouseup", endTextareaDrag, true);
    }
    document.defaultView?.addEventListener?.("blur", endTextareaDrag);
    const previousRelease = layout.release;
    layout.release = () => {
      previousRelease?.();
      textarea.removeEventListener("pointerdown", beginTextareaDrag);
      document.removeEventListener("pointermove", moveTextareaDrag, true);
      document.removeEventListener("pointerup", endTextareaDrag, true);
      document.removeEventListener("pointercancel", endTextareaDrag, true);
      if (vue) {
        textarea.removeEventListener("mousedown", beginTextareaDrag);
        document.removeEventListener("mousemove", moveTextareaDrag, true);
        document.removeEventListener("mouseup", endTextareaDrag, true);
      }
      document.defaultView?.removeEventListener?.("blur", endTextareaDrag);
    };
  }
  if (root?.addEventListener && document.addEventListener) {
    let cornerDrag = null;
    const begin = (event) => {
      const corner = event.target?.closest?.("[data-corner]")?.dataset?.corner;
      if (!corner) return;
      layout.userResizing = true;
      const actual = Math.round(textarea.offsetHeight || layout.height);
      const rect = textarea.getBoundingClientRect?.();
      const scale = Number(rect?.height) / (textarea.offsetHeight || 1);
      cornerDrag = { pointerId: event.pointerId, y: event.clientY, height: actual,
        scale: scale > 0 ? scale : 1, direction: corner.startsWith("N") ? -1 : 1 };
    };
    const move = (event) => {
      if (!cornerDrag || (event.pointerId != null && cornerDrag.pointerId != null && event.pointerId !== cornerDrag.pointerId)) return;
      const height = clampPromptHeight(cornerDrag.height +
        cornerDrag.direction * (event.clientY - cornerDrag.y) / cornerDrag.scale);
      if (height === layout.height) return;
      layout.height = height;
      textarea.style.height = `${height}px`;
      if (row) row.style.height = `${height}px`;
      node.properties ||= {};
      node.properties.matrixWan3PromptHeight = height;
      node.setDirtyCanvas?.(true, true);
    };
    const end = () => { layout.userResizing = false; cornerDrag = null; };
    root.addEventListener("pointerdown", begin, true);
    document.addEventListener("pointermove", move, true);
    document.addEventListener("pointerup", end, true);
    document.addEventListener("pointercancel", end, true);
    document.defaultView?.addEventListener?.("blur", end);
    const previousRelease = layout.release;
    layout.release = () => {
      previousRelease?.();
      root.removeEventListener("pointerdown", begin, true);
      document.removeEventListener("pointermove", move, true);
      document.removeEventListener("pointerup", end, true);
      document.removeEventListener("pointercancel", end, true);
      document.defaultView?.removeEventListener?.("blur", end);
    };
  }
  if (typeof ResizeObserver !== "undefined") {
    layout.observer = new ResizeObserver(() => {
      if (node[PROMPT_LAYOUT] !== layout || node._matrixWan3Removed) return;
      if (!layout.textareaDrag || layout.vue) return;
      const height = clampPromptHeight(textarea.offsetHeight || 0);
      const delta = height - layout.dragHeight;
      if (!delta) return;
      layout.height = height;
      layout.dragHeight = height;
      node.properties ||= {};
      node.properties.matrixWan3PromptHeight = height;
      if (row) row.style.height = `${height}px`;
      const width = Number(node.size?.[0]);
      const current = Number(node.size?.[1]);
      if (Number.isFinite(width) && Number.isFinite(current)) {
        layout.resizingPrompt = true;
        try { node.setSize?.([width, current + delta]); }
        finally { layout.resizingPrompt = false; }
      }
      node.setDirtyCanvas?.(true, true);
    });
    layout.observer.observe(textarea);
  }
  node[PROMPT_LAYOUT] = layout;
  if (!node._matrixWan3PromptResizeWrapped) {
    const previousResize = node.onResize;
    node.onResize = function (...args) {
      const result = previousResize?.apply(this, args);
      const currentLayout = this[PROMPT_LAYOUT];
      if (currentLayout?.vue && !currentLayout.haloFramePending && this[HALO_CONTROL]?.renderStatic) {
        currentLayout.haloFramePending = true;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          currentLayout.haloFramePending = false;
          if (this[PROMPT_LAYOUT] === currentLayout && !this._matrixWan3Removed) this[HALO_CONTROL]?.renderStatic?.();
        }));
      }
      const currentHeight = Number(args[0]?.[1] ?? this.size?.[1]);
      this._matrixWan3LastNodeHeight = currentHeight;
      return result;
    };
    node._matrixWan3PromptResizeWrapped = true;
  }
  node._matrixWan3LastNodeHeight = Number(node.size?.[1]);
  if (!vue && measuredHeight && initialHeight > measuredHeight && Number.isFinite(node._matrixWan3LastNodeHeight)) {
    layout.resizingPrompt = true;
    try { node.setSize?.([Number(node.size?.[0]) || 430, node._matrixWan3LastNodeHeight + initialHeight - measuredHeight]); }
    finally { layout.resizingPrompt = false; }
    node._matrixWan3LastNodeHeight = Number(node.size?.[1]);
  }
  const requiredHeight = Number(node.computeSize?.()?.[1]);
  const actualHeight = Number(node.size?.[1]);
  if (!vue && Number.isFinite(requiredHeight) && Number.isFinite(actualHeight) && actualHeight < requiredHeight) {
    node.setSize?.([Number(node.size?.[0]) || 430, requiredHeight]);
  }
  node.setDirtyCanvas?.(true, true);
}

// Nodes 2.0 keys WidgetDOM by graph/node/name/type, separately from its random
// registry ID. A fresh nonserialized name remounts DOM after history rebuilds.
const ownedWidgetName = (role) => `matrix_wan3_${role}_${crypto.randomUUID()}`;

const modeLabel = (name) => name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function credentialScope(node) {
  return String(node.widgets?.find((widget) => widget.name === "credential_scope")?.value ?? "");
}

function keyStatus(node, updates = {}) {
  const state = { present: false, source: null, verified: false, disconnected: false, error: "", ...KEY_STATUS.get(node), ...updates };
  KEY_STATUS.set(node, state);
  KEY_REVISIONS.set(node, (KEY_REVISIONS.get(node) || 0) + 1);
  node[KEY_CONTROL]?.update?.(state);
  node.setDirtyCanvas?.(true, false);
  return state;
}

function keyStatusText(node) {
  const state = KEY_STATUS.get(node);
  if (!state) return "Select to manage";
  if (state.error) return "Status unavailable";
  if (state.disconnected) return "disconnected";
  if (!state.present) return "Set API key";
  return `•••• · saved · ${state.verified ? "balance checked" : "unchecked"}`;
}

function removeOwnedWidget(node, widget) {
  const index = node.widgets?.indexOf(widget) ?? -1;
  if (index >= 0) node.widgets.splice(index, 1);
  node.setDirtyCanvas?.(true, true);
}

function installRemovalHook(node) {
  if (node[REMOVAL_HOOK]) return;
  const hook = { previous: node.onRemoved };
  hook.wrapper = function (...removeArgs) {
    this._matrixWan3Removed = true;
    MODALS.get(this)?.();
    this[HALO_CONTROL]?.destroy?.();
    this[KEY_CONTROL]?.restore?.();
    this[PROMPT_LAYOUT]?.observer?.disconnect();
    this[PROMPT_LAYOUT]?.release?.();
    delete this[PROMPT_LAYOUT];
    this[PROMPT_WATCH]?.disconnect();
    delete this[PROMPT_WATCH];
    return hook.previous?.apply(this, removeArgs);
  };
  node[REMOVAL_HOOK] = hook;
  node.onRemoved = hook.wrapper;
}

function installKeyControl(node) {
  if (node[KEY_CONTROL]) return;
  if (typeof node.addDOMWidget !== "function") return;
  const control = document.createElement("button");
  control.type = "button";
  control.className = "matrix-wan3-key-control";
  control.setAttribute("aria-label", "Manage WaveSpeed API key");
  Object.assign(control.style, {
    boxSizing: "border-box", width: "calc(100% - 8px)", margin: "0 4px", height: `${KEY_ROW_HEIGHT}px`, minHeight: `${KEY_ROW_HEIGHT}px`, maxHeight: `${KEY_ROW_HEIGHT}px`, flex: `0 0 ${KEY_ROW_HEIGHT}px`, padding: "4px 10px", display: "flex", alignItems: "center", justifyContent: "space-between",
    border: `1px solid ${HALO_TOKENS.fieldBorder}`, borderRadius: "5px", background: "#040A04FA", color: HALO_TOKENS.primaryText,
    font: "11px/16px 'Cascadia Mono','Cascadia Code',Consolas,monospace", cursor: "pointer", textAlign: "left",
  });
  const label = document.createElement("span");
  label.textContent = "WAVESPEED KEY";
  label.style.color = HALO_TOKENS.parameterLabel;
  const status = document.createElement("span");
  status.textContent = keyStatusText(node);
  control.append(label, status);
  control.addEventListener("click", (event) => { event.stopPropagation?.(); modal(node); });
  let widget;
  widget = node.addDOMWidget(ownedWidgetName("key_status"), "matrix-wan3-key-control", control, {
    serialize: false, hideOnZoom: false, getMinHeight: () => haloWidgetLayoutHeight(KEY_ROW_HEIGHT, widget), getMaxHeight: () => haloWidgetLayoutHeight(KEY_ROW_HEIGHT, widget), getHeight: () => haloWidgetLayoutHeight(KEY_ROW_HEIGHT, widget),
  });
  if (!widget) return;
  widget.serialize = false;
  widget.options ||= {};
  widget.options.serialize = false;
  const providerIndex = node.widgets.findIndex((item) => item.name === "operation");
  const widgetIndex = node.widgets.indexOf(widget);
  if (providerIndex >= 0 && widgetIndex >= 0 && widgetIndex !== providerIndex) {
    node.widgets.splice(widgetIndex, 1);
    node.widgets.splice(providerIndex, 0, widget);
  }
  const update = (state) => {
    status.textContent = keyStatusText(node);
    status.style.color = state?.error ? HALO_TOKENS.errorText : state?.verified ? HALO_TOKENS.green : HALO_TOKENS.primaryText;
    control.setAttribute("aria-label", `Manage WaveSpeed API key: ${status.textContent}`);
  };
  update(KEY_STATUS.get(node));
  const keyControl = {
    widget,
    element: control,
    update,
    restore() {
      control.remove?.();
      removeOwnedWidget(node, widget);
      if (node[KEY_CONTROL] === keyControl) delete node[KEY_CONTROL];
    },
  };
  node[KEY_CONTROL] = keyControl;
  refreshKeyControl(node, keyControl);
}

function readCredentialStatus(node, pending = KEY_MUTATIONS.get(credentialScope(node))) {
  return pending ? pending.then(() => request("status", node)) : request("status", node);
}

function refreshKeyControl(node, control) {
  const scope = credentialScope(node);
  if (!scope) return;
  const revision = KEY_REVISIONS.get(node) || 0;
  const current = () => node[KEY_CONTROL] === control && !node._matrixWan3Removed && credentialScope(node) === scope && (KEY_REVISIONS.get(node) || 0) === revision;
  readCredentialStatus(node).then((r) => {
    if (current()) keyStatus(node, { present: r.present, source: r.source, verified: false, disconnected: !!r.disconnected, error: "" });
  }).catch((e) => { if (current()) keyStatus(node, { error: e.message }); });
}

function installHalo(node) {
  if (node[HALO_CONTROL] || typeof node.addDOMWidget !== "function") return;
  const root = document.createElement("div");
  root.className = "matrix-wan3-brand";
  Object.assign(root.style, {
    height: "27px", minHeight: "27px", maxHeight: "27px", flex: "0 0 27px", padding: "5px 10px", display: "flex", alignItems: "center", justifyContent: "space-between",
    color: HALO_TOKENS.instanceId,
    font: "700 10px/15px 'Cascadia Mono','Cascadia Code',Consolas,monospace", letterSpacing: ".5px",
  });
  const brand = document.createElement("span");
  brand.textContent = "matrix-lab-nodes";
  const product = document.createElement("span");
  product.textContent = "WAN 3 · WAVE SPEED";
  product.style.color = HALO_TOKENS.secondaryText;
  root.append(brand, product);
  let widget;
  widget = node.addDOMWidget(ownedWidgetName("halo_brand"), "matrix-wan3-halo-brand", root, { serialize: false, hideOnZoom: false, getMinHeight: () => haloWidgetLayoutHeight(27, widget), getMaxHeight: () => haloWidgetLayoutHeight(27, widget), getHeight: () => haloWidgetLayoutHeight(27, widget) });
  if (!widget) return;
  widget.serialize = false;
  widget.options ||= {};
  widget.options.serialize = false;
  const halo = mountHaloSurface(root, node, { app, profile: "execution" });
  const haloControl = {
    widget,
    root,
    renderStatic: () => halo?.renderStatic?.(),
    destroy() {
      halo?.destroy?.();
      root.remove?.();
      removeOwnedWidget(node, widget);
      if (node[HALO_CONTROL] === haloControl) delete node[HALO_CONTROL];
    },
  };
  node[HALO_CONTROL] = haloControl;
}

function restoreNodeDecorations(node) {
  node._matrixWan3Removed = false;
  installHalo(node);
  installKeyControl(node);
  installRemovalHook(node);
  fitNodeHeight(node);
}

function mediaRole(name) {
  const local = String(name || "").replace(/^operation\./, "");
  if (["image", "last_image", "video"].includes(local)) return local;
  if (/^reference_images(?:\.|$)/.test(local) || /^reference_image_\d+$/.test(local)) return "reference_images";
  if (/^reference_videos(?:\.|$)/.test(local) || /^reference_video_\d+$/.test(local)) return "reference_videos";
  if (/^reference_audios(?:\.|$)/.test(local) || /^reference_audio_\d+$/.test(local)) return "reference_audios";
  return null;
}

function modeHasInput(mode, input) {
  const role = mediaRole(input?.name);
  return !!role && (MODE_INPUTS[mode] || MODE_INPUTS["Text to Video"]).has(role);
}

function dynamicInputName(name) {
  const existing = String(name || "");
  if (existing.startsWith("operation.")) return existing;
  if (["image", "last_image", "video"].includes(existing)) return `operation.${existing}`;
  let match = existing.match(/^reference_image_(\d+)$/);
  if (match) return `operation.reference_images.image_${match[1]}`;
  match = existing.match(/^reference_video_(\d+)$/);
  if (match) return `operation.reference_videos.video_${match[1]}`;
  match = existing.match(/^reference_audio_(\d+)$/);
  if (match) return `operation.reference_audios.audio_${match[1]}`;
  return null;
}

function migrateLegacyGraphData(graphData) {
  const nodes = graphData?.nodes;
  const graphLinks = graphData?.links;
  if (!Array.isArray(nodes) || !Array.isArray(graphLinks)) return false;
  const linkById = new Map(graphLinks.map((link) => [Array.isArray(link) ? link[0] : link?.id, link]));
  for (const node of nodes) {
    if (node.type === NODE && node.inputs?.some((input) => input.name === "provider" && input.link != null)) {
      throw new Error("A linked legacy Provider cannot be migrated safely. Disconnect it in a copy before loading this workflow.");
    }
  }
  const plans = [];
  for (const node of nodes) {
    if (node.type !== NODE || !Array.isArray(node.inputs)) continue;
    const legacyMedia = node.inputs.filter((input) => mediaRole(input.name) && !String(input.name).startsWith("operation."));
    if (!legacyMedia.length) continue;
    const mode = node.widgets_values_named?.operation ?? node.widgets_values?.[1] ?? "Text to Video";
    const supported = LEGACY_FIXED_INPUTS[mode];
    if (!supported) throw new Error(`Cannot safely migrate MATRIX_Wan3 operation "${mode}". Preserve the original workflow and update the node manually.`);
    const maxReferenceSlot = new Map();
    for (const input of legacyMedia) {
      const role = mediaRole(input.name);
      if (!role?.startsWith("reference_") || input.link == null) continue;
      if (!MODE_INPUTS[mode]?.has(role)) {
        throw new Error(`Cannot safely migrate the linked legacy MATRIX_Wan3 input "${input.localized_name || input.name}" for ${mode}. Keep the original workflow and disconnect or rebuild this input in a copy before loading it.`);
      }
      const localName = dynamicInputName(input.name)?.replace(/^operation\./, "").split(".").at(-1);
      const slot = Number(localName?.match(/_(\d+)$/)?.[1]);
      if (!Number.isInteger(slot) || slot < 1 || slot > LEGACY_REFERENCE_MAX[role]) throw new Error(`Cannot safely migrate the linked legacy MATRIX_Wan3 input "${input.localized_name || input.name}" because its slot number is invalid.`);
      maxReferenceSlot.set(role, Math.max(maxReferenceSlot.get(role) || 0, slot));
    }
    const media = [];
    for (const input of legacyMedia) {
      const role = mediaRole(input.name);
      const targetName = dynamicInputName(input.name);
      const localName = targetName?.replace(/^operation\./, "").split(".").at(-1);
      const fixedName = ["image", "last_image", "video"].includes(localName);
      const reference = role?.startsWith("reference_");
      const referenceSlot = Number(localName?.match(/_(\d+)$/)?.[1]);
      if (input.link != null && !reference && (!supported.has(localName) || !fixedName)) {
        throw new Error(`Cannot safely migrate the linked legacy MATRIX_Wan3 input "${input.localized_name || input.name}" for ${mode}. Keep the original workflow and disconnect or rebuild this input in a copy before loading it.`);
      }
      if (reference) {
        const maxSlot = maxReferenceSlot.get(role) || 0;
        if (!MODE_INPUTS[mode]?.has(role) || !maxSlot || referenceSlot > maxSlot) continue;
      } else if (input.link == null && (!supported.has(localName) || !fixedName)) continue;
      if (!targetName) continue;
      media.push({ input, targetName, role, localName });
    }
    const orderedMedia = [...media].sort((a, b) => {
      const rank = (item) => ({ image: 0, video: 0, last_image: 1, reference_images: 2, reference_videos: 3, reference_audios: 4 }[item.role] ?? 5);
      const rankDifference = rank(a) - rank(b);
      if (rankDifference) return rankDifference;
      const slot = (item) => Number(item.localName.match(/_(\d+)$/)?.[1] || 0);
      return slot(a) - slot(b);
    });
    const provider = node.inputs.find((input) => input.name === "provider");
    const operation = node.inputs.find((input) => input.name === "operation");
    if (!provider || !operation) throw new Error("Cannot safely migrate this legacy MATRIX_Wan3 node because Provider or Operation input is missing.");
    const rest = node.inputs.filter((input) => !legacyMedia.includes(input) && input !== provider && input !== operation && !mediaRole(input.name));
    const inputs = [provider, operation, ...orderedMedia.map((item) => item.input), ...rest];
    const linkTargets = [];
    orderedMedia.forEach(({ input, targetName }, index) => {
      if (input.link == null) return;
      const link = linkById.get(input.link);
      if (!link || !Array.isArray(link) || String(link[3]) !== String(node.id)) {
        throw new Error(`Cannot safely migrate linked MATRIX_Wan3 input "${input.name}" because its saved graph link is missing.`);
      }
      linkTargets.push({ link, slot: 2 + index });
      input.name = targetName;
    });
    for (const { input, targetName } of orderedMedia) input.name = targetName;
    plans.push({ node, inputs, linkTargets });
  }
  for (const { node, inputs, linkTargets } of plans) {
    node.inputs = inputs;
    for (const { link, slot } of linkTargets) link[4] = slot;
  }
  let billingMigrated = false;
  for (const node of nodes) {
    if (node.type !== NODE || !Array.isArray(node.inputs)) continue;
    const providerIndex = node.inputs.findIndex((input) => input.name === "provider");
    if (providerIndex < 0) continue;
    const providerInput = node.inputs[providerIndex];
    if (providerInput.link != null) throw new Error("A linked legacy Provider cannot be migrated safely. Disconnect it in a copy before loading this workflow.");
    const provider = node.widgets_values_named?.provider ?? node.widgets_values?.[0];
    const activation = provider === "WaveSpeed (billed)" ? "wavespeed_v1" : "blocked";
    node.widgets_values_named ||= {};
    node.widgets_values_named.billing_activation = activation;
    delete node.widgets_values_named.provider;
    if (Array.isArray(node.widgets_values)) node.widgets_values.splice(0, 1);
    node.inputs.splice(providerIndex, 1);
    for (const link of graphLinks) {
      if (Array.isArray(link) && String(link[3]) === String(node.id) && link[4] > providerIndex) link[4]--;
    }
    billingMigrated = true;
  }
  return plans.length > 0 || billingMigrated;
}

function findGraphLink(node, linkId) {
  const links = node.graph?.links;
  if (links instanceof Map) return links.get(linkId) ?? links.get(String(linkId));
  if (Array.isArray(links)) return links.find((link) => (Array.isArray(link) ? link[0] : link?.id) == linkId);
  return links?.[linkId] ?? links?.[String(linkId)];
}

function setGraphLinkTargetSlot(link, slot) {
  if (Array.isArray(link)) link[4] = slot;
  else if (link && typeof link === "object") link.target_slot = slot;
}

function migrateLegacyWorkflow(node, serialized) {
  const properties = node.properties && typeof node.properties === "object" && !Array.isArray(node.properties) ? node.properties : (node.properties = {});
  const current = properties.matrixWan3 && typeof properties.matrixWan3 === "object" && !Array.isArray(properties.matrixWan3) ? properties.matrixWan3 : {};
  const activation = widgetsFor(node).billing_activation;
  if (activation && serialized) {
    const named = serialized.widgets_values_named;
    const provider = named?.provider ?? (serialized.inputs?.some((input) => input.name === "provider") ? serialized.widgets_values?.[0] : undefined);
    activation.value = provider === "Demo (free, offline)" ? "blocked"
      : provider === "WaveSpeed (billed)" || named?.billing_activation === "wavespeed_v1" ? "wavespeed_v1" : "blocked";
  }
  const named = serialized?.widgets_values_named;
  if (named && typeof named === "object" && !Array.isArray(named)) {
    for (const widget of node.widgets || []) {
      if (widget.name && widget.name !== "billing_activation" && Object.prototype.hasOwnProperty.call(named, widget.name) && widget.type !== "button") widget.value = named[widget.name];
    }
  }
  if (current.schemaVersion === WORKFLOW_SCHEMA_VERSION) return false;
  const preferences = sanitizeModePreferences(node);

  const selectedMode = widgetsFor(node).operation?.value;
  const removeIndices = [];
  const movedLinks = [];
  let migrationConflict = false;
  for (const [index, input] of (node.inputs || []).entries()) {
    const targetName = dynamicInputName(input.name);
    if (!targetName) continue;
    const targetIndex = (node.inputs || []).findIndex((candidate, candidateIndex) => candidateIndex !== index && candidate.name === targetName);
    if (targetIndex >= 0) {
      const target = node.inputs[targetIndex];
      if (input.link != null) {
        if (target.link != null && target.link !== input.link) {
          migrationConflict = true;
          input._matrixWan3MigrationConflict = true;
          continue;
        }
        const link = findGraphLink(node, input.link);
        if (!link) {
          migrationConflict = true;
          input._matrixWan3MigrationConflict = true;
          continue;
        }
        target.link = input.link;
        input.link = null;
        movedLinks.push({ link, target });
      }
      removeIndices.push(index);
      continue;
    }
    if (input.link == null && !modeHasInput(selectedMode, input)) {
      removeIndices.push(index);
      continue;
    }
    input.name = targetName;
  }
  for (const index of removeIndices.reverse()) {
    if (typeof node.removeInput === "function") node.removeInput(index);
    else node.inputs.splice(index, 1);
  }
  for (const { link, target } of movedLinks) setGraphLinkTargetSlot(link, node.inputs.indexOf(target));
  node._matrixWan3MigrationBlocked = migrationConflict;
  properties.matrixWan3 = {
    ...(migrationConflict ? {} : { schemaVersion: WORKFLOW_SCHEMA_VERSION }),
    ...(Object.keys(preferences).length ? { imageToVideo: preferences } : {}),
  };
  return true;
}

async function request(path, node, body = undefined) {
  const scope = credentialScope(node);
  if (!scope) throw new Error("This node does not have a session scope yet. Reopen the node or reload the workflow.");
  const method = path === "status" ? "GET" : "POST";
  const payload = method === "POST" ? { node_id: scope, ...(body || {}) } : undefined;
  const response = await fetch(`${BASE}/${path}${path === "status" ? `?node_id=${encodeURIComponent(scope)}` : ""}`, {
    method,
    credentials: "same-origin",
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function modal(node) {
  MODALS.get(node)?.();
  const wrap = document.createElement("div");
  wrap.dataset.matrixWan3Credential = "1";
  Object.assign(wrap.style, { position: "fixed", inset: "0", zIndex: "100000", background: "#0009", display: "grid", placeItems: "center", padding: "24px" });
  const panel = document.createElement("section");
  Object.assign(panel.style, { boxSizing: "border-box", width: "min(470px, 100%)", padding: "22px", borderRadius: "8px", border: `1px solid ${HALO_TOKENS.fieldBorder}`, background: "#071108", color: HALO_TOKENS.primaryText, boxShadow: "0 16px 60px #000a", font: "12px/1.45 'Cascadia Mono','Cascadia Code',Consolas,monospace" });
  const heading = document.createElement("h2");
  heading.textContent = "WAVESPEED KEY";
  Object.assign(heading.style, { margin: "0 0 6px", color: HALO_TOKENS.green, font: "700 17px/1.2 'Cascadia Mono','Cascadia Code',Consolas,monospace" });
  const description = document.createElement("p");
  description.textContent = widgetsFor(node).billing_activation?.value === "blocked"
    ? "This older Demo workflow is paused. Saving a WaveSpeed key activates billed Runs. The key stays in private ComfyUI user data, outside the workflow."
    : "Your key is saved in private ComfyUI user data and survives restarts. It is never saved in the workflow. Disconnect deletes the saved key.";
  Object.assign(description.style, { margin: "0 0 14px", color: HALO_TOKENS.secondaryText });
  const source = document.createElement("div");
  Object.assign(source.style, { marginBottom: "12px", padding: "6px 9px", border: `1px solid ${HALO_TOKENS.fieldBorder}`, borderRadius: "4px", color: HALO_TOKENS.parameterLabel });
  const renderSource = (state) => { source.textContent = `KEY  ${state?.disconnected ? "DELETED" : state?.present ? "SAVED" : "NONE"}  ·  ${state?.verified ? "BALANCE CHECKED" : "BALANCE UNCHECKED"}`; };
  renderSource(KEY_STATUS.get(node));
  const input = document.createElement("input");
  input.type = "password"; input.autocomplete = "new-password"; input.placeholder = "Paste API key";
  Object.assign(input.style, { width: "100%", boxSizing: "border-box", padding: "10px", marginBottom: "12px", color: "inherit", background: "#040A04", border: `1px solid ${HALO_TOKENS.fieldBorder}`, borderRadius: "4px", font: "inherit" });
  const status = document.createElement("div");
  status.setAttribute("role", "status");
  Object.assign(status.style, { minHeight: "34px", marginBottom: "12px", color: HALO_TOKENS.secondaryText });
  const actions = document.createElement("div");
  Object.assign(actions.style, { display: "flex", gap: "8px", flexWrap: "wrap" });
  const busyButtons = [];
  const button = (label, action, primary = false) => { const b = document.createElement("button"); b.type = "button"; b.textContent = label; b.onclick = action; Object.assign(b.style, { padding: "8px 12px", border: `1px solid ${HALO_TOKENS.fieldBorder}`, borderRadius: "4px", background: primary ? "#173c22" : "#0c1b10", color: primary ? HALO_TOKENS.green : HALO_TOKENS.primaryText, cursor: "pointer", font: "inherit" }); if (action) busyButtons.push(b); return b; };
  let version = 0;
  const scope = credentialScope(node);
  const earlierMutation = KEY_MUTATIONS.get(scope);
  let busy = !!earlierMutation;
  const feedback = (message, error = false) => { status.textContent = message; status.style.color = error ? HALO_TOKENS.errorText : HALO_TOKENS.secondaryText; renderSource(KEY_STATUS.get(node)); };
  const perform = async (label, work) => {
    if (busy) return;
    busy = true;
    const current = ++version;
    for (const b of busyButtons) b.disabled = true;
    input.disabled = true;
    feedback(label);
    try { await work(current); }
    catch (e) { if (current === version) { keyStatus(node, { error: e.message }); feedback(e.message, true); } }
    finally { if (current === version) { busy = false; for (const b of busyButtons) b.disabled = false; input.disabled = false; } }
  };
  const mutate = (label, work) => {
    const operation = perform(label, work);
    if (busy) {
      KEY_MUTATIONS.set(scope, operation);
      operation.finally(() => { if (KEY_MUTATIONS.get(scope) === operation) KEY_MUTATIONS.delete(scope); });
    }
    return operation;
  };
  const escape = (event) => { if (event.key === "Escape") close(); };
  const close = () => { version++; input.value = ""; wrap.remove(); window.removeEventListener("keydown", escape); if (MODALS.get(node) === close) MODALS.delete(node); };
  actions.append(
    button("Save key", () => { const key = input.value; input.value = ""; if (!key) { feedback("Enter an API key.", true); return; } mutate("Saving key…", async (current) => { await request("set", node, { key }); if (!node._matrixWan3Removed && credentialScope(node) === scope) { const activation = widgetsFor(node).billing_activation; if (activation) { activation.value = "wavespeed_v1"; activation.callback?.(activation.value); node.setDirtyCanvas?.(true, true); } } if (current !== version) return; keyStatus(node, { present: true, source: "saved", verified: false, disconnected: false, error: "" }); feedback("Saved across restarts. Balance access has not been checked. Run starts a billed generation."); }); }, true),
    button("Check balance access", () => perform("Checking balance access…", async (current) => { const r = await request("verify", node); if (current !== version) return; const verified = r.access === "verified"; keyStatus(node, { present: true, source: r.source || KEY_STATUS.get(node)?.source, verified, error: verified ? "" : (r.error || "Balance access not verified") }); feedback(verified ? "Balance access verified. Generation has not been tested." : (r.error || "Balance access not verified"), !verified); })),
    button("Disconnect this node", () => mutate("Deleting saved key…", async (current) => { await request("disconnect", node, {}); if (current !== version) return; input.value = ""; keyStatus(node, { present: false, source: null, verified: false, disconnected: true, error: "" }); feedback("Saved key deleted. Save a key to reconnect."); })),
    button("Close", close),
  );
  panel.append(heading, description, source, input, status, actions); wrap.append(panel);
  if (earlierMutation) {
    input.disabled = true;
    for (const b of busyButtons) b.disabled = true;
    feedback("Finishing the previous key change…");
  }
  wrap.addEventListener("pointerdown", (event) => { if (event.target === wrap) close(); });
  window.addEventListener("keydown", escape);
  document.body.append(wrap); input.focus(); MODALS.set(node, close);
  const initialVersion = version;
  const initialStatus = readCredentialStatus(node, earlierMutation);
  initialStatus.then((r) => { if (initialVersion !== version) return; busy = false; input.disabled = false; for (const b of busyButtons) b.disabled = false; keyStatus(node, { present: r.present, source: r.source, verified: false, disconnected: !!r.disconnected, error: "" }); feedback(r.disconnected ? "This node is disconnected." : r.present ? `Key available from ${r.source}; balance access has not been checked.` : "No key configured for this node."); }).catch((e) => { if (initialVersion !== version) return; busy = false; input.disabled = false; for (const b of busyButtons) b.disabled = false; keyStatus(node, { error: e.message }); feedback(e.message, true); });
  const watchCollapse = () => { if (!wrap.isConnected) return; if (node.flags?.collapsed || node.graph == null) { close(); return; } requestAnimationFrame(watchCollapse); };
  requestAnimationFrame(watchCollapse);
  return close;
}

function applyProjection(node, mode) {
  const visibleWidgets = MODE_WIDGETS[mode] || MODE_WIDGETS["Text to Video"];
  const seedMode = widgetsFor(node).seed_mode?.value;
  for (const widget of node.widgets || []) {
    if (widget.name === "credential_scope" || widget.name === "intent_nonce" || widget.name === "billing_activation") {
      setWidgetHidden(widget, true);
      continue;
    }
    if (widget.name === "operation" || widget.name?.startsWith("WaveSpeed key") || widget.name?.startsWith("matrix_wan3_")) continue;
    if (!Object.values(MODE_WIDGETS).some((set) => set.has(widget.name))) continue;
    if (widget._matrixWan3WidgetType === undefined) widget._matrixWan3WidgetType = widget.type;
    const visible = visibleWidgets.has(widget.name) && (widget.name !== "seed" || seedMode === "Fixed");
    widget.type = visible ? widget._matrixWan3WidgetType : "hidden";
    setWidgetHidden(widget, !visible);
  }
  node.setDirtyCanvas?.(true, true);
}

function installSeedProjection(node) {
  const seedMode = widgetsFor(node).seed_mode;
  if (!seedMode || seedMode._matrixWan3SeedWrapped) return;
  const seed = widgetsFor(node).seed;
  if (seed) {
    seed.options ||= {};
    seed.options.min = 1;
    seed.options.max = 9_999;
  }
  const previous = seedMode.callback;
  seedMode.callback = function (value, ...args) {
    if (value === "Fixed" && seed && !seed._matrixWan3LegacyFixedSeed) {
      const numeric = Number(seed.value);
      seed.value = Number.isSafeInteger(numeric) ? Math.max(1, Math.min(9_999, numeric)) : 1;
    }
    const result = previous?.apply(this, [value, ...args]);
    applyProjection(node, widgetsFor(node).operation?.value);
    return result;
  };
  seedMode._matrixWan3SeedWrapped = true;
}

function preserveLegacyFixedSeed(node, serialized) {
  const { seed_mode: mode, seed } = widgetsFor(node);
  const saved = serialized?.widgets_values_named;
  if (!seed || (saved?.seed_mode ?? mode?.value) !== "Fixed") return;
  const value = Number(saved?.seed ?? seed.value);
  if (!Number.isSafeInteger(value) || value < 0 || value > 2_147_483_647) return;
  seed._matrixWan3LegacyFixedSeed = true;
  seed.value = value;
  seed.options ||= {};
  if (value === 0) seed.options.min = 0;
  if (value > 9_999) seed.options.max = value;
}

function incompatibleInputs(node, nextMode) {
  const active = MODE_INPUTS[nextMode] || new Set();
  const controls = widgetsFor(node);
  const projected = modeControlValues(node, nextMode, controls);
  const changedControls = new Set(Object.entries(projected).filter(([name, value]) => controls[name] && controls[name].value !== value).map(([name]) => name));
  const conflicts = (node.inputs || []).filter((input) => input.link != null && (input.name === "operation" || changedControls.has(input.name) || (mediaRole(input.name) && !modeHasInput(nextMode, input))));
  return conflicts;
}

function syncOperationChoices(node) {
  const widget = widgetsFor(node).operation;
  if (!widget) return;
  if (widget._matrixWan3BaseType === undefined) widget._matrixWan3BaseType = widget.type;
  const linkedModeInputs = (node.inputs || []).some((input) => input.link != null && (input.name === "operation" || mediaRole(input.name)));
  widget.type = linkedModeInputs ? "hidden" : widget._matrixWan3BaseType;
  setWidgetHidden(widget, linkedModeInputs);
  const notice = node._matrixWan3OperationNotice;
  if (notice) {
    notice.hidden = !linkedModeInputs;
    notice.style.display = linkedModeInputs ? "block" : "none";
    if (notice._widget) {
      notice._widget.type = linkedModeInputs ? notice._widget._matrixWan3BaseType : "hidden";
      setWidgetHidden(notice._widget, !linkedModeInputs);
    }
    notice.textContent = linkedModeInputs
      ? `${widget.value || node._matrixWan3Operation}: operation locked while media is connected. Disconnect media inputs to change operation.`
      : "";
  }
}

function installOperationNotice(node) {
  if (node._matrixWan3OperationNotice || typeof node.addDOMWidget !== "function") return;
  const notice = document.createElement("div");
  notice.textContent = "Operation locked while media is connected. Disconnect media inputs to change operation.";
  Object.assign(notice.style, { padding: "5px 8px", borderLeft: "2px solid #e0aa54", color: "#e8d3ad", font: "11px/1.35 system-ui", whiteSpace: "normal" });
  notice.hidden = true;
  notice.style.display = "none";
  let widget;
  widget = node.addDOMWidget(ownedWidgetName("operation_notice"), "matrix-wan3-operation-notice", notice, {
    serialize: false, hideOnZoom: true,
    getMinHeight: () => haloWidgetLayoutHeight(56, widget),
    getMaxHeight: () => haloWidgetLayoutHeight(56, widget),
    getHeight: () => haloWidgetLayoutHeight(56, widget),
  });
  if (widget) {
    widget._matrixWan3BaseType = widget.type;
    notice._widget = widget;
    node._matrixWan3OperationNotice = notice;
  }
  syncOperationChoices(node);
}

function modeDialog(node, nextMode, conflicts, accept, cancel) {
  const wrap = document.createElement("div");
  wrap.dataset.matrixWan3ModeDialog = "1";
  Object.assign(wrap.style, { position: "fixed", inset: "0", zIndex: "100001", background: "#0009", display: "grid", placeItems: "center", padding: "24px" });
  const panel = document.createElement("section");
  Object.assign(panel.style, { width: "min(460px, 100%)", padding: "22px", borderRadius: "12px", background: "#20242b", color: "#f4f6f8", boxShadow: "0 16px 60px #0008", font: "14px system-ui" });
  const names = conflicts.map((item) => modeLabel(item.name));
  const escape = (event) => { if (event.key === "Escape") { close(); cancel(); } };
  const close = () => { wrap.remove(); window.removeEventListener("keydown", escape); if (MODALS.get(node) === close) MODALS.delete(node); };
  const heading = document.createElement("h2"); heading.textContent = "This operation uses different inputs"; heading.style.margin = "0 0 8px";
  const detail = document.createElement("p"); detail.textContent = `Switching to ${nextMode} conflicts with: ${names.join(", ")}.`; detail.style.color = "#bbc2cb";
  const buttons = document.createElement("div"); Object.assign(buttons.style, { display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "18px" });
  const makeButton = (label, action) => { const b = document.createElement("button"); b.type = "button"; b.textContent = label; b.onclick = action; Object.assign(b.style, { padding: "8px 12px", border: "1px solid #59616d", borderRadius: "6px", background: "#303741", color: "inherit", cursor: "pointer" }); return b; };
  buttons.append(makeButton("Cancel", () => { close(); cancel(); }), makeButton("Disconnect listed inputs and switch", () => { close(); accept(); }));
  panel.append(heading, detail, buttons); wrap.append(panel);
  wrap.addEventListener("pointerdown", (event) => { if (event.target === wrap) { close(); cancel(); } });
  window.addEventListener("keydown", escape);
  MODALS.get(node)?.();
  document.body.append(wrap); MODALS.set(node, close);
  const watchCollapse = () => { if (!wrap.isConnected) return; if (node.flags?.collapsed || node.graph == null) { close(); cancel(); return; } requestAnimationFrame(watchCollapse); };
  requestAnimationFrame(watchCollapse);
}

function commitMode(node, widget, oldCallback, value, args, conflicts) {
  const canvas = args[1];
  const graph = node.graph;
  if (!graph) { widget.value = node._matrixWan3Operation; return; }
  if (conflicts.length && typeof node.disconnectInput !== "function") { widget.value = node._matrixWan3Operation; return; }
  canvas?.emitBeforeChange?.();
  graph.beforeChange?.();
  try {
    const previousMode = node._matrixWan3Operation;
    const controls = widgetsFor(node);
    if (previousMode === "Image to Video") saveI2VPreferences(node, controls);
    for (const input of conflicts) {
      const index = (node.inputs || []).indexOf(input);
      if (index >= 0) node.disconnectInput(index);
    }
    widget.value = value;
    node._matrixWan3Operation = value;
    const projectedValues = modeControlValues(node, value, controls);
    for (const [name, nextValue] of Object.entries(projectedValues)) {
      const control = controls[name];
      if (!control || control.value === nextValue) continue;
      control.value = nextValue;
      control.callback?.apply(control, [nextValue, ...args.slice(1)]);
    }
    applyProjection(node, value);
    oldCallback?.apply(widget, [value, ...args.slice(1)]);
  } finally {
    graph.afterChange?.();
    canvas?.emitAfterChange?.();
  }
}

function installModeProjection(node) {
  const widget = node.widgets?.find((item) => item.name === "operation");
  if (!widget || widget._matrixWan3Wrapped) return;
  const oldCallback = widget.callback;
  node._matrixWan3Operation = widget.value;
  sanitizeModePreferences(node);
  widget._matrixWan3Wrapped = true;
  widget.callback = function (value, ...args) {
    const previous = node._matrixWan3Operation;
    if (value === previous) return oldCallback?.apply(this, [value, ...args]);
    const conflicts = incompatibleInputs(node, value);
    // Revert the native widget until the user explicitly resolves incompatible wires.
    widget.value = previous;
    syncOperationChoices(node);
    applyProjection(node, previous);
    if (!conflicts.length) {
      commitMode(node, widget, oldCallback, value, [value, ...args], []);
      return;
    }
    modeDialog(node, value, conflicts, () => {
      const currentConflicts = incompatibleInputs(node, value);
      commitMode(node, widget, oldCallback, value, [value, ...args], currentConflicts);
    }, () => { widget.value = previous; applyProjection(node, previous); });
  };
  installOperationNotice(node);
  syncOperationChoices(node);
  applyProjection(node, widget.value);
}

function nodesInGraph(node) {
  return node.graph?._nodes || app.graph?._nodes || [];
}

function widgetsFor(node) {
  return Object.fromEntries((node.widgets || []).map((widget) => [widget.name, widget]));
}

function setWidgetHidden(widget, hidden) {
  if (!widget.options || typeof widget.options !== "object") widget.options = {};
  widget.hidden = Boolean(hidden);
  widget.options.hidden = Boolean(hidden);
}

const I2V_ASPECTS = new Set(["Auto", "16:9", "9:16", "1:1", "4:3", "3:4"]);

function sanitizeModePreferences(node) {
  if (!node.properties || typeof node.properties !== "object" || Array.isArray(node.properties)) node.properties = {};
  const previous = node.properties.matrixWan3;
  const stored = previous?.imageToVideo;
  const schemaVersion = previous?.schemaVersion === WORKFLOW_SCHEMA_VERSION ? WORKFLOW_SCHEMA_VERSION : undefined;
  const safe = {};
  if (stored && typeof stored === "object" && !Array.isArray(stored)) {
    if (I2V_ASPECTS.has(stored.aspect_ratio)) safe.aspect_ratio = stored.aspect_ratio;
    if (stored.image_variant === "Regular" || stored.image_variant === "Spicy") safe.image_variant = stored.image_variant;
  }
  if (Object.keys(safe).length || schemaVersion) node.properties.matrixWan3 = { ...(schemaVersion ? { schemaVersion } : {}), ...(Object.keys(safe).length ? { imageToVideo: safe } : {}) };
  else delete node.properties.matrixWan3;
  return safe;
}

function saveI2VPreferences(node, controls = widgetsFor(node)) {
  const safe = sanitizeModePreferences(node);
  if (I2V_ASPECTS.has(controls.aspect_ratio?.value)) safe.aspect_ratio = controls.aspect_ratio.value;
  if (controls.image_variant?.value === "Regular" || controls.image_variant?.value === "Spicy") safe.image_variant = controls.image_variant.value;
  node.properties.matrixWan3 = { ...(node.properties.matrixWan3?.schemaVersion === WORKFLOW_SCHEMA_VERSION ? { schemaVersion: WORKFLOW_SCHEMA_VERSION } : {}), imageToVideo: safe };
}

function modeControlValues(node, nextMode, controls = widgetsFor(node)) {
  if (nextMode === "Image to Video") {
    const preferences = sanitizeModePreferences(node);
    return {
      aspect_ratio: preferences.aspect_ratio ?? "Auto",
      image_variant: preferences.image_variant ?? "Regular",
    };
  }
  const projected = { image_variant: "Regular" };
  if (controls.aspect_ratio?.value === "Auto") projected.aspect_ratio = "16:9";
  return projected;
}

function configureModeState(node) {
  const controls = widgetsFor(node);
  sanitizeModePreferences(node);
  const mode = controls.operation?.value;
  node._matrixWan3Operation = mode;
  if (mode === "Image to Video") saveI2VPreferences(node, controls);
  else {
    if (controls.image_variant) controls.image_variant.value = "Regular";
    if (controls.aspect_ratio?.value === "Auto") controls.aspect_ratio.value = "16:9";
  }
  applyProjection(node, mode);
  return mode;
}

function fitNodeHeight(node) {
  const computed = node.computeSize?.();
  const target = Number(computed?.[1]);
  const current = Number(node.size?.[1]);
  const width = Number(node.size?.[0]);
  if (!Number.isFinite(target) || target <= 0 || !Number.isFinite(current) || current <= target + 32 || node[PROMPT_LAYOUT]?.height > 120 || Number(node.properties?.matrixWan3PromptHeight) > 120) return false;
  node.setSize?.([Number.isFinite(width) ? width : Number(computed?.[0]) || 430, target]);
  node.setDirtyCanvas?.(true, true);
  return true;
}

function refreshNodeIdentity(node, { freshIntent = false } = {}) {
  const widgets = widgetsFor(node);
  const scope = widgets.credential_scope;
  const otherHasScope = scope?.value && nodesInGraph(node).some((other) => other !== node && other.type === node.type && widgetsFor(other).credential_scope?.value === scope.value);
  if (!scope) return;
  if (!scope.value || otherHasScope) {
    scope.value = crypto.randomUUID();
    scope.callback?.(scope.value);
    freshIntent = true;
  }
  const nonce = widgets.intent_nonce;
  if (nonce && (!nonce.value || nonce.value === "initial" || freshIntent)) {
    nonce.value = crypto.randomUUID();
    nonce.callback?.(nonce.value);
  }
}

app.registerExtension({
  name: "matrix.wan3",
  beforeConfigureGraph(graphData) {
    migrateLegacyGraphData(graphData);
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = original?.apply(this, args);
      const activation = widgetsFor(this).billing_activation;
      if (activation) activation.value = "wavespeed_v1";
      refreshNodeIdentity(this);
      installModeProjection(this);
      installSeedProjection(this);
      installHalo(this);
      requestAnimationFrame(() => {
        if (this.graph || !this._matrixWan3Removed) {
          installKeyControl(this);
          installNativeLayout(this);
          fitNodeHeight(this);
        }
      });
      const previousConfigure = this.onConfigure;
      this.onConfigure = function (...configureArgs) {
        const configured = previousConfigure?.apply(this, configureArgs);
        migrateLegacyWorkflow(this, configureArgs[0]);
        refreshNodeIdentity(this);
        restoreNodeDecorations(this);
        installModeProjection(this);
        installSeedProjection(this);
        preserveLegacyFixedSeed(this, configureArgs[0]);
        const configuredMode = configureModeState(this);
        syncOperationChoices(this);
        applyProjection(this, configuredMode);
        fitNodeHeight(this);
        requestAnimationFrame(() => installNativeLayout(this));
        return configured;
      };
      const previousAfterGraphConfigured = this.onAfterGraphConfigured;
      this.onAfterGraphConfigured = function (...graphArgs) {
        const configured = previousAfterGraphConfigured?.apply(this, graphArgs);
        restoreNodeDecorations(this);
        syncOperationChoices(this);
        applyProjection(this, widgetsFor(this).operation?.value);
        return configured;
      };
      const previousConnectionsChange = this.onConnectionsChange;
      this.onConnectionsChange = function (...connectionArgs) {
        const changed = previousConnectionsChange?.apply(this, connectionArgs);
        syncOperationChoices(this);
        applyProjection(this, widgetsFor(this).operation?.value);
        fitNodeHeight(this);
        return changed;
      };
      installRemovalHook(this);
      return result;
    };
  },
});
