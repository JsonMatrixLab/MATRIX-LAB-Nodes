"""Save a ComfyUI VIDEO as MP4 without source or workflow metadata.

The image Metadata Killer has an IMAGE socket; this is a separate VIDEO node.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

import av
import folder_paths
from comfy_api.latest import InputImpl, io, ui


def _check_interrupted() -> None:
    """Use ComfyUI's cancellation boundary without making tests require a queue."""
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


def remux_without_metadata(
    source: str | Path,
    target: str | Path,
    *,
    interrupt_check: Callable[[], None] = _check_interrupted,
) -> None:
    """Copy MP4 video/audio packets while dropping descriptive container/stream tags."""
    with av.open(str(source), mode="r") as incoming, av.open(
        str(target), mode="w", format="mp4", options={"movflags": "+faststart"}
    ) as outgoing:
        if incoming.format is None or "mp4" not in incoming.format.name.split(","):
            raise ValueError("MATRIX VIDEO METADATA KILLER currently supports MP4 input only")
        streams = {}
        for stream in incoming.streams:
            if stream.type not in {"video", "audio"} or stream.codec_context is None:
                continue
            copy = outgoing.add_stream_from_template(stream, opaque=True)
            copy.metadata.clear()
            streams[stream.index] = copy
        if not any(stream.type == "video" for stream in outgoing.streams):
            raise ValueError("Input has no supported video stream")
        outgoing.metadata.clear()
        for packet in incoming.demux():
            interrupt_check()
            target_stream = streams.get(packet.stream.index)
            if target_stream is None or packet.dts is None:
                continue
            packet.stream = target_stream
            outgoing.mux(packet)


def _safe_output_root() -> Path:
    return Path(folder_paths.get_output_directory()).resolve(strict=True)


def _publish_without_overwrite(staged: Path, output_dir: Path, filename: str, counter: int) -> Path:
    """Atomically publish by hard-linking; retry counters instead of replacing any file."""
    root = _safe_output_root()
    resolved_dir = output_dir.resolve(strict=True)
    if not resolved_dir.is_relative_to(root):
        raise ValueError("Resolved output directory escapes ComfyUI's output directory")
    for candidate_counter in range(counter, counter + 100_000):
        candidate = (resolved_dir / f"{filename}_{candidate_counter:05}_.mp4").resolve()
        if not candidate.parent.is_relative_to(root) or candidate.parent != resolved_dir:
            raise ValueError("Unsafe output filename returned by ComfyUI")
        try:
            os.link(staged, candidate)
        except FileExistsError:
            continue
        return candidate
    raise FileExistsError("Could not allocate an unused output filename")


class MATRIXVideoMetadataKiller(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MATRIX_VideoMetadataKiller",
            display_name="MATRIX VIDEO METADATA KILLER",
            category="MATRIX LAB/Input & Output",
            description="Save an MP4 with video and audio streams preserved and descriptive metadata removed.",
            inputs=[
                io.Video.Input("video"),
                io.String.Input("filename_prefix", default="MATRIX/video-clean"),
            ],
            is_output_node=True,
            outputs=[io.Video.Output("video")],
        )

    @classmethod
    def execute(cls, video, filename_prefix: str) -> io.NodeOutput:
        width, height = video.get_dimensions()
        output_dir, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), width, height
        )
        with tempfile.TemporaryDirectory(prefix="matrix-video-clean-") as scratch:
            source = Path(scratch) / "source.mp4"
            video.save_to(str(source))
            with tempfile.TemporaryDirectory(prefix=".matrix-video-clean-", dir=output_dir) as staged:
                ready = Path(staged) / "ready.mp4"
                remux_without_metadata(source, ready)
                target = _publish_without_overwrite(ready, Path(output_dir), filename, counter)
        cleaned = InputImpl.VideoFromFile(str(target))
        return io.NodeOutput(
            cleaned,
            ui=ui.PreviewVideo([ui.SavedResult(target.name, subfolder, io.FolderType.output)]),
        )


NODE_CLASS_MAPPINGS = {"MATRIX_VideoMetadataKiller": MATRIXVideoMetadataKiller}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MATRIX_VideoMetadataKiller": "MATRIX VIDEO METADATA KILLER"
}
