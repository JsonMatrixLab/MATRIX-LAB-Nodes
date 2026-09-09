# Detector and segmentation setup

MATRIX LAB NODES does not bundle, download, or install model weights or optional detector runtimes. Package import can succeed while `MATRIX_SkinMask` and `MATRIX_EyeMask` remain unavailable. Acquire each asset from its cited source only after reviewing its license and suitability for your use, then verify the exact SHA-256 before execution.

Paths below are relative to the active ComfyUI root. Do not rename a different model to match an expected filename; the runtime checks both logical identity and content hash.

## Required assets

| Used by | ComfyUI-relative path | Expected SHA-256 | Source | License evidence and limit |
| --- | --- | --- | --- | --- |
| Eye Mask detection | `models/ultralytics/bbox/Eyeful_v2-Individual.pt` | `278fee230b1be01cfb8c47c3f9ad7118c7aa33149a2249b80cea4da236361fbe` | [Pinned Hugging Face file](https://huggingface.co/Bryan32/Adetailer/blob/701874bdc5ebc0db00543eb867dd0e778db93d1c/Eyeful_v2-Individual.pt) | A license for this weight has not been established from the retained source evidence. Review before use or redistribution. |
| Eye Mask SAM refinement | `models/sams/sam_vit_b_01ec64.pth` | `ec2df62732614e57411cdcf32a23ffdf28910380d03139ee0f4fcbe91eb8c912` | [Official model file](https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth) | The [Segment Anything repository](https://github.com/facebookresearch/segment-anything) publishes Apache-2.0 terms. Confirm those terms cover your intended use of the weight. |
| Skin Mask person gate | `models/onnx/rembg/u2net_human_seg.onnx` | `01eb6a29a5c4d8edb30b56adad9bb3a2a0535338e480724a213e0acfd2d1c73c` | [Pinned Hugging Face file](https://huggingface.co/jellybox/u2net-human-seg/resolve/736b768145e597134968bde9ace5bf8fd19ffa8c/u2net_human_seg.onnx) | The host and [upstream U-2-Net repository](https://github.com/xuebinqin/U-2-Net) identify Apache-2.0 terms; the conversion lineage has not been fully established here. |
| Skin Mask human parts | `models/onnx/human-parts/deeplabv3p-resnet50-human.onnx` | `a6e823a82da10ba24c29adfb544130684568c46bfac865e215bbace3b4035a71` | [Hugging Face file](https://huggingface.co/Metal3d/deeplabv3p-resnet50-human/blob/main/deeplabv3p-resnet50-human.onnx) | The host model card uses CC0 but questions the underlying model license. Treat the underlying license as unresolved. |

SAM is needed only when Eye Mask's `sam_refine` is enabled. The person-segmentation weight is needed when Skin Mask's `person_gate` is enabled. Skin-part inference still needs the human-parts weight whenever any body-part switch is enabled.

## Verify the files

From the active ComfyUI root, calculate SHA-256 without opening or modifying the weights.

PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\models\ultralytics\bbox\Eyeful_v2-Individual.pt
Get-FileHash -Algorithm SHA256 -LiteralPath .\models\sams\sam_vit_b_01ec64.pth
Get-FileHash -Algorithm SHA256 -LiteralPath .\models\onnx\rembg\u2net_human_seg.onnx
Get-FileHash -Algorithm SHA256 -LiteralPath .\models\onnx\human-parts\deeplabv3p-resnet50-human.onnx
```

Linux or macOS shell:

```bash
sha256sum models/ultralytics/bbox/Eyeful_v2-Individual.pt
sha256sum models/sams/sam_vit_b_01ec64.pth
sha256sum models/onnx/rembg/u2net_human_seg.onnx
sha256sum models/onnx/human-parts/deeplabv3p-resnet50-human.onnx
```

Every result must match the table exactly. Stop on a missing or mismatched file. Do not bypass the registry, substitute a similarly named model, or edit `_core/runtime-assets.json`.

## Optional runtime packages

The detector paths may need `onnxruntime`, `ultralytics`, and `segment-anything` in the same Python environment that launches ComfyUI. Development validation observed versions 1.29.0, 8.4.142, and 1.0 respectively; these observations are not minimum supported versions or installation pins. Inspect the environment and package requirements before making changes, especially where Torch/CUDA could be affected.

Ultralytics publishes AGPL-3.0 and Enterprise licensing options in its [official licensing guidance](https://github.com/ultralytics/ultralytics/blob/main/docs/en/help/contributing.md). Which terms apply to this proprietary pack and a particular deployment has not been established by this release documentation. Review the current upstream terms before installation or distribution.

After the exact assets and compatible runtimes are present, restart ComfyUI and test each mask node with non-sensitive local media. A successful import or hash check alone does not prove inference compatibility, output quality, or license suitability.
