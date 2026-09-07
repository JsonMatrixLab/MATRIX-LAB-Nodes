export const HALO_VERSION = "1.0.0";
export const HALO_MOTION_SETTING_ID = "MATRIXLAB.HALO.Motion";

export const HALO_GLYPHS =
  "アカサタナハマヤラワイキシチニヒミリヰウクスツヌフムユルエケセテネヘメレヱオコソトノホモヨロヲ0123456789";

export const HALO_EXECUTION_NODE_IDS = Object.freeze([
  "MATRIXSpectralSampler",
  "MATRIX_LatentTail",
  "MATRIX_SkinMask",
  "MATRIX_EyeMask",
  "MATRIX_CropTailPaste",
  "MATRIX_SaveClean",
  "MATRIX_OutputStage",
  "MATRIX_Renoise",
  "MATRIX_CameraLook",
]);

function numericStyle(value) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function measureHaloContentHeight(root, fallback = 0) {
  if (!root) return Math.max(0, Number(fallback) || 0);
  const children = Array.from(root.children || root.childNodes || []).filter((child) => {
    const position = child?.style?.position;
    return child?.tagName !== "CANVAS" && position !== "absolute" && position !== "fixed";
  });
  const bottoms = children
    .map((child) => {
      const top = Number(child.offsetTop);
      const height = Number(child.offsetHeight);
      return Number.isFinite(top) && Number.isFinite(height) && height > 0 ? top + height : 0;
    })
    .filter((bottom) => bottom > 0);
  // A hidden/detached deck has no measurable flow. Its fallback is already
  // a complete content height; adding padding again feeds the previous result
  // back into the next observer pass and grows the node indefinitely.
  if (!bottoms.length) return Math.max(0, Number(fallback) || 0);
  const contentBottom = Math.max(...bottoms);
  const view = root.ownerDocument?.defaultView || globalThis;
  const style = view.getComputedStyle?.(root) || globalThis.getComputedStyle?.(root);
  return Math.max(0, contentBottom + numericStyle(style?.paddingBottom) + numericStyle(style?.borderBottomWidth));
}

// ComfyUI owns the DOM-widget slot and may stretch it to the user's saved node
// height. Keep that allocation separate from the intrinsic bordered surface so
// native allocation never becomes the intrinsic content measurement.
export function createHaloWidgetHost(surface, suppliedDocument) {
  const doc = suppliedDocument || surface?.ownerDocument || globalThis.document;
  if (!surface || !doc?.createElement) return null;
  const host = doc.createElement("div");
  host.className = "matrixlab-halo-host";
  host.appendChild(surface);
  return host;
}

// Renderer chrome is only learnable after the owned DOM root has a real layout.
// Returning null for an unmounted/zero-sized root keeps the first probe from
// permanently caching a false zero and lets the next resize pass learn it.
export function measureHaloVerticalChrome(root, currentHeight, suppliedChrome) {
  const ownedHeight = Number(root?.offsetHeight);
  if (!(ownedHeight > 0)) return null;
  const measured = Math.max(0, (Number(currentHeight) || 0) - ownedHeight);
  const supplied = typeof suppliedChrome === "object"
    ? Number(suppliedChrome?.vertical)
    : Number(suppliedChrome);
  return supplied > 0 && Number.isFinite(supplied) ? supplied : measured;
}

// The native minimum already includes widget margins, sockets and layout chrome.
// Measuring against a stretched DOM root would mistake user surplus for chrome.
export function haloMinimumNodeHeight(node, contentHeight, suppliedChrome = 0) {
  try {
    const minimum = Number(node.computeSize?.()?.[1]);
    if (Number.isFinite(minimum) && minimum > 0) return minimum;
  } catch {}
  const chrome = typeof suppliedChrome === "object" ? Number(suppliedChrome?.vertical) : Number(suppliedChrome);
  return Math.max(0, Number(contentHeight) || 0) + Math.max(0, chrome || 0);
}

const resizeInteractions = new WeakMap();
const resizeDocuments = new WeakMap();

// Nodes 2.0 ignores external size changes during a physical resize. Defer our
// corrections until pointerup has completed, without touching renderer internals.
export function bindHaloResizeInteraction(doc, node) {
  if (!doc?.addEventListener) return () => {};
  let state = resizeDocuments.get(doc);
  if (!state) {
    state = { active: false, pending: new Map(), owners: new Set(), timer: null };
    state.down = () => { state.active = true; };
    state.up = () => {
      clearTimeout(state.timer);
      state.timer = setTimeout(() => {
        state.active = false;
        const pending = [...state.pending];
        state.pending.clear();
        for (const [owner, repair] of pending) {
          if (state.owners.has(owner) && owner.size?.[0] === repair.observed[0] && owner.size?.[1] === repair.observed[1]) {
            setHaloNodeSize(owner, repair.size);
          }
        }
      }, 0);
    };
    doc.addEventListener("pointerdown", state.down, true);
    doc.addEventListener("pointerup", state.up, true);
    doc.addEventListener("pointercancel", state.up, true);
    doc.defaultView?.addEventListener?.("blur", state.up);
    resizeDocuments.set(doc, state);
  }
  state.owners.add(node);
  resizeInteractions.set(node, state);
  return () => {
    state.pending.delete(node);
    state.owners.delete(node);
    resizeInteractions.delete(node);
    if (!state.owners.size) {
      clearTimeout(state.timer);
      doc.removeEventListener("pointerdown", state.down, true);
      doc.removeEventListener("pointerup", state.up, true);
      doc.removeEventListener("pointercancel", state.up, true);
      doc.defaultView?.removeEventListener?.("blur", state.up);
      resizeDocuments.delete(doc);
    }
  };
}

// Programmatic size repairs happen outside LiteGraph's pointer-resize dirty pass.
// Keep the public size mutation and invalidate the owning canvas together so
// Classic cached bounds and DOM-widget placement refresh on the next frame.
export function setHaloNodeSize(node, size) {
  if (!node || !size || size.length < 2) return size;
  const interaction = resizeInteractions.get(node);
  if (interaction?.active) {
    interaction.pending.set(node, { size: [...size], observed: [...node.size] });
    return size;
  }
  if (typeof node.setSize === "function") node.setSize(size);
  else node.size = size;
  node.setDirtyCanvas?.(true, true);
  return size;
}

export function measureHaloHorizontalChrome(root, currentWidth, suppliedChrome) {
  const ownedWidth = Number(root?.clientWidth || root?.offsetWidth);
  if (!(ownedWidth > 0)) return null;
  const measured = Math.max(0, (Number(currentWidth) || 0) - ownedWidth);
  const supplied = typeof suppliedChrome === "object"
    ? Number(suppliedChrome?.horizontal)
    : Number(suppliedChrome);
  return supplied > 0 && Number.isFinite(supplied) ? supplied : measured;
}

const DOM_WIDGET_DEFAULT_MARGIN = 10;
const DOM_WIDGET_FIXED_ALLOCATION_EXTRA = 4;

/**
 * Convert owned DOM height into the height requested from ComfyUI's public
 * DOM-widget bridge. Growable DOM widgets allocate the requested height and
 * then remove both margins; fixed computeSize widgets receive an extra 4px
 * before those margins are removed.
 */
export function haloWidgetLayoutHeight(contentHeight, widget, mode = "layout") {
  const content = Math.max(0, Number(contentHeight) || 0);
  const marginValue = Number(widget?.margin);
  const margin = Number.isFinite(marginValue) && marginValue >= 0
    ? marginValue
    : DOM_WIDGET_DEFAULT_MARGIN;
  const fixedAdjustment = mode === "fixed" ? -DOM_WIDGET_FIXED_ALLOCATION_EXTRA : 0;
  return content + margin * 2 + fixedAdjustment;
}

export const HALO_TOKENS = Object.freeze({
  body: "#050A05",
  nativeTitle: "#0A150A",
  staticBorder: "#21492B",
  matrixText: "#39FF7A",
  primaryText: "#EDF8F0",
  secondaryText: "#97AA9C",
  parameterLabel: "#ABC0B1",
  committedValue: "#5CF2A5",
  numericOutput: "#00FF41",
  instanceId: "#7FB58B",
  headerDivider: "#204B2B",
  fieldBorder: "#31543C",
  fieldHoverBorder: "#56FF82",
  footerSurface: "#08170BDE",
  footerDivider: "#24462E",
  footerText: "#94C69E",
  helpText: "#A3BAAA",
  primaryActionText: "#BDFFD0",
  primaryActionBorder: "#00FF41",
  primaryActionHover: "#154624",
  actionHighlight: "#BAFFCE24",
  green: "#00FF41",
  focus: "#FFCA6B",
  warningText: "#FFCA6B",
  warningSurface: "#241B0D",
  errorText: "#FF6B5A",
  errorSurface: "#26110F",
  linkedText: "#97AA9C",
  linkedSurface: "#0C1710",
  linkedBorder: "#34513E",
  successText: "#7DFA8A",
  depthShadow: "#000000BB",
  ambientShadow: "#00FF4117",
  transparent: "#00000000",
  ownedHeader: "linear-gradient(110deg, #112719EF 0%, #08150BEE 100%)",
  parameterField: "linear-gradient(125deg, #172B1EDF 0%, #0B1710ED 100%)",
  primaryAction: "linear-gradient(180deg, #173E24 0%, #0B2113 100%)",
  shimmer: "linear-gradient(90deg, #AFFFC900 0%, #AFFFC940 50%, #AFFFC900 100%)",
  outerRadius: 16,
  outerBorderWidth: 1,
  headerHeight: 49,
  headerPaddingX: 16,
  headerGap: 8,
  footerHeight: 34.5,
  footerPaddingX: 17,
  footerPaddingY: 10,
  deckMargin: 7,
  deckPaddingX: 16,
  deckPaddingY: 18,
  fieldHeight: 38,
  fieldPaddingX: 10,
  fieldPaddingY: 8,
  fieldRadius: 9,
  fieldGap: 8,
  fieldChildGap: 12,
  sectionGap: 16,
  primaryActionHeight: 40,
  primaryActionRadius: 10,
  secondaryActionMinHeight: 36,
  secondaryActionRadius: 8,
  executionMinWidth: 360,
  uiMinWidth: 420,
  zoomMotionCutoff: 0.45,
  glyphCell: 16,
  glyphFont: "bold 14px monospace",
  glyphOffsetX: 2,
  glyphOffsetY: 1,
  columnPitch: 14,
  trailLength: 8,
  trailPitch: 14,
  trailAlpha: 0.2,
  trailAlphaStep: 0.025,
  minSpeedPerSecond: 36,
  maxSpeedPerSecond: 144,
  maxTimeStepSeconds: 0.05,
  wrapOvershoot: 20,
  restartMinY: -40,
  restartMaxY: 0,
  edgeWidth: 1.8,
  edgeShadowBlur: 10,
  edgeDash: Object.freeze([24, 60]),
  edgeDashCycle: 84,
  edgeSpeed: 90,
  canvasOverscan: 12,
  maxDevicePixelRatio: 2,
});

const FONT_URL = new URL("./assets/CascadiaMono.woff2", import.meta.url).href;
const SCHEDULER_KEY = Symbol.for(`matrixlab.halo.scheduler.v${HALO_VERSION}`);
const SURFACE_KEY = Symbol.for(`matrixlab.halo.surface.v${HALO_VERSION}`);
const EXECUTION_KEY = Symbol.for(`matrixlab.halo.execution.v${HALO_VERSION}`);
const STYLE_KEY = Symbol.for(`matrixlab.halo.style.v${HALO_VERSION}`);
const SETTING_KEY = Symbol.for(`matrixlab.halo.motion-setting.v${HALO_VERSION}`);
const MOTION_STORAGE_KEY = "matrixlab.halo.motion";
const EXECUTION_IDS = new Set(HALO_EXECUTION_NODE_IDS);
const UTILITY_IDS = new Set(["MATRIX_ResolutionPlan"]);

function browserDocument(root, override) {
  return override || root?.ownerDocument || globalThis.document;
}

function readMotionPreference(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(MOTION_STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

function roundedRect(ctx, x, y, width, height, radius) {
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(x, y, width, height, radius);
    return;
  }
  const r = Math.min(radius, width / 2, height / 2);
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.arcTo(x + width, y, x + width, y + r, r);
  ctx.lineTo(x + width, y + height - r);
  ctx.arcTo(x + width, y + height, x + width - r, y + height, r);
  ctx.lineTo(x + r, y + height);
  ctx.arcTo(x, y + height, x, y + height - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
}

function makeScheduler(options = {}) {
  const win = options.window || globalThis;
  const doc = options.document || win.document;
  const requestFrame = options.requestAnimationFrame || win.requestAnimationFrame?.bind(win);
  const cancelFrame = options.cancelAnimationFrame || win.cancelAnimationFrame?.bind(win);
  const now = options.now || (() => win.performance?.now?.() ?? Date.now());
  const clients = new Set();
  let frameId = null;
  let lastTime = null;
  let motionEnabled = readMotionPreference(options.storage || win.localStorage);
  let profile = null;

  const profileSummary = (session) => {
    const costs = session.samples.map((sample) => sample.costMs).sort((a, b) => a - b);
    const percentile = (fraction) => costs.length
      ? costs[Math.max(0, Math.ceil(costs.length * fraction) - 1)]
      : null;
    return Object.freeze({
      frames: costs.length,
      maxFrames: session.maxFrames,
      complete: session.complete,
      medianMs: percentile(0.5),
      p95Ms: percentile(0.95),
      maxMs: costs.length ? costs[costs.length - 1] : null,
      eligibleCounts: Object.freeze(session.samples.map((sample) => sample.eligibleCount)),
      measurementScope: "shared frame: eligibility, drawing and next-frame scheduling",
    });
  };

  const eligibleClients = () => [...clients].filter((client) => client.isEligible());
  const frame = (timestamp) => {
    const measuredProfile = profile;
    const profileStart = measuredProfile ? now() : 0;
    frameId = null;
    const current = Number.isFinite(timestamp) ? timestamp : now();
    const elapsed = lastTime == null ? 0 : Math.min(0.05, Math.max(0, (current - lastTime) / 1000));
    lastTime = current;
    const eligible = motionEnabled ? eligibleClients() : [];
    for (const client of eligible) client.drawFrame(current / 1000, elapsed);
    if (eligible.length) schedule();
    else lastTime = null;
    if (measuredProfile) {
      measuredProfile.samples.push({
        costMs: Math.max(0, now() - profileStart),
        eligibleCount: eligible.length,
      });
      if (measuredProfile.samples.length >= measuredProfile.maxFrames) {
        measuredProfile.complete = true;
        if (profile === measuredProfile) profile = null;
      }
    }
  };
  const schedule = () => {
    if (frameId != null || !motionEnabled || !requestFrame || !eligibleClients().length) return;
    frameId = requestFrame(frame);
  };
  const stop = () => {
    if (frameId != null && cancelFrame) cancelFrame(frameId);
    frameId = null;
    lastTime = null;
  };
  const visibilityChanged = () => {
    if (doc?.hidden) stop();
    else schedule();
  };
  doc?.addEventListener?.("visibilitychange", visibilityChanged);
  const wakeEvents = ["resize", "scroll", "wheel", "pointerup"];
  for (const eventName of wakeEvents) win.addEventListener?.(eventName, schedule, { passive: true, capture: true });

  return {
    version: HALO_VERSION,
    register(client) {
      clients.add(client);
      schedule();
      return () => {
        clients.delete(client);
        if (!eligibleClients().length) stop();
      };
    },
    wake: schedule,
    stop,
    setMotionEnabled(enabled, persist = true) {
      motionEnabled = enabled !== false;
      if (persist) {
        try {
          (options.storage || win.localStorage)?.setItem(MOTION_STORAGE_KEY, motionEnabled ? "on" : "off");
        } catch {}
      }
      if (motionEnabled) schedule();
      else stop();
    },
    isMotionEnabled: () => motionEnabled,
    size: () => clients.size,
    pending: () => frameId != null,
    startProfile(maxFrames = 240) {
      const boundedFrames = Math.min(240, Math.max(1, Math.trunc(Number(maxFrames) || 240)));
      if (profile) profile.stopped = true;
      const session = {
        maxFrames: boundedFrames,
        samples: [],
        complete: false,
        stopped: false,
        summary() { return profileSummary(session); },
        stop() {
          session.stopped = true;
          if (profile === session) profile = null;
          return profileSummary(session);
        },
      };
      profile = session;
      schedule();
      return session;
    },
    destroy() {
      stop();
      clients.clear();
      doc?.removeEventListener?.("visibilitychange", visibilityChanged);
      for (const eventName of wakeEvents) win.removeEventListener?.(eventName, schedule, { capture: true });
    },
  };
}

export function registerHaloMotionSetting(app, options = {}) {
  const host = options.global || globalThis;
  if (host[SETTING_KEY]) return host[SETTING_KEY];
  const settings = app?.ui?.settings;
  if (typeof settings?.addSetting !== "function") return null;
  const scheduler = options.scheduler || getHaloScheduler(options.schedulerOptions);
  const state = { id: HALO_MOTION_SETTING_ID, scheduler, definition: null };
  host[SETTING_KEY] = state;
  const definition = {
    id: HALO_MOTION_SETTING_ID,
    name: "MATRIXLAB HALO motion",
    tooltip: "Animate MATRIXLAB HALO rain and perimeter effects.",
    type: "boolean",
    defaultValue: true,
    onChange(value) {
      scheduler.setMotionEnabled(value !== false, false);
    },
  };
  state.definition = definition;
  try {
    settings.addSetting(definition);
    const configured = settings.getSettingValue?.(HALO_MOTION_SETTING_ID);
    if (typeof configured === "boolean") scheduler.setMotionEnabled(configured, false);
  } catch (error) {
    delete host[SETTING_KEY];
    options.onError?.(error);
    return null;
  }
  return state;
}

export function getHaloScheduler(options) {
  const host = options?.global || globalThis;
  const existing = host[SCHEDULER_KEY];
  if (existing?.version === HALO_VERSION) return existing;
  const scheduler = makeScheduler(options);
  host[SCHEDULER_KEY] = scheduler;
  return scheduler;
}

function installStyle(doc) {
  if (!doc?.head?.appendChild || doc[STYLE_KEY]) return;
  const style = doc.createElement("style");
  style.dataset.matrixlabHalo = HALO_VERSION;
  style.textContent = `
@font-face{font-family:"MATRIXLAB HALO Mono";src:url("${FONT_URL}") format("woff2");font-style:normal;font-weight:400 700;font-display:swap}
.matrixlab-halo{position:relative;isolation:isolate;box-sizing:border-box;overflow:visible;border:1px solid ${HALO_TOKENS.staticBorder};border-radius:16px;background:${HALO_TOKENS.body};box-shadow:0 18px 44px ${HALO_TOKENS.depthShadow},0 0 26px ${HALO_TOKENS.ambientShadow};color:${HALO_TOKENS.primaryText};font-family:"MATRIXLAB HALO Mono","Cascadia Mono","Cascadia Code",Consolas,"Liberation Mono",monospace;font-size:13px;line-height:19.5px;font-style:normal;font-variant-ligatures:none;font-variant-numeric:tabular-nums}
.matrixlab-halo-host{position:relative;box-sizing:border-box;display:flex;width:100%;height:100%;min-width:0;min-height:0;flex-direction:column;align-items:stretch;justify-content:flex-start;overflow:visible}
.matrixlab-halo-host>.matrixlab-halo{min-width:0;flex:0 0 auto}
.matrixlab-halo.matrixlab-halo--unified{background:transparent;border-color:transparent;box-shadow:none}
.matrixlab-halo-node-body{background-color:${HALO_TOKENS.body}!important;box-shadow:inset 0 0 0 1px ${HALO_TOKENS.staticBorder};overflow:visible}
.matrixlab-halo-node-body>.flex:first-child{position:relative;z-index:3}
.matrixlab-halo *{box-sizing:border-box;font-family:inherit;font-variant-ligatures:inherit;font-variant-numeric:inherit}
.matrixlab-halo__rain,.matrixlab-halo__edge{position:absolute;display:block;pointer-events:none;user-select:none;aria-hidden:true}
.matrixlab-halo__rain{z-index:1;inset:0;width:100%;height:100%;border-radius:15px;overflow:hidden}
.matrixlab-halo__edge{z-index:5;inset:-12px;width:calc(100% + 24px);height:calc(100% + 24px)}
.matrixlab-halo__content{position:relative;z-index:2;display:flex;flex-direction:column;align-items:stretch;gap:8px;margin:0 7px;padding:18px 16px}
.matrixlab-halo__field{position:relative;z-index:2;display:flex;min-width:0;flex-wrap:wrap;min-height:38px;align-items:center;justify-content:space-between;gap:12px;padding:8px 10px;border:1px solid ${HALO_TOKENS.fieldBorder};border-radius:9px;background:${HALO_TOKENS.parameterField};color:${HALO_TOKENS.parameterLabel};transition:background-color 150ms ease,border-color 150ms ease}
.matrixlab-halo__saved-images button,.matrixlab-halo__saved-images a{font-size:11px;padding:6px 8px;border:1px solid ${HALO_TOKENS.fieldBorder};border-radius:6px;background:${HALO_TOKENS.parameterField};color:${HALO_TOKENS.parameterLabel};text-decoration:none;cursor:pointer}
.matrixlab-halo__saved-images button:disabled{opacity:.4;cursor:default}
.matrixlab-halo__saved-images button:focus-visible,.matrixlab-halo__saved-images a:focus-visible{outline:2px solid ${HALO_TOKENS.focus};outline-offset:2px}
.matrixlab-halo__field:hover{border-color:${HALO_TOKENS.fieldHoverBorder}}
.matrixlab-halo__field[data-linked="true"]{border-color:${HALO_TOKENS.linkedBorder};background:${HALO_TOKENS.linkedSurface};color:${HALO_TOKENS.linkedText}}
.matrixlab-halo__field label{min-width:0;flex:1 1 108px;overflow-wrap:anywhere;font-size:11px;line-height:16.5px}
.matrixlab-halo__field input,.matrixlab-halo__field select{box-sizing:border-box;min-width:0;width:108px;flex:0 1 108px;max-width:100%;min-height:24px;border:1px solid ${HALO_TOKENS.fieldBorder};border-radius:6px;background:${HALO_TOKENS.linkedSurface};color:${HALO_TOKENS.primaryText};text-align:right}
.matrixlab-halo__field input[type="checkbox"]{width:18px;flex:0 0 18px}
.matrixlab-halo__field select,.matrixlab-halo__field select option{direction:ltr;text-align:left;text-align-last:left}
.matrixlab-halo__field input:focus-visible,.matrixlab-halo__field select:focus-visible,.matrixlab-halo__field button:focus-visible{outline:2px solid ${HALO_TOKENS.focus};outline-offset:4px}
.matrixlab-halo__field input:disabled,.matrixlab-halo__field select:disabled{color:${HALO_TOKENS.linkedText};opacity:1}
.matrixlab-halo__linked{font-size:9px;line-height:13.5px;letter-spacing:1px;color:${HALO_TOKENS.linkedText}}
.matrixlab-halo [data-halo-effect]{position:relative;overflow:hidden}
.matrixlab-halo [data-halo-effect="primary"]:active:not(:disabled){transform:translateY(1px)}
.matrixlab-halo__ripple,.matrixlab-halo__shimmer{position:absolute;pointer-events:none;user-select:none}
.matrixlab-halo__ripple{z-index:0;width:12px;height:12px;border-radius:50%;background:#ABFFCB66;transform:translate(-50%,-50%)}
.matrixlab-halo__shimmer{z-index:0;inset:-50%;background:${HALO_TOKENS.shimmer};transform:translateX(-80%) rotate(25deg)}
`;
  doc.head.appendChild(style);
  doc[STYLE_KEY] = style;
}

let atlas = null;
function glyphAtlas(doc) {
  if (atlas) return atlas;
  const canvas = doc.createElement("canvas");
  canvas.width = HALO_GLYPHS.length * HALO_TOKENS.glyphCell;
  canvas.height = HALO_TOKENS.glyphCell;
  const ctx = canvas.getContext("2d");
  ctx.font = HALO_TOKENS.glyphFont;
  ctx.textBaseline = "top";
  ctx.fillStyle = HALO_TOKENS.green;
  for (let index = 0; index < HALO_GLYPHS.length; index += 1) {
    ctx.fillText(HALO_GLYPHS[index], index * HALO_TOKENS.glyphCell + HALO_TOKENS.glyphOffsetX, HALO_TOKENS.glyphOffsetY);
  }
  return (atlas = { canvas, cell: HALO_TOKENS.glyphCell });
}

function logicalSize(root) {
  const width = Number(root.offsetWidth) || Number(root.clientWidth);
  const height = Number(root.offsetHeight) || Number(root.clientHeight);
  if (width > 0 && height > 0) return { width, height };
  const rect = root.getBoundingClientRect?.();
  return {
    width: Math.max(1, width || Number(rect?.width) || 1),
    height: Math.max(1, height || Number(rect?.height) || 1),
  };
}

function resizeCanvas(canvas, cssWidth, cssHeight, dpr) {
  const width = Math.max(1, Math.round(cssWidth * dpr));
  const height = Math.max(1, Math.round(cssHeight * dpr));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
}

function defaultVisible(root, doc) {
  if (root.isConnected === false || root.hidden || doc?.hidden) return false;
  const rect = root.getBoundingClientRect?.();
  if (!rect) return true;
  const view = doc?.defaultView || globalThis;
  const width = Number(view.innerWidth) || Number(doc?.documentElement?.clientWidth) || Infinity;
  const height = Number(view.innerHeight) || Number(doc?.documentElement?.clientHeight) || Infinity;
  return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.bottom > 0 && rect.left < width && rect.top < height;
}

function installInteractionEffects(root, isEligible) {
  const active = new Map();
  const listeners = [];
  const add = (name, listener, options) => {
    root.addEventListener?.(name, listener, options);
    listeners.push([name, listener, options]);
  };
  const contains = (ancestor, item) => {
    for (let cursor = item; cursor; cursor = cursor.parentElement || cursor.parentNode) {
      if (cursor === ancestor) return true;
      if (cursor === root) break;
    }
    return false;
  };
  const effectButton = (target) => {
    for (let cursor = target; cursor; cursor = cursor.parentElement || cursor.parentNode) {
      if (cursor?.dataset?.haloEffect) return cursor;
      if (cursor === root) break;
    }
    return null;
  };
  const stateFor = (button) => {
    if (!active.has(button)) active.set(button, { pointer: false, focus: false, ripple: null, shimmer: null });
    return active.get(button);
  };
  const removeEffect = (state, name) => {
    const effect = state[name];
    if (!effect) return;
    effect.animation?.cancel?.();
    effect.element?.remove?.();
    state[name] = null;
  };
  const permitted = (button) => Boolean(button && !button.disabled && button.getAttribute?.("aria-disabled") !== "true" && isEligible());
  const animate = (element, frames, timing) => typeof element.animate === "function"
    ? element.animate(frames, timing)
    : null;

  const ripple = (button, event) => {
    if (!permitted(button)) return;
    const state = stateFor(button);
    removeEffect(state, "ripple");
    const rect = button.getBoundingClientRect?.() || { left: 0, top: 0, width: 0, height: 0 };
    const keyboard = event?.detail === 0 || !Number.isFinite(event?.clientX) || !Number.isFinite(event?.clientY);
    const logical = logicalSize(button);
    const scaleX = logical.width / (Number(rect.width) || logical.width);
    const scaleY = logical.height / (Number(rect.height) || logical.height);
    const x = keyboard ? logical.width / 2 : (Number(event.clientX) - Number(rect.left)) * scaleX;
    const y = keyboard ? logical.height / 2 : (Number(event.clientY) - Number(rect.top)) * scaleY;
    const element = root.ownerDocument?.createElement?.("span") || globalThis.document?.createElement?.("span");
    if (!element) return;
    element.className = "matrixlab-halo__ripple";
    element.setAttribute?.("aria-hidden", "true");
    element.style.left = `${x}px`;
    element.style.top = `${y}px`;
    button.appendChild?.(element);
    const animation = animate(element, [
      { width: "12px", height: "12px", opacity: 1 },
      { width: "170px", height: "170px", opacity: 0 },
    ], { duration: 450, easing: "ease-out", fill: "forwards" });
    state.ripple = { element, animation };
    if (animation) animation.onfinish = () => {
      if (state.ripple?.element === element) state.ripple = null;
      element.remove?.();
    };
    else { element.remove?.(); state.ripple = null; }
  };

  const shimmer = (button) => {
    if (!permitted(button) || button.dataset.haloEffect !== "primary") return;
    const state = stateFor(button);
    removeEffect(state, "shimmer");
    const element = root.ownerDocument?.createElement?.("span") || globalThis.document?.createElement?.("span");
    if (!element) return;
    element.className = "matrixlab-halo__shimmer";
    element.setAttribute?.("aria-hidden", "true");
    button.appendChild?.(element);
    const animation = animate(element, [
      { transform: "translateX(-80%) rotate(25deg)" },
      { transform: "translateX(80%) rotate(25deg)" },
    ], { duration: 600, easing: "ease-out", fill: "forwards" });
    state.shimmer = { element, animation };
    if (animation) animation.onfinish = () => {
      if (state.shimmer?.element === element) state.shimmer = null;
      element.remove?.();
    };
    else { element.remove?.(); state.shimmer = null; }
  };

  add("click", (event) => ripple(effectButton(event.target), event), true);
  add("pointerover", (event) => {
    const button = effectButton(event.target);
    if (!button || contains(button, event.relatedTarget)) return;
    const state = stateFor(button);
    const wasEntered = state.pointer || state.focus;
    state.pointer = true;
    if (!wasEntered) shimmer(button);
  });
  add("pointerout", (event) => {
    const button = effectButton(event.target);
    if (!button || contains(button, event.relatedTarget)) return;
    stateFor(button).pointer = false;
  });
  add("focusin", (event) => {
    const button = effectButton(event.target);
    if (!button) return;
    const state = stateFor(button);
    const wasEntered = state.pointer || state.focus;
    state.focus = true;
    if (!wasEntered) shimmer(button);
  });
  add("focusout", (event) => {
    const button = effectButton(event.target);
    if (!button || contains(button, event.relatedTarget)) return;
    stateFor(button).focus = false;
  });

  return () => {
    for (const [name, listener, options] of listeners) root.removeEventListener?.(name, listener, options);
    for (const state of active.values()) {
      removeEffect(state, "ripple");
      removeEffect(state, "shimmer");
    }
    active.clear();
  };
}

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

/**
 * Temporarily hide the owned DOM widget while native ghost placement owns the
 * pointer. Classic keeps a separate same-sized DOM overlay, so making the
 * surface itself pointer-transparent is not sufficient.
 */
export function bindHaloGhostPlacement(root, node, canvas) {
  if (!root || !node || !canvas?.addEventListener) return () => {};

  let snapshot = null;

  const findPresentation = () =>
    (node.widgets || []).find((widget) => {
      const element = widget?.element;
      return element === root || element?.contains?.(root);
    }) || null;

  const restore = () => {
    if (!snapshot) return;
    const { widget, hadHidden, hidden, options, hadOptions, hadOptionHidden, optionHidden } = snapshot;
    if (hadHidden) widget.hidden = hidden;
    else delete widget.hidden;
    if (hadOptionHidden) options.hidden = optionHidden;
    else delete options.hidden;
    if (!hadOptions) delete widget.options;
    snapshot = null;
    node.setDirtyCanvas?.(true, true);
  };

  const setHidden = (active) => {
    if (!active) {
      restore();
      return;
    }
    const widget = findPresentation();
    if (!widget || snapshot?.widget === widget) return;
    restore();
    const hadHidden = hasOwn(widget, "hidden");
    const hidden = widget.hidden;
    const hadOptions = hasOwn(widget, "options");
    const options = widget.options || (widget.options = {});
    const hadOptionHidden = hasOwn(options, "hidden");
    const optionHidden = options.hidden;
    snapshot = { widget, hadHidden, hidden, hadOptions, options, hadOptionHidden, optionHidden };
    widget.hidden = true;
    options.hidden = true;
    node.setDirtyCanvas?.(true, true);
  };

  const onGhostPlacement = (event) => {
    const detail = event?.detail;
    if (!detail || String(detail.nodeId) !== String(node.id)) return;
    setHidden(detail.active === true);
  };

  canvas.addEventListener("litegraph:ghost-placement", onGhostPlacement);
  if (node.flags?.ghost) setHidden(true);

  return () => {
    canvas.removeEventListener?.("litegraph:ghost-placement", onGhostPlacement);
    restore();
  };
}

// Decoration spans the native socket body without participating in widget layout.
// The Vue selectors below are feature-detected integration points, not public APIs.
export function bindHaloNodeHousing(root, node, app, rainCanvas) {
  let body = null;
  const previous = node.onDrawBackground;
  const draw = function (ctx) {
    ctx.save();
    try {
      if (!this.flags?.collapsed) {
        ctx.beginPath();
        roundedRect(ctx, 0, 0, this.size[0], this.size[1], HALO_TOKENS.outerRadius);
        ctx.fillStyle = HALO_TOKENS.body;
        ctx.fill();
        // Classic sockets are painted after this hook. Composite rain here so
        // the native labels and connection dots stay above the decoration.
        if (app?.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") !== true && rainCanvas?.width > 0 && rainCanvas?.height > 0) {
          ctx.save();
          ctx.clip();
          ctx.drawImage(rainCanvas, 0, 0, this.size[0], this.size[1]);
          ctx.restore();
        }
        ctx.strokeStyle = HALO_TOKENS.staticBorder;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      return previous?.apply(this, arguments);
    } finally { ctx.restore(); }
  };
  node.onDrawBackground = draw;
  function clearBody() {
    body?.classList?.remove("matrixlab-halo-node-body");
    body = null;
  }
  return {
    bounds() {
      const rect = root.getBoundingClientRect?.();
      let housing;
      const vue = app?.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") === true;
      if (vue) {
        const outer = root.closest?.("[data-node-id]");
        const candidate = outer?.querySelector?.(`[data-testid="node-body-${node.id}"]`);
        if (body !== candidate) { clearBody(); body = candidate; }
        body?.classList?.add("matrixlab-halo-node-body");
        housing = body?.getBoundingClientRect?.();
      } else {
        clearBody();
        const canvas = app?.canvas;
        const viewport = canvas?.canvas?.getBoundingClientRect?.();
        const scale = Number(canvas?.ds?.scale);
        const offset = canvas?.ds?.offset;
        if (viewport && offset && scale > 0) housing = {
          left: viewport.left + (node.pos[0] + offset[0]) * scale,
          top: viewport.top + (node.pos[1] + offset[1]) * scale,
          width: node.size[0] * scale, height: node.size[1] * scale,
        };
      }
      const scale = rect?.width / root.offsetWidth;
      const valid = rect?.width > 0 && housing?.width > 0 && housing?.height > 0 && scale > 0 && !node.flags?.collapsed;
      if (valid) root.classList?.add("matrixlab-halo--unified");
      else root.classList?.remove("matrixlab-halo--unified");
      if (!valid) return null;
      return { left: (housing.left - rect.left) / scale, top: (housing.top - rect.top) / scale,
        width: housing.width / scale, height: housing.height / scale };
    },
    destroy() {
      clearBody();
      root.classList?.remove("matrixlab-halo--unified");
      if (node.onDrawBackground === draw) node.onDrawBackground = previous;
      node.setDirtyCanvas?.(true, true);
    },
  };
}

export function mountHaloSurface(root, node, options = {}) {
  if (!root || typeof root.appendChild !== "function") return null;
  if (root[SURFACE_KEY]) return root[SURFACE_KEY];
  const doc = browserDocument(root, options.document);
  if (!doc?.createElement) return null;
  installStyle(doc);
  const profile = options.profile === "execution" ? "execution" : "ui";
  const rainCanvas = doc.createElement("canvas");
  const edgeCanvas = doc.createElement("canvas");
  rainCanvas.className = "matrixlab-halo__rain";
  edgeCanvas.className = "matrixlab-halo__edge";
  rainCanvas.setAttribute?.("aria-hidden", "true");
  edgeCanvas.setAttribute?.("aria-hidden", "true");
  root.classList?.add("matrixlab-halo", `matrixlab-halo--${profile}`);
  root.dataset.haloVersion = HALO_VERSION;
  root.prepend?.(edgeCanvas);
  root.prepend?.(rainCanvas);

  const media = options.matchMedia?.("(prefers-reduced-motion: reduce)") ||
    doc.defaultView?.matchMedia?.("(prefers-reduced-motion: reduce)") ||
    globalThis.matchMedia?.("(prefers-reduced-motion: reduce)");
  const scheduler = options.scheduler || getHaloScheduler(options.schedulerOptions);
  if (options.app) registerHaloMotionSetting(options.app, { scheduler, global: options.settingGlobal });
  const random = options.random || Math.random;
  let destroyed = false;
  let inViewport = true;
  let drops = [];
  let unregister = null;
  let resizeObserver = null;
  let intersectionObserver = null;
  let removeInteractionEffects = null;
  const removeGhostPlacement = bindHaloGhostPlacement(root, node, options.app?.canvas?.canvas);
  const removeResizeInteraction = bindHaloResizeInteraction(doc, node);
  const housing = bindHaloNodeHousing(root, node, options.app, rainCanvas);
  const getZoom = options.getZoom || (() => Number(options.app?.canvas?.ds?.scale) || 1);

  function isEligible() {
    const locallyEnabled = typeof options.motionEnabled === "function" ? options.motionEnabled() : options.motionEnabled !== false;
    return !destroyed && locallyEnabled && scheduler.isMotionEnabled() && media?.matches !== true &&
      !node?.flags?.collapsed && getZoom() > HALO_TOKENS.zoomMotionCutoff && inViewport &&
      (options.isVisible ? options.isVisible(root, node) : defaultVisible(root, doc));
  }

  function prepare(canvas, width, height, overscan = 0) {
    const dpr = Math.min(Number(options.devicePixelRatio || doc.defaultView?.devicePixelRatio || globalThis.devicePixelRatio) || 1, HALO_TOKENS.maxDevicePixelRatio);
    resizeCanvas(canvas, width + overscan * 2, height + overscan * 2, dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform?.(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width + overscan * 2, height + overscan * 2);
    return ctx;
  }

  function ensureDrops(width, height) {
    const count = Math.max(3, Math.floor(width / HALO_TOKENS.columnPitch));
    if (drops.length === count) return;
    drops = Array.from({ length: count }, (_, column) => ({
      x: column * HALO_TOKENS.columnPitch + 4,
      y: random() * (height - HALO_TOKENS.restartMinY) + HALO_TOKENS.restartMinY,
      speed: HALO_TOKENS.minSpeedPerSecond + random() * (HALO_TOKENS.maxSpeedPerSecond - HALO_TOKENS.minSpeedPerSecond),
      glyph: Math.floor(random() * HALO_GLYPHS.length),
    }));
  }

  function drawFrame(timeSeconds, elapsedSeconds) {
    if (destroyed) return;
    const content = logicalSize(root);
    const bounds = housing.bounds();
    const frame = bounds || { left: 0, top: 0, ...content };
    const { width, height } = frame;
    ensureDrops(width, height);
    const rain = prepare(rainCanvas, width, height);
    rainCanvas.style.left = `${frame.left}px`;
    rainCanvas.style.top = `${frame.top}px`;
    rainCanvas.style.right = "auto";
    rainCanvas.style.bottom = "auto";
    const classicHousing = Boolean(bounds) && options.app?.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") !== true;
    rainCanvas.style.visibility = classicHousing ? "hidden" : "visible";
    const cache = glyphAtlas(doc);
    rain.save();
    rain.beginPath();
    roundedRect(rain, 0, 0, width, height, 15);
    rain.clip();
    for (const drop of drops) {
      drop.y += drop.speed * Math.min(HALO_TOKENS.maxTimeStepSeconds, Math.max(0, elapsedSeconds || 0));
      if (drop.y > height + HALO_TOKENS.wrapOvershoot) drop.y = HALO_TOKENS.restartMinY + random() * (HALO_TOKENS.restartMaxY - HALO_TOKENS.restartMinY);
      for (let trail = 0; trail < HALO_TOKENS.trailLength; trail += 1) {
        const y = drop.y - trail * HALO_TOKENS.trailPitch;
        if (y < -HALO_TOKENS.glyphCell || y > height) continue;
        rain.globalAlpha = Math.max(0, HALO_TOKENS.trailAlpha - trail * HALO_TOKENS.trailAlphaStep);
        rain.drawImage(cache.canvas, ((drop.glyph + trail) % HALO_GLYPHS.length) * cache.cell, 0, cache.cell, cache.cell, drop.x, y, cache.cell, cache.cell);
      }
    }
    rain.restore();
    const edge = prepare(edgeCanvas, frame.width, frame.height, HALO_TOKENS.canvasOverscan);
    edgeCanvas.style.left = `${frame.left - HALO_TOKENS.canvasOverscan}px`;
    edgeCanvas.style.top = `${frame.top - HALO_TOKENS.canvasOverscan}px`;
    edgeCanvas.style.right = "auto";
    edgeCanvas.style.bottom = "auto";
    edge.save();
    edge.translate(HALO_TOKENS.canvasOverscan, HALO_TOKENS.canvasOverscan);
    edge.beginPath();
    const halfEdge = HALO_TOKENS.edgeWidth / 2;
    roundedRect(edge, halfEdge, halfEdge, Math.max(0, frame.width - HALO_TOKENS.edgeWidth), Math.max(0, frame.height - HALO_TOKENS.edgeWidth), HALO_TOKENS.outerRadius);
    edge.strokeStyle = HALO_TOKENS.green;
    edge.shadowColor = HALO_TOKENS.green;
    edge.shadowBlur = HALO_TOKENS.edgeShadowBlur;
    edge.lineWidth = HALO_TOKENS.edgeWidth;
    edge.setLineDash(HALO_TOKENS.edgeDash);
    edge.lineDashOffset = -((timeSeconds * HALO_TOKENS.edgeSpeed) % HALO_TOKENS.edgeDashCycle);
    edge.stroke();
    edge.restore();
    if (classicHousing) node.setDirtyCanvas?.(true, false);
  }

  function renderStatic() {
    drawFrame((globalThis.performance?.now?.() || Date.now()) / 1000, 0);
  }

  const wake = () => scheduler.wake();
  if (typeof options.ResizeObserver === "function" || typeof globalThis.ResizeObserver === "function") {
    const Observer = options.ResizeObserver || globalThis.ResizeObserver;
    resizeObserver = new Observer(() => { renderStatic(); wake(); });
    resizeObserver.observe(root);
  }
  if (typeof options.IntersectionObserver === "function" || typeof globalThis.IntersectionObserver === "function") {
    const Observer = options.IntersectionObserver || globalThis.IntersectionObserver;
    intersectionObserver = new Observer((entries) => {
      inViewport = entries.some((entry) => entry.target === root && entry.isIntersecting);
      wake();
    });
    intersectionObserver.observe(root);
  }
  media?.addEventListener?.("change", wake);
  unregister = scheduler.register({ isEligible, drawFrame });
  removeInteractionEffects = installInteractionEffects(root, isEligible);

  const control = {
    version: HALO_VERSION,
    profile,
    root,
    contentRoot: root,
    node,
    scheduler,
    isEligible,
    renderStatic,
    setMotionEnabled(enabled) {
      options.motionEnabled = enabled !== false;
      if (options.motionEnabled) wake();
      else renderStatic();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      unregister?.();
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      media?.removeEventListener?.("change", wake);
      removeInteractionEffects?.();
      removeGhostPlacement();
      removeResizeInteraction();
      housing.destroy();
      rainCanvas.remove?.();
      edgeCanvas.remove?.();
      root.classList?.remove("matrixlab-halo", `matrixlab-halo--${profile}`);
      delete root.dataset.haloVersion;
      if (root[SURFACE_KEY] === control) delete root[SURFACE_KEY];
    },
  };
  root[SURFACE_KEY] = control;
  renderStatic();
  return control;
}

function linkedInput(node, widgetName) {
  return (node.inputs || []).some((input) =>
    (input?.name === widgetName || input?.widget?.name === widgetName) && input.link != null
  );
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

function restoreWidgets(snapshots) {
  for (const state of snapshots) {
    state.widget.draw = state.draw;
    state.widget.computeSize = state.computeSize;
    if (state.widget.callback === state.watchedCallback) state.widget.callback = state.callback;
    if (state.hadOptions) {
      state.widget.options = state.options;
      if (state.widget.options) state.widget.options.hidden = state.hidden;
    } else {
      delete state.widget.options;
    }
  }
}

function hideWidgets(snapshots) {
  for (const { widget } of snapshots) {
    widget.options ||= {};
    widget.options.hidden = true;
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
  }
}

function numericKind(widget) {
  const declared = [
    widget?.inputData?.[0],
    widget?.options?.socket,
    widget?.options?.inputType,
    widget?.options?.type,
  ].find((value) => value === "INT" || value === "FLOAT");
  if (declared) return declared;
  const precision = Number(widget?.options?.precision);
  return Number.isFinite(precision) && precision === 0 ? "INT" : "FLOAT";
}

function finiteOption(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function numericInputStep(widget) {
  const preferred = finiteOption(widget?.options?.step2);
  if (preferred !== null && preferred > 0) return preferred;
  const legacy = finiteOption(widget?.options?.step);
  // Legacy LiteGraph stores number-widget drag scale at ten times the real
  // increment. ComfyUI's step2 is already the exact spinner increment.
  if (legacy !== null && legacy > 0) return legacy / 10;
  return numericKind(widget) === "INT" ? 1 : "any";
}

function coerceValue(widget, raw) {
  if (typeof widget.value === "boolean") return { accepted: true, value: Boolean(raw) };
  if (typeof widget.value === "number") {
    if (typeof raw === "string" && raw.trim() === "") return { accepted: false, value: widget.value };
    let value = Number(raw);
    if (!Number.isFinite(value)) return { accepted: false, value: widget.value };
    const kind = numericKind(widget);
    if (kind === "INT" && !Number.isSafeInteger(value)) return { accepted: false, value: widget.value };
    const rawMin = finiteOption(widget.options?.min);
    const rawMax = finiteOption(widget.options?.max);
    const min = kind === "INT" && rawMin !== null ? Math.ceil(rawMin) : rawMin;
    const max = kind === "INT" && rawMax !== null ? Math.floor(rawMax) : rawMax;
    if (min !== null && max !== null && min > max) return { accepted: false, value: widget.value };
    if (min !== null) value = Math.max(min, value);
    if (max !== null) value = Math.min(max, value);
    return { accepted: true, value };
  }
  return { accepted: true, value: String(raw) };
}

function createWidgetField(doc, node, widget, options) {
  const field = doc.createElement("div");
  field.className = "matrixlab-halo__field";
  const label = doc.createElement("label");
  label.textContent = widget.label || widget.name;
  const inputId = `matrixlab-halo-${node.id ?? "node"}-${widget.name}`;
  label.htmlFor = inputId;
  let control;
  const choices = () => {
    const values = typeof widget.options?.values === "function"
      ? widget.options.values.call(widget) : widget.options?.values;
    return Array.isArray(values) ? values : Array.isArray(widget.options) ? widget.options : null;
  };
  let renderedChoices = null;
  if (choices()) {
    control = doc.createElement("select");
  } else {
    control = doc.createElement("input");
    control.type = typeof widget.value === "boolean" ? "checkbox" : typeof widget.value === "number" ? "number" : "text";
    if (finiteOption(widget.options?.min) !== null) control.min = String(widget.options.min);
    if (finiteOption(widget.options?.max) !== null) control.max = String(widget.options.max);
    if (typeof widget.value === "number") control.step = String(numericInputStep(widget));
  }
  control.id = inputId;
  const render = () => {
    if (control.tagName === "SELECT") {
      const values = (choices() || []).map(String);
      if (!renderedChoices || values.length !== renderedChoices.length || values.some((value, index) => value !== renderedChoices[index])) {
        control.replaceChildren(...values.map(value => {
          const option = doc.createElement("option");
          option.value = option.textContent = value;
          return option;
        }));
        renderedChoices = values;
      }
    }
    const linked = linkedInput(node, widget.name);
    field.dataset.linked = String(linked);
    control.disabled = linked;
    if (control.type === "checkbox") control.checked = Boolean(widget.value);
    else control.value = String(widget.value ?? "");
    marker.hidden = !linked;
  };
  const commit = (event) => {
    if (linkedInput(node, widget.name)) { render(); return; }
    const raw = control.type === "checkbox" ? control.checked : control.value;
    const result = coerceValue(widget, raw);
    if (!result.accepted) { render(); return; }
    const next = result.value;
    widget.value = next;
    const position = options.getCallbackPosition?.(event, node) ?? node.pos;
    widget.callback?.call(widget, next, options.app?.canvas || options.canvas || null, node, position, event);
    render();
  };
  control.addEventListener("change", commit);
  const marker = doc.createElement("span");
  marker.className = "matrixlab-halo__linked";
  marker.textContent = "LINKED";
  field.append(label, control, marker);
  render();
  return { field, render, destroy: () => control.removeEventListener("change", commit) };
}

// Keep output history in ComfyUI; own only the presentation of this node's saved images.
export function mountHaloSavedImages(node, root, options = {}) {
  const doc = root.ownerDocument;
  const section = doc.createElement("section");
  section.className = "matrixlab-halo__saved-images";
  Object.assign(section.style, { display: "flex", flexDirection: "column", flex: "1 1 180px", minHeight: "180px", minWidth: "0", gap: "8px", position: "relative", zIndex: "2" });
  const viewport = doc.createElement("div");
  Object.assign(viewport.style, { position: "relative", flex: "1 1 auto", minHeight: "130px", overflow: "hidden", borderRadius: "9px", background: "rgba(0,0,0,0.25)" });
  const status = doc.createElement("span");
  status.textContent = "Saved image appears here";
  const toolbar = doc.createElement("div");
  Object.assign(toolbar.style, { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" });
  const previous = doc.createElement("button"); previous.type = "button"; previous.textContent = "Previous";
  const next = doc.createElement("button"); next.type = "button"; next.textContent = "Next";
  const open = doc.createElement("a"); open.textContent = "Open image"; open.target = "_blank"; open.rel = "noopener noreferrer";
  const download = doc.createElement("a"); download.textContent = "Download";
  toolbar.append(previous, status, next, open, download);
  section.append(viewport, toolbar); root.appendChild(section);
  let descriptors = [], selected = 0, pendingImage = null, revision = 0, destroyed = false;
  let lastImages = null;
  const previousHidden = node.hideOutputImages;
  let ownsHidden = false;
  const nativeWidgets = new Map();
  const syncNativeWidgets = () => {
    for (const widget of node.widgets || []) {
      if (widget.name !== "$$canvas-image-preview") continue;
      if (ownsHidden && !nativeWidgets.has(widget)) {
        nativeWidgets.set(widget, { hidden: widget.hidden, computeLayoutSize: widget.computeLayoutSize });
        widget.hidden = true;
        widget.computeLayoutSize = () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 });
      }
    }
    if (!ownsHidden) {
      for (const [widget, state] of nativeWidgets) { widget.hidden = state.hidden; widget.computeLayoutSize = state.computeLayoutSize; }
      nativeWidgets.clear();
    }
  };
  const originalBackground = node.onDrawBackground;
  const background = function (...args) {
    try { return originalBackground?.apply(this, args); }
    finally { update(options.app?.nodeOutputs?.[node.id]); syncNativeWidgets(); }
  };
  node.onDrawBackground = background;
  const hideNative = (hidden) => {
    if (hidden) { node.hideOutputImages = true; ownsHidden = true; }
    else { if (ownsHidden && node.hideOutputImages === true) node.hideOutputImages = previousHidden; ownsHidden = false; }
    syncNativeWidgets();
    node.setDirtyCanvas?.(true, true);
  };
  const cancelLoad = () => {
    if (pendingImage) { pendingImage.onload = null; pendingImage.onerror = null; pendingImage = null; }
  };
  const show = () => {
    cancelLoad();
    const token = ++revision;
    previous.disabled = selected <= 0; next.disabled = selected >= descriptors.length - 1;
    open.hidden = download.hidden = true;
    viewport.replaceChildren();
    if (!descriptors.length) { status.textContent = "Saved image appears here"; hideNative(false); return; }
    const descriptor = descriptors[selected];
    const query = new URLSearchParams({ filename: descriptor.filename, subfolder: descriptor.subfolder || "", type: descriptor.type || "output" });
    const url = options.imageURL?.(query) ?? `${options.app?.api?.apiURL?.("/view") || "./view"}?${query}`;
    hideNative(true);
    open.href = download.href = url; download.download = descriptor.filename;
    open.hidden = download.hidden = false;
    const image = doc.createElement("img"); pendingImage = image;
    image.alt = descriptor.filename;
    Object.assign(image.style, { position: "absolute", inset: "0", width: "100%", height: "100%", objectFit: "contain" });
    status.textContent = `Loading ${selected + 1} / ${descriptors.length}`;
    image.onload = () => {
      if (destroyed || revision !== token) return;
      cancelLoad(); viewport.replaceChildren(image);
      status.textContent = `${selected + 1} / ${descriptors.length}`;

    };
    image.onerror = () => {
      if (destroyed || revision !== token) return;
      cancelLoad(); status.textContent = "Preview unavailable";
    };
    image.src = url;
  };
  const update = (output) => {
    if (destroyed || !output || !Object.prototype.hasOwnProperty.call(output, "images")) return;
    if (output.images === lastImages) return;
    lastImages = output.images;
    descriptors = Array.isArray(output.images) ? output.images.filter(item => item && typeof item.filename === "string" && item.filename) : [];
    selected = 0; show();
  };
  const goPrevious = () => { if (selected > 0) { selected--; show(); } };
  const goNext = () => { if (selected + 1 < descriptors.length) { selected++; show(); } };
  previous.addEventListener("click", goPrevious); next.addEventListener("click", goNext);
  show();
  return { section, update, destroy() {
    destroyed = true; revision++; cancelLoad(); hideNative(false);
    if (node.onDrawBackground === background) node.onDrawBackground = originalBackground;
    previous.removeEventListener("click", goPrevious); next.removeEventListener("click", goNext); section.remove();
  } };
}

function mountHaloPrimitiveNode(node, options = {}, allowedIds = EXECUTION_IDS, profile = "execution") {
  const nodeType = node?.comfyClass || node?.type;
  if (!allowedIds.has(nodeType) || !node || typeof node.addDOMWidget !== "function") return null;
  if (node[EXECUTION_KEY]) return node[EXECUTION_KEY];
  const doc = options.document || globalThis.document;
  if (!doc?.createElement) return null;
  const canonicalWidgets = [...(node.widgets || [])].filter(widget => widget.name !== "$$canvas-image-preview");
  const snapshots = canonicalWidgets.map(snapshotWidget);
  const beforeMount = new Set(node.widgets || []);
  const root = doc.createElement("div");
  root.className = "matrixlab-halo__content";
  const host = createHaloWidgetHost(root, doc);
  if (!host) return null;
  const presentationName = profile === "execution" ? "matrixlab_halo_execution_ui" : "matrixlab_halo_utility_ui";
  const fields = canonicalWidgets.filter((widget) => widget?.name).map((widget) => createWidgetField(doc, node, widget, options));
  for (const field of fields) root.appendChild(field.field);
  const savedImages = nodeType === "MATRIX_SaveClean" ? mountHaloSavedImages(node, root, options) : null;
  if (savedImages) Object.assign(root.style, { flex: "1 1 auto", minHeight: "0" });
  const contentMinimum = () => savedImages
    ? Math.max(fields.length * 46 + 36, ...fields.map(({ field }) => (Number(field.offsetTop) || 0) + (Number(field.offsetHeight) || 0) + 18)) + 188
    : measureHaloContentHeight(root, fields.length * 46 + 36);
  let presentation = null;
  let halo = null;
  let destroyed = false;
  let resizeTimer = null;
  let sizingObserver = null;
  let previousResize = node.onResize;
  let wrappedResize = null;
  let previousRemoved = node.onRemoved;
  let wrappedRemoved = null;
  let measuredHorizontalChrome = null;
  const refreshHooks = [];

  const removePresentation = () => {
    if (!Array.isArray(node.widgets)) return;
    for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
      const widget = node.widgets[index];
      if (!beforeMount.has(widget) && (widget === presentation || widget?.element === host || widget?.name === presentationName)) {
        node.widgets.splice(index, 1);
      }
    }
  };
  const rollback = () => {
    clearTimeout(resizeTimer);
    sizingObserver?.disconnect();
    fields.forEach((field) => field.destroy());
    for (const { name, previous, wrapped } of refreshHooks) {
      if (node[name] === wrapped) node[name] = previous;
    }
    restoreWidgets(snapshots);
    halo?.destroy();
    savedImages?.destroy();
    removePresentation();
    root.remove?.();
    host.remove?.();
  };

  try {
    presentation = node.addDOMWidget(presentationName, "matrixlab-halo", host, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => haloWidgetLayoutHeight(contentMinimum(), presentation),
      getHeight: () => haloWidgetLayoutHeight(contentMinimum(), presentation),
      afterResize: () => fields.forEach((field) => field.render()),
    });
    if (!presentation) throw new Error("ComfyUI did not create the HALO DOM widget");
    presentation.serialize = false;
    presentation.options ||= {};
    presentation.options.serialize = false;
    halo = mountHaloSurface(root, node, { ...options, profile });
    if (!halo) throw new Error("HALO surface mount failed");
    hideWidgets(snapshots);
  } catch (error) {
    rollback();
    options.onError?.(error);
    return null;
  }

  const minimumSize = () => {
    if (destroyed) return;
    const currentWidth = Number(node.size?.[0]) || 0;
    const currentHeight = Number(node.size?.[1]) || 0;
    const minimumWidth = profile === "execution" ? HALO_TOKENS.executionMinWidth : HALO_TOKENS.uiMinWidth;
    const suppliedChrome = options.getRendererChrome?.(node, presentation);
    const suppliedHorizontalChrome = typeof suppliedChrome === "object"
      ? Number(suppliedChrome?.horizontal) || 0
      : Number(options.rendererChromeX) || 0;
    if (measuredHorizontalChrome == null) {
      measuredHorizontalChrome = measureHaloHorizontalChrome(root, currentWidth, {
        horizontal: suppliedHorizontalChrome,
      });
    }
    const horizontalChrome = measuredHorizontalChrome ?? 0;
    const width = Math.max(
      currentWidth,
      minimumWidth + horizontalChrome,
    );
    const contentHeight = contentMinimum();
    const requiredHeight = haloMinimumNodeHeight(node, contentHeight,
      suppliedChrome ?? options.rendererChrome);
    const height = savedImages ? Math.max(currentHeight, requiredHeight) : requiredHeight;
    if (width === currentWidth && height === currentHeight) return;
    const size = [width, height];
    setHaloNodeSize(node, size);
  };
  const scheduleMinimum = () => {
    if (destroyed) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { resizeTimer = null; savedImages?.update(options.app?.nodeOutputs?.[node.id]); minimumSize(); fields.forEach((field) => field.render()); halo.renderStatic(); }, 0);
  };
  // Canonical callbacks own state; the DOM is refreshed only after they finish.
  const refresh = () => {
    if (destroyed) return;
    fields.forEach((field) => field.render());
    scheduleMinimum();
  };
  for (const state of snapshots) {
    state.watchedCallback = function (...args) {
      try { return state.callback?.apply(this, args); }
      finally { refresh(); }
    };
    state.widget.callback = state.watchedCallback;
  }
  for (const name of ["onConnectionsChange", "onConfigure"]) {
    const previous = node[name];
    const wrapped = function (...args) {
      try { return previous?.apply(this, args); }
      finally { savedImages?.update(options.app?.nodeOutputs?.[node.id]); refresh(); }
    };
    refreshHooks.push({ name, previous, wrapped });
    node[name] = wrapped;
  }
  if (savedImages) {
    const previous = node.onExecuted;
    const wrapped = function (output, ...args) {
      try { return previous?.call(this, output, ...args); }
      finally { savedImages.update(output); refresh(); }
    };
    refreshHooks.push({ name: "onExecuted", previous, wrapped });
    node.onExecuted = wrapped;
    savedImages.update(options.app?.nodeOutputs?.[node.id]);
  }
  wrappedResize = function (...args) {
    const result = previousResize?.apply(this, args);
    scheduleMinimum();
    return result;
  };
  node.onResize = wrappedResize;
  const SizingObserver = doc.defaultView?.ResizeObserver || globalThis.ResizeObserver;
  if (typeof SizingObserver === "function") {
    sizingObserver = new SizingObserver(scheduleMinimum);
    sizingObserver.observe(root);
  }

  const control = {
    node,
    host,
    root,
    contentRoot: root,
    presentation,
    halo,
    canonicalWidgets,
    render: () => fields.forEach((field) => field.render()),
    destroy() {
      if (destroyed) return;
      destroyed = true;
      rollback();
      if (node.onResize === wrappedResize) node.onResize = previousResize;
      if (node.onRemoved === wrappedRemoved) node.onRemoved = previousRemoved;
      if (node[EXECUTION_KEY] === control) delete node[EXECUTION_KEY];
    },
  };
  node[EXECUTION_KEY] = control;
  wrappedRemoved = function (...args) {
    control.destroy();
    return previousRemoved?.apply(this, args);
  };
  node.onRemoved = wrappedRemoved;
  scheduleMinimum();
  return control;
}

export function mountHaloExecutionNode(node, options = {}) {
  return mountHaloPrimitiveNode(node, options, EXECUTION_IDS, "execution");
}

export function mountHaloUtilityNode(node, options = {}) {
  return mountHaloPrimitiveNode(node, options, UTILITY_IDS, "ui");
}
