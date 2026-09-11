import { app } from "../../scripts/app.js";
import { mountHaloExecutionNode } from "./halo.84c0c1fe41e5e23f.mjs";
const ids = new Set(["MATRIX_CropTailPaste", "MATRIX_EyeMask", "MATRIX_LatentTail", "MATRIX_MetadataKiller", "MATRIX_OutputStage", "MATRIX_PhotoFinisher", "MATRIX_SkinMask", "MATRIX_SpectralSampler", "MATRIXSpectralSampler"]);
const attach = (node) => {
  if (ids.has(node.comfyClass || node.type)) mountHaloExecutionNode(node, {app});
};
app.registerExtension({
  name: "matrixlab.halo.execution.cc9ad13f358e89d9",
  nodeCreated: attach, loadedGraphNode: attach,
});
