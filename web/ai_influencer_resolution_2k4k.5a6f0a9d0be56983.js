import { app } from "../../scripts/app.js";
import { createHaloResolutionDeck, createHaloWidgetHost, haloMinimumNodeHeight, haloWidgetLayoutHeight, measureHaloContentHeight, measureHaloHorizontalChrome, setHaloNodeSize, calculateTierResolution } from "./halo_resolution.3078c6fb7c5009a2.mjs";
const ASPECT_RATIOS = ["1:1", "9:16", "3:4"];
const RESOLUTION_TIERS = ["2K", "4K"];
export function calculateResolution(state) {
  if (!ASPECT_RATIOS.includes(state.aspect_ratio)) throw new Error("Unsupported aspect ratio");
  return calculateTierResolution(state.aspect_ratio, state.resolution_tier);
}

const NODE_IDS = new Set(
  "MATRIXLAB_AIInfluencerResolution2K4K".split(",").filter(Boolean),
);
const DEFAULT_STATE = Object.freeze({ aspect_ratio: "3:4", resolution_tier: "2K" });
const MIN_SURFACE_WIDTH = 420;
const CONTENT_HEIGHT = 460;

export const BUTTONS = Object.freeze([
  ...ASPECT_RATIOS.map((value) => ({ group: "aspect_ratio", value, label: value })),
  ...RESOLUTION_TIERS.map((value) => ({
    group: "resolution_tier",
    value,
    label: value,
  })),
]);

export function applyButton(state, group, value) {
  if (!BUTTONS.some((button) => button.group === group && button.value === value)) {
    throw new Error(`Unsupported resolution control: ${group}=${value}`);
  }
  return { ...state, [group]: value };
}

export const CONTROL = Symbol.for("matrix.ai-influencer-resolution-2k4k.control");

function widgetsByName(node) {
  return Object.fromEntries((node.widgets || []).map((widget) => [widget.name, widget]));
}

function readState(node) {
  const widgets = widgetsByName(node);
  return {
    aspect_ratio: widgets.aspect_ratio?.value ?? DEFAULT_STATE.aspect_ratio,
    resolution_tier: widgets.resolution_tier?.value ?? DEFAULT_STATE.resolution_tier,
  };
}

function isWidgetLinked(node, name) {
  return (node.inputs || []).some((input) =>
    (input?.widget?.name === name || input?.name === name)
    && input.link !== null
    && input.link !== undefined
  );
}

function hideCanonicalWidgets(node, control) {
  const names = new Set(Object.keys(DEFAULT_STATE));
  for (const widget of node.widgets || []) {
    if (!names.has(widget.name)) continue;
    const hadOptions = Boolean(widget.options);
    widget.options ||= {};
    const entry = {
      widget,
      draw: widget.draw,
      computeSize: widget.computeSize,
      callback: widget.callback,
      hidden: widget.options.hidden,
      hadOptions,
    };
    const previousCallback = widget.callback;
    entry.watchedCallback = function () {
      try {
        return previousCallback?.apply(this, arguments);
      } finally {
        control.render?.();
      }
    };
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
    widget.options.hidden = true;
    widget.callback = entry.watchedCallback;
    control.widgetPresentation.push(entry);
  }
}

function restoreCanonicalWidgets(control) {
  for (const entry of control.widgetPresentation) {
    entry.widget.draw = entry.draw;
    entry.widget.computeSize = entry.computeSize;
    if (entry.widget.callback === entry.watchedCallback) entry.widget.callback = entry.callback;
    if (entry.hidden === undefined) delete entry.widget.options.hidden;
    else entry.widget.options.hidden = entry.hidden;
    if (!entry.hadOptions && Object.keys(entry.widget.options).length === 0) {
      delete entry.widget.options;
    }
  }
  control.widgetPresentation.length = 0;
}

function createHaloPanel(node, control) {
  return createHaloResolutionDeck({
    document,
    node,
    control,
    ariaLabel: "AI Influencer resolution 2K/4K controls",
    haloOptions: { app },
    groups: [
      {
        id: "aspect_ratio",
        label: "ASPECT",
        items: BUTTONS.filter((item) => item.group === "aspect_ratio").map((item) => ({
          id: `${item.group}:${item.value}`,
          label: item.label,
          ratio: item.value.split(":").map(Number),
          group: item.group,
          value: item.value,
        })),
      },
      {
        id: "resolution_tier",
        label: "SIZE",
        items: BUTTONS.filter((item) => item.group === "resolution_tier").map((item) => ({
          id: `${item.group}:${item.value}`,
          label: item.label,
          group: item.group,
          value: item.value,
        })),
      },
    ],
    activate(action, event) {
      const separator = action.indexOf(":");
      return control.activate(action.slice(0, separator), action.slice(separator + 1), event);
    },
    isDisabled(action) {
      const group = action.slice(0, action.indexOf(":"));
      return isWidgetLinked(node, group);
    },
    disabledReason(action) {
      return `${action.slice(0, action.indexOf(":"))} is controlled by a connected input.`;
    },
    view() {
      const state = readState(node);
      try {
        const dimensions = calculateResolution(state);
        return {
          tier: state.resolution_tier.toUpperCase(),
          profile: "",
          active: {
            aspect_ratio: `aspect_ratio:${state.aspect_ratio}`,
            resolution_tier: `resolution_tier:${state.resolution_tier}`,
          },
          dimensions,
          ratioLabel: state.aspect_ratio,
          method: "",
          error: control.errorMessage || "",
        };
      } catch (problem) {
        return {
          tier: "INVALID",
          profile: "",
          active: {},
          dimensions: [0, 0],
          ratioLabel: state.aspect_ratio,
          method: "",
          error: control.errorMessage || String(problem?.message || problem),
        };
      }
    },
  });
}

function install(node) {
  if (node[CONTROL]) return node[CONTROL];
  if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return null;
  const control = {
    destroyed: false,
    enforcingMinimumSize: false,
    horizontalChrome: null,
    resizeObserver: null,
    resizeTimer: null,
    previousResize: null,
    watchedResize: null,
    widgetPresentation: [],
    activate(group, value, event) {
      if (this.destroyed) return false;
      if (isWidgetLinked(node, group)) {
        this.errorMessage = `${group} is controlled by a connected input.`;
        this.render?.();
        return false;
      }
      try {
        const next = applyButton(readState(node), group, value);
        const widget = widgetsByName(node)[group];
        if (!widget) throw new Error(`Missing canonical widget: ${group}`);
        widget.value = next[group];
        widget.callback?.call(widget, next[group], app.canvas, node, node.pos, event);
        this.errorMessage = "";
        node.setDirtyCanvas?.(true, true);
        this.render();
        return true;
      } catch (problem) {
        this.errorMessage = String(problem?.message || problem);
        this.render?.();
        return false;
      }
    },
  };
  const existingWidgets = new Set(node.widgets || []);
  let element;
  let host;
  let domWidget;
  try {
    element = createHaloPanel(node, control);
    host = createHaloWidgetHost(element, document);
    if (!host) throw new Error("AI Influencer Resolution 2K/4K HALO host unavailable");
    control.host = host;
    domWidget = node.addDOMWidget("matrixlab_ai_influencer_resolution_2k4k_ui", "matrixlab-prism", host, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, control.minimumContentHeight || CONTENT_HEIGHT), domWidget),
      getHeight: () => haloWidgetLayoutHeight(measureHaloContentHeight(element, control.minimumContentHeight || CONTENT_HEIGHT), domWidget),
    });
    if (!domWidget) throw new Error("ComfyUI did not create the DOM widget");
    domWidget.serialize = false;
    domWidget.options ||= {};
    domWidget.options.serialize = false;
    if (!control.mountHalo?.()) throw new Error("AI Influencer Resolution 2K/4K HALO surface unavailable");
    hideCanonicalWidgets(node, control);
    node[CONTROL] = control;
  } catch (problem) {
    control.destroyed = true;
    control.halo?.destroy();
    restoreCanonicalWidgets(control);
    if (Array.isArray(node.widgets)) {
      for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
        const widget = node.widgets[index];
        if (!existingWidgets.has(widget)
          && (widget === domWidget || widget?.element === host || widget?.name === "matrixlab_ai_influencer_resolution_2k4k_ui")) {
          node.widgets.splice(index, 1);
        }
      }
    }
    element?.remove();
    host?.remove();
    console.warn("AI Influencer Resolution 2K/4K UI unavailable; native widgets remain active", problem);
    return null;
  }

  const ensureMinimumSize = () => {
    if (control.destroyed || control.enforcingMinimumSize) return;
    const currentWidth = Number(node.size?.[0]) || 0;
    const currentHeight = Number(node.size?.[1]) || 0;
    if (control.horizontalChrome == null) control.horizontalChrome = measureHaloHorizontalChrome(element, currentWidth);
    const width = Math.max(currentWidth, MIN_SURFACE_WIDTH + (control.horizontalChrome ?? 0));
    const contentHeight = measureHaloContentHeight(element, control.minimumContentHeight || CONTENT_HEIGHT);
    const height = haloMinimumNodeHeight(node, contentHeight);
    if (width === currentWidth && height === currentHeight) return;
    const size = [width, height];
    control.enforcingMinimumSize = true;
    try {
      setHaloNodeSize(node, size);
    } finally {
      control.enforcingMinimumSize = false;
    }
  };
  const scheduleMinimumSize = () => {
    clearTimeout(control.resizeTimer);
    control.resizeTimer = setTimeout(() => {
      control.resizeTimer = null;
      ensureMinimumSize();
      control.render();
    }, 0);
  };
  control.scheduleMinimumSize = scheduleMinimumSize;
  control.previousResize = node.onResize;
  control.watchedResize = function () {
    const result = control.previousResize?.apply(this, arguments);
    if (!control.enforcingMinimumSize) scheduleMinimumSize();
    control.render();
    return result;
  };
  node.onResize = control.watchedResize;
  if (typeof ResizeObserver === "function") {
    control.resizeObserver = new ResizeObserver(() => {
      control.scheduleMinimumSize?.();
      control.render();
    });
    control.resizeObserver.observe(element);
  }

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
  name: "matrix.ai-influencer-resolution-2k4k.halo",
  nodeCreated(node) {
    if (NODE_IDS.has(node.comfyClass || node.type)) install(node);
  },
  loadedGraphNode(node) {
    if (NODE_IDS.has(node.comfyClass || node.type)) install(node);
  },
});
