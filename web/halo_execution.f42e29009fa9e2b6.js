import { app } from "../../scripts/app.js";
import { mountHaloExecutionNode } from "./halo.1b57eadf6f0e9a67.mjs";
const ids = new Set(["MATRIXSpectralSampler", "MATRIX_CameraLook", "MATRIX_CropTailPaste", "MATRIX_EyeMask", "MATRIX_LatentTail", "MATRIX_OutputStage", "MATRIX_Renoise", "MATRIX_SaveClean", "MATRIX_SkinMask"]);
const attach = (node) => {
  if (ids.has(node.comfyClass || node.type)) mountHaloExecutionNode(node, {app});
};
app.registerExtension({
  name: "matrixlab.halo.execution.fcdefaebf9909c7c",
  nodeCreated: attach, loadedGraphNode: attach,
});
