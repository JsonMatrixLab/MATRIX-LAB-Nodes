import { app } from "../../scripts/app.js";
import {
  createHaloResolutionDeck,
  createHaloWidgetHost,
  haloMinimumNodeHeight,
  haloWidgetLayoutHeight,
  measureHaloContentHeight,
  setHaloNodeSize,
} from "./halo_resolution.8dff7e8fca32fa44.mjs";

const NODE_ID = "MATRIX_Flux3KleinResolution";
export const CONTROL = Symbol.for("matrix.flux-3-klein-resolution.control-deck");
export const ASPECT_RATIOS = Object.freeze(["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"]);
export const RESOLUTIONS = Object.freeze(["1K", "1.5K", "2K", "4K"]);
export const DEFAULT_STATE = Object.freeze({ aspect_ratio: "1:1", resolution: "1K" });
const TIER_SIDE = Object.freeze({ "1K": 1024, "1.5K": 1536, "2K": 2048, "4K": 4096 });
const SIZES = Object.freeze({
  "1K": { "1:1": [1024, 1024], "4:3": [1184, 880], "3:4": [880, 1184], "3:2": [1248, 832], "2:3": [832, 1248], "16:9": [1360, 768], "9:16": [768, 1360] },
  "1.5K": { "1:1": [1536, 1536], "4:3": [1776, 1328], "3:4": [1328, 1776], "3:2": [1888, 1248], "2:3": [1248, 1888], "16:9": [2048, 1152], "9:16": [1152, 2048] },
  "2K": { "1:1": [2048, 2048], "4:3": [2352, 1776], "3:4": [1776, 2352], "3:2": [2496, 1680], "2:3": [1680, 2496], "16:9": [2720, 1536], "9:16": [1536, 2720] },
  "4K": { "1:1": [4096, 4096], "4:3": [4096, 3088], "3:4": [3088, 4096], "3:2": [4096, 2752], "2:3": [2752, 4096], "16:9": [4096, 2320], "9:16": [2320, 4096] },
});

export function calculateFlux3KleinResolution(state) {
  if (typeof state?.aspect_ratio !== "string" || !ASPECT_RATIOS.includes(state.aspect_ratio)) {
    throw new Error("aspect_ratio must be one of " + ASPECT_RATIOS.join(", "));
  }
  if (typeof state?.resolution !== "string" || !Object.hasOwn(SIZES, state.resolution)) {
    throw new Error("resolution must be one of " + RESOLUTIONS.join(", "));
  }
  const [width, height] = SIZES[state.resolution][state.aspect_ratio];
  if (width % 16 || height % 16) throw new Error("width and height must be multiples of 16");
  if (Math.max(width, height) > 4096) throw new Error("longest dimension must be at most 4096");
  if (width * height > TIER_SIDE[state.resolution] ** 2) throw new Error("pixel area exceeds the resolution tier");
  return [width, height];
}

export function applyFlux3KleinAction(state, action) {
  if (action === "reset") return { ...DEFAULT_STATE };
  let next;
  if (action.startsWith("ratio:")) next = { ...state, aspect_ratio: action.slice(6) };
  else if (action.startsWith("res:")) next = { ...state, resolution: action.slice(4) };
  else throw new Error("Unknown FLUX 3 Klein resolution action: " + action);
  calculateFlux3KleinResolution(next);
  return next;
}

export function readFlux3KleinStateFromWidgets(widgets) {
  const byName = Object.fromEntries((widgets || []).map((widget) => [widget.name, widget]));
  return Object.fromEntries(
    Object.entries(DEFAULT_STATE).map(([name, fallback]) => [name, byName[name]?.value ?? fallback])
  );
}

function widgetsByName(node) {
  return Object.fromEntries((node.widgets || []).map((widget) => [widget.name, widget]));
}

function readState(node) {
  return readFlux3KleinStateFromWidgets(node.widgets);
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
  if (control.widgetPresentation.length !== Object.keys(DEFAULT_STATE).length) {
    throw new Error("canonical FLUX 3 Klein widgets unavailable");
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

function createDeckElement(node, control) {
  const root = createHaloResolutionDeck({
    document,
    node,
    control,
    ariaLabel: "MATRIX FLUX 3 Klein Resolution controls",
    haloOptions: { app },
    groups: [
      {
        id: "ratio",
        label: "ASPECT",
        items: ASPECT_RATIOS.map((value) => ({
          id: "ratio:" + value, group: "ratio", value, label: value, ratio: value.split(":").map(Number),
        })),
      },
      {
        id: "res",
        label: "RES",
        items: RESOLUTIONS.map((value) => ({ id: "res:" + value, group: "res", value, label: value })),
      },
    ],
    actions: [{ id: "reset", label: "RESET" }],
    activate: (action) => control.activate(action),
    isDisabled(action) {
      const names = action.startsWith("ratio:") ? ["aspect_ratio"]
        : action.startsWith("res:") ? ["resolution"] : Object.keys(DEFAULT_STATE);
      return names.some((name) => isWidgetLinked(node, widgetsByName(node)[name]));
    },
    disabledReason: () => "Controlled by a linked input",
    view() {
      const state = readState(node);
      let result = [0, 0];
      try {
        result = calculateFlux3KleinResolution(state);
        control.errorMessage = "";
      } catch (error) {
        control.errorMessage = String(error?.message || error);
      }
      return {
        tier: state.resolution,
        profile: "KLEIN",
        active: { ratio: "ratio:" + state.aspect_ratio, res: "res:" + state.resolution },
        dimensions: result.slice(0, 2),
        ratioLabel: state.aspect_ratio,
        method: result[0] ? (result[0] * result[1] / 1048576).toFixed(2) + " MP \u00b7 " + (result[0] * result[1] / 256) + " TOKENS" : "",
        error: control.errorMessage || "",
      };
    },
  });
  control.element = root;
  if (typeof ResizeObserver === "function") {
    control.resizeObserver = new ResizeObserver(() => control.render());
    control.resizeObserver.observe(root);
  }
  return root;
}

function install(node) {
  if (node[CONTROL]) return node[CONTROL];
  if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return null;
  const control = {
    destroyed: false,
    enforcingMinimumSize: false,
    resizeTimer: null,
    widgetPresentation: [],
    activate(action) {
      if (this.destroyed) return false;
      try {
        const next = applyFlux3KleinAction(readState(node), action);
        calculateFlux3KleinResolution(next);
        writeState(node, next);
        this.errorMessage = "";
      } catch (error) {
        this.errorMessage = String(error?.message || error);
        console.warn("MATRIX FLUX 3 Klein Resolution action was refused", error);
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
    if (!host) throw new Error("FLUX 3 Klein HALO host unavailable");
    domWidget = node.addDOMWidget("matrixlab_flux_3_klein_resolution_ui", "matrixlab-flux3-klein-resolution", host, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, 430), domWidget),
      getHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, 430), domWidget),
      afterResize: () => control.render?.(),
    });
    if (!domWidget) throw new Error("ComfyUI did not create the DOM widget");
    domWidget.serialize = false;
    domWidget.options ||= {};
    domWidget.options.serialize = false;
    if (!control.mountHalo?.()) throw new Error("FLUX 3 Klein HALO surface unavailable");
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
            (widget === domWidget || widget?.element === host || widget?.name === "matrixlab_flux_3_klein_resolution_ui")) {
          node.widgets.splice(index, 1);
        }
      }
    }
    element?.remove();
    host?.remove();
    console.warn("MATRIX FLUX 3 Klein Resolution kept native widgets after frontend mount failure", error);
    return null;
  }
  const ensureMinimumSize = () => {
    if (control.destroyed || control.enforcingMinimumSize) return;
    control.enforcingMinimumSize = true;
    try {
      const width = Math.max(420, Number(node.size?.[0]) || 420);
      const height = haloMinimumNodeHeight(node, measureHaloContentHeight(element, 430), domWidget);
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
  name: "matrix.flux-3-klein-resolution.halo",
  nodeCreated(node) { if ((node.comfyClass || node.type) === NODE_ID) install(node); },
  loadedGraphNode(node) { if ((node.comfyClass || node.type) === NODE_ID) install(node); },
});
