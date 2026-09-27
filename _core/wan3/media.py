"""Explicit, loss-aware local media preparation for signed WaveSpeed uploads."""

from __future__ import annotations

import hashlib
import io
import math
import os
import struct
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MediaError(ValueError):
    pass


@dataclass
class PreparedMedia:
    path: Path
    filename: str
    content_type: str
    sha256: str
    size: int
    duration: float | None = None
    width: int | None = None
    height: int | None = None

    def cleanup(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def flatten_reference_images(slots: list[Any], *, maximum: int = 10) -> list[Any]:
    """Expand IMAGE batches in socket order then batch order without resizing."""
    expanded: list[Any] = []
    for slot_index, image in enumerate(slots, start=1):
        shape = getattr(image, "shape", None)
        if shape is None:
            try:
                import numpy as np
                shape = np.asarray(image).shape
            except ImportError as exc:
                raise MediaError("Image upload needs ComfyUI's existing NumPy package.") from exc
        if len(shape) != 4:
            raise MediaError(f"reference_image_{slot_index:02d} must use IMAGE shape [B,H,W,C].")
        count = int(shape[0])
        if count < 1:
            raise MediaError(f"reference_image_{slot_index:02d} contains an empty image batch.")
        if len(expanded) + count > maximum:
            raise MediaError(f"At most {maximum} reference images may be supplied after flattening IMAGE batches.")
        expanded.extend(image[index:index + 1] for index in range(count))
    return expanded


def _digest_file(path: Path, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise MediaError(f"Prepared media exceeds the {max_bytes:,}-byte local upload ceiling.")
            digest.update(chunk)
    return digest.hexdigest(), size


def prepare_image(image: Any, *, slot: str, max_bytes: int = 200 * 1024 * 1024) -> PreparedMedia:
    """Encode one Comfy IMAGE [B,H,W,C] to lossless full-size PNG; never pick batch item zero."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise MediaError("Image upload needs ComfyUI's existing NumPy and Pillow packages.") from exc
    array = image.detach().to("cpu").numpy() if hasattr(image, "detach") else np.asarray(image)
    if array.ndim != 4 or array.shape[0] != 1:
        raise MediaError(f"{slot} must contain exactly one image (IMAGE shape [1,H,W,C]); batches are not truncated.")
    if array.shape[1] < 1 or array.shape[2] < 1 or array.shape[3] not in (3, 4):
        raise MediaError(f"{slot} must have positive dimensions and RGB or RGBA channels.")
    if not np.isfinite(array).all() or float(array.min()) < 0 or float(array.max()) > 1:
        raise MediaError(f"{slot} contains non-finite or out-of-range pixels; expected finite IMAGE values from 0 to 1.")
    pixels = np.rint(array[0] * 255).astype(np.uint8)
    image_obj = Image.fromarray(pixels, "RGB" if pixels.shape[-1] == 3 else "RGBA")
    buffer = io.BytesIO()
    image_obj.save(buffer, format="PNG", optimize=False)
    return _write_bytes(buffer.getvalue(), f"{slot}.png", "image/png", max_bytes)


def prepare_audio(audio: Any, *, slot: str, max_bytes: int = 200 * 1024 * 1024) -> PreparedMedia:
    """Encode Comfy AUDIO to PCM16 WAV without changing channels, rate, or duration."""
    try:
        import numpy as np
    except ImportError as exc:
        raise MediaError("Audio upload needs ComfyUI's existing NumPy package.") from exc
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise MediaError(f"{slot} is not a standard Comfy AUDIO object.")
    waveform = audio["waveform"]
    samples = waveform.detach().to("cpu").numpy() if hasattr(waveform, "detach") else np.asarray(waveform)
    if samples.ndim == 3:
        if samples.shape[0] != 1:
            raise MediaError(f"{slot} must contain one audio batch; batches are not truncated.")
        samples = samples[0]
    if samples.ndim != 2 or samples.shape[0] < 1 or samples.shape[1] < 1:
        raise MediaError(f"{slot} must use standard [channels, samples] audio layout.")
    if not isinstance(audio["sample_rate"], int) or isinstance(audio["sample_rate"], bool) or audio["sample_rate"] <= 0:
        raise MediaError(f"{slot} has an invalid sample rate.")
    if not np.isfinite(samples).all() or float(samples.min()) < -1 or float(samples.max()) > 1:
        raise MediaError(f"{slot} has non-finite or out-of-range samples; expected finite values from -1 to 1.")
    pcm = np.rint(samples.T * 32767).astype("<i2", copy=False)
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(int(samples.shape[0]))
        writer.setsampwidth(2)
        writer.setframerate(audio["sample_rate"])
        writer.writeframes(pcm.tobytes())
    return _write_bytes(output.getvalue(), f"{slot}.wav", "audio/wav", max_bytes, duration=samples.shape[1] / audio["sample_rate"])


def prepare_video(video: Any, *, slot: str, allow_materialization: bool, max_bytes: int = 200 * 1024 * 1024) -> PreparedMedia:
    """Materialize a native VIDEO using its effective save protocol after explicit consent."""
    if not allow_materialization:
        raise MediaError("Preparing a native VIDEO may encode or materialize it. Enable the explicit video-materialization option before uploading.")
    if not callable(getattr(video, "save_to", None)) or not callable(getattr(video, "get_active_trim_window", None)):
        raise MediaError(f"{slot} must implement ComfyUI's native VIDEO protocol.")
    try:
        import av
    except ImportError as exc:
        raise MediaError("Video upload needs PyAV from the active ComfyUI environment.") from exc
    fd, name = tempfile.mkstemp(prefix="matrix-wan3-", suffix=".mp4")
    os.close(fd)
    path = Path(name)
    try:
        # Always use save_to: get_stream_source can expose a backing file that bypasses a trim/crop.
        video.save_to(str(path))
        if not path.is_file():
            raise MediaError(f"{slot} did not produce a local video file.")
        digest, size = _digest_file(path, max_bytes)
        with av.open(str(path), mode="r") as container:
            streams = [stream for stream in container.streams if stream.type == "video"]
            if len(streams) != 1:
                raise MediaError(f"{slot} must contain exactly one video stream.")
            stream = streams[0]
            duration = float(stream.duration * stream.time_base) if stream.duration and stream.time_base else float(container.duration / av.time_base) if container.duration else None
            width, height = int(stream.width), int(stream.height)
        if duration is None or not math.isfinite(duration) or duration <= 0:
            raise MediaError(f"{slot} has no reliable positive duration metadata.")
        return PreparedMedia(path, f"{slot}.mp4", "video/mp4", digest, size, duration, width, height)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _write_bytes(data: bytes, filename: str, content_type: str, max_bytes: int, *, duration: float | None = None) -> PreparedMedia:
    if len(data) > max_bytes:
        raise MediaError(f"Prepared media exceeds the {max_bytes:,}-byte local upload ceiling.")
    fd, name = tempfile.mkstemp(prefix="matrix-wan3-", suffix=Path(filename).suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    return PreparedMedia(Path(name), filename, content_type, hashlib.sha256(data).hexdigest(), len(data), duration)
