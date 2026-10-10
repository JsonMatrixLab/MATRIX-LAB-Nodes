import { app } from "../../scripts/app.js";
import {
  createHaloResolutionDeck,
  createHaloWidgetHost,
  haloMinimumNodeHeight,
  haloWidgetLayoutHeight,
  measureHaloContentHeight,
  setHaloNodeSize,
} from "./halo_resolution.8dff7e8fca32fa44.mjs";

const NODE_ID = "MATRIX_QwenImage21Resolution";
export const CONTROL = Symbol.for("matrix.qwen-image-21-resolution.control-deck");
export const ASPECT_RATIOS = Object.freeze(["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"]);
export const DEFAULT_STATE = Object.freeze({ aspect_ratio: "1:1" });
const NATIVE_SIZES = Object.freeze({
  "1:1": [2048, 2048],
  "4:3": [2400, 1792],
  "3:4": [1792, 2400],
  "3:2": [2528, 1696],
  "2:3": [1696, 2528],
  "16:9": [2752, 1536],
  "9:16": [1536, 2752],
});

export function calculateQwenImage21Resolution(state) {
  if (typeof state?.aspect_ratio !== "string" || !Object.hasOwn(NATIVE_SIZES, state.aspect_ratio)) {
    throw new Error("aspect_ratio must be one of " + ASPECT_RATIOS.join(", "));
  }
  const [width, height] = NATIVE_SIZES[state.aspect_ratio];
  const longestSide = Math.max(width, height);
  if (width % 32 || height % 32) throw new Error("width and height must be multiples of 32");
  if (longestSide > 2752) throw new Error("longest dimension must be at most 2752");
  if (width * height > 2400 * 1792) throw new Error("pixel area must be at most 4300800");
  return [width, height];
}

export function applyQwenImage21Action(state, action) {
  if (action === "reset") return { ...DEFAULT_STATE };
  if (!action.startsWith("ratio:")) throw new Error("Unknown Qwen Image 2.1 resolution action: " + action);
  const next = { ...state, aspect_ratio: action.slice(6) };
  calculateQwenImage21Resolution(next);
  return next;
}

export function readQwenImage21StateFromWidgets(widgets) {
  const widget = (widgets || []).find((item) => item.name === "aspect_ratio");
  return { aspect_ratio: widget?.value ?? DEFAULT_STATE.aspect_ratio };
}

function widgetsByName(node) {
  return Object.fromEntries((node.widgets || []).map((widget) => [widget.name, widget]));
}

function readState(node) {
  return readQwenImage21StateFromWidgets(node.widgets);
}

function isWidgetLinked(node, widget) {
  return (node.inputs || []).some((input) =>
    (input?.widget?.name === widget?.name || input?.name === widget?.name) && input.link != null
  );
}

function writeState(node, next) {
  const widget = widgetsByName(node).aspect_ratio;
  if (!widget || widget.value === next.aspect_ratio) return;
  if (isWidgetLinked(node, widget)) throw new Error("aspect_ratio is controlled by a connected input");
  app.graph?.beforeChange?.();
  try {
    widget.value = next.aspect_ratio;
    widget.callback?.call(widget, widget.value, app.canvas, node, undefined, undefined);
  } finally {
    app.graph?.afterChange?.();
  }
  node.setDirtyCanvas?.(true, true);
}

function hideCanonicalWidget(node, control) {
  const widget = widgetsByName(node).aspect_ratio;
  if (!widget) throw new Error("canonical aspect_ratio widget unavailable");
  const hadOptions = Boolean(widget.options);
  widget.options ||= {};
  control.widgetPresentation = {
    widget,
    draw: widget.draw,
    computeSize: widget.computeSize,
    callback: widget.callback,
    hidden: widget.hidden,
    optionHidden: widget.options.hidden,
    hadOptions,
  };
  const previous = widget.callback;
  control.widgetPresentation.watchedCallback = function () {
    try { return previous?.apply(this, arguments); } finally { control.render?.(); }
  };
  widget.draw = () => {};
  widget.computeSize = () => [0, -4];
  widget.hidden = true;
  widget.options.hidden = true;
  widget.callback = control.widgetPresentation.watchedCallback;
}

function restoreCanonicalWidget(control) {
  const entry = control.widgetPresentation;
  if (!entry) return;
  const { widget } = entry;
  widget.draw = entry.draw;
  widget.computeSize = entry.computeSize;
  if (widget.callback === entry.watchedCallback) widget.callback = entry.callback;
  if (entry.hidden === undefined) delete widget.hidden; else widget.hidden = entry.hidden;
  if (entry.optionHidden === undefined) delete widget.options.hidden;
  else widget.options.hidden = entry.optionHidden;
  if (!entry.hadOptions && Object.keys(widget.options).length === 0) delete widget.options;
  control.widgetPresentation = null;
}

function createDeckElement(node, control) {
  const root = createHaloResolutionDeck({
    document,
    node,
    control,
    ariaLabel: "MATRIX Qwen Image 2.1 Resolution controls",
    haloOptions: { app },
    groups: [{
      id: "ratio",
      label: "ASPECT",
      items: ASPECT_RATIOS.map((value) => ({
        id: "ratio:" + value,
        group: "ratio",
        value,
        label: value,
        ratio: value.split(":").map(Number),
      })),
    }],
    actions: [{ id: "reset", label: "RESET" }],
    activate: (action) => control.activate(action),
    isDisabled: () => isWidgetLinked(node, widgetsByName(node).aspect_ratio),
    disabledReason: () => "Controlled by a linked input",
    view() {
      const state = readState(node);
      let result = [0, 0];
      try {
        result = calculateQwenImage21Resolution(state);
        control.errorMessage = "";
      } catch (error) {
        control.errorMessage = String(error?.message || error);
      }
      return {
        tier: "QWEN IMAGE 2.1",
        profile: "NATIVE",
        active: { ratio: "ratio:" + state.aspect_ratio },
        dimensions: result.slice(0, 2),
        ratioLabel: state.aspect_ratio,
        method: "EXACT NATIVE SIZE",
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
    activate(action) {
      if (this.destroyed) return false;
      try {
        const next = applyQwenImage21Action(readState(node), action);
        calculateQwenImage21Resolution(next);
        writeState(node, next);
        this.errorMessage = "";
      } catch (error) {
        this.errorMessage = String(error?.message || error);
        console.warn("MATRIX Qwen Image 2.1 Resolution action was refused", error);
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
    if (!host) throw new Error("Qwen Image 2.1 HALO host unavailable");
    domWidget = node.addDOMWidget("matrixlab_qwen_image_21_resolution_ui", "matrixlab-qwen21-resolution", host, {
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
    if (!control.mountHalo?.()) throw new Error("Qwen Image 2.1 HALO surface unavailable");
    hideCanonicalWidget(node, control);
    node[CONTROL] = control;
  } catch (error) {
    control.destroyed = true;
    control.resizeObserver?.disconnect();
    control.halo?.destroy();
    restoreCanonicalWidget(control);
    if (Array.isArray(node.widgets)) {
      for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
        const widget = node.widgets[index];
        if (!widgetsBeforeMount.has(widget) &&
            (widget === domWidget || widget?.element === host || widget?.name === "matrixlab_qwen_image_21_resolution_ui")) {
          node.widgets.splice(index, 1);
        }
      }
    }
    element?.remove();
    host?.remove();
    console.warn("MATRIX Qwen Image 2.1 Resolution kept native widgets after frontend mount failure", error);
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
    restoreCanonicalWidget(control);
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
  name: "matrix.qwen-image-21-resolution.halo",
  nodeCreated(node) { if ((node.comfyClass || node.type) === NODE_ID) install(node); },
  loadedGraphNode(node) { if ((node.comfyClass || node.type) === NODE_ID) install(node); },
});
