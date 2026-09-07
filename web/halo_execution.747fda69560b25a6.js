import { app } from "../../scripts/app.js";
import { mountHaloExecutionNode } from "./halo.cdbfe5654df6eedc.mjs";
const ids = new Set(["MATRIXSpectralSampler", "MATRIX_CameraLook", "MATRIX_CropTailPaste", "MATRIX_EyeMask", "MATRIX_LatentTail", "MATRIX_OutputStage", "MATRIX_Renoise", "MATRIX_SaveClean", "MATRIX_SkinMask"]);
const attach = (node) => {
  if (ids.has(node.comfyClass || node.type)) mountHaloExecutionNode(node, {app});
};
app.registerExtension({
  name: "matrixlab.halo.execution.fcdefaebf9909c7c",
  nodeCreated: attach, loadedGraphNode: attach,
});
