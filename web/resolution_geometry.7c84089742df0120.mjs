export const ASPECT_RATIOS = Object.freeze(["1:1", "9:16", "3:4"]);
export const RESOLUTION_TIERS = Object.freeze(["1K", "2K", "4K Progressive"]);

const PLAN_TABLE = Object.freeze({
  "1:1|1K": [2048, 2048, 2048, 2048, 1024, 1024, "1.0"],
  "9:16|1K": [1152, 2048, 1152, 2048, 576, 1024, "1.0"],
  "3:4|1K": [1536, 2048, 1536, 2048, 768, 1024, "1.0"],
  "1:1|2K": [2048, 2048, 2048, 2048, 2048, 2048, "1.0"],
  "9:16|2K": [1152, 2048, 1152, 2048, 1152, 2048, "1.0"],
  "3:4|2K": [1536, 2048, 1536, 2048, 1536, 2048, "1.0"],
  "1:1|4K Progressive": [2048, 2048, 4096, 4096, 4096, 4096, "0.5,1.0"],
  "9:16|4K Progressive": [1152, 2048, 2304, 4096, 2304, 4096, "0.5,1.0"],
  "3:4|4K Progressive": [1536, 2048, 3072, 4096, 3072, 4096, "0.5,1.0"],
});

export function resolveResolutionGeometry(state) {
  if (!state || !ASPECT_RATIOS.includes(state.aspect_ratio)) {
    throw new Error(`Unsupported aspect ratio: ${state?.aspect_ratio}`);
  }
  if (!RESOLUTION_TIERS.includes(state.resolution_tier)) {
    throw new Error(`Unsupported resolution tier: ${state?.resolution_tier}`);
  }
  const row = PLAN_TABLE[`${state.aspect_ratio}|${state.resolution_tier}`];
  if (!row) throw new Error("Resolution plan is missing");
  const [generationWidth, generationHeight, detailWidth, detailHeight, deliveryWidth, deliveryHeight, samplerScales] = row;
  return { generationWidth, generationHeight, detailWidth, detailHeight, deliveryWidth, deliveryHeight, samplerScales };
}

export function calculatePlan(state) {
  const geometry = resolveResolutionGeometry(state);
  const diagnosticTier = state.resolution_tier === "4K Progressive" ? "4K" : state.resolution_tier;
  return {
    ...geometry,
    renderWidth: geometry.detailWidth,
    renderHeight: geometry.detailHeight,
    outputWidth: geometry.deliveryWidth,
    outputHeight: geometry.deliveryHeight,
    plan: `aspect=${state.aspect_ratio};tier=${diagnosticTier};render=${geometry.detailWidth}x${geometry.detailHeight};output=${geometry.deliveryWidth}x${geometry.deliveryHeight};scales=${geometry.samplerScales}`,
  };
}
