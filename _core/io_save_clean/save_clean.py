"""Verified metadata-free JPEG and PNG output for ComfyUI IMAGE batches."""

from __future__ import annotations

import os
import re
import struct
import tempfile
import unicodedata
import uuid
import zlib
from pathlib import Path
from typing import Callable, Any

import torch
from PIL import Image


PathAllocator = Callable[[str, int, int], tuple[str, str, int, str, str]]
InterruptChecker = Callable[[], None]
Encoder = Callable[[Image.Image, str | os.PathLike[str], int], None]
Verifier = Callable[[str | os.PathLike[str]], bool]
MAX_COLLISION_RETRIES = 1000


def _default_path_allocator(prefix: str, width: int, height: int):
    import folder_paths

    return folder_paths.get_save_image_path(
        prefix, folder_paths.get_output_directory(), width, height
    )


def _default_interrupt_checker() -> None:
    from comfy.model_management import throw_exception_if_processing_interrupted

    throw_exception_if_processing_interrupted()


def _default_preview_directory() -> str:
    import folder_paths

    return folder_paths.get_temp_directory()


def _encode_jpeg(image: Image.Image, path: str | os.PathLike[str], quality: int) -> None:
    image.save(
        path,
        format="JPEG",
        quality=quality,
        subsampling=0,
        optimize=False,
        progressive=False,
    )


def _encode_png(image: Image.Image, path: str | os.PathLike[str], quality: int) -> None:
    del quality
    image.save(path, format="PNG", compress_level=4, optimize=False)


def _validate_prefix(filename_prefix: object) -> str:
    if not isinstance(filename_prefix, str):
        raise TypeError("filename_prefix must be a string")
    prefix = filename_prefix.strip()
    if not prefix:
        raise ValueError("filename_prefix must be non-empty after trimming")
    if len(prefix) > 128:
        raise ValueError("filename_prefix must contain at most 128 characters")
    if filename_prefix.endswith((".", " ")):
        raise ValueError("filename_prefix may not end with a dot or space")
    if any(ch in '<>:"/\\|?*' for ch in prefix):
        raise ValueError("filename_prefix contains a character forbidden in portable filenames")
    stem = prefix.split(".", 1)[0].rstrip(" .").upper()
    if stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
        raise ValueError("filename_prefix may not use a reserved Windows device name")
    if prefix in {".", ".."}:
        raise ValueError("filename_prefix may not be a path component")
    if "/" in prefix or "\\" in prefix or re.match(r"^[A-Za-z]:", prefix):
        raise ValueError("filename_prefix may not select a directory")
    if any(ch == "\x00" or unicodedata.category(ch) == "Cc" for ch in prefix):
        raise ValueError("filename_prefix may not contain control characters")
    return prefix


def _supported_dtypes() -> set[torch.dtype]:
    result = {torch.float16, torch.float32, torch.bfloat16}
    for name in ("float8_e4m3fn", "float8_e5m2"):
        dtype = getattr(torch, name, None)
        if dtype is not None:
            result.add(dtype)
    return result


def _validate_inputs(
    images: object, filename_prefix: object, format: object, quality: object
) -> tuple[torch.Tensor, str, str, int]:
    prefix = _validate_prefix(filename_prefix)
    if format not in {"JPEG", "PNG"}:
        raise ValueError("format must be exactly JPEG or PNG")
    if isinstance(quality, bool) or not isinstance(quality, int):
        raise TypeError("quality must be an integer")
    if not 1 <= quality <= 100:
        raise ValueError("quality must be between 1 and 100 inclusive")
    if not isinstance(images, torch.Tensor):
        raise TypeError("images must be a torch tensor")
    if images.ndim != 4:
        raise ValueError(f"images must have shape [B,H,W,C], received {list(images.shape)}")
    batch, height, width, channels = images.shape
    if batch < 1:
        raise ValueError("IMAGE batch must contain at least one frame")
    if height < 1 or width < 1:
        raise ValueError(f"IMAGE dimensions must be positive, received {list(images.shape)}")
    if channels not in (1, 3, 4):
        raise ValueError(f"unsupported IMAGE channel count, received {list(images.shape)}")
    if channels == 4 and format == "JPEG":
        raise ValueError("JPEG cannot preserve alpha channels; select PNG for RGBA images")
    if images.dtype not in _supported_dtypes():
        raise TypeError(f"unsupported IMAGE dtype: {images.dtype}")

    return images, prefix, format, quality


def _preflight_finite(images: torch.Tensor) -> None:
    # Check the entire invocation before allocation or publication, while keeping
    # additional tensor memory bounded to one CPU float32 frame.
    for frame in images:
        cpu_frame = frame.detach().to(device="cpu", dtype=torch.float32)
        if not bool(torch.isfinite(cpu_frame).all().item()):
            raise ValueError("IMAGE contains a non-finite sample")


def _frame_to_uint8(frame: torch.Tensor) -> torch.Tensor:
    cpu_float = frame.detach().to(device="cpu", dtype=torch.float32)
    return cpu_float.clamp(0.0, 1.0).mul(255.0).round().to(torch.uint8)


def _to_pillow(frame: torch.Tensor) -> Image.Image:
    pixels = _frame_to_uint8(frame).numpy()
    if pixels.shape[2] == 1:
        return Image.fromarray(pixels[:, :, 0], mode="L")
    if pixels.shape[2] == 4:
        return Image.fromarray(pixels, mode="RGBA")
    return Image.fromarray(pixels, mode="RGB")


def inspect_jpeg_privacy(payload: bytes) -> list[str]:
    """Return privacy-bearing JPEG marker findings; malformed input is a finding."""
    if len(payload) < 4 or payload[:2] != b"\xff\xd8":
        return ["not a JPEG container"]

    findings: list[str] = []
    position = 2
    in_scan = False
    while position < len(payload):
        marker_start = payload.find(b"\xff", position)
        if marker_start < 0 or marker_start + 1 >= len(payload):
            break
        code_position = marker_start + 1
        while code_position < len(payload) and payload[code_position] == 0xFF:
            code_position += 1
        if code_position >= len(payload):
            return findings + ["truncated JPEG marker"]
        marker = payload[code_position]
        if in_scan and marker == 0x00:
            position = code_position + 1
            continue
        if marker in range(0xD0, 0xD8):
            position = code_position + 1
            continue
        if marker == 0xD9:
            if code_position + 1 != len(payload):
                findings.append("JPEG has trailing data")
            return findings
        if marker == 0xE1:
            findings.append("APP1 EXIF/XMP marker")
        elif marker == 0xED:
            findings.append("APP13 IPTC/Photoshop marker")
        elif 0xE1 <= marker <= 0xEF:
            findings.append(f"APP{marker - 0xE0} application metadata marker")
        elif marker == 0xFE:
            findings.append("COM comment marker")
        if marker in (0xD8, 0x01):
            position = code_position + 1
            continue
        if code_position + 2 >= len(payload):
            return findings + ["truncated JPEG segment"]
        segment_length = int.from_bytes(payload[code_position + 1 : code_position + 3], "big")
        if segment_length < 2:
            return findings + ["invalid JPEG segment length"]
        segment_payload = payload[
            code_position + 3 : code_position + 1 + segment_length
        ]
        if marker == 0xE0 and not segment_payload.startswith((b"JFIF\x00", b"JFXX\x00")):
            findings.append("APP0 non-JFIF application marker")
        position = code_position + 1 + segment_length
        in_scan = marker == 0xDA
    return findings + ["JPEG has no end marker"]


def verify_clean_jpeg(path: str | os.PathLike[str]) -> bool:
    payload = Path(path).read_bytes()
    if inspect_jpeg_privacy(payload):
        return False
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.format != "JPEG" or len(image.getexif()) != 0:
            return False
        if not {"exif", "xmp", "comment", "icc_profile"}.isdisjoint(image.info):
            return False
    return True


def inspect_png_privacy(payload: bytes) -> list[str]:
    """Return unexpected PNG chunks or structural findings."""
    signature = b"\x89PNG\r\n\x1a\n"
    if not payload.startswith(signature):
        return ["not a PNG container"]

    findings: list[str] = []
    position = len(signature)
    saw_iend = False
    while position < len(payload):
        if position + 12 > len(payload):
            return findings + ["truncated PNG chunk"]
        length = struct.unpack(">I", payload[position : position + 4])[0]
        chunk_end = position + 12 + length
        if chunk_end > len(payload):
            return findings + ["truncated PNG chunk"]
        chunk_type = payload[position + 4 : position + 8]
        chunk_data = payload[position + 8 : position + 8 + length]
        expected_crc = struct.unpack(">I", payload[position + 8 + length : chunk_end])[0]
        observed_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if observed_crc != expected_crc:
            findings.append("PNG chunk CRC mismatch")
        if chunk_type not in {b"IHDR", b"IDAT", b"IEND"}:
            name = chunk_type.decode("ascii", errors="replace")
            findings.append(f"{name} metadata chunk")
        position = chunk_end
        if chunk_type == b"IEND":
            saw_iend = True
            if length != 0:
                findings.append("invalid PNG end chunk")
            if position != len(payload):
                findings.append("PNG has trailing data")
            break
    if not saw_iend:
        findings.append("PNG has no end chunk")
    return findings


def verify_clean_png(path: str | os.PathLike[str]) -> bool:
    payload = Path(path).read_bytes()
    if inspect_png_privacy(payload):
        return False
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.format != "PNG" or image.info:
            return False
    return True


def _publish_without_overwrite(temp_path: Path, final_path: Path) -> None:
    # A same-directory hard link is atomic and fails if the destination exists.
    os.link(temp_path, final_path)


def _verify_clean_preview(path: Path) -> bool:
    """Accept only static WebP pixel chunks, with an exact RIFF boundary."""
    payload = path.read_bytes()
    if len(payload) < 12 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        return False
    if int.from_bytes(payload[4:8], "little") + 8 != len(payload):
        return False
    position = 12
    while position < len(payload):
        if position + 8 > len(payload):
            return False
        kind = payload[position:position + 4]
        length = int.from_bytes(payload[position + 4:position + 8], "little")
        if kind not in {b"VP8 ", b"VP8L", b"VP8X", b"ALPH"}:
            return False
        end = position + 8 + length
        if end > len(payload):
            return False
        if kind == b"VP8X" and (length != 10 or payload[position + 8] & ~0x10):
            return False
        position = end + (length & 1)
    if position != len(payload):
        return False
    with Image.open(path) as image:
        image.load()
        return (image.format == "WEBP" and not image.is_animated
                and max(image.size) <= 1024 and min(image.size) > 0
                and not any(key in image.info for key in ("exif", "xmp", "icc_profile", "comment"))
                and not image.getexif())


def _save_preview(original: Path, preview_dir: str | os.PathLike[str]) -> dict[str, str]:
    # Decode the verified saved original, including JPEG encoding changes. The
    # preview therefore represents the delivered file rather than pre-encode pixels.
    with Image.open(original) as saved:
        saved.load()
        pixels = saved.convert("RGBA" if "A" in saved.getbands() else "RGB")
        pixels.info.clear()
        pixels.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        directory = Path(preview_dir)
        filename = f"matrix-preview-{uuid.uuid4().hex}.webp"
        handle, name = tempfile.mkstemp(prefix=".matrix-preview-", suffix=".tmp", dir=directory)
        os.close(handle)
        temporary = Path(name)
        try:
            pixels.save(temporary, format="WEBP", quality=85, method=2)
            if not _verify_clean_preview(temporary):
                raise RuntimeError("Preview metadata verification failed")
            _publish_without_overwrite(temporary, directory / filename)
        finally:
            temporary.unlink(missing_ok=True)
    return {"filename": filename, "subfolder": "", "type": "temp"}


def _report_partial_failure(error: BaseException, descriptors: list[dict[str, Any]], total: int) -> None:
    filenames = [item["filename"] for item in descriptors]
    message = f"Metadata Killer saved {len(filenames)} of {total} files before stopping"
    if filenames:
        message += ": " + ", ".join(filenames)
    # Python 3.10 has no BaseException.add_note. Diagnostic enrichment must
    # never replace the real save/cancellation failure on any supported runtime.
    add_note = getattr(error, "add_note", None)
    if callable(add_note):
        try:
            add_note(message)
        except Exception:
            pass
    try:
        error.matrix_published_files = tuple(filenames)
    except Exception:
        pass
    # Preserve the exception class (especially ComfyUI cancellation), while making
    # the ordinary runtime error message truthful about already published files.
    try:
        if isinstance(error, OSError) and isinstance(error.strerror, str):
            error.strerror = error.strerror + "; " + message
        elif len(error.args) == 1 and isinstance(error.args[0], str):
            error.args = (error.args[0] + "; " + message,)
    except Exception:
        pass


def save_clean_images(
    images: torch.Tensor,
    filename_prefix: str,
    format: str,
    quality: int,
    *,
    path_allocator: PathAllocator | None = None,
    interrupt_checker: InterruptChecker | None = None,
    jpeg_verifier: Verifier | None = None,
    png_verifier: Verifier | None = None,
    encoder: Encoder | None = None,
    preview_dir: str | os.PathLike[str] | Callable[[], str] | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    allocator = path_allocator or _default_path_allocator
    check_interrupted = interrupt_checker or _default_interrupt_checker
    images, prefix, output_format, quality = _validate_inputs(
        images, filename_prefix, format, quality
    )
    if output_format == "JPEG":
        verifier = jpeg_verifier or verify_clean_jpeg
        encode = encoder or _encode_jpeg
        extension = "jpg"
    else:
        verifier = png_verifier or verify_clean_png
        encode = encoder or _encode_png
        extension = "png"
    check_interrupted()
    _preflight_finite(images)
    _, height, width, _ = images.shape
    output_folder, basename, counter, subfolder, _ = allocator(prefix, width, height)
    output_dir = Path(output_folder)
    descriptors: list[dict[str, Any]] = []

    for frame in images:
        filename = f"{basename}_{counter:05}_.{extension}"
        final_path = output_dir / filename
        temp_path: Path | None = None
        try:
            check_interrupted()
            handle, raw_temp_path = tempfile.mkstemp(
                prefix=f".{filename}.", suffix=".tmp", dir=output_dir
            )
            os.close(handle)
            temp_path = Path(raw_temp_path)
            encode(_to_pillow(frame), temp_path, quality)
            if not verifier(temp_path):
                raise RuntimeError(
                    f"{output_format} metadata verification failed closed"
                )
            check_interrupted()
            for attempt in range(MAX_COLLISION_RETRIES):
                try:
                    _publish_without_overwrite(temp_path, final_path)
                    break
                except FileExistsError:
                    check_interrupted()
                    counter += 1
                    filename = f"{basename}_{counter:05}_.{extension}"
                    final_path = output_dir / filename
            else:
                raise FileExistsError("Output name collision retry limit reached; existing files preserved")
        except BaseException as error:
            _report_partial_failure(error, descriptors, len(images))
            raise
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        descriptor = {"filename": filename, "subfolder": subfolder, "type": "output", "matrix_metadata_verified": True}
        descriptors.append(descriptor)
        counter += 1
        if preview_dir is not None:
            try:
                try:
                    directory = preview_dir() if callable(preview_dir) else preview_dir
                    descriptor["matrix_preview"] = _save_preview(final_path, directory)
                except Exception:
                    # Preview is optional, and must not downgrade a verified original.
                    descriptor["matrix_preview_error"] = "Preview unavailable; original saved and verified."
                check_interrupted()
            except BaseException as error:
                _report_partial_failure(error, descriptors, len(images))
                raise
    return {"ui": {"images": descriptors}}


class SaveClean:
    """ComfyUI node surface compiled from the io.save-clean capability."""

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "Matrix Lab/image"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": (
                    "STRING",
                    {"default": "MATRIX", "multiline": False},
                ),
                "format": (["JPEG", "PNG"], {"default": "JPEG"}),
                "quality": ("INT", {"default": 100, "min": 1, "max": 100, "step": 1}),
            }
        }

    def save(self, images, filename_prefix, format, quality):
        return save_clean_images(
            images, filename_prefix, format, quality,
            preview_dir=_default_preview_directory,
        )
