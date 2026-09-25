import { app } from "../../scripts/app.js";
import {
  createHaloResolutionDeck,
  createHaloWidgetHost,
  haloMinimumNodeHeight,
  haloWidgetLayoutHeight,
  measureHaloContentHeight,
  setHaloNodeSize,
} from "./halo_resolution.8dff7e8fca32fa44.mjs";

const NODE_ID = "MATRIX_H3Resolution";
export const LEGACY_NODE_ID = "MATRIX_H3Resolution_V06_MIGRATION_REQUIRED";
export const CONTROL = Symbol.for("matrix.h3-resolution.control-deck");
export const ASPECT_RATIOS = Object.freeze(["1:1", "16:9", "9:16", "4:3", "3:4", "Custom"]);
export const RESOLUTION_TIERS = Object.freeze(["1K", "2K"]);
export const DEFAULT_STATE = Object.freeze({
  aspect_ratio: "9:16",
  resolution_tier: "1K",
  custom_width: 576,
  custom_height: 1024,
});

const PRESET_OUTPUTS = Object.freeze({
  "1:1|1K": [1024, 1024], "16:9|1K": [1024, 576], "9:16|1K": [576, 1024],
  "4:3|1K": [1024, 768], "3:4|1K": [768, 1024],
  "1:1|2K": [2048, 2048], "16:9|2K": [2048, 1152], "9:16|2K": [1152, 2048],
  "4:3|2K": [2048, 1536], "3:4|2K": [1536, 2048],
});

function requireChoice(value, name, choices) {
  if (typeof value !== "string" || !choices.includes(value)) {
    throw new Error(name + " must be one of " + choices.join(", "));
  }
}

function requireDimension(value, name) {
  if (!Number.isInteger(value)) throw new Error(name + " must be an integer");
  if (value < 32 || value > 2048) throw new Error(name + " must be between 32 and 2048");
  if (value % 32) throw new Error(name + " must be a multiple of 32");
  return value;
}

export function calculateH3Resolution(state) {
  requireChoice(state?.aspect_ratio, "aspect_ratio", ASPECT_RATIOS);
  requireChoice(state?.resolution_tier, "resolution_tier", RESOLUTION_TIERS);
  const customWidth = requireDimension(state?.custom_width, "custom_width");
  const customHeight = requireDimension(state?.custom_height, "custom_height");
  if (state.aspect_ratio === "Custom") return [customWidth, customHeight];
  return [...PRESET_OUTPUTS[state.aspect_ratio + "|" + state.resolution_tier]];
}

export function applyH3Action(state, action) {
  if (action.startsWith("ratio:")) {
    const next = { ...state, aspect_ratio: action.slice(6) };
    calculateH3Resolution(next);
    return next;
  }
  if (action.startsWith("size:")) {
    const next = { ...state, resolution_tier: action.slice(5) };
    calculateH3Resolution(next);
    return next;
  }
  if (action === "reset") return { ...DEFAULT_STATE };
  throw new Error("Unknown H3 resolution action: " + action);
}

export function readH3StateFromWidgets(widgets) {
  const byName = Object.fromEntries((widgets || []).map((widget) => [widget.name, widget]));
  return Object.fromEntries(
    Object.entries(DEFAULT_STATE).map(([name, fallback]) => [name, byName[name]?.value ?? fallback])
  );
}

export function refuseLegacyV06Graphs(graph) {
  for (const node of graph?.nodes || []) {
    if ((node?.type === NODE_ID || node?.comfyClass === NODE_ID) &&
        Array.isArray(node.widgets_values) && node.widgets_values.length === 5) {
      node.type = LEGACY_NODE_ID;
      node.comfyClass = LEGACY_NODE_ID;
      node.title = "MATRIX H3 RESOLUTION — MIGRATION REQUIRED";
      node.properties ||= {};
      node.properties.matrix_h3_migration = "Migration required: replace the V0.6 five-output node and reconnect outputs by meaning.";
    }
  }
  return graph;
}

function widgetsByName(node) {
  return Object.fromEntries((node.widgets || []).map((widget) => [widget.name, widget]));
}

function readState(node) {
  return readH3StateFromWidgets(node.widgets);
}

function isWidgetLinked(node, widget) {
  return (node.inputs || []).some((input) =>
    (input?.widget?.name === widget?.name || input?.name === widget?.name) && input.link != null
  );
}

function writeState(node, next) {
  const widgets = widgetsByName(node);
  const changed = Object.entries(next).filter(([name, value]) => widgets[name] && widgets[name].value !== value);
  const linked = changed.find(([name]) => isWidgetLinked(node, widgets[name]));
  if (linked) throw new Error(linked[0] + " is controlled by a connected input");
  app.graph?.beforeChange?.();
  try {
    for (const [name, value] of changed) widgets[name].value = value;
    for (const [name, value] of changed) {
      widgets[name].callback?.call(widgets[name], value, app.canvas, node, undefined, undefined);
    }
  } finally {
    app.graph?.afterChange?.();
  }
  node.setDirtyCanvas?.(true, true);
}

function hideCanonicalWidgets(node, control) {
  for (const widget of node.widgets || []) {
    if (!Object.hasOwn(DEFAULT_STATE, widget.name)) continue;
    const hadOptions = Boolean(widget.options);
    widget.options ||= {};
    const entry = {
      widget, draw: widget.draw, computeSize: widget.computeSize, callback: widget.callback,
      hidden: widget.hidden, optionHidden: widget.options.hidden, hadOptions,
    };
    const previous = widget.callback;
    entry.watchedCallback = function () {
      try { return previous?.apply(this, arguments); } finally { control.render?.(); }
    };
    control.widgetPresentation.push(entry);
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
    widget.hidden = true;
    widget.options.hidden = true;
    widget.callback = entry.watchedCallback;
  }
}

function restoreCanonicalWidgets(control) {
  for (const entry of control.widgetPresentation) {
    const { widget } = entry;
    widget.draw = entry.draw;
    widget.computeSize = entry.computeSize;
    if (widget.callback === entry.watchedCallback) widget.callback = entry.callback;
    if (entry.hidden === undefined) delete widget.hidden; else widget.hidden = entry.hidden;
    if (entry.optionHidden === undefined) delete widget.options.hidden;
    else widget.options.hidden = entry.optionHidden;
    if (!entry.hadOptions && Object.keys(widget.options).length === 0) delete widget.options;
  }
  control.widgetPresentation.length = 0;
}

function createCustomFields(node, control) {
  const section = document.createElement("section");
  section.style.cssText = "position:relative;z-index:2;margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:8px";
  const inputs = {};
  for (const [name, label] of [["custom_width", "CUSTOM WIDTH"], ["custom_height", "CUSTOM HEIGHT"]]) {
    const wrapper = document.createElement("label");
    wrapper.style.cssText = "display:grid;gap:5px;color:#A0B7A7;font-size:9px;letter-spacing:.08em";
    const title = document.createElement("span");
    title.textContent = label;
    const input = document.createElement("input");
    input.type = "number";
    input.min = "32";
    input.max = "2048";
    input.step = "32";
    input.style.cssText = "box-sizing:border-box;width:100%;min-height:34px;border:1px solid #31543C;border-radius:8px;background:#0B1710;color:#EDF8F0;padding:7px 9px;font:400 12px/18px inherit";
    input.addEventListener("change", () => {
      try {
        const value = Number(input.value);
        requireDimension(value, name);
        const next = { ...readState(node), aspect_ratio: "Custom", [name]: value };
        calculateH3Resolution(next);
        writeState(node, next);
        control.errorMessage = "";
      } catch (error) {
        control.errorMessage = String(error?.message || error);
        input.value = String(readState(node)[name]);
      }
      control.render?.();
    });
    wrapper.append(title, input);
    section.append(wrapper);
    inputs[name] = input;
  }
  const note = document.createElement("div");
  note.style.cssText = "grid-column:1/-1;color:#8FAF99;font-size:9px;line-height:14px";
  note.textContent = "Custom dimensions are exact generation pixels on a 32-pixel grid.";
  section.append(note);
  control.customInputs = inputs;
  return section;
}

function createDeckElement(node, control) {
  const ratioItems = ASPECT_RATIOS.map((value) => ({
    id: "ratio:" + value, group: "ratio", value,
    label: value === "Custom" ? "CUSTOM" : value,
    ratio: value === "Custom" ? null : value.split(":").map(Number),
  }));
  const sizeItems = RESOLUTION_TIERS.map((value) => ({
    id: "size:" + value, group: "size", value, label: value,
  }));
  const root = createHaloResolutionDeck({
    document, node, control, ariaLabel: "MATRIX H3 Resolution controls", haloOptions: { app },
    groups: [
      { id: "ratio", label: "ASPECT", items: ratioItems },
      { id: "size", label: "SIZE", items: sizeItems },
    ],
    actions: [{ id: "reset", label: "RESET" }],
    activate: (action) => control.activate(action),
    isDisabled(action) {
      const names = action.startsWith("ratio:") ? ["aspect_ratio"]
        : action.startsWith("size:") ? ["resolution_tier"] : Object.keys(DEFAULT_STATE);
      return names.some((name) => isWidgetLinked(node, widgetsByName(node)[name]));
    },
    disabledReason: () => "Controlled by a linked input",
    view() {
      const state = readState(node);
      let dimensions = [state.custom_width, state.custom_height];
      try {
        dimensions = calculateH3Resolution(state);
      } catch (error) {
        control.errorMessage = String(error?.message || error);
      }
      return {
        tier: state.aspect_ratio === "Custom" ? "CUSTOM" : state.resolution_tier,
        profile: "H3",
        active: { ratio: "ratio:" + state.aspect_ratio, size: "size:" + state.resolution_tier },
        dimensions,
        ratioLabel: state.aspect_ratio,
        method: "",
        error: control.errorMessage || "",
      };
    },
  });
  root.appendChild(createCustomFields(node, control));
  control.element = root;
  if (typeof ResizeObserver === "function") {
    control.resizeObserver = new ResizeObserver(() => control.render());
    control.resizeObserver.observe(root);
  }
  const baseRender = control.render;
  control.render = () => {
    const state = readState(node);
    for (const [name, input] of Object.entries(control.customInputs || {})) {
      if (document.activeElement !== input) input.value = String(state[name]);
      input.disabled = isWidgetLinked(node, widgetsByName(node)[name]);
    }
    baseRender();
  };
  return root;
}

function install(node) {
  if (node[CONTROL]) return node[CONTROL];
  if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return null;
  const control = {
    destroyed: false, resizeTimer: null, enforcingMinimumSize: false,
    widgetPresentation: [], previousResize: null, watchedResize: null,
    activate(action) {
      if (this.destroyed) return false;
      try {
        const next = applyH3Action(readState(node), action);
        calculateH3Resolution(next);
        writeState(node, next);
        this.errorMessage = "";
      } catch (error) {
        this.errorMessage = String(error?.message || error);
        console.warn("MATRIX H3 Resolution action was refused", error);
        this.render?.();
        return false;
      }
      this.render?.();
      return true;
    },
  };
  const widgetsBeforeMount = new Set(node.widgets || []);
  let element;
  let host;
  let domWidget;
  try {
    element = createDeckElement(node, control);
    host = createHaloWidgetHost(element, document);
    if (!host) throw new Error("MATRIX H3 Resolution HALO host unavailable");
    control.host = host;
    domWidget = node.addDOMWidget("matrixlab_h3_resolution_ui", "matrixlab-prism", host, {
      serialize: false, hideOnZoom: false,
      getMinHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, 510), domWidget),
      getHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, 510), domWidget),
      afterResize: () => control.render?.(),
    });
    if (!domWidget) throw new Error("ComfyUI did not create the DOM widget");
    domWidget.serialize = false;
    domWidget.options ||= {};
    domWidget.options.serialize = false;
    if (!control.mountHalo?.()) throw new Error("MATRIX H3 Resolution HALO surface unavailable");
    hideCanonicalWidgets(node, control);
    node[CONTROL] = control;
  } catch (error) {
    control.destroyed = true;
    control.resizeObserver?.disconnect();
    control.halo?.destroy();
    restoreCanonicalWidgets(control);
    if (Array.isArray(node.widgets)) {
      for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
        const widget = node.widgets[index];
        if (!widgetsBeforeMount.has(widget) &&
            (widget === domWidget || widget?.element === host || widget?.name === "matrixlab_h3_resolution_ui")) {
          node.widgets.splice(index, 1);
        }
      }
    }
    element?.remove();
    host?.remove();
    console.warn("MATRIX H3 Resolution kept native widgets after frontend mount failure", error);
    return null;
  }
  const ensureMinimumSize = () => {
    if (control.destroyed || control.enforcingMinimumSize) return;
    control.enforcingMinimumSize = true;
    try {
      const width = Math.max(420, Number(node.size?.[0]) || 420);
      const height = haloMinimumNodeHeight(node, measureHaloContentHeight(element, 510), domWidget);
      setHaloNodeSize(node, [width, height]);
    } finally {
      control.enforcingMinimumSize = false;
    }
  };
  control.scheduleMinimumSize = () => {
    clearTimeout(control.resizeTimer);
    control.resizeTimer = setTimeout(() => {
      control.resizeTimer = null;
      ensureMinimumSize();
      control.render?.();
    }, 0);
  };
  control.previousResize = node.onResize;
  control.watchedResize = function () {
    const result = control.previousResize?.apply(this, arguments);
    if (!control.enforcingMinimumSize) control.scheduleMinimumSize();
    control.render?.();
    return result;
  };
  node.onResize = control.watchedResize;
  const previousRemoved = node.onRemoved;
  node.onRemoved = function () {
    control.destroyed = true;
    clearTimeout(control.resizeTimer);
    control.resizeObserver?.disconnect();
    control.halo?.destroy();
    restoreCanonicalWidgets(control);
    if (this.onResize === control.watchedResize) this.onResize = control.previousResize;
    if (this[CONTROL] === control) delete this[CONTROL];
    element?.remove();
    host?.remove();
    return previousRemoved?.apply(this, arguments);
  };
  node.resizable = true;
  ensureMinimumSize();
  control.render();
  node.setDirtyCanvas?.(true, true);
  return control;
}

app.registerExtension({
  name: "matrix.h3-resolution.halo.classic",
  beforeConfigureGraph(graph) { refuseLegacyV06Graphs(graph); },
  nodeCreated(node) { if ((node.comfyClass || node.type) === NODE_ID) install(node); },
  loadedGraphNode(node) { if ((node.comfyClass || node.type) === NODE_ID) install(node); },
});
