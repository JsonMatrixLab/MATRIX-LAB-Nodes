"""Purpose-built SCAIL-2 orchestration; native nodes own model execution."""
import math
import torch


def plan_frames(count):
    if type(count) is not int or not 1 <= count <= 16384:
        raise ValueError("frame_count must be an integer in 1..16384")
    aligned = 1 + 4 * ((count + 2) // 4)
    continuations = (max(aligned - 81, 0) + 75) // 76
    coverage = 81 + 76 * continuations if continuations else aligned
    return aligned, continuations, coverage


def _rgb(name, value):
    if not isinstance(value, torch.Tensor) or value.ndim != 4:
        raise ValueError(f"{name} must be a BHWC RGB tensor")
    if min(value.shape) < 1 or value.shape[-1] != 3 or not value.is_floating_point():
        raise ValueError(f"{name} must be nonempty floating RGB")
    if not torch.isfinite(value).all() or value.min() < 0 or value.max() > 1:
        raise ValueError(f"{name} must contain finite values in 0..1")


def run_windows(item, condition, sample, decode, interrupt=lambda: None):
    """Execute the same implementation with native or CPU-test adapters."""
    count = item["frame_count"]
    aligned, continuations, coverage = plan_frames(count)
    pose, mask = item["pose_video"], item["pose_video_mask"]
    ref, ref_mask = item["reference_image"], item["reference_image_mask"]
    for name, value in (("pose_video", pose), ("pose_video_mask", mask),
                        ("reference_image", ref), ("reference_image_mask", ref_mask)):
        _rgb(name, value)
    if pose.shape != mask.shape or pose.shape[0] != count:
        raise ValueError("pose and colored mask must have equal shapes and exactly frame_count frames")
    if ref.shape != ref_mask.shape:
        raise ValueError("reference image and colored mask shapes must match")
    width, height = item["width"], item["height"]
    if any(type(v) is not int or not 32 <= v <= 16384 or v % 32 for v in (width, height)):
        raise ValueError("width and height must be multiples of 32 in 32..16384")
    if type(item["replacement_mode"]) is not bool:
        raise ValueError("replacement_mode must be boolean")
    for name, lower, upper in (("seed", 0, 2**64-1), ("steps", 1, 10000)):
        value = item[name]
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError(f"invalid {name}")
    for name, lower, upper in (("cfg", 0, 100), ("denoise", 0, 1),
                                ("pose_strength", 0, 10), ("pose_start", 0, 1), ("pose_end", 0, 1)):
        value = item[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"invalid {name}")
    if item["pose_start"] > item["pose_end"]:
        raise ValueError("pose_start must not exceed pose_end")
    # Paired tail hold preserves every selected pose and mask, including arbitrary-N tails.
    if coverage > count:
        pose = torch.cat((pose, pose[-1:].expand(coverage-count, -1, -1, -1)))
        mask = torch.cat((mask, mask[-1:].expand(coverage-count, -1, -1, -1)))
    chunks, previous, offset = [], None, 0
    for index in range(continuations + 1):
        interrupt()
        length = 81 if continuations else aligned
        kwargs = {name: item[name] for name in (
            "positive", "negative", "vae", "width", "height", "pose_strength",
            "pose_start", "pose_end", "replacement_mode", "reference_image", "reference_image_mask")}
        if "clip_vision_output" in item:
            kwargs["clip_vision_output"] = item["clip_vision_output"]
        kwargs.update(length=length, batch_size=1, pose_video=pose, pose_video_mask=mask,
                      video_frame_offset=offset, previous_frame_count=5, previous_frames=previous)
        result = condition(**kwargs)
        positive, negative, latent, next_offset = tuple(result)
        expected_offset = offset + length - (5 if previous is not None else 0)
        if type(next_offset) is not int or next_offset != expected_offset:
            raise ValueError("native SCAIL offset disagrees with the 81/5/76 contract")
        # Native returned offset remains authoritative; never derive the next input from the loop index.
        offset = next_offset
        sampled = sample(model=item["model"], seed=item["seed"], steps=item["steps"], cfg=item["cfg"],
                         sampler_name=item["sampler_name"], scheduler=item["scheduler"],
                         positive=positive, negative=negative, latent_image=latent, denoise=item["denoise"])[0]
        images = decode(vae=item["vae"], samples=sampled)[0]
        if not isinstance(images, torch.Tensor) or images.shape != (length, height, width, 3):
            raise ValueError("native decode returned unexpected image count or geometry")
        # Retain decoded five-frame context before dropping it from the stitched timeline.
        previous = images[-5:].detach()
        chunks.append(images[5 if index else 0:].detach().cpu())
    images = torch.cat(chunks)[:count]
    if images.shape[0] != count:
        raise ValueError("stitched output does not contain exactly frame_count frames")
    return (images,)


def execute_utility_operation(item):
    from comfy_extras.nodes_scail import WanSCAILToVideo
    from nodes import KSampler, VAEDecode
    from comfy.model_management import throw_exception_if_processing_interrupted
    return run_windows(item, WanSCAILToVideo.execute, KSampler().sample, VAEDecode().decode,
                       throw_exception_if_processing_interrupted)


__all__ = ["plan_frames", "run_windows", "execute_utility_operation"]
