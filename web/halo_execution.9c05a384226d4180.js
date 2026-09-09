import { app } from "../../scripts/app.js";
import { mountHaloExecutionNode } from "./halo.3bc35993e091e5c5.mjs";
const ids = new Set(["MATRIXSpectralSampler", "MATRIX_CropTailPaste", "MATRIX_EyeMask", "MATRIX_LatentTail", "MATRIX_OutputStage", "MATRIX_PhotoFinisher", "MATRIX_SaveClean", "MATRIX_SkinMask"]);
const attach = (node) => {
  if (ids.has(node.comfyClass || node.type)) mountHaloExecutionNode(node, {app});
};
app.registerExtension({
  name: "matrixlab.halo.execution.d5bdc09336581bf5",
  nodeCreated: attach, loadedGraphNode: attach,
});
