import { app } from "../../scripts/app.js";
import { mountHaloExecutionNode } from "./halo.dd87986d74909bc0.mjs";
const ids = new Set(["MATRIX_CropTailPaste", "MATRIX_EyeMask", "MATRIX_LatentTail", "MATRIX_MetadataKiller", "MATRIX_OutputStage", "MATRIX_PhotoFinisher", "MATRIX_SkinMask", "MATRIX_SpectralSampler"]);
const attach = (node) => {
  if (ids.has(node.comfyClass || node.type)) mountHaloExecutionNode(node, {app});
};
app.registerExtension({
  name: "matrixlab.halo.execution.cc9ad13f358e89d9",
  nodeCreated: attach, loadedGraphNode: attach,
});
