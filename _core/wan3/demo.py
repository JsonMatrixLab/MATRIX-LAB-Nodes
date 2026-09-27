"""Deterministic, local-only demonstration provider."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction


def demo_frames(settings: dict, *, width: int = 64, height: int = 64, count: int = 8):
    """Return deterministic RGB frames without network calls, uploads, or filesystem writes."""
    import numpy as np

    material = json.dumps(settings, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    seed = hashlib.sha256(material).digest()
    frames = np.zeros((count, height, width, 3), dtype=np.float32)
    base = np.frombuffer(seed[:3], dtype=np.uint8).astype(np.float32) / 255.0
    x_axis = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y_axis = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    for frame_index in range(count):
        phase = (frame_index / max(1, count - 1))
        for channel in range(3):
            plane = base[channel] * (0.25 + 0.55 * x_axis) + ((channel + 1) / 5.0) * (0.15 + 0.55 * y_axis)
            frames[frame_index, :, :, channel] = np.clip(plane + phase * (0.12 if channel == frame_index % 3 else 0.02), 0.0, 1.0)
    return frames


def demo_video(settings: dict):
    """Create a native Comfy VIDEO in memory. This branch never writes to ComfyUI storage."""
    import torch
    from comfy_api.latest import InputImpl, Types

    frames = torch.from_numpy(demo_frames(settings))
    components = Types.VideoComponents(images=frames, audio=None, frame_rate=Fraction(4, 1))
    return InputImpl.VideoFromComponents(components, bit_depth=8, color_space="sRGB")
