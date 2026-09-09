"""Public surface for the io.save-clean block."""

from typing import Callable

from .save_clean import (
    _default_preview_directory,
    SaveClean,
    inspect_jpeg_privacy,
    inspect_png_privacy,
    save_clean_images,
    verify_clean_jpeg,
    verify_clean_png,
)


_FACTORY_PATH_ALLOCATOR: Callable | None = None
_FACTORY_INTERRUPT_CHECKER: Callable[[], None] | None = None


def configure_factory_io(path_allocator: Callable, interrupt_checker: Callable[[], None]) -> None:
    """Install ComfyUI-owned output-path and interruption adapters."""
    global _FACTORY_PATH_ALLOCATOR, _FACTORY_INTERRUPT_CHECKER
    if not callable(path_allocator) or not callable(interrupt_checker):
        raise TypeError("factory save adapters must be callable")
    _FACTORY_PATH_ALLOCATOR = path_allocator
    _FACTORY_INTERRUPT_CHECKER = interrupt_checker


def execute_utility_operation(item):
    """Factory output-node seam returning UI descriptors, not tensor outputs."""
    if not isinstance(item, dict) or "images" not in item:
        raise ValueError("io.save-clean requires an input mapping with 'images'")
    if _FACTORY_PATH_ALLOCATOR is None or _FACTORY_INTERRUPT_CHECKER is None:
        raise RuntimeError("io.save-clean runtime output adapter is not configured by the pack bootstrap")
    return save_clean_images(
        item["images"],
        item.get("filename_prefix", "MATRIX"),
        item.get("format", "JPEG"),
        item.get("quality", 100),
        path_allocator=_FACTORY_PATH_ALLOCATOR,
        interrupt_checker=_FACTORY_INTERRUPT_CHECKER,
        preview_dir=_default_preview_directory,
    )

__all__ = [
    "SaveClean",
    "configure_factory_io",
    "execute_utility_operation",
    "inspect_jpeg_privacy",
    "inspect_png_privacy",
    "save_clean_images",
    "verify_clean_jpeg",
    "verify_clean_png",
]
