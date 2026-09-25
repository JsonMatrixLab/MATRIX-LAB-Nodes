import { mountImageGallery } from "./gallery.e159304effcb5c7f.mjs";
import { createHaloWidgetHost, haloWidgetLayoutHeight, measureHaloContentHeight, setHaloNodeSize } from "./halo.87ce22ea9cb20e75.mjs";

const { app } = globalThis.comfyAPI?.app || {};
const { api } = globalThis.comfyAPI?.api || {};

const NODE_TYPES = new Set(["MATRIX_ImageBatchLoader", "MATRIXLAB_ImageBatchLoader"]);
const COLLECTION_WIDGET = "collection";
const PRESENTATION_WIDGET = "matrixlab_image_collection_ui";
const MIN_WIDTH = 420;
const DEFAULT_WIDTH = 430;
const CONTROL = Symbol.for("matrixlab.image-collection.control");

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
  };
}

function hideWidget(snapshot) {
  const { widget } = snapshot;
  widget.options ||= {};
  widget.options.hidden = true;
  widget.draw = () => {};
  widget.computeSize = () => [0, -4];
}

function restoreWidget(snapshot) {
  const { widget } = snapshot;
  widget.draw = snapshot.draw;
  widget.computeSize = snapshot.computeSize;
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
    if (!beforeWidgets.has(widget) && (widget === presentation || widget?.name === PRESENTATION_WIDGET)) {
      node.widgets.splice(index, 1);
    }
  }
}

function install(node) {
  if (node?.[CONTROL]) {
    const collection = widgetByName(node, COLLECTION_WIDGET);
    node[CONTROL].syncFromWidget?.(collection?.value);
    return node[CONTROL];
  }
  if (!NODE_TYPES.has(node?.comfyClass || node?.type) || typeof document === "undefined") return null;
  if (typeof node.addDOMWidget !== "function") return null;
  const collection = widgetByName(node, COLLECTION_WIDGET);
  if (!collection) return null;

  const beforeWidgets = new Set(node.widgets || []);
  const snapshot = snapshotWidget(collection);
  const previousResize = node.onResize;
  const previousRemoved = node.onRemoved;
  const previousConfigure = node.onConfigure;
  const previousConnectionsChange = node.onConnectionsChange;
  const root = document.createElement("div");
  root.style.width = "100%";
  root.style.minWidth = `${MIN_WIDTH}px`;
  root.style.boxSizing = "border-box";
  const host = createHaloWidgetHost(root, document);
  if (!host) return null;
  let presentation = null;
  let gallery = null;
  let destroyed = false;
  let widthRepairTimer = null;
  const measuredHeight = () => {
    return haloWidgetLayoutHeight(measureHaloContentHeight(root, 250), presentation);
  };

  const ensureMinimumWidth = () => {
    if (destroyed) return;
    const currentWidth = Number(node.size?.[0]) || 0;
    const margin = Number(presentation?.margin);
    const nativeNode = root.closest?.("[data-node-id]");
    const nativeSlot = root.parentElement;
    const horizontalInsets = nativeNode?.offsetWidth > 0 && nativeSlot?.offsetWidth > 0
      ? Math.max(0, nativeNode.offsetWidth - nativeSlot.offsetWidth)
      : 2 * (Number.isFinite(margin) && margin >= 0 ? margin : 10);
    const width = Math.max(MIN_WIDTH + horizontalInsets, currentWidth || DEFAULT_WIDTH + horizontalInsets);
    if (width > currentWidth) setHaloNodeSize(node, [width, Number(node.size?.[1]) || 0]);
  };

  const destroy = () => {
    if (destroyed) return;
    destroyed = true;
    clearTimeout(widthRepairTimer);
    gallery?.destroy?.();
    restoreWidget(snapshot);
    removePresentation(node, beforeWidgets, presentation);
    root.remove?.();
    host.remove?.();
    if (node.onResize === wrappedResize) node.onResize = previousResize;
    if (node.onRemoved === wrappedRemoved) node.onRemoved = previousRemoved;
    if (node.onConfigure === wrappedConfigure) node.onConfigure = previousConfigure;
    if (node.onConnectionsChange === wrappedConnectionsChange) node.onConnectionsChange = previousConnectionsChange;
    if (node[CONTROL] === control) delete node[CONTROL];
  };
  const sync = (value = collection.value) => gallery?.syncFromWidget?.(value);
  const control = { host, root, widget: collection, get gallery() { return gallery; }, syncFromWidget: sync, destroy };
  const scheduleMinimumWidth = () => {
    clearTimeout(widthRepairTimer);
    widthRepairTimer = setTimeout(() => { widthRepairTimer = null; ensureMinimumWidth(); }, 0);
  };
  const wrappedResize = function (...args) {
    const result = previousResize?.apply(this, args);
    scheduleMinimumWidth();
    gallery?.render?.();
    return result;
  };
  const wrappedRemoved = function (...args) {
    destroy();
    return previousRemoved?.apply(this, args);
  };
  const wrappedConfigure = function (...args) {
    const result = previousConfigure?.apply(this, args);
    sync();
    return result;
  };
  const wrappedConnectionsChange = function (...args) {
    const result = previousConnectionsChange?.apply(this, args);
    sync();
    return result;
  };

  try {
    ensureMinimumWidth();
    presentation = node.addDOMWidget(PRESENTATION_WIDGET, "matrixlab-image-collection", host, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: measuredHeight,
      getHeight: measuredHeight,
    });
    if (!presentation) throw new Error("ComfyUI did not create the image collection DOM widget");
    presentation.serialize = false;
    presentation.options ||= {};
    presentation.options.serialize = false;
    gallery = mountImageGallery(root, node, collection, {
      api,
      app,
      document,
    });
    if (!gallery) throw new Error("Image collection gallery mount failed");
    snapshot.ownedCallback = function (...args) {
      try {
        return snapshot.callback?.apply(this, args);
      } finally {
        control.syncFromWidget(collection.value);
      }
    };
    collection.callback = snapshot.ownedCallback;
    hideWidget(snapshot);
    node[CONTROL] = control;
    node.onResize = wrappedResize;
    node.onRemoved = wrappedRemoved;
    node.onConfigure = wrappedConfigure;
    node.onConnectionsChange = wrappedConnectionsChange;
    gallery.syncFromWidget(collection.value);
    scheduleMinimumWidth();
    return control;
  } catch (error) {
    gallery?.destroy?.();
    restoreWidget(snapshot);
    removePresentation(node, beforeWidgets, presentation);
    root.remove?.();
    host.remove?.();
    node.onResize = previousResize;
    node.onRemoved = previousRemoved;
    app?.toast?.error?.(error?.message || String(error));
    return null;
  }
}

app?.registerExtension?.({
  name: "matrix.image-collection.gallery",
  nodeCreated: install,
  loadedGraphNode: install,
});

export { install as mountImageCollection };
