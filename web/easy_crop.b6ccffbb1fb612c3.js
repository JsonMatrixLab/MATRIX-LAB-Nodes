import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { createHaloWidgetHost, haloMinimumNodeHeight, haloWidgetLayoutHeight, measureHaloContentHeight, measureHaloHorizontalChrome, mountHaloSurface, setHaloNodeSize } from "./halo.235d06670e2dc4df.mjs";

const NODE_IDS = new Set(["MATRIXLAB_EasyCrop"]);
export const CONTROL = Symbol.for("matrixlab.easy-crop.control");
export const ASPECTS = Object.freeze(["Free", "1:1", "16:9", "9:16", "Custom"]);
export const DEFAULT_STATE = Object.freeze({
  image: "",
  aspect_ratio: "Free",
  custom_ratio_width: 1,
  custom_ratio_height: 1,
  crop_x: 0,
  crop_y: 0,
  crop_width: 1,
  crop_height: 1,
});

const MIN_SURFACE_WIDTH = 420;
const DECK_HEIGHTS = Object.freeze({
  narrow: Object.freeze({normal: 637, custom: 683}),
  wide: Object.freeze({normal: 638, custom: 684}),
});
const MAX_RATIO_PART = 1000;
const EPSILON = 1e-9;
const CORE_PREVIEW_WIDGET = "$$canvas-image-preview";

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function roundState(value) {
  return Number(clamp(value, 0, 1).toFixed(6));
}

function validRatioPart(value) {
  return Number.isInteger(value) && value >= 1 && value <= MAX_RATIO_PART;
}

function validUnit(value) {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

export function minimumNodeHeight(width, custom = false) {
  const layout = Number(width) >= 560 ? DECK_HEIGHTS.wide : DECK_HEIGHTS.narrow;
  return custom ? layout.custom : layout.normal;
}

export function ratioForState(state) {
  if (state.aspect_ratio === "Free") return null;
  if (state.aspect_ratio === "Custom") {
    if (!validRatioPart(state.custom_ratio_width) || !validRatioPart(state.custom_ratio_height)) return null;
    return state.custom_ratio_width / state.custom_ratio_height;
  }
  const [width, height] = String(state.aspect_ratio).split(":").map(Number);
  return width > 0 && height > 0 ? width / height : null;
}

export function largestCenteredCrop(imageWidth, imageHeight, ratio) {
  if (!(imageWidth > 0) || !(imageHeight > 0) || !(ratio > 0)) {
    return { crop_x: 0, crop_y: 0, crop_width: 1, crop_height: 1 };
  }
  const imageRatio = imageWidth / imageHeight;
  if (imageRatio > ratio) {
    const width = ratio / imageRatio;
    return { crop_x: roundState((1 - width) / 2), crop_y: 0, crop_width: roundState(width), crop_height: 1 };
  }
  const height = imageRatio / ratio;
  return { crop_x: 0, crop_y: roundState((1 - height) / 2), crop_width: 1, crop_height: roundState(height) };
}

function sanitizeRect(rect, minimumWidth = EPSILON, minimumHeight = EPSILON) {
  const width = clamp(Number(rect.crop_width) || 0, minimumWidth, 1);
  const height = clamp(Number(rect.crop_height) || 0, minimumHeight, 1);
  return {
    crop_x: roundState(clamp(Number(rect.crop_x) || 0, 0, 1 - width)),
    crop_y: roundState(clamp(Number(rect.crop_y) || 0, 0, 1 - height)),
    crop_width: roundState(width),
    crop_height: roundState(height),
  };
}

export function moveCrop(rect, deltaX, deltaY) {
  return sanitizeRect({
    ...rect,
    crop_x: rect.crop_x + deltaX,
    crop_y: rect.crop_y + deltaY,
  });
}

export function resizeCrop(rect, handle, deltaX, deltaY, ratio, imageWidth, imageHeight) {
  const minWidth = 1 / Math.max(1, imageWidth || 1);
  const minHeight = 1 / Math.max(1, imageHeight || 1);
  let left = rect.crop_x;
  let top = rect.crop_y;
  let right = left + rect.crop_width;
  let bottom = top + rect.crop_height;
  if (handle.includes("w")) left = clamp(left + deltaX, 0, right - minWidth);
  if (handle.includes("e")) right = clamp(right + deltaX, left + minWidth, 1);
  if (handle.includes("n")) top = clamp(top + deltaY, 0, bottom - minHeight);
  if (handle.includes("s")) bottom = clamp(bottom + deltaY, top + minHeight, 1);
  let next = sanitizeRect({crop_x: left, crop_y: top, crop_width: right - left, crop_height: bottom - top}, minWidth, minHeight);
  if (!(ratio > 0) || !(imageWidth > 0) || !(imageHeight > 0)) return next;

  const normalizedRatio = ratio * imageHeight / imageWidth;
  const anchorX = handle.includes("w") ? right : handle.includes("e") ? left : (left + right) / 2;
  const anchorY = handle.includes("n") ? bottom : handle.includes("s") ? top : (top + bottom) / 2;
  let width = next.crop_width;
  let height = next.crop_height;
  if ((handle === "n" || handle === "s") || (!handle.includes("e") && !handle.includes("w"))) {
    width = height * normalizedRatio;
  } else {
    height = width / normalizedRatio;
  }
  const maxWidth = handle.includes("w") ? anchorX : handle.includes("e") ? 1 - anchorX : 2 * Math.min(anchorX, 1 - anchorX);
  const maxHeight = handle.includes("n") ? anchorY : handle.includes("s") ? 1 - anchorY : 2 * Math.min(anchorY, 1 - anchorY);
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  width = Math.max(minWidth, width * scale);
  height = Math.max(minHeight, height * scale);
  left = handle.includes("w") ? anchorX - width : handle.includes("e") ? anchorX : anchorX - width / 2;
  top = handle.includes("n") ? anchorY - height : handle.includes("s") ? anchorY : anchorY - height / 2;
  return sanitizeRect({crop_x: left, crop_y: top, crop_width: width, crop_height: height}, minWidth, minHeight);
}

function canonicalWidgets(node) {
  return (node.widgets || []).filter((widget) => Object.hasOwn(DEFAULT_STATE, widget.name));
}

function presentationWidgets(node) {
  return (node.widgets || []).filter((widget) =>
    Object.hasOwn(DEFAULT_STATE, widget.name) ||
    (widget.name === "upload" && widget.type === "button" && widget.value === "image")
  );
}

function widgetsByName(node) {
  return Object.fromEntries(canonicalWidgets(node).map((widget) => [widget.name, widget]));
}

function readState(node) {
  const widgets = widgetsByName(node);
  return Object.fromEntries(Object.entries(DEFAULT_STATE).map(([name, fallback]) => [name, widgets[name]?.value ?? fallback]));
}

function isWidgetLinked(node, widget) {
  return Boolean(widget) && (node.inputs || []).some((input) =>
    (input?.widget?.name === widget.name || input?.name === widget.name) &&
    input.link !== null && input.link !== undefined
  );
}

function writeState(node, control, next) {
  const widgets = widgetsByName(node);
  const changed = Object.entries(next)
    .map(([name, value]) => [widgets[name], value])
    .filter(([widget, value]) => widget && widget.value !== value);
  if (changed.some(([widget]) => isWidgetLinked(node, widget))) return false;
  for (const [widget, value] of changed) widget.value = value;
  for (const [widget, value] of changed) {
    try {
      widget.callback?.call(widget, value, app.canvas, node, undefined, undefined);
    } catch (error) {
      console.warn("MATRIXLAB Easy Crop widget callback failed", error);
    }
  }
  control.render?.();
  node.setDirtyCanvas?.(true, true);
  return true;
}

function claimNativeImagePreview(node, control) {
  control.outputPreview = {
    hadOwn: Object.hasOwn(node, "hideOutputImages"),
    value: node.hideOutputImages,
  };
  node.hideOutputImages = true;
}

function restoreNativeImagePreview(node, control) {
  if (!control.outputPreview) return;
  if (control.outputPreview.hadOwn) node.hideOutputImages = control.outputPreview.value;
  else delete node.hideOutputImages;
  control.outputPreview = null;
}

function hidePresentationWidgets(node, control) {
  for (const widget of presentationWidgets(node)) {
    const hadOptions = Boolean(widget.options);
    widget.options ||= {};
    const callback = widget.callback;
    const watchedCallback = function () {
      try {
        return callback?.apply(this, arguments);
      } finally {
        control.render?.();
      }
    };
    control.widgetPresentation.push({
      widget, hadOptions, hidden: widget.options.hidden, callback, watchedCallback,
      draw: widget.draw, computeSize: widget.computeSize,
    });
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
    widget.options.hidden = true;
    widget.callback = watchedCallback;
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

function prism(element, major = false) {
  Object.assign(element.style, {
    boxSizing: "border-box",
    border: `1px solid ${major ? "#253E2E" : "#31543C"}`,
    borderRadius: `${major ? 10 : 9}px`,
    background: major ? "#07130960" : "linear-gradient(125deg, #172B1EDF 0%, #0B1710ED 100%)",
    color: "#EDF8F0",
  });
  return element;
}

function makeButton(label, action, control) {
  const button = prism(document.createElement("button"));
  button.type = "button";
  button.textContent = label;
  button.dataset.action = action;
  Object.assign(button.style, {
    minHeight: "40px", padding: "0 12px", cursor: "pointer", borderRadius: "10px",
    fontSize: "11px", lineHeight: "16.5px", fontWeight: "400", letterSpacing: "1px",
  });
  const listener = (event) => control.activate(action, event);
  button.addEventListener("click", listener);
  control.cleanups.push(() => button.removeEventListener("click", listener));
  return button;
}

function makeSection(label) {
  const section = document.createElement("section");
  section.setAttribute("aria-label", label);
  Object.assign(section.style, {display: "grid", gridAutoRows: "max-content", alignContent: "start", gap: "8px"});
  const heading = document.createElement("div");
  heading.textContent = label;
  Object.assign(heading.style, {minHeight: "13.5px", lineHeight: "13.5px", color: "#A0B7A7", fontSize: "9px", fontWeight: "400", letterSpacing: "1px"});
  section.append(heading);
  return section;
}

function parseAnnotatedImage(value) {
  const match = String(value || "").match(/^(.*?)(?:\s+\[(input|output|temp)\])?$/);
  const path = (match?.[1] || "").replaceAll("\\", "/");
  const slash = path.lastIndexOf("/");
  return {
    filename: slash >= 0 ? path.slice(slash + 1) : path,
    subfolder: slash >= 0 ? path.slice(0, slash) : "",
    type: match?.[2] || "input",
  };
}

export function imageViewURL(value) {
  const image = parseAnnotatedImage(value);
  if (!image.filename) return "";
  const query = new URLSearchParams(image).toString();
  return api.apiURL(`/view?${query}`);
}

function createRoot(node, control) {
  const root = document.createElement("div");
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", "MATRIXLAB Easy Crop controls");
  Object.assign(root.style, {
    boxSizing: "border-box", width: "100%", minWidth: "0", padding: "18px 16px",
    display: "grid", gridAutoRows: "max-content", alignContent: "start", gap: "12px",
    color: "#EDF8F0", background: "#050A05",
  });
  control.root = root;

  const loadSection = makeSection("01 IMAGE");
  const loadRow = document.createElement("div");
  Object.assign(loadRow.style, {display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", gap: "8px"});
  const fileName = prism(document.createElement("div"));
  Object.assign(fileName.style, {height: "42px", minHeight: "42px", padding: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#748279", fontSize: "12px"});
  const loadButton = makeButton("LOAD IMAGE", "load", control);
  loadButton.dataset.haloEffect = "primary";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/png,image/jpeg,image/webp,image/bmp,image/tiff";
  fileInput.tabIndex = -1;
  fileInput.style.display = "none";
  loadRow.append(fileName, loadButton, fileInput);
  loadSection.append(loadRow);
  root.append(loadSection);

  const preview = prism(document.createElement("div"), true);
  preview.setAttribute("aria-label", "Crop preview");
  Object.assign(preview.style, {position: "relative", height: "300px", overflow: "hidden", touchAction: "none", background: "#09110C"});
  const empty = document.createElement("div");
  empty.textContent = "LOAD AN IMAGE TO BEGIN";
  Object.assign(empty.style, {position: "absolute", inset: "0", display: "grid", placeItems: "center", color: "#748279", fontSize: "11px"});
  const image = document.createElement("img");
  image.alt = "Selected source";
  image.draggable = false;
  Object.assign(image.style, {position: "absolute", objectFit: "contain", userSelect: "none", pointerEvents: "none"});
  const shade = document.createElement("div");
  Object.assign(shade.style, {position: "absolute", pointerEvents: "none", boxShadow: "0 0 0 9999px #00000094"});
  const crop = document.createElement("div");
  crop.tabIndex = 0;
  crop.setAttribute("role", "application");
  crop.setAttribute("aria-label", "Crop selection");
  crop.dataset.drag = "move";
  Object.assign(crop.style, {position: "absolute", boxSizing: "border-box", border: "1px solid #5CF2A5", cursor: "move", touchAction: "none", outline: "none"});
  const handles = {};
  const handleCursors = {nw: "nwse-resize", n: "ns-resize", ne: "nesw-resize", e: "ew-resize", se: "nwse-resize", s: "ns-resize", sw: "nesw-resize", w: "ew-resize"};
  const markerPositions = {nw: ["0", "0"], n: ["16px", "0"], ne: ["32px", "0"], e: ["32px", "16px"], se: ["32px", "32px"], s: ["16px", "32px"], sw: ["0", "32px"], w: ["0", "16px"]};
  for (const handle of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
    const element = document.createElement("div");
    element.dataset.handle = handle;
    element.setAttribute("role", "button");
    element.setAttribute("aria-label", `Resize crop ${handle}`);
    Object.assign(element.style, {position: "absolute", width: "40px", height: "40px", cursor: handleCursors[handle], touchAction: "none"});
    const marker = document.createElement("span");
    Object.assign(marker.style, {position: "absolute", left: markerPositions[handle][0], top: markerPositions[handle][1], width: "8px", height: "8px", boxSizing: "border-box", border: "1px solid #5CF2A5", background: "#070C09", pointerEvents: "none"});
    element.append(marker);
    crop.append(element);
    handles[handle] = element;
  }
  preview.append(empty, image, shade, crop);
  root.append(preview);
  control.preview = preview;
  control.crop = crop;
  control.image = image;

  const ratioSection = makeSection("02 ASPECT RATIO");
  const ratioGrid = document.createElement("div");
  Object.assign(ratioGrid.style, {display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: "7px"});
  const ratioButtons = ASPECTS.map((aspect) => makeButton(aspect.toUpperCase(), `ratio:${aspect}`, control));
  for (const button of ratioButtons) { button.style.height = "52px"; button.dataset.haloEffect = "secondary"; }
  ratioGrid.append(...ratioButtons);
  ratioSection.append(ratioGrid);
  const customRow = document.createElement("div");
  Object.assign(customRow.style, {display: "none", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", gap: "8px"});
  const ratioInputs = {};
  for (const name of ["custom_ratio_width", "custom_ratio_height"]) {
    const input = prism(document.createElement("input"));
    input.type = "number";
    input.name = name;
    input.min = "1";
    input.max = String(MAX_RATIO_PART);
    input.step = "1";
    input.setAttribute("aria-label", name.replaceAll("_", " "));
    Object.assign(input.style, {minHeight: "38px", minWidth: "0", padding: "8px 10px", borderRadius: "9px", fontSize: "13px", lineHeight: "19.5px", fontWeight: "400"});
    const change = () => {
      const value = Number(input.value);
      if (!validRatioPart(value) || !control.applyAspect("Custom", {[name]: value})) {
        input.value = String(readState(node)[name]);
      }
    };
    input.addEventListener("change", change);
    control.cleanups.push(() => input.removeEventListener("change", change));
    ratioInputs[name] = input;
  }
  const separator = document.createElement("span");
  separator.textContent = ":";
  customRow.append(ratioInputs.custom_ratio_width, separator, ratioInputs.custom_ratio_height);
  ratioSection.append(customRow);
  root.append(ratioSection);

  const actions = document.createElement("div");
  Object.assign(actions.style, {display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px"});
  const centerButton = makeButton("CENTER", "center", control);
  const resetButton = makeButton("RESET", "reset", control);
  centerButton.dataset.haloEffect = resetButton.dataset.haloEffect = "secondary";
  actions.append(centerButton, resetButton);
  root.append(actions);

  const status = document.createElement("div");
  status.setAttribute("role", "status");
  Object.assign(status.style, {height: "16px", minHeight: "16px", lineHeight: "16px", color: "#748279", fontSize: "10px"});
  root.append(status);

  const startPointer = (event) => {
    if ((event.button ?? 0) !== 0 || node.flags?.collapsed || !control.imageWidth) return;
    const path = event.composedPath?.() || [];
    let target = path.find((element) => element?.dataset?.handle) || event.target;
    while (target && target !== crop && !target.dataset?.handle) target = target.parentElement;
    const handle = target?.dataset?.handle || "move";
    const widgets = widgetsByName(node);
    if (["crop_x", "crop_y", "crop_width", "crop_height"].some((name) => isWidgetLinked(node, widgets[name]))) return;
    event.preventDefault();
    event.stopPropagation();
    crop.focus();
    control.pointer = {
      id: event.pointerId,
      handle,
      startX: event.clientX,
      startY: event.clientY,
      rect: readState(node),
    };
    crop.setPointerCapture?.(event.pointerId);
  };
  const movePointer = (event) => {
    if (!control.pointer || event.pointerId !== control.pointer.id || !control.imageBox?.width || !control.imageBox?.height) return;
    event.preventDefault();
    event.stopPropagation();
    const screenBox = image.getBoundingClientRect?.();
    const screenWidth = Number(screenBox?.width) || control.imageBox.width;
    const screenHeight = Number(screenBox?.height) || control.imageBox.height;
    const dx = (event.clientX - control.pointer.startX) / screenWidth;
    const dy = (event.clientY - control.pointer.startY) / screenHeight;
    const state = readState(node);
    const ratio = ratioForState(state);
    const next = control.pointer.handle === "move"
      ? moveCrop(control.pointer.rect, dx, dy)
      : resizeCrop(control.pointer.rect, control.pointer.handle, dx, dy, ratio, control.imageWidth, control.imageHeight);
    writeState(node, control, next);
  };
  const endPointer = (event) => {
    if (!control.pointer || event.pointerId !== control.pointer.id) return;
    control.pointer = null;
    crop.releasePointerCapture?.(event.pointerId);
  };
  crop.addEventListener("pointerdown", startPointer);
  crop.addEventListener("pointermove", movePointer);
  crop.addEventListener("pointerup", endPointer);
  crop.addEventListener("pointercancel", endPointer);
  control.cleanups.push(
    () => crop.removeEventListener("pointerdown", startPointer),
    () => crop.removeEventListener("pointermove", movePointer),
    () => crop.removeEventListener("pointerup", endPointer),
    () => crop.removeEventListener("pointercancel", endPointer),
  );

  const keyDown = (event) => {
    const deltas = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
    if (!deltas[event.key] || node.flags?.collapsed || !control.imageWidth) return;
    const widgets = widgetsByName(node);
    if (["crop_x", "crop_y"].some((name) => isWidgetLinked(node, widgets[name]))) return;
    event.preventDefault();
    event.stopPropagation();
    const multiplier = event.shiftKey ? 10 : 1;
    const [x, y] = deltas[event.key];
    writeState(node, control, moveCrop(readState(node), x * multiplier / control.imageWidth, y * multiplier / control.imageHeight));
  };
  crop.addEventListener("keydown", keyDown);
  control.cleanups.push(() => crop.removeEventListener("keydown", keyDown));

  const loadImage = () => fileInput.click();
  control.loadImage = loadImage;
  const upload = async () => {
    const selected = fileInput.files?.[0];
    if (!selected || control.destroyed) return;
    const epoch = ++control.uploadEpoch;
    control.uploadController?.abort?.();
    control.uploadController = typeof AbortController === "function" ? new AbortController() : null;
    status.textContent = "UPLOADING…";
    const form = new FormData();
    form.append("image", selected);
    form.append("type", "input");
    form.append("overwrite", "false");
    try {
      const response = await api.fetchApi("/upload/image", {method: "POST", body: form, signal: control.uploadController?.signal});
      if (control.destroyed || epoch !== control.uploadEpoch) return;
      if (!response.ok) throw new Error(`upload failed (${response.status})`);
      const stored = await response.json();
      if (control.destroyed || epoch !== control.uploadEpoch) return;
      const path = stored.subfolder ? `${stored.subfolder}/${stored.name}` : stored.name;
      const value = stored.type && stored.type !== "input" ? `${path} [${stored.type}]` : path;
      control.resetOnNextImageLoad = true;
      if (!writeState(node, control, {image: value, crop_x: 0, crop_y: 0, crop_width: 1, crop_height: 1})) {
        control.resetOnNextImageLoad = false;
        throw new Error("image widget is linked");
      }
      status.textContent = "";
    } catch (error) {
      if (!control.destroyed && epoch === control.uploadEpoch) status.textContent = `UPLOAD FAILED: ${error.message}`;
    } finally {
      if (epoch === control.uploadEpoch) {
        control.uploadController = null;
        fileInput.value = "";
      }
    }
  };
  fileInput.addEventListener("change", upload);
  control.cleanups.push(() => fileInput.removeEventListener("change", upload));

  const imageLoaded = () => {
    control.imageWidth = image.naturalWidth;
    control.imageHeight = image.naturalHeight;
    control.loadedImageValue = readState(node).image;
    status.textContent = `${control.imageWidth} × ${control.imageHeight}`;
    if (control.resetOnNextImageLoad) {
      control.resetOnNextImageLoad = false;
      const state = readState(node);
      const ratio = ratioForState(state);
      writeState(node, control, state.aspect_ratio === "Free"
        ? {crop_x: 0, crop_y: 0, crop_width: 1, crop_height: 1}
        : largestCenteredCrop(control.imageWidth, control.imageHeight, ratio));
    }
    control.render();
  };
  const imageFailed = () => {
    control.imageWidth = 0;
    control.imageHeight = 0;
    status.textContent = "IMAGE PREVIEW UNAVAILABLE";
    control.render();
  };
  image.addEventListener("load", imageLoaded);
  image.addEventListener("error", imageFailed);
  control.cleanups.push(() => image.removeEventListener("load", imageLoaded), () => image.removeEventListener("error", imageFailed));

  control.applyAspect = (aspect, patch = {}) => {
    const widgets = widgetsByName(node);
    const dependencies = ["aspect_ratio", "crop_x", "crop_y", "crop_width", "crop_height"];
    if (aspect === "Custom") dependencies.push("custom_ratio_width", "custom_ratio_height");
    if (dependencies.some((name) => isWidgetLinked(node, widgets[name]))) return false;
    const state = {...readState(node), ...patch, aspect_ratio: aspect};
    const ratio = ratioForState(state);
    const cropState = aspect === "Free" ? {crop_x: 0, crop_y: 0, crop_width: 1, crop_height: 1}
      : largestCenteredCrop(control.imageWidth, control.imageHeight, ratio);
    return writeState(node, control, {aspect_ratio: aspect, ...patch, ...cropState});
  };
  control.activate = (action) => {
    if (control.destroyed || node.flags?.collapsed) return;
    if (action === "load") return loadImage();
    if (action.startsWith("ratio:")) return control.applyAspect(action.slice(6));
    const state = readState(node);
    if (action === "center") {
      return writeState(node, control, {
        crop_x: roundState((1 - state.crop_width) / 2),
        crop_y: roundState((1 - state.crop_height) / 2),
      });
    }
    if (action === "reset") return control.applyAspect(state.aspect_ratio);
  };

  control.render = () => {
    if (control.destroyed) return;
    const state = readState(node);
    const widgets = widgetsByName(node);
    const width = Number(root.clientWidth) || Math.max(0, (Number(node.size?.[0]) || 0) - 20);
    root.dataset.layout = width >= 560 ? "wide" : "narrow";
    ratioGrid.style.gridTemplateColumns = width >= 560 ? "repeat(5,minmax(0,1fr))" : "repeat(3,minmax(0,1fr))";
    preview.style.height = width >= 560 ? "360px" : "300px";
    fileName.textContent = state.image || "NO IMAGE SELECTED";
    fileName.title = state.image || "";
    customRow.style.display = state.aspect_ratio === "Custom" ? "grid" : "none";
    const contractHeight = minimumNodeHeight(width, state.aspect_ratio === "Custom");
    const measuredContentHeight = measureHaloContentHeight(root);
    const minimumHeight = Math.max(
      contractHeight,
      measuredContentHeight,
    );
    if (control.minimumHeight !== minimumHeight) {
      control.minimumHeight = minimumHeight;
      control.scheduleMinimumSize?.();
    }
    for (const [name, input] of Object.entries(ratioInputs)) {
      input.value = String(state[name]);
      input.disabled = isWidgetLinked(node, widgets[name]);
    }
    const cropLinked = ["crop_x", "crop_y", "crop_width", "crop_height"]
      .some((name) => isWidgetLinked(node, widgets[name]));
    const aspectLinked = isWidgetLinked(node, widgets.aspect_ratio);
    const customRatioLinked = ["custom_ratio_width", "custom_ratio_height"]
      .some((name) => isWidgetLinked(node, widgets[name]));
    for (const [index, button] of ratioButtons.entries()) {
      const active = ASPECTS[index] === state.aspect_ratio;
      button.setAttribute("aria-pressed", String(active));
      button.style.borderColor = active ? "#56FF82" : "#355D42";
      button.style.background = active
        ? "linear-gradient(180deg, #17442A 0%, #102A1B 100%)"
        : "linear-gradient(180deg, #1B2E22 0%, #0C1C12 100%)";
      button.style.color = active ? "#9EFFB9" : "#B7CBBD";
      button.disabled = !control.imageWidth || aspectLinked || cropLinked
        || (ASPECTS[index] === "Custom" && customRatioLinked);
    }
    centerButton.disabled = cropLinked;
    resetButton.disabled = cropLinked || aspectLinked
      || (state.aspect_ratio === "Custom" && customRatioLinked);
    loadButton.disabled = cropLinked || isWidgetLinked(node, widgets.image);
    const source = imageViewURL(state.image);
    if (source && control.requestedSource !== source) {
      control.requestedSource = source;
      control.imageWidth = 0;
      control.imageHeight = 0;
      image.src = source;
    } else if (!source) {
      control.requestedSource = "";
      image.removeAttribute?.("src");
      control.imageWidth = 0;
      control.imageHeight = 0;
    }
    const visible = Boolean(source && control.imageWidth && control.imageHeight);
    empty.style.display = visible ? "none" : "grid";
    image.style.display = visible ? "block" : "none";
    shade.style.display = visible ? "block" : "none";
    crop.style.display = visible ? "block" : "none";
    if (!visible) return;
    const previewWidth = Number(preview.clientWidth) || Math.max(1, width - 32);
    const previewHeight = Number(preview.clientHeight) || (width >= 560 ? 360 : 300);
    const scale = Math.min(previewWidth / control.imageWidth, previewHeight / control.imageHeight);
    const shownWidth = control.imageWidth * scale;
    const shownHeight = control.imageHeight * scale;
    const left = (previewWidth - shownWidth) / 2;
    const top = (previewHeight - shownHeight) / 2;
    control.imageBox = {left, top, width: shownWidth, height: shownHeight};
    Object.assign(image.style, {left: `${left}px`, top: `${top}px`, width: `${shownWidth}px`, height: `${shownHeight}px`});
    const rect = sanitizeRect(state, 1 / control.imageWidth, 1 / control.imageHeight);
    const cropLeft = left + rect.crop_x * shownWidth;
    const cropTop = top + rect.crop_y * shownHeight;
    const cropWidth = rect.crop_width * shownWidth;
    const cropHeight = rect.crop_height * shownHeight;
    for (const element of [shade, crop]) Object.assign(element.style, {left: `${cropLeft}px`, top: `${cropTop}px`, width: `${cropWidth}px`, height: `${cropHeight}px`});
    const positions = {
      nw: ["0", "0"], n: ["calc(50% - 20px)", "0"], ne: ["calc(100% - 40px)", "0"],
      e: ["calc(100% - 40px)", "calc(50% - 20px)"], se: ["calc(100% - 40px)", "calc(100% - 40px)"],
      s: ["calc(50% - 20px)", "calc(100% - 40px)"], sw: ["0", "calc(100% - 40px)"], w: ["0", "calc(50% - 20px)"],
    };
    for (const [name, element] of Object.entries(handles)) {
      element.style.left = positions[name][0];
      element.style.top = positions[name][1];
    }
  };
  for (const element of root.children) {
    element.style.position ||= "relative";
    element.style.zIndex = "2";
  }
  return root;
}

function install(node) {
  if (node[CONTROL]) return node[CONTROL];
  if (typeof document === "undefined" || typeof node.addDOMWidget !== "function") return null;
  const control = {
    destroyed: false, host: null, root: null, cleanups: [], widgetPresentation: [], outputPreview: null,
    pointer: null, imageWidth: 0, imageHeight: 0, imageBox: null,
    uploadEpoch: 0, uploadController: null,
    resizeTimer: null, resizeObserver: null, previousResize: null, watchedResize: null,
    presentation: null, minimumHeight: 0, scheduleMinimumSize: null, enforcingSize: false, horizontalChrome: null,
    activate() {}, render() {}, applyAspect() {},
  };
  const widgetsBeforeMount = new Set(node.widgets || []);
  let root;
  try {
    root = createRoot(node, control);
    const host = createHaloWidgetHost(root, document);
    if (!host) throw new Error("MATRIXLAB Easy Crop HALO host unavailable");
    control.host = host;
    const presentation = node.addDOMWidget(CORE_PREVIEW_WIDGET, "matrixlab-easy-crop", host, {serialize: false, hideOnZoom: false});
    if (!presentation) throw new Error("ComfyUI did not create the DOM widget");
    presentation.serialize = false;
    presentation.options ||= {};
    presentation.options.serialize = false;
    presentation.computeSize = (width) => {
      const state = readState(node);
      const layoutWidth = Number(root.clientWidth) || Number(width) || Number(node.size?.[0]) || MIN_SURFACE_WIDTH;
      const fallback = minimumNodeHeight(layoutWidth, state.aspect_ratio === "Custom");
      return [0, haloWidgetLayoutHeight(measureHaloContentHeight(root, fallback), presentation, "fixed")];
    };
    control.presentation = presentation;
    control.halo = mountHaloSurface(root, node, {profile: "ui", app});
    if (!control.halo) throw new Error("MATRIXLAB Easy Crop HALO surface unavailable");
    claimNativeImagePreview(node, control);
    hidePresentationWidgets(node, control);
    node[CONTROL] = control;
    control.render();
  } catch (error) {
    control.cleanups.splice(0).forEach((cleanup) => cleanup());
    control.halo?.destroy();
    restoreCanonicalWidgets(control);
    restoreNativeImagePreview(node, control);
    for (let index = (node.widgets || []).length - 1; index >= 0; index -= 1) {
      if (!widgetsBeforeMount.has(node.widgets[index])) node.widgets.splice(index, 1);
    }
    control.host?.remove();
    console.warn("MATRIXLAB Easy Crop UI unavailable; native widgets remain active", error);
    return null;
  }

  const ensureMinimumSize = () => {
    if (control.destroyed || control.enforcingSize) return;
    const currentWidth = Number(node.size?.[0]) || 0;
    const currentHeight = Number(node.size?.[1]) || 0;
    if (control.horizontalChrome == null) {
      control.horizontalChrome = measureHaloHorizontalChrome(root, currentWidth);
    }
    const width = Math.max(currentWidth, MIN_SURFACE_WIDTH + (control.horizontalChrome ?? 0));
    const fallbackHeight = minimumNodeHeight(
      Number(root.clientWidth) || width,
      readState(node).aspect_ratio === "Custom",
    );
    const contentHeight = measureHaloContentHeight(root, control.minimumHeight || fallbackHeight);
    const height = haloMinimumNodeHeight(node, contentHeight);
    if (width === currentWidth && height === currentHeight) return;
    const size = [width, height];
    control.enforcingSize = true;
    try {
      setHaloNodeSize(node, size);
    } finally {
      control.enforcingSize = false;
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
    if (!control.enforcingSize) scheduleMinimumSize();
    control.render();
    return result;
  };
  node.onResize = control.watchedResize;
  if (typeof ResizeObserver === "function") {
    control.resizeObserver = new ResizeObserver(() => {
      control.scheduleMinimumSize?.();
      control.render();
    });
    control.resizeObserver.observe(root);
  }
  const previousRemoved = node.onRemoved;
  node.onRemoved = function () {
    control.destroyed = true;
    control.uploadEpoch += 1;
    control.uploadController?.abort?.();
    control.uploadController = null;
    clearTimeout(control.resizeTimer);
    control.resizeObserver?.disconnect();
    control.cleanups.splice(0).forEach((cleanup) => cleanup());
    control.halo?.destroy();
    restoreCanonicalWidgets(control);
    restoreNativeImagePreview(this, control);
    root.remove();
    control.host?.remove();
    if (this.onResize === control.watchedResize) this.onResize = control.previousResize;
    if (this[CONTROL] === control) delete this[CONTROL];
    return previousRemoved?.apply(this, arguments);
  };
  ensureMinimumSize();
  node.setDirtyCanvas?.(true, true);
  return control;
}

app.registerExtension({
  name: "matrixlab.easy-crop",
  nodeCreated(node) {
    if (NODE_IDS.has(node.comfyClass || node.type)) install(node);
  },
  loadedGraphNode(node) {
    if (NODE_IDS.has(node.comfyClass || node.type)) install(node);
  },
});
