import { isVueNodesMode } from "./renderer.2c53217d2a7c4360.mjs";

const HEADER = "#0a150a", BODY = "#050a05", ACCENT = "#00ff41", TITLE = "#39ff7a";
const DASH = [22, 46], STROKE = 3, BLUR = 8, PERIOD = 1700, OFFSET = 68, RADIUS = 9, OUTSET = 3;
const KEY = Symbol.for("matrix.flat"), HOOK = Symbol.for("matrix.flat.hooked");
const COLOR = Symbol.for("matrix.flat.color"), BGCOLOR = Symbol.for("matrix.flat.bgcolor");

export function installFlat(app, nodeIds) {
  const state = globalThis[KEY] ||= {ids:new Set(), apps:new Set(), timer:null, observer:null};
  nodeIds.forEach((id) => state.ids.add(id)); state.apps.add(app);
  const reduce = () => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const nodeType = (node) => node?.comfyClass || node?.type;
  const eligible = (node, owner = app) => !isVueNodesMode() && !node?.flags?.collapsed && !reduce()
    && document.visibilityState === "visible" && owner.canvas?.visible_nodes?.includes(node);
  const tick = () => {
    const active = [...state.apps].filter((owner) => (owner.canvas?.graph?._nodes || []).some((node) =>
      state.ids.has(nodeType(node)) && eligible(node, owner)));
    if (!active.length) { clearInterval(state.timer); state.timer = null; return; }
    active.forEach((owner) => owner.canvas?.setDirty?.(true, true));
  };
  const start = (node) => { if (!state.timer && eligible(node)) state.timer = setInterval(tick, 34); };
  state.decorate ||= (root, node) => {
    const active = state.ids.has(nodeType(node));
    root.classList.toggle("matrix-flat", active);
    root.classList.toggle("matrix-flat-collapsed", active && !!node?.flags?.collapsed);
    let svg = root.querySelector(":scope > svg.matrix-flat-border");
    if (!active) { svg?.remove(); return; }
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.classList.add("matrix-flat-border"); svg.setAttribute("aria-hidden", "true");
      svg.innerHTML = `<rect x="1.5" y="1.5" width="calc(100% - 3px)" height="calc(100% - 3px)" rx="${RADIUS}"/>`;
      root.append(svg);
    }
  };
  state.scan ||= () => document.querySelectorAll("[data-node-id]").forEach((root) => {
    const raw = root.dataset.nodeId;
    const node = [...state.apps].map((owner) => owner.canvas?.graph).map((graph) =>
      graph?.getNodeById?.(raw) || (/^-?\d+$/.test(raw) ? graph?.getNodeById?.(Number(raw)) : null)).find(Boolean);
    state.decorate(root, node);
  });
  const setup = () => {
    if (!document.getElementById("matrix-flat-style")) {
      const style = document.createElement("style"); style.id = "matrix-flat-style";
      style.textContent = `
.matrix-flat .bg-node-component-header-surface{background-color:${HEADER}!important;--component-node-background:${BODY}!important}
.matrix-flat .lg-node-header{color:${TITLE}}
.matrix-flat-border{position:absolute;pointer-events:none;z-index:2;top:-3px;left:-3px;width:calc(100% + 6px);height:calc(100% + 6px);overflow:visible}
.matrix-flat-border rect{fill:none;stroke:${ACCENT};stroke-width:${STROKE};stroke-dasharray:${DASH.join(" ")};filter:drop-shadow(0 0 ${BLUR}px ${ACCENT});animation:matrix-flat-dash ${PERIOD}ms linear infinite}
@keyframes matrix-flat-dash{to{stroke-dashoffset:-${OFFSET}}}
.matrix-flat-collapsed .matrix-flat-border rect{animation:none}
@media (prefers-reduced-motion: reduce){.matrix-flat-border rect{animation:none}}
:root{--matrix-flat-header:${HEADER};--matrix-flat-body:${BODY};--matrix-flat-accent:${ACCENT};--matrix-flat-title:${TITLE};--matrix-flat-line:${ACCENT}59}
.matrix-flat-btn,.matrix-flat-select,.matrix-flat-slot,.matrix-flat-strip,.matrix-flat-track{box-sizing:border-box;border:1px solid var(--matrix-flat-line);border-radius:6px;background:var(--matrix-flat-body);color:var(--matrix-flat-title);font:inherit;font-size:12px}
.matrix-flat-btn,.matrix-flat-select{background:var(--matrix-flat-header);padding:3px 8px;cursor:pointer}
.matrix-flat-btn:hover,.matrix-flat-select:hover,.matrix-flat-slot:hover{border-color:var(--matrix-flat-accent)}
.matrix-flat-btn:disabled,.matrix-flat-select:disabled{opacity:.45;cursor:default}
.matrix-flat-btn:focus-visible,.matrix-flat-select:focus-visible,.matrix-flat-slot:focus-visible{outline:2px solid var(--matrix-flat-accent);outline-offset:1px}
.matrix-flat-slot{display:flex;align-items:center;justify-content:center;overflow:hidden;border-style:dashed;color:var(--matrix-flat-accent)}
.matrix-flat-slot>img,.matrix-flat-slot>video{width:100%;height:100%;object-fit:cover}
.matrix-flat-strip{display:flex;gap:4px;padding:4px;overflow-x:auto}`;
      document.head.append(style);
    }
    if (!state.observer) { state.observer = new MutationObserver(state.scan); state.observer.observe(document, {childList:true, subtree:true}); }
    state.scan();
  };
  const beforeRegisterNodeDef = (type, data) => {
    if (!state.ids.has(data?.name || type?.comfyClass || type?.type) || type.prototype[HOOK]) return;
    const proto = type.prototype, originalSerialize = proto.serialize, originalDraw = proto.onDrawForeground;
    Object.defineProperty(proto, HOOK, {value:true});
    Object.defineProperties(proto, {
      color: {configurable:true, get(){ return this[COLOR] ?? HEADER; }, set(value){ this[COLOR] = value; }},
      bgcolor: {configurable:true, get(){ return this[BGCOLOR] ?? BODY; }, set(value){ this[BGCOLOR] = value; }},
    });
    type.title_text_color = TITLE;
    proto.serialize = function(...args) {
      const value = originalSerialize?.apply(this, args) || {};
      if (value.color === HEADER) delete value.color; if (value.bgcolor === BODY) delete value.bgcolor;
      return value;
    };
    proto.onDrawForeground = function(ctx, ...args) {
      originalDraw?.call(this, ctx, ...args); start(this);
      const title = globalThis.LiteGraph?.NODE_TITLE_HEIGHT || 30, collapsed = this.flags?.collapsed;
      const width = collapsed ? (this._collapsed_width ?? globalThis.LiteGraph?.NODE_COLLAPSED_WIDTH ?? this.size[0]) : this.size[0];
      ctx.save(); ctx.beginPath(); ctx.roundRect(-OUTSET, -title-OUTSET, width+OUTSET*2,
        (collapsed ? title : this.size[1]+title)+OUTSET*2, RADIUS);
      ctx.setLineDash(DASH); ctx.lineDashOffset = collapsed || reduce() ? 0 : -(performance.now() % PERIOD) * OFFSET / PERIOD;
      ctx.strokeStyle = ACCENT; ctx.lineWidth = STROKE; ctx.shadowColor = ACCENT; ctx.shadowBlur = BLUR;
      ctx.stroke(); ctx.restore();
    };
  };
  return {setup, beforeRegisterNodeDef};
}
