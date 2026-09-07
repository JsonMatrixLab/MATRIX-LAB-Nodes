import { HALO_TOKENS, createHaloWidgetHost, haloMinimumNodeHeight, haloWidgetLayoutHeight, measureHaloContentHeight, measureHaloHorizontalChrome, measureHaloVerticalChrome, mountHaloSurface, setHaloNodeSize } from "./halo.cdbfe5654df6eedc.mjs";

export { createHaloWidgetHost, haloMinimumNodeHeight, haloWidgetLayoutHeight, measureHaloContentHeight, measureHaloHorizontalChrome, measureHaloVerticalChrome, setHaloNodeSize };

const STYLE_KEY = Symbol.for("matrixlab.halo.resolution.style.v1.0.0");

function installStyles(doc) {
  if (doc[STYLE_KEY]) return;
  const style = doc.createElement("style");
  style.dataset.matrixlabHaloResolution = "1.0.0";
  style.textContent = `
.matrixlab-halo-resolution{width:100%;min-width:0;padding:18px 16px;display:flex;flex-direction:column;align-items:stretch;align-content:flex-start;gap:0;overflow:visible}
.matrixlab-halo-resolution__tier{position:relative;z-index:2;min-height:32px;padding:0 0 10px;display:flex;align-items:center;justify-content:space-between;gap:8px;color:${HALO_TOKENS.green};font-size:11px;line-height:16.5px;font-weight:700;letter-spacing:1px}
.matrixlab-halo-resolution__profile{padding:3px 7px;border:1px solid #325D40;border-radius:5px;background:#14291C;color:#C1DACA;font-size:9px;line-height:13.5px;font-weight:400;letter-spacing:0}
.matrixlab-halo-resolution__section{position:relative;z-index:2;margin-top:13px}
.matrixlab-halo-resolution__heading{margin-bottom:9px;display:flex;align-items:center;gap:8px;color:#A0B7A7;font-size:9px;line-height:13.5px;letter-spacing:1px}
.matrixlab-halo-resolution__heading-index{color:${HALO_TOKENS.green}}
.matrixlab-halo-resolution__heading-rule{height:1px;flex:1;background:#294534}
.matrixlab-halo-resolution__grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
.matrixlab-halo-resolution__choice{min-width:0;height:52px;padding:0 8px;display:flex;align-items:center;justify-content:center;gap:8px;border:1px solid #355D42;border-radius:10px;background:linear-gradient(180deg,#1B2E22 0%,#0C1C12 100%);box-shadow:inset 0 1px 0 #B6FFCB15,0 2px 5px #00000033;color:#B7CBBD;font-size:13px;line-height:19.5px;cursor:pointer;transition:background-color 150ms ease,border-color 150ms ease}
.matrixlab-halo-resolution__choice:hover:not(:disabled){border-color:#83FFA4;background:#153923}
.matrixlab-halo-resolution__choice[aria-pressed="true"]{border-color:#56FF82;background:linear-gradient(180deg,#17442A 0%,#102A1B 100%);box-shadow:inset 0 0 15px #00FF4114,0 0 10px #00FF4112;color:#9EFFB9}
.matrixlab-halo-resolution__choice:focus-visible,.matrixlab-halo-resolution__action:focus-visible{outline:2px solid ${HALO_TOKENS.focus};outline-offset:-3px}
.matrixlab-halo-resolution__choice:disabled,.matrixlab-halo-resolution__action:disabled{opacity:.38;cursor:default}
.matrixlab-halo-resolution__ratio-icon{width:20px;height:18px;display:grid;place-items:center}
.matrixlab-halo-resolution__ratio-icon>span{display:block;max-width:20px;max-height:18px;border:1px solid currentColor;opacity:.75}
.matrixlab-halo-resolution__preview{position:relative;z-index:2;height:128px;margin-top:12px;display:grid;place-items:center;overflow:hidden;border:1px solid #253E2E;border-radius:10px;background-color:#07130960;background-image:radial-gradient(circle,#294031 1px,#00000000 1px);background-size:10px 10px}
.matrixlab-halo-resolution__frame{position:relative;max-width:87px;max-height:87px;border:1px solid #5CF2A5;background:linear-gradient(145deg,#00FF4118 0%,#00FF4100 100%);transition:width 250ms ease,height 250ms ease}
.matrixlab-halo-resolution__corner{position:absolute;width:9px;height:9px;border-color:${HALO_TOKENS.green};border-style:solid}
.matrixlab-halo-resolution__corner:first-child{left:-2px;top:-2px;border-width:2px 0 0 2px}.matrixlab-halo-resolution__corner:last-child{right:-2px;bottom:-2px;border-width:0 2px 2px 0}
.matrixlab-halo-resolution__preview-label{position:absolute;left:9px;top:7px;color:#8FAF99;font-size:8px;line-height:12px}.matrixlab-halo-resolution__preview-ratio{position:absolute;right:9px;bottom:7px;color:#8FAF99;font-size:9px;line-height:13.5px}
.matrixlab-halo-resolution__dimensions{position:relative;z-index:2;margin:12px 0 4px;text-align:center;color:${HALO_TOKENS.primaryText};font-size:25px;line-height:30px;letter-spacing:-1px}
.matrixlab-halo-resolution__multiply{padding:0 7px;color:#70A47F;font-size:16px;line-height:24px;letter-spacing:0}
.matrixlab-halo-resolution__method{position:relative;z-index:2;min-height:30px;text-align:center;color:#9CB9A6;font-size:9px;line-height:15.3px}
.matrixlab-halo-resolution__actions{position:relative;z-index:2;margin-top:10px;display:flex;gap:7px}
.matrixlab-halo-resolution__action{min-width:0;min-height:36px;flex:1;padding:0 10px;border:1px solid #31513C;border-radius:8px;background:#101F15;color:#B0C6B7;font-size:10px;line-height:15px;cursor:pointer}
.matrixlab-halo-resolution__validation{position:relative;z-index:2;margin-top:8px;padding:8px 10px;border:1px solid ${HALO_TOKENS.errorText};border-radius:8px;background:${HALO_TOKENS.errorSurface};color:${HALO_TOKENS.errorText};font-size:10px;line-height:16px;white-space:normal;overflow-wrap:anywhere}
`;
  doc.head.appendChild(style);
  doc[STYLE_KEY] = style;
}

function heading(doc, index, label) {
  const row = doc.createElement("div");
  row.className = "matrixlab-halo-resolution__heading";
  const number = doc.createElement("span");
  number.className = "matrixlab-halo-resolution__heading-index";
  number.textContent = String(index).padStart(2, "0");
  const text = doc.createElement("span");
  text.textContent = label;
  const rule = doc.createElement("span");
  rule.className = "matrixlab-halo-resolution__heading-rule";
  row.append(number, text, rule);
  return row;
}

function ratioShape(item) {
  const pair = item.ratio || String(item.label).split(":").map(Number);
  const width = Number(pair[0]);
  const height = Number(pair[1]);
  if (!(width > 0 && height > 0)) return { width: 14, height: 14 };
  const scale = Math.min(20 / width, 18 / height);
  return { width: Math.max(1, width * scale), height: Math.max(1, height * scale) };
}

function choiceButton(doc, item, activate) {
  const button = doc.createElement("button");
  button.type = "button";
  button.className = "matrixlab-halo-resolution__choice";
  button.dataset.action = item.id;
  button.dataset.haloEffect = "secondary";
  if (item.group) button.dataset.group = item.group;
  if (item.value !== undefined) button.dataset.value = String(item.value);
  button.setAttribute("aria-label", item.ariaLabel || item.label);
  const icon = doc.createElement("span");
  icon.className = "matrixlab-halo-resolution__ratio-icon";
  const shape = doc.createElement("span");
  const size = ratioShape(item);
  shape.style.width = `${size.width}px`;
  shape.style.height = `${size.height}px`;
  icon.appendChild(shape);
  const label = doc.createElement("span");
  label.textContent = item.label;
  button.append(icon, label);
  button.addEventListener("click", (event) => activate(item.id, event));
  return button;
}

function actionButton(doc, item, activate) {
  const button = doc.createElement("button");
  button.type = "button";
  button.className = "matrixlab-halo-resolution__action";
  button.dataset.action = item.id;
  button.dataset.haloEffect = "secondary";
  button.textContent = item.label;
  button.addEventListener("click", (event) => activate(item.id, event));
  return button;
}

export function createHaloResolutionDeck(options) {
  const { document: doc = globalThis.document, node, control } = options;
  installStyles(doc);
  const root = doc.createElement("div");
  root.className = "matrixlab-halo-resolution";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", options.ariaLabel || "MATRIXLAB Resolution controls");
  const tier = doc.createElement("div");
  tier.className = "matrixlab-halo-resolution__tier";
  const tierText = doc.createElement("span");
  const profile = doc.createElement("span");
  profile.className = "matrixlab-halo-resolution__profile";
  tier.append(tierText, profile);
  root.appendChild(tier);

  const groups = [];
  const deferredSections = [];
  for (const [groupIndex, group] of (options.groups || []).entries()) {
    const section = doc.createElement("section");
    section.className = "matrixlab-halo-resolution__section";
    section.appendChild(heading(doc, groupIndex + 1, group.label));
    const grid = doc.createElement("div");
    grid.className = "matrixlab-halo-resolution__grid";
    const buttons = group.items.map((item) => choiceButton(doc, item, activate));
    grid.append(...buttons);
    section.appendChild(grid);
    if (groupIndex === 0) root.appendChild(section);
    else deferredSections.push(section);
    groups.push({ ...group, buttons, grid });
  }

  const preview = doc.createElement("div");
  preview.className = "matrixlab-halo-resolution__preview";
  const previewLabel = doc.createElement("span");
  previewLabel.className = "matrixlab-halo-resolution__preview-label";
  previewLabel.textContent = "OUTPUT";
  const frame = doc.createElement("div");
  frame.className = "matrixlab-halo-resolution__frame";
  const cornerA = doc.createElement("span");
  const cornerB = doc.createElement("span");
  cornerA.className = cornerB.className = "matrixlab-halo-resolution__corner";
  frame.append(cornerA, cornerB);
  const previewRatio = doc.createElement("span");
  previewRatio.className = "matrixlab-halo-resolution__preview-ratio";
  preview.append(previewLabel, frame, previewRatio);
  root.appendChild(preview);

  const dimensions = doc.createElement("div");
  dimensions.className = "matrixlab-halo-resolution__dimensions";
  const widthText = doc.createElement("span");
  const multiply = doc.createElement("span");
  multiply.className = "matrixlab-halo-resolution__multiply";
  multiply.textContent = "×";
  const heightText = doc.createElement("span");
  dimensions.append(widthText, multiply, heightText);
  const method = doc.createElement("div");
  method.className = "matrixlab-halo-resolution__method";
  root.append(dimensions, method);
  root.append(...deferredSections);

  const actions = doc.createElement("div");
  actions.className = "matrixlab-halo-resolution__actions";
  const actionButtons = (options.actions || []).map((item) => actionButton(doc, item, activate));
  actions.append(...actionButtons);
  if (actionButtons.length) root.appendChild(actions);
  const validation = doc.createElement("div");
  validation.className = "matrixlab-halo-resolution__validation";
  validation.setAttribute("role", "status");
  validation.hidden = true;
  root.appendChild(validation);

  function activate(action, event) {
    if (node.flags?.collapsed || options.isDisabled?.(action)) return false;
    const result = options.activate(action, event);
    render();
    return result;
  }
  const navigable = () => [...groups.flatMap((group) => group.buttons), ...actionButtons].filter((button) => !button.disabled);
  root.addEventListener("keydown", (event) => {
    if (node.flags?.collapsed) return;
    if (!event.target?.dataset?.action || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    const buttons = navigable();
    const current = buttons.indexOf(event.target);
    if (current < 0 || buttons.length < 2) return;
    const delta = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
    buttons[(current + delta + buttons.length) % buttons.length].focus({ preventScroll: true });
    event.preventDefault();
    event.stopPropagation();
  });

  function render() {
    if (control.destroyed) return;
    const state = options.view();
    const width = Number(root.clientWidth) || Math.max(HALO_TOKENS.uiMinWidth, Number(node.size?.[0]) || HALO_TOKENS.uiMinWidth);
    root.dataset.layout = width >= 560 ? "wide" : "narrow";
    tierText.textContent = state.tier || "RESOLUTION";
    profile.textContent = state.profile ?? "MATRIXLAB";
    profile.style.display = profile.textContent ? "" : "none";
    for (const group of groups) {
      group.grid.style.gridTemplateColumns = `repeat(${Math.min(group.items.length, width >= 560 ? 6 : 3)},minmax(0,1fr))`;
      for (const [index, button] of group.buttons.entries()) {
        const item = group.items[index];
        button.setAttribute("aria-pressed", String(state.active?.[group.id] === item.id));
        button.disabled = Boolean(options.isDisabled?.(item.id));
        button.title = button.disabled ? options.disabledReason?.(item.id) || "Linked input" : "";
      }
    }
    for (const [index, button] of actionButtons.entries()) {
      const item = options.actions[index];
      button.disabled = Boolean(options.isDisabled?.(item.id));
      button.title = button.disabled ? options.disabledReason?.(item.id) || "Linked input" : "";
    }
    const resolved = state.dimensions || [0, 0];
    widthText.textContent = String(resolved[0]);
    heightText.textContent = String(resolved[1]);
    const fitted = fitPreviewFrame(resolved[0], resolved[1]);
    frame.style.width = `${fitted.width}px`;
    frame.style.height = `${fitted.height}px`;
    previewRatio.textContent = state.ratioLabel || "";
    method.textContent = state.method || "";
    method.style.display = method.textContent ? "" : "none";
    validation.hidden = !state.error;
    validation.textContent = state.error || "";
    const measuredHeight = measureHaloContentHeight(root, control.minimumContentHeight || 0);
    if (measuredHeight !== control.minimumContentHeight) {
      control.minimumContentHeight = measuredHeight;
      control.scheduleMinimumSize?.();
    }
    control.halo?.renderStatic();
  }

  control.root = root;
  control.element = root;
  control.dimensionWidth = widthText;
  control.dimensionHeight = heightText;
  control.methodLine = method;
  control.render = render;
  control.mountHalo = () => {
    control.halo = mountHaloSurface(root, node, { ...options.haloOptions, profile: "ui" });
    return control.halo;
  };
  control.removeElementListeners = () => {};
  return root;
}

export function fitPreviewFrame(width, height, longestEdge = 87) {
  const safeWidth = Number(width);
  const safeHeight = Number(height);
  const edge = Math.max(1, Number(longestEdge) || 87);
  if (!(safeWidth > 0) || !(safeHeight > 0)) return { width: edge, height: edge };
  const scale = edge / Math.max(safeWidth, safeHeight);
  return { width: safeWidth * scale, height: safeHeight * scale };
}

// Universal size selection; no model alignment or multi-stage sampling assumptions.
export function calculateTierResolution(aspectRatio, resolutionTier) {
  const longest = { "1K": 1024, "2K": 2048, "4K": 4096 }[resolutionTier];
  const parts = String(aspectRatio).split(":").map(Number);
  if (typeof longest !== "number" || parts.length !== 2 || parts.some(value => !Number.isInteger(value) || value < 1)) {
    throw new Error("Unsupported aspect ratio or resolution tier");
  }
  const [width, height] = parts;
  const shorter = Math.floor(longest * Math.min(width, height) / Math.max(width, height) + 0.5);
  return width >= height ? [longest, shorter] : [shorter, longest];
}

// Run on serialized graphs before ComfyUI applies widgets by position.
export function migrateResolutionGraph(graph) {
  for (const node of graph?.nodes || []) {
    const values = node.widgets_values;
    const general = node.type === "MATRIXLAB_Resolution"
      && Array.isArray(values) && values.length >= 5 && typeof values[1] === "number";
    const influencer = node.type === "MATRIXLAB_AIInfluencerResolution"
      && node.outputs?.some(output => output.name === "render_width");
    if (!general && !influencer) continue;
    const linkedInputs = node.inputs?.some(input => input.link != null);
    const linkedOutputs = node.outputs?.some(output => output.links?.length);
    const requireReplacement = () => {
      node.type += "_LegacyRequiresReplacement";
      node.title = "Legacy Resolution - replace with a new Resolution node";
    };
    if (linkedInputs || (influencer && linkedOutputs)) {
      requireReplacement();
      continue;
    }
    if (general) {
      const [aspect, longest, customWidth, customHeight, alignment] = values;
      const ratios = { "1:1": [1, 1], "16:9": [16, 9], "9:16": [9, 16],
        "4:3": [4, 3], "3:4": [3, 4], "3:2": [3, 2], "2:3": [2, 3],
        "4:5": [4, 5], "5:4": [5, 4], "21:9": [21, 9] };
      if (![1, 2, 4, 8, 16, 32, 64].includes(alignment)
        || ![longest, customWidth, customHeight].every(Number.isInteger)
        || longest < 1024 || longest > 2048
        || customWidth < 512 || customWidth > 2048 || customHeight < 512 || customHeight > 2048
        || (aspect !== "Custom" && !Object.hasOwn(ratios, aspect))) {
        requireReplacement();
        continue;
      }
      const align = value => Math.floor((2 * value + alignment) / (2 * alignment)) * alignment;
      let width, height;
      if (aspect === "Custom") {
        [width, height] = [Math.max(512, align(customWidth)), Math.max(512, align(customHeight))];
      } else {
        const [rw, rh] = ratios[aspect];
        const edge = align(longest);
        const denominator = Math.max(rw, rh) * alignment;
        const short = Math.floor((2 * edge * Math.min(rw, rh) + denominator) / (2 * denominator)) * alignment;
        [width, height] = rw >= rh ? [edge, short] : [short, edge];
      }
      node.widgets_values = ["Custom", "2K", width, height];
      // Unlinked converted legacy widgets must not keep obsolete input names.
      node.inputs = (node.inputs || []).filter(input => !["max_side", "divisible_by"].includes(input.name));
      node.title = "Resolution - previous pixel dimensions preserved as Custom";
    } else {
      if (!Array.isArray(values) || !["1:1", "9:16", "3:4"].includes(values[0])
        || !["1K", "2K", "4K Progressive"].includes(values[1])) {
        requireReplacement();
        continue;
      }
      node.widgets_values = [values[0], values[1] === "4K Progressive" ? "4K" : values[1]];
      node.outputs = ["width", "height"].map((name, slot_index) => ({ name, type: "INT", links: null, slot_index }));
      node.title = "AI Influencer Resolution - migrated to pixel sizes";
    }
  }
  for (const subgraph of graph?.definitions?.subgraphs || []) migrateResolutionGraph(subgraph);
}
