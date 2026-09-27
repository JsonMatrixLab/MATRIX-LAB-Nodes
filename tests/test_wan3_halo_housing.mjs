import assert from "node:assert/strict";
import test from "node:test";
import { HALO_TOKENS, haloWidgetLayoutHeight, mountHaloSurface } from "../web/halo.87ce22ea9cb20e75.mjs";

test("WAN shared HALO tokens and widget-height API match runtime expectations", () => {
  assert.equal(HALO_TOKENS.green, "#00FF41");
  assert.equal(HALO_TOKENS.fieldBorder, "#31543C");
  assert.equal(haloWidgetLayoutHeight(27, { margin: 10 }), 47);
  assert.equal(haloWidgetLayoutHeight(56, { margin: 8 }), 72);
});

test("WAN shared HALO surface API safely rejects an unavailable mount root", () => {
  assert.equal(mountHaloSurface(null, { size: [430, 1000] }), null);
  assert.equal(mountHaloSurface({}, { size: [430, 1000] }), null);
});
