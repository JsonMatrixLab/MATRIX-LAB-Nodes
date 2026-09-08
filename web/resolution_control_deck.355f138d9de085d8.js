import { app } from "../../scripts/app.js";
import { createHaloResolutionDeck, createHaloWidgetHost, haloMinimumNodeHeight, haloWidgetLayoutHeight, measureHaloContentHeight, setHaloNodeSize, calculateTierResolution, migrateResolutionGraph } from "./halo_resolution.f5554171d9d043a1.mjs";

const NODE_IDS = new Set("MATRIXLAB_Resolution".split(",").filter(Boolean));
const RATIOS = {
  "1:1": [1, 1], "16:9": [16, 9], "9:16": [9, 16], "4:3": [4, 3],
  "3:4": [3, 4], "3:2": [3, 2], "2:3": [2, 3], "4:5": [4, 5],
};
const RATIO_LABELS = [...Object.keys(RATIOS), "Custom"];
const SIZE_VALUES = ["1K", "2K", "4K"];
const DEFAULT_STATE = Object.freeze({
  aspect_ratio: "3:4", resolution_tier: "2K", custom_width: 2048,
  custom_height: 2048,
});
let activeEditorOwner = null;

export const BUTTONS = Object.freeze([
  ...RATIO_LABELS.map((value) => ({
    id: `ratio:${value}`, kind: "ratio", label: value === "Custom" ? "CUSTOM" : value, value,
  })),
  { id: "swap", kind: "swap", label: "SWAP" },
  ...SIZE_VALUES.map((value) => ({ id: `size:${value}`, kind: "size", label: String(value), value })),
  { id: "reset", kind: "reset", label: "RESET" },
]);

export function calculateResolution(state) {
  if (!Object.hasOwn(RATIOS, state.aspect_ratio) && state.aspect_ratio !== "Custom") {
    throw new Error(`Unsupported aspect ratio: ${state.aspect_ratio}`);
  }
  if (!SIZE_VALUES.includes(state.resolution_tier)) throw new Error(`Unsupported resolution tier: ${state.resolution_tier}`);
  for (const name of state.aspect_ratio === "Custom" ? ["custom_width", "custom_height"] : []) {
    const value = state[name];
    if (!Number.isInteger(value) || value < 1 || value > 16384) throw new Error(`Invalid ${name}: ${value}`);
  }
  return state.aspect_ratio === "Custom"
    ? [state.custom_width, state.custom_height]
    : calculateTierResolution(state.aspect_ratio, state.resolution_tier);
}

export function previewResolution(state) {
  try {
    return { ok: true, dimensions: calculateResolution(state), error: null };
  } catch (error) {
    return { ok: false, dimensions: null, error: String(error?.message || error) };
  }
}

export function applyCustomDimensions(state, width, height) {
  return { ...state, aspect_ratio: "Custom", custom_width: width, custom_height: height };
}

export function applyButton(state, buttonId) {
  const button = BUTTONS.find((candidate) => candidate.id === buttonId);
  if (!button) throw new Error(`Unknown resolution button: ${buttonId}`);
  if (button.kind === "ratio") return { ...state, aspect_ratio: button.value };
  if (button.kind === "size") return { ...state, resolution_tier: button.value };
  if (button.kind === "swap") {
    const [width, height] = calculateResolution(state);
    return { ...state, aspect_ratio: "Custom", custom_width: height, custom_height: width };
  }
  if (button.kind === "reset") return { ...DEFAULT_STATE };
  throw new Error(`Unhandled resolution button kind: ${button.kind}`);
}

export const CONTROL = Symbol.for("matrix.resolution.control-deck");

const COLORS = Object.freeze({
  muted: "#748279", accent: "#5CF2A5", accentInk: "#08130D",
  warning: "#FFCA6B", outline: "rgba(237,248,240,0.13)",
});
const MIN_WIDTH = 420;
const WIDE_BREAKPOINT = 560;

function semanticSurfaceHeight(width) {
  return Number(width) >= WIDE_BREAKPOINT ? 560 : 620;
}

function widgetsByName(node) {
  return Object.fromEntries((node.widgets || []).map((widget) => [widget.name, widget]));
}

function readState(node) {
  const widgets = widgetsByName(node);
  return {
    aspect_ratio: widgets.aspect_ratio?.value ?? DEFAULT_STATE.aspect_ratio,
    resolution_tier: widgets.resolution_tier?.value ?? DEFAULT_STATE.resolution_tier,
    custom_width: widgets.custom_width?.value ?? DEFAULT_STATE.custom_width,
    custom_height: widgets.custom_height?.value ?? DEFAULT_STATE.custom_height,
  };
}

function isWidgetLinked(node, widget) {
  return (node.inputs || []).some((input) =>
    (input?.widget?.name === widget?.name || input?.name === widget?.name) &&
    input.link !== null &&
    input.link !== undefined
  );
}

function writeState(node, next) {
  const widgets = widgetsByName(node);
  const changed = [];
  for (const [name, value] of Object.entries(next)) {
    const widget = widgets[name];
    if (!widget || widget.value === value) continue;
    changed.push([widget, value]);
  }
  const linked = changed.find(([widget]) => isWidgetLinked(node, widget));
  if (linked) throw new Error(`${linked[0].name} is controlled by a connected input`);
  for (const [widget, value] of changed) widget.value = value;
  for (const [widget, value] of changed) {
    try {
      widget.callback?.call(widget, value, app.canvas, node, undefined, undefined);
    } catch (error) {
      console.warn("MATRIXLAB Resolution widget callback failed", error);
    }
  }
  node.setDirtyCanvas?.(true, true);
}

export function nextDialogFocusIndex(currentIndex, count, reverse = false) {
  if (!Number.isInteger(count) || count <= 0) return -1;
  if (!Number.isInteger(currentIndex) || currentIndex < 0 || currentIndex >= count) return 0;
  return (currentIndex + (reverse ? -1 : 1) + count) % count;
}

function openCustomEditor(node, control, initialField = "custom_width") {
  if (typeof document === "undefined" || control.destroyed) return false;
  control.closeEditor?.();
  activeEditorOwner?.close?.();
  const previousFocus = document.activeElement;
  const editorToken = Symbol("matrixlab-resolution-editor");
  const state = readState(node);
  const overlay = document.createElement("div");
  overlay.setAttribute("role", "presentation");
  Object.assign(overlay.style, {
    position: "fixed", inset: "0", zIndex: "100000", display: "grid",
    placeItems: "center", background: "#000000C2",
  });
  const form = document.createElement("form");
  form.noValidate = true;
  form.setAttribute("role", "dialog");
  form.setAttribute("aria-modal", "true");
  Object.assign(form.style, {
    boxSizing: "border-box", width: "min(390px, calc(100vw - 32px))", padding: "20px",
    border: "1px solid #31543C", borderRadius: "16px", background: "#050A05",
    color: "#EDF8F0", boxShadow: "0 18px 44px #000000BB, 0 0 26px #00FF4117",
    fontFamily: '"MATRIXLAB HALO Mono", "Cascadia Mono", "Cascadia Code", Consolas, "Liberation Mono", monospace',
  });
  const heading = document.createElement("div");
  heading.id = "matrix-resolution-custom-editor";
  heading.textContent = "CUSTOM RESOLUTION";
  heading.style.cssText = "font-size:13px;font-weight:700;letter-spacing:.08em;margin-bottom:6px";
  form.setAttribute("aria-labelledby", heading.id);
  const helper = document.createElement("div");
  helper.textContent = "Set exact width and height. Apply commits both values together.";
  helper.style.cssText = `color:${COLORS.muted};font-size:10px;line-height:1.45;margin-bottom:16px`;
  const fields = document.createElement("div");
  fields.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:8px";
  const inputs = {};
  for (const [name, title] of [["custom_width", "WIDTH"], ["custom_height", "HEIGHT"]]) {
    const wrapper = document.createElement("label");
    wrapper.style.cssText = `display:grid;gap:6px;color:${COLORS.muted};font-size:9px;letter-spacing:.12em`;
    wrapper.append(title);
    const input = document.createElement("input");
    input.type = "number";
    input.min = "1";
    input.max = "16384";
    input.step = "1";
    input.value = String(state[name]);
    input.name = name;
    input.setAttribute("aria-label", title);
    input.style.cssText = "box-sizing:border-box;width:100%;min-height:38px;border:1px solid #31543C;border-radius:9px;background:linear-gradient(125deg,#172B1EDF 0%,#0B1710ED 100%);color:#EDF8F0;padding:8px 10px;font:400 13px/19.5px inherit;outline:none";
    input.addEventListener("focus", () => { input.style.borderColor = COLORS.warning; });
    input.addEventListener("blur", () => { input.style.borderColor = COLORS.outline; });
    wrapper.append(input);
    fields.append(wrapper);
    inputs[name] = input;
  }
  const livePreview = document.createElement("div");
  livePreview.style.cssText = `margin-top:10px;color:${COLORS.accent};font-size:11px;min-height:17px`;
  const error = document.createElement("div");
  error.setAttribute("aria-live", "polite");
  error.style.cssText = `min-height:18px;margin-top:5px;color:${COLORS.warning};font-size:10px`;
  const actions = document.createElement("div");
  actions.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "CANCEL";
  const apply = document.createElement("button");
  apply.type = "submit";
  apply.textContent = "APPLY";
  for (const button of [cancel, apply]) {
    button.style.cssText = "min-height:36px;border:1px solid #31513C;border-radius:8px;background:#101F15;color:#B0C6B7;font:400 10px/15px inherit;cursor:pointer";
  }
  apply.style.background = COLORS.accent;
  apply.style.borderColor = COLORS.accent;
  apply.style.color = COLORS.accentInk;
  actions.append(cancel, apply);
  form.append(heading, helper, fields, livePreview, error, actions);
  overlay.append(form);
  document.body.append(overlay);

  const canvas = app.canvas;
  const previousProcessKey = canvas?.processKey;
  const guardedProcessKey = typeof previousProcessKey === "function"
    ? function (event) {
      if (overlay.isConnected && overlay.contains(event?.target)) return false;
      return previousProcessKey.apply(this, arguments);
    } : null;
  if (guardedProcessKey) canvas.processKey = guardedProcessKey;
  let focusTimer = null;

  const updatePreview = () => {
    const width = Number(inputs.custom_width.value);
    const height = Number(inputs.custom_height.value);
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 16384 || height > 16384) {
      livePreview.textContent = "";
      return;
    }
    const result = previewResolution(applyCustomDimensions(state, width, height));
    livePreview.textContent = result.ok
      ? `${result.dimensions[0]} × ${result.dimensions[1]}  ·  ${((result.dimensions[0] * result.dimensions[1]) / 1_000_000).toFixed(2)} MP`
      : "";
  };
  for (const input of Object.values(inputs)) input.addEventListener("input", updatePreview);
  updatePreview();

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    clearTimeout(focusTimer);
    if (activeEditorOwner?.token === editorToken) {
      if (guardedProcessKey && canvas.processKey === guardedProcessKey) {
        canvas.processKey = previousProcessKey;
      }
      activeEditorOwner = null;
    }
    if (overlay.isConnected) overlay.remove();
    if (control.closeEditor === close) control.closeEditor = null;
    if (previousFocus?.isConnected && typeof previousFocus.focus === "function") previousFocus.focus();
  };
  control.closeEditor = close;
  activeEditorOwner = { token: editorToken, close };
  cancel.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    close();
  }, { once: true });
  overlay.addEventListener("mousedown", (event) => {
    event.stopPropagation();
    if (event.target === overlay) close();
  });
  for (const eventName of ["mouseup", "click", "keydown", "keyup", "keypress"]) {
    overlay.addEventListener(eventName, (event) => event.stopPropagation());
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const width = Number(inputs.custom_width.value);
    const height = Number(inputs.custom_height.value);
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || width > 16384 || height < 1 || height > 16384) {
      error.textContent = "Enter whole numbers from 1 to 16384 for both dimensions.";
      (!Number.isInteger(width) || width < 1 || width > 16384 ? inputs.custom_width : inputs.custom_height).focus();
      return;
    }
    const next = applyCustomDimensions(readState(node), width, height);
    const validated = previewResolution(next);
    if (!validated.ok) {
      error.textContent = validated.error;
      return;
    }
    writeState(node, next);
    close();
  });
  overlay.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [inputs.custom_width, inputs.custom_height, cancel, apply];
    const currentIndex = focusable.indexOf(document.activeElement);
    const nextIndex = nextDialogFocusIndex(currentIndex, focusable.length, event.shiftKey);
    if (nextIndex < 0) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    focusable[nextIndex].focus();
  });
  const initial = inputs[initialField] || inputs.custom_width;
  initial.focus();
  initial.select();
  focusTimer = setTimeout(() => {
    if (!overlay.isConnected) return;
    initial.focus();
    initial.select();
  }, 0);
  return true;
}

function hideCanonicalWidgets(node, control) {
  for (const widget of node.widgets || []) {
    if (!Object.hasOwn(DEFAULT_STATE, widget.name)) continue;
    const hadOptions = Boolean(widget.options);
    widget.options ||= {};
    const entry = {
      widget,
      draw: widget.draw,
      computeSize: widget.computeSize,
      callback: widget.callback,
      hadOptions,
      hidden: widget.options.hidden,
    };
    const previousCallback = widget.callback;
    entry.watchedCallback = function () {
      try {
        return previousCallback?.apply(this, arguments);
      } finally {
        control.render?.();
      }
    };
    control.widgetPresentation.push(entry);
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
    widget.options.hidden = true;
    widget.callback = entry.watchedCallback;
  }
}

function restoreCanonicalWidgets(control) {
  for (const entry of control.widgetPresentation) {
    entry.widget.draw = entry.draw;
    entry.widget.computeSize = entry.computeSize;
    if (entry.widget.callback === entry.watchedCallback) entry.widget.callback = entry.callback;
    if (entry.hidden === undefined) delete entry.widget.options.hidden;
    else entry.widget.options.hidden = entry.hidden;
    if (!entry.hadOptions && Object.keys(entry.widget.options).length === 0) delete entry.widget.options;
  }
  control.widgetPresentation.length = 0;
}

function createDeckElement(node, control) {
  const ratioItems = RATIO_LABELS.map((value) => ({
    id: `ratio:${value}`,
    label: value === "Custom" ? "CUSTOM" : value,
    ratio: RATIOS[value],
  }));
  const sizeItems = SIZE_VALUES.map((value) => ({ id: `size:${value}`, label: String(value) }));
  const root = createHaloResolutionDeck({
    document,
    node,
    control,
    ariaLabel: "MATRIXLAB Resolution controls",
    haloOptions: { app },
    groups: [
      { id: "ratio", label: "ASPECT", items: ratioItems },
      { id: "size", label: "SIZE", items: sizeItems },
    ],
    actions: [
      { id: "custom_width", label: "CUSTOM WIDTH" },
      { id: "custom_height", label: "CUSTOM HEIGHT" },
      { id: "swap", label: "SWAP" },
      { id: "reset", label: "RESET" },
    ],
    activate(action, event) {
      if (action === "custom_width" || action === "custom_height") {
        return openCustomEditor(node, control, action);
      }
      return control.activate(action, event);
    },
    isDisabled(action) {
      const state = readState(node);
      const widget = action.startsWith("ratio:") ? "aspect_ratio"
        : action.startsWith("size:") ? "resolution_tier"
          : action === "custom_width" || action === "custom_height" ? action : null;
      if (widget && isWidgetLinked(node, widgetsByName(node)[widget])) return true;
      if (["swap", "reset"].includes(action)) {
        const dependencies = ["aspect_ratio", "resolution_tier", "custom_width", "custom_height"];
        if (dependencies.some((name) => isWidgetLinked(node, widgetsByName(node)[name]))) return true;
      }
      return action.startsWith("custom_") && state.aspect_ratio !== "Custom";
    },
    disabledReason: () => "Controlled by a linked input or inactive mode",
    view() {
      const state = readState(node);
      const summary = previewResolution(state);
      const dimensions = summary.dimensions || [state.custom_width, state.custom_height];
      return {
        tier: state.aspect_ratio === "Custom" ? "CUSTOM" : state.resolution_tier,
        profile: "",
        active: {
          ratio: `ratio:${state.aspect_ratio}`,
          size: `size:${state.resolution_tier}`,
        },
        dimensions,
        ratioLabel: state.aspect_ratio,
        method: "",
        error: control.errorMessage || summary.error,
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
    destroyed: false, closeEditor: null,
    resizeTimer: null, enforcingMinimumSize: false,
    previousResize: null, watchedResize: null,
    widgetPresentation: [],
    activate(buttonId) {
      if (this.destroyed) return false;
      if (buttonId === "ratio:Custom") return openCustomEditor(node, this);
      try {
        const next = applyButton(readState(node), buttonId);
        const after = previewResolution(next);
        if (!after.ok) throw new Error(after.error);
        writeState(node, next);
        this.errorMessage = "";
      } catch (error) {
        this.errorMessage = String(error?.message || error);
        console.warn("MATRIXLAB Resolution action was refused", error);
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
    if (!host) throw new Error("MATRIXLAB Resolution HALO host unavailable");
    control.host = host;
    domWidget = node.addDOMWidget("matrixlab_resolution_ui", "matrixlab-prism", host, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, control.minimumContentHeight || semanticSurfaceHeight(element.clientWidth)), domWidget),
      getHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, control.minimumContentHeight || semanticSurfaceHeight(element.clientWidth)), domWidget),
      afterResize: () => control.render?.(),
    });
    if (!domWidget) throw new Error("ComfyUI did not create the DOM widget");
    // LiteGraph checks the widget property itself, not options.serialize.
    domWidget.serialize = false;
    domWidget.options ||= {};
    domWidget.options.serialize = false;
    if (!control.mountHalo?.()) throw new Error("MATRIXLAB Resolution HALO surface unavailable");
    hideCanonicalWidgets(node, control);
    node[CONTROL] = control;
  } catch (error) {
    control.destroyed = true;
    control.resizeObserver?.disconnect();
    control.removeElementListeners?.();
    control.halo?.destroy();
    restoreCanonicalWidgets(control);
    if (Array.isArray(node.widgets)) {
      for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
        const widget = node.widgets[index];
        if (widgetsBeforeMount.has(widget)) continue;
        if (widget === domWidget || widget?.element === host || widget?.name === "matrixlab_resolution_ui") {
          node.widgets.splice(index, 1);
        }
      }
    }
    element?.remove();
    host?.remove();
    console.warn("MATRIXLAB Resolution DOM UI unavailable; native widgets remain active", error);
    return null;
  }

  const ensureMinimumSize = () => {
    if (control.destroyed || control.enforcingMinimumSize) return;
    const currentWidth = Number(node.size?.[0]) || 0;
    const currentHeight = Number(node.size?.[1]) || 0;
    const renderedWidth = Number(element?.clientWidth) || 0;
    const measuredHorizontalChrome = renderedWidth > 0
      ? Math.max(0, currentWidth - renderedWidth)
      : 0;
    const width = Math.max(currentWidth, MIN_WIDTH + measuredHorizontalChrome);
    const contentHeight = measureHaloContentHeight(element, control.minimumContentHeight || semanticSurfaceHeight(element?.clientWidth));
    const height = haloMinimumNodeHeight(node, contentHeight);
    if (width === currentWidth && height === currentHeight) return;
    control.enforcingMinimumSize = true;
    try {
      const nextSize = [width, height];
      setHaloNodeSize(node, nextSize);
    } finally {
      control.enforcingMinimumSize = false;
    }
  };
  const scheduleMinimumSize = () => {
    clearTimeout(control.resizeTimer);
    control.resizeTimer = setTimeout(() => {
      control.resizeTimer = null;
      ensureMinimumSize();
      control.render?.();
    }, 0);
  };
  control.scheduleMinimumSize = scheduleMinimumSize;
  control.previousResize = node.onResize;
  control.watchedResize = function () {
    const result = control.previousResize?.apply(this, arguments);
    if (!control.enforcingMinimumSize) scheduleMinimumSize();
    control.render?.();
    return result;
  };
  node.onResize = control.watchedResize;

  const previousRemoved = node.onRemoved;
  node.onRemoved = function () {
    control.destroyed = true;
    clearTimeout(control.resizeTimer);
    control.closeEditor?.();
    control.resizeObserver?.disconnect();
    control.removeElementListeners?.();
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
  name: "matrix.resolution.halo",
  beforeConfigureGraph(graph) { migrateResolutionGraph(graph); },
  nodeCreated(node) {
    if (NODE_IDS.has(node.comfyClass || node.type)) install(node);
  },
  loadedGraphNode(node) {
    if (NODE_IDS.has(node.comfyClass || node.type)) install(node);
  },
});
