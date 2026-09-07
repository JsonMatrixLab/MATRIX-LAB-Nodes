import { haloMinimumNodeHeight, measureHaloContentHeight, mountHaloSurface, setHaloNodeSize } from "./halo.cdbfe5654df6eedc.mjs";

export const GALLERY_STATE_VERSION = 1;
export const MAX_GALLERY_IMAGES = 5;
export const EMPTY_GALLERY_STATE = '{"version":1,"items":[],"selected":null}';

const MIN_WIDTH = 420;
const WIDE_WIDTH = 560;
const MAX_GRID_HEIGHT = 320;
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"]);

function refuse(message) {
  throw new Error(`MATRIXLAB image collection: ${message}`);
}

function rejectDuplicateFields(text) {
  if (typeof text !== "string") refuse("state must be a JSON string");
  let index = 0;
  const whitespace = () => { while (/\s/.test(text[index] || "")) index += 1; };
  const scanString = () => {
    const start = index;
    if (text[index++] !== '"') refuse("state is not valid JSON");
    while (index < text.length) {
      const character = text[index++];
      if (character === '"') return JSON.parse(text.slice(start, index));
      if (character === "\\") {
        if (text[index] === "u") index += 5;
        else index += 1;
      }
    }
    refuse("state is not valid JSON");
  };
  const scanValue = () => {
    whitespace();
    if (text[index] === "{") return scanObject();
    if (text[index] === "[") return scanArray();
    if (text[index] === '"') { scanString(); return; }
    const match = text.slice(index).match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
    if (!match) refuse("state is not valid JSON");
    index += match[0].length;
  };
  const scanObject = () => {
    index += 1;
    const keys = new Set();
    whitespace();
    if (text[index] === "}") { index += 1; return; }
    while (index < text.length) {
      whitespace();
      const key = scanString();
      if (keys.has(key)) refuse(`duplicate JSON field: ${key}`);
      keys.add(key);
      whitespace();
      if (text[index++] !== ":") refuse("state is not valid JSON");
      scanValue();
      whitespace();
      if (text[index] === "}") { index += 1; return; }
      if (text[index++] !== ",") refuse("state is not valid JSON");
    }
    refuse("state is not valid JSON");
  };
  const scanArray = () => {
    index += 1;
    whitespace();
    if (text[index] === "]") { index += 1; return; }
    while (index < text.length) {
      scanValue();
      whitespace();
      if (text[index] === "]") { index += 1; return; }
      if (text[index++] !== ",") refuse("state is not valid JSON");
    }
    refuse("state is not valid JSON");
  };
  scanValue();
  whitespace();
  if (index !== text.length) refuse("state is not valid JSON");
}

function inputPath(identity) {
  if (typeof identity !== "string" || !identity.endsWith(" [input]")) {
    refuse("image identity must use the explicit [input] annotation");
  }
  const relative = identity.slice(0, -8);
  if (/[\uD800-\uDFFF]/.test(relative)) refuse("image identity contains invalid Unicode");
  if (!relative || relative.includes("\\") || relative.startsWith("/") || /^[A-Za-z]:/.test(relative)) {
    refuse("image identity is not input-relative");
  }
  const parts = relative.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    refuse("image identity is not input-relative");
  }
  return relative;
}

export function parseGalleryState(value) {
  let data;
  try {
    rejectDuplicateFields(value);
    data = JSON.parse(value);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("MATRIXLAB image collection:")) throw error;
    refuse("state is not valid JSON");
  }
  if (!data || Array.isArray(data) || typeof data !== "object") refuse("state must be an object");
  const keys = Object.keys(data).sort();
  if (keys.join(",") !== "items,selected,version") refuse("state must contain exactly version, items, and selected");
  if (data.version !== GALLERY_STATE_VERSION || !Number.isInteger(data.version)) refuse("unsupported state version");
  if (!Array.isArray(data.items)) refuse("items must be an array");
  const known = new Set();
  const items = data.items.map((item, index) => {
    if (!item || Array.isArray(item) || typeof item !== "object" || Object.keys(item).join(",") !== "image") {
      refuse(`item ${index + 1} must contain exactly image`);
    }
    inputPath(item.image);
    if (known.has(item.image)) refuse(`item ${index + 1} duplicates an existing image identity`);
    known.add(item.image);
    return { image: item.image };
  });
  const selected = data.selected;
  if (selected !== null && (!Number.isInteger(selected) || selected < 0 || selected >= items.length)) {
    refuse("selected must be null or identify an existing item");
  }
  return { version: GALLERY_STATE_VERSION, items, selected };
}

export function canonicalGalleryState(value) {
  const state = typeof value === "string" ? parseGalleryState(value) : parseGalleryState(JSON.stringify(value));
  return JSON.stringify({ version: GALLERY_STATE_VERSION, items: state.items, selected: state.selected });
}

function isLinked(node, widget) {
  return (node?.inputs || []).some((input) =>
    (input?.name === widget?.name || input?.widget?.name === widget?.name) && input.link != null
  );
}

function identityFromUpload(payload) {
  if (!payload || payload.type !== "input" || typeof payload.name !== "string" || !payload.name) {
    refuse("ComfyUI upload returned an invalid input identity");
  }
  const folder = String(payload.subfolder || "").replaceAll("\\", "/").replace(/^\/+|\/+$/g, "");
  const identity = `${folder ? `${folder}/` : ""}${payload.name} [input]`;
  inputPath(identity);
  return identity;
}

function responseErrorText(payload, response) {
  if (typeof payload?.error === "string" && payload.error) return payload.error;
  if (typeof payload?.error?.message === "string" && payload.error.message) return payload.error.message;
  if (typeof payload?.message === "string" && payload.message) return payload.message;
  const status = Number(response?.status);
  return Number.isFinite(status) && status > 0 ? `Upload failed (${status})` : "Upload failed";
}

function viewUrl(api, identity) {
  const relative = inputPath(identity);
  const slash = relative.lastIndexOf("/");
  const filename = slash < 0 ? relative : relative.slice(slash + 1);
  const subfolder = slash < 0 ? "" : relative.slice(0, slash);
  const query = new URLSearchParams({ filename, type: "input" });
  if (subfolder) query.set("subfolder", subfolder);
  const url = `/view?${query}`;
  return typeof api?.apiURL === "function" ? api.apiURL(url) : url;
}

function fileAccepted(file) {
  const extension = String(file?.name || "").split(".").pop().toLowerCase();
  return IMAGE_EXTENSIONS.has(extension);
}

function icon(doc, path) {
  const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.style.pointerEvents = "none";
  const shape = doc.createElementNS("http://www.w3.org/2000/svg", "path");
  shape.setAttribute("d", path);
  shape.setAttribute("fill", "none");
  shape.setAttribute("stroke", "currentColor");
  shape.setAttribute("stroke-width", "1.5");
  shape.setAttribute("stroke-linecap", "round");
  shape.setAttribute("stroke-linejoin", "round");
  svg.appendChild(shape);
  return svg;
}

function addStyle(doc, root) {
  const style = doc.createElement("style");
  style.textContent = `
.matrixlab-gallery{position:relative;z-index:2;display:grid;grid-auto-rows:max-content;align-content:start;margin:0 7px;padding:18px 16px;gap:0;color:#EDF8F0}
.matrixlab-gallery__heading{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#A0B7A7;font-size:9px;line-height:13.5px;letter-spacing:1px;text-transform:uppercase;margin-bottom:9px}
.matrixlab-gallery__count{color:#00FF41;font-size:10px;line-height:16px;letter-spacing:0;text-transform:none}
.matrixlab-gallery__drop{display:flex;min-height:136px;padding:18px;align-items:center;justify-content:center;flex-direction:column;gap:7px;border:1px dashed #3C7750;border-radius:10px;background:#0C1D12;color:#BADCC5;cursor:pointer;text-align:center;transition:background-color 150ms ease,border-color 150ms ease}
.matrixlab-gallery__drop[data-active="true"]{border-color:#00FF41;background:#123E20}.matrixlab-gallery__drop:focus-visible,.matrixlab-gallery button:focus-visible{outline:2px solid #FFCA6B;outline-offset:-3px}
.matrixlab-gallery__drop svg{width:24px;height:24px;stroke-width:1.5}.matrixlab-gallery__drop-main{font-size:13px;line-height:19.5px}.matrixlab-gallery__drop-hint{font-size:9px;line-height:13.5px;color:#92B39B}
.matrixlab-gallery__grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px;max-height:${MAX_GRID_HEIGHT}px;overflow:auto;scrollbar-width:thin;scrollbar-color:#3B6148 #0C1D12}
.matrixlab-gallery[data-wide="true"] .matrixlab-gallery__grid{grid-template-columns:repeat(4,minmax(0,1fr))}
.matrixlab-gallery__tile{min-width:0;padding:6px;border:1px solid #33573D;border-radius:9px;background:#0D1C12;color:#BDF3CD}.matrixlab-gallery__tile[data-selected="true"]{border-color:#56FF82}
.matrixlab-gallery__preview{display:block;width:100%;height:80px;object-fit:contain;border-radius:6px;background-color:#0C160F;background-image:linear-gradient(45deg,#18261C 25%,transparent 25%),linear-gradient(-45deg,#18261C 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#18261C 75%),linear-gradient(-45deg,transparent 75%,#18261C 75%);background-size:10px 10px;background-position:0 0,0 5px,5px -5px,-5px 0}
.matrixlab-gallery__name{margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px;line-height:13.5px}.matrixlab-gallery__thumbnail-error{margin-top:5px;color:#FF8B7D;font-size:9px;line-height:13.5px;overflow-wrap:anywhere}.matrixlab-gallery__actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;margin-top:6px}.matrixlab-gallery__actions button{display:flex;min-width:0;min-height:28px;align-items:center;justify-content:center;border:1px solid #3B6148;border-radius:6px;background:#172F20;color:#BDF3CD;cursor:pointer}.matrixlab-gallery__actions button:disabled{opacity:.38;cursor:default}
.matrixlab-gallery__selected{color:#9EFFB9;margin-left:4px}.matrixlab-gallery__status{min-height:30px;margin-top:10px;font-size:10px;line-height:16px;color:#97AA9C;overflow-wrap:anywhere}.matrixlab-gallery__status[data-error="true"]{padding:8px 10px;border:1px solid #FF6B5A;border-radius:8px;background:#26110F;color:#FF6B5A}.matrixlab-gallery__empty{margin:20px 0;color:#779681;font-size:10px;line-height:18px;text-align:center}.matrixlab-gallery__pending{opacity:.7}
`;
  root.appendChild(style);
  return style;
}

function callback(options, name, ...args) {
  try { options[name]?.(...args); }
  catch (error) { options.onError?.(error); }
}

export function mountImageGallery(root, node, canonicalWidget, options = {}) {
  if (!root?.appendChild || !canonicalWidget || typeof canonicalWidget.name !== "string") return null;
  const doc = options.document || root.ownerDocument || globalThis.document;
  const api = options.api;
  if (!doc?.createElement || typeof api?.fetchApi !== "function") return null;
  const beforeChildren = new Set(Array.from(root.childNodes || []));
  const beforeClassName = root.className;
  const hadHaloVersion = Object.prototype.hasOwnProperty.call(root.dataset || {}, "haloVersion");
  const beforeHaloVersion = root.dataset?.haloVersion;
  const previousResize = node?.onResize;
  const previousRemoved = node?.onRemoved;
  const objectUrls = new Set();
  let halo = null;
  let resizeObserver = null;
  let destroyed = false;
  let repairTimer = null;
  let draggedIndex = null;
  let pending = [];
  let uploadInProgress = false;
  let uploadEpoch = 0;
  let uploadController = null;
  let errorMessage = "";
  const thumbnailErrors = new Map();
  const thumbnailTokens = new Map();
  let state;
  try { state = parseGalleryState(canonicalWidget.value ?? EMPTY_GALLERY_STATE); }
  catch (error) { state = parseGalleryState(EMPTY_GALLERY_STATE); errorMessage = error.message; }

  const container = doc.createElement("div");
  container.className = "matrixlab-gallery";
  addStyle(doc, container);
  const heading = doc.createElement("div");
  heading.className = "matrixlab-gallery__heading";
  const headingText = doc.createElement("span");
  headingText.textContent = "01 / Image collection · 1–5 images";
  const count = doc.createElement("span");
  count.className = "matrixlab-gallery__count";
  heading.append(headingText, count);
  const input = doc.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = "image/png,image/jpeg,image/webp,image/bmp,image/tiff";
  input.hidden = true;
  input.setAttribute("aria-label", "Add images to collection");
  const drop = doc.createElement("button");
  drop.type = "button";
  drop.className = "matrixlab-gallery__drop";
  drop.dataset.haloEffect = "primary";
  drop.append(
    icon(doc, "M12 5v14M5 12h14"),
    Object.assign(doc.createElement("span"), { className: "matrixlab-gallery__drop-main", textContent: "Drop images or choose files" }),
    Object.assign(doc.createElement("span"), { className: "matrixlab-gallery__drop-hint", textContent: "1–5 images · static images · originals stay in ComfyUI input" }),
  );
  const grid = doc.createElement("div");
  grid.className = "matrixlab-gallery__grid";
  grid.setAttribute("aria-label", "Ordered image collection");
  grid.setAttribute("role", "listbox");
  const empty = doc.createElement("p");
  empty.className = "matrixlab-gallery__empty";
  empty.textContent = "No images selected. Adding files does not queue a prompt.";
  const status = doc.createElement("div");
  status.className = "matrixlab-gallery__status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  container.append(heading, input, drop, grid, empty, status);

  function scheduleSize() {
    clearTimeout(repairTimer);
    repairTimer = setTimeout(() => {
      repairTimer = null;
      if (destroyed || !node) return;
      const width = Math.max(MIN_WIDTH, Number(node.size?.[0]) || MIN_WIDTH);
      container.dataset.wide = String(width >= WIDE_WIDTH);
      const contentHeight = measureHaloContentHeight(root, 250);
      const suppliedChrome = options.getRendererChrome?.(node) ?? options.rendererChrome;
      const height = haloMinimumNodeHeight(node, contentHeight, suppliedChrome);
      if (width !== Number(node.size?.[0]) || height !== Number(node.size?.[1])) setHaloNodeSize(node, [width, height]);
      halo?.renderStatic?.();
    }, 0);
  }

  function commit(next, event, selectionChanged = false) {
    if (isLinked(node, canonicalWidget)) { errorMessage = "Collection state is linked and read-only."; render(); return false; }
    const canonical = canonicalGalleryState(next);
    canonicalWidget.value = canonical;
    state = parseGalleryState(canonical);
    try {
      canonicalWidget.callback?.call(canonicalWidget, canonical, options.app?.canvas || options.canvas || null, node, node?.pos, event);
    } catch (error) {
      callback(options, "onError", error);
    }
    callback(options, "onChange", state, event);
    if (selectionChanged) callback(options, "onSelectionChange", state.selected, state.selected == null ? null : state.items[state.selected], event);
    errorMessage = "";
    node?.setDirtyCanvas?.(true, true);
    render();
    return true;
  }

  function move(from, to, event) {
    if (!Number.isInteger(from) || !Number.isInteger(to) || from === to || from < 0 || to < 0 || from >= state.items.length || to >= state.items.length) return;
    const selectedIdentity = state.selected == null ? null : state.items[state.selected].image;
    const items = state.items.slice();
    const [item] = items.splice(from, 1);
    items.splice(to, 0, item);
    const selected = selectedIdentity == null ? null : items.findIndex((entry) => entry.image === selectedIdentity);
    commit({ version: 1, items, selected }, event);
  }

  function remove(index, event) {
    const items = state.items.slice();
    items.splice(index, 1);
    let selected = state.selected;
    if (selected === index) selected = items.length ? Math.min(index, items.length - 1) : null;
    else if (selected != null && selected > index) selected -= 1;
    commit({ version: 1, items, selected }, event, true);
  }

  function button(label, path, disabled, action) {
    const control = doc.createElement("button");
    control.type = "button";
    control.disabled = disabled;
    control.dataset.haloEffect = "secondary";
    control.setAttribute("aria-label", label);
    control.title = label;
    control.appendChild(icon(doc, path));
    control.addEventListener("click", action);
    return control;
  }

  function tileFor(item, index, source, isPending = false) {
    const tile = doc.createElement("article");
    tile.className = `matrixlab-gallery__tile${isPending ? " matrixlab-gallery__pending" : ""}`;
    tile.dataset.selected = String(!isPending && state.selected === index);
    tile.draggable = !isPending && !isLinked(node, canonicalWidget);
    const image = doc.createElement("img");
    image.className = "matrixlab-gallery__preview";
    image.src = source;
    const identity = isPending ? item.name : item.image;
    const filename = (isPending ? identity : inputPath(identity)).split("/").pop();
    image.alt = `Thumbnail for ${filename}`;
    const token = {};
    thumbnailTokens.set(identity, token);
    image.addEventListener?.("load", () => {
      if (destroyed || thumbnailTokens.get(identity) !== token) return;
      if (thumbnailErrors.delete(identity)) render();
    });
    image.addEventListener?.("error", () => {
      if (destroyed || thumbnailTokens.get(identity) !== token) return;
      if (thumbnailErrors.has(identity)) return;
      thumbnailErrors.set(identity, `${filename}: thumbnail unavailable; the file may be missing or corrupt.`);
      render();
    });
    const name = doc.createElement("div");
    name.className = "matrixlab-gallery__name";
    name.textContent = filename;
    name.title = identity;
    const thumbnailError = thumbnailErrors.get(identity);
    const failure = thumbnailError ? Object.assign(doc.createElement("div"), {
      className: "matrixlab-gallery__thumbnail-error",
      textContent: thumbnailError,
    }) : null;
    if (failure) failure.setAttribute("role", "alert");
    if (isPending) { tile.append(image, name); if (failure) tile.append(failure); return tile; }
    tile.tabIndex = 0;
    tile.setAttribute("role", "option");
    tile.setAttribute("aria-selected", String(state.selected === index));
    const select = (event) => commit({ ...state, selected: index }, event, true);
    tile.addEventListener("click", (event) => { if (!event.target.closest?.("button")) select(event); });
    tile.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(event); }
    });
    tile.addEventListener("dragstart", (event) => { draggedIndex = index; event.dataTransfer?.setData("text/plain", String(index)); });
    tile.addEventListener("dragover", (event) => { if (draggedIndex != null) event.preventDefault(); });
    tile.addEventListener("drop", (event) => { event.preventDefault(); const from = draggedIndex; draggedIndex = null; move(from, index, event); });
    tile.addEventListener("dragend", () => { draggedIndex = null; });
    const actions = doc.createElement("div");
    actions.className = "matrixlab-gallery__actions";
    actions.append(
      button("Move image earlier", "M15 18l-6-6 6-6", index === 0 || isLinked(node, canonicalWidget), (event) => move(index, index - 1, event)),
      button("Move image later", "M9 18l6-6-6-6", index === state.items.length - 1 || isLinked(node, canonicalWidget), (event) => move(index, index + 1, event)),
      button("Remove image reference", "M5 5l14 14M19 5L5 19", isLinked(node, canonicalWidget), (event) => remove(index, event)),
    );
    if (state.selected === index) {
      const selected = doc.createElement("span");
      selected.className = "matrixlab-gallery__selected";
      selected.textContent = "✓ Selected";
      selected.setAttribute("aria-hidden", "true");
      name.appendChild(selected);
    }
    tile.append(image, name);
    if (failure) tile.append(failure);
    tile.append(actions);
    return tile;
  }

  function render() {
    if (destroyed) return;
    const activeThumbnailIdentities = new Set([
      ...state.items.map((item) => item.image),
      ...pending.filter(Boolean).map((item) => item.file.name),
    ]);
    for (const identity of thumbnailErrors.keys()) {
      if (!activeThumbnailIdentities.has(identity)) thumbnailErrors.delete(identity);
    }
    for (const identity of thumbnailTokens.keys()) {
      if (!activeThumbnailIdentities.has(identity)) thumbnailTokens.delete(identity);
    }
    grid.replaceChildren();
    state.items.forEach((item, index) => grid.appendChild(tileFor(item, index, viewUrl(api, item.image))));
    pending.filter(Boolean).forEach((item) => grid.appendChild(tileFor(item.file, -1, item.url, true)));
    const total = state.items.length;
    count.textContent = `${total} image${total === 1 ? "" : "s"}${state.selected == null ? " · none selected" : ` · selected image ${state.selected + 1}`}`;
    const pendingCount = pending.filter(Boolean).length;
    empty.hidden = total > 0 || pendingCount > 0;
    grid.hidden = total === 0 && pendingCount === 0;
    drop.disabled = uploadInProgress || isLinked(node, canonicalWidget);
    drop.setAttribute("aria-disabled", String(drop.disabled));
    const activeThumbnailErrors = [...thumbnailErrors.keys()].filter((identity) => state.items.some((item) => item.image === identity));
    if (errorMessage) {
      status.dataset.error = "true";
      status.textContent = errorMessage;
    } else if (activeThumbnailErrors.length) {
      status.dataset.error = "true";
      status.textContent = `${activeThumbnailErrors.length} image thumbnail${activeThumbnailErrors.length === 1 ? " is" : "s are"} unavailable; the file may be missing or corrupt.`;
    } else {
      status.dataset.error = "false";
      status.textContent = pendingCount
        ? `Uploading ${pendingCount} image${pendingCount === 1 ? "" : "s"}…`
        : "Run processes all images in shown order; selection preview only.";
    }
    scheduleSize();
  }

  async function upload(files, event) {
    const selectedFiles = Array.from(files || []).filter(fileAccepted);
    if (!selectedFiles.length) { errorMessage = "Choose supported static image files."; render(); return; }
    if (state.items.length + selectedFiles.length > MAX_GALLERY_IMAGES) {
      errorMessage = `Choose 1–${MAX_GALLERY_IMAGES} images total; remove an existing image before adding more.`;
      render();
      return;
    }
    if (isLinked(node, canonicalWidget)) { errorMessage = "Collection state is linked and read-only."; render(); return; }
    if (uploadInProgress) { errorMessage = "An upload is already in progress."; render(); return; }
    uploadInProgress = true;
    const epoch = ++uploadEpoch;
    uploadController = typeof AbortController === "function" ? new AbortController() : null;
    pending = selectedFiles.map((file) => {
      const url = options.URL?.createObjectURL?.(file) || globalThis.URL?.createObjectURL?.(file) || "";
      if (url) objectUrls.add(url);
      return { file, url };
    });
    errorMessage = "";
    callback(options, "onUploadStart", selectedFiles);
    render();
    const uploaded = new Array(selectedFiles.length);
    const identities = new Set(state.items.map((item) => item.image));
    let nextIndex = 0;
    let stopped = false;
    const uploadOne = async (file, index) => {
      try {
        const form = new FormData();
        form.append("image", file, file.name);
        form.append("type", "input");
        form.append("overwrite", "false");
        const response = await api.fetchApi("/upload/image", { method: "POST", body: form, signal: uploadController?.signal });
        if (destroyed || epoch !== uploadEpoch) return;
        if (!response || typeof response.json !== "function") throw new Error("ComfyUI upload returned no response");
        let payload;
        try { payload = await response.json(); }
        catch { throw new Error("ComfyUI upload returned malformed JSON"); }
        if (!response.ok) throw new Error(responseErrorText(payload, response));
        const identity = identityFromUpload(payload);
        if (identities.has(identity)) throw new Error(`ComfyUI returned a duplicate identity for ${file.name}`);
        identities.add(identity);
        uploaded[index] = { image: identity };
      } catch (error) {
        if (!stopped) {
          stopped = true;
          errorMessage = `${file.name}: ${error instanceof Error ? error.message : "Upload failed"}`;
          callback(options, "onUploadError", error, file);
        }
      } finally {
        const item = pending[index];
        if (item?.url) { (options.URL || globalThis.URL)?.revokeObjectURL?.(item.url); objectUrls.delete(item.url); }
        if (item?.file?.name) thumbnailErrors.delete(item.file.name);
        pending[index] = null;
        render();
      }
    };
    const worker = async () => {
      while (!stopped && !destroyed && epoch === uploadEpoch) {
        const index = nextIndex++;
        if (index >= selectedFiles.length) return;
        await uploadOne(selectedFiles[index], index);
      }
    };
    await Promise.all(Array.from({ length: Math.min(3, selectedFiles.length) }, () => worker()));
    const added = uploaded.filter(Boolean);
    if (destroyed || epoch !== uploadEpoch) return;
    const retainedError = errorMessage;
    if (added.length) {
      const items = [...state.items, ...added];
      const selected = state.selected == null ? state.items.length : state.selected;
      commit({ version: 1, items, selected }, event, state.selected == null);
      callback(options, "onUploadComplete", added, state);
    }
    errorMessage = retainedError;
    for (const item of pending) if (item?.url) (options.URL || globalThis.URL)?.revokeObjectURL?.(item.url);
    pending = [];
    uploadInProgress = false;
    uploadController = null;
    input.value = "";
    render();
  }

  const choose = () => input.click();
  const change = (event) => void upload(input.files, event);
  const dragover = (event) => { event.preventDefault(); drop.dataset.active = "true"; };
  const dragleave = () => { drop.dataset.active = "false"; };
  const dropped = (event) => { event.preventDefault(); drop.dataset.active = "false"; void upload(event.dataTransfer?.files, event); };
  drop.addEventListener("click", choose);
  input.addEventListener("change", change);
  drop.addEventListener("dragover", dragover);
  drop.addEventListener("dragleave", dragleave);
  drop.addEventListener("drop", dropped);

  const control = {
    root,
    container,
    widget: canonicalWidget,
    get state() { return parseGalleryState(canonicalGalleryState(state)); },
    render,
    syncFromWidget(value = canonicalWidget.value) {
      if (destroyed) return false;
      try {
        state = parseGalleryState(value ?? EMPTY_GALLERY_STATE);
        errorMessage = "";
      } catch (error) {
        state = parseGalleryState(EMPTY_GALLERY_STATE);
        errorMessage = error instanceof Error ? error.message : "Invalid collection state";
      }
      render();
      return true;
    },
    upload: (files, event) => upload(files, event),
    destroy() {
      if (destroyed) return;
      destroyed = true;
      uploadEpoch += 1;
      uploadController?.abort?.();
      uploadController = null;
      clearTimeout(repairTimer);
      resizeObserver?.disconnect?.();
      drop.removeEventListener("click", choose);
      input.removeEventListener("change", change);
      drop.removeEventListener("dragover", dragover);
      drop.removeEventListener("dragleave", dragleave);
      drop.removeEventListener("drop", dropped);
      for (const url of objectUrls) (options.URL || globalThis.URL)?.revokeObjectURL?.(url);
      objectUrls.clear();
      thumbnailErrors.clear();
      thumbnailTokens.clear();
      halo?.destroy?.();
      for (const child of Array.from(root.childNodes || [])) if (!beforeChildren.has(child)) child.remove?.();
      root.className = beforeClassName;
      if (hadHaloVersion) root.dataset.haloVersion = beforeHaloVersion;
      else if (root.dataset) delete root.dataset.haloVersion;
      if (node?.onResize === wrappedResize) node.onResize = previousResize;
      if (node?.onRemoved === wrappedRemoved) node.onRemoved = previousRemoved;
      callback(options, "onDestroy");
    },
  };
  const wrappedResize = function (...args) { const result = previousResize?.apply(this, args); scheduleSize(); return result; };
  const wrappedRemoved = function (...args) { control.destroy(); return previousRemoved?.apply(this, args); };

  try {
    root.appendChild(container);
    halo = (options.mountHaloSurface || mountHaloSurface)(root, node, { ...options, profile: "ui" });
    if (!halo) throw new Error("HALO surface mount failed");
    const Observer = options.ResizeObserver || globalThis.ResizeObserver;
    if (typeof Observer === "function") {
      resizeObserver = new Observer(() => scheduleSize());
      resizeObserver.observe(container);
    }
    if (node) { node.onResize = wrappedResize; node.onRemoved = wrappedRemoved; }
    render();
    return control;
  } catch (error) {
    control.destroy();
    callback(options, "onError", error);
    return null;
  }
}
