"""Public single-node ComfyUI schema and scheduler-owned entry point."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from comfy_api.latest import io

from ..._core.wan3.catalog import ContractError, build_payload
from ..._core.wan3.credentials import resolve_key
from ..._core.wan3.runner import execute_live, media_slots, _media_tokens


def _reference_group(io_type, group_id: str, slot_prefix: str, display_name: str, maximum: int, tooltip: str):
    return io.Autogrow.Input(
        group_id,
        template=io.Autogrow.TemplateNames(
            io_type.Input(f"{slot_prefix}_slot", display_name=display_name, optional=True),
            names=[f"{slot_prefix}_{index:02d}" for index in range(1, maximum + 1)],
            min=0,
        ),
        display_name=display_name.rstrip("s"),
        tooltip=tooltip,
    )


def _ordered_group(value: Any) -> list[Any]:
    """Return native Autogrow values in numeric slot order, independent of map insertion order."""
    if value is None:
        return []
    if isinstance(value, Mapping):
        def slot_index(item):
            key = str(item[0])
            suffix = key.rsplit("_", 1)[-1]
            return (0, int(suffix)) if suffix.isdigit() else (1, key)
        ordered = sorted(value.items(), key=slot_index)
        return [item for _name, item in ordered if item is not None]
    if isinstance(value, (list, tuple)):
        return [item for item in value if item is not None]
    raise ContractError("Native reference groups must be ordered slot mappings.")


def _operation_media(selected: Mapping[str, Any]) -> dict[str, Any]:
    return media_slots(
        operation=selected.get("operation"),
        image=selected.get("image"),
        last_image=selected.get("last_image"),
        video=selected.get("video"),
        reference_images=_ordered_group(selected.get("reference_images")),
        reference_videos=_ordered_group(selected.get("reference_videos")),
        reference_audios=_ordered_group(selected.get("reference_audios")),
    )


def _queue_context():
    try:
        from comfy_execution.utils import get_executing_context
        context = get_executing_context()
    except ImportError as exc:
        raise ContractError("ComfyUI queue context is unavailable; paid submission is blocked.") from exc
    if not context or not context.prompt_id or not context.node_id:
        raise ContractError("ComfyUI did not supply a queued prompt and node identity; paid submission is blocked.")
    return context


class MATRIXWan3(io.ComfyNode):
    """One native VIDEO-producing node with route-specific typed media sockets."""

    @classmethod
    def define_schema(cls):
        i2v_inputs = [
            io.Image.Input("image", display_name="First frame", optional=True),
            io.Image.Input("last_image", display_name="Last frame", optional=True),
        ]
        reference_inputs = [
            _reference_group(io.Image, "reference_images", "image", "Reference images", 10,
                             "Ordered image references; up to 10 images across all batches."),
            _reference_group(io.Video, "reference_videos", "video", "Reference videos", 5,
                             "Ordered video references; up to 5 videos."),
            _reference_group(io.Audio, "reference_audios", "audio", "Reference audio", 5,
                             "Ordered audio references; up to 5 clips."),
        ]
        edit_inputs = [
            io.Video.Input("video", display_name="Source video", optional=True),
            reference_inputs[0],
            reference_inputs[2],
        ]
        operation = io.DynamicCombo.Input(
            "operation",
            options=[
                io.DynamicCombo.Option("Text to Video", []),
                io.DynamicCombo.Option("Image to Video", i2v_inputs),
                io.DynamicCombo.Option("Reference to Video", reference_inputs),
                io.DynamicCombo.Option("Edit Video", edit_inputs),
                io.DynamicCombo.Option(
                    "Extend Video",
                    [
                        io.Video.Input("video", display_name="Source video", optional=True),
                        io.Image.Input("last_image", display_name="Last frame", optional=True),
                    ],
                ),
            ],
            tooltip="Select one operation. Only that operation's native media inputs are available.",
        )
        inputs = [
            operation,
            io.Combo.Input("tier", options=["Standard", "Prime"], default="Standard"),
            io.Combo.Input("image_variant", display_name="Image route", options=["Regular", "Spicy"], default="Regular", optional=True),
            io.String.Input("prompt", default="", multiline=True, optional=True, placeholder="Describe the clip or edit"),
            io.Combo.Input("resolution", options=["480p", "720p", "1080p"], default="720p"),
            io.Int.Input("duration", default=5, min=2, max=30, step=1),
            io.Combo.Input("aspect_ratio", options=["Auto", "16:9", "9:16", "1:1", "4:3", "3:4"], default="16:9"),
            io.Boolean.Input("enable_audio", default=True),
            io.Boolean.Input("generate_audio", display_name="Generate audio", default=True, advanced=True),
            io.Boolean.Input("enable_prompt_expansion", default=False, advanced=True),
            io.Combo.Input("seed_mode", options=["Random", "Fixed"], default="Random", advanced=True),
            io.Int.Input("seed", default=1, min=0, max=2_147_483_647, control_after_generate=False, advanced=True),
            io.Combo.Input("edit_duration", display_name="Edit output duration", options=["Auto", *range(2, 16)], default="Auto", advanced=True),
            io.Boolean.Input("allow_video_materialization", display_name="Encode VIDEO for upload", default=False, advanced=True,
                             tooltip="A native VIDEO may need local encoding/materialization before upload. Keep off unless you explicitly accept it."),
            io.Boolean.Input("acknowledge_provider_trimming", display_name="Allow video trimming", default=False, advanced=True),
            io.String.Input("intent_nonce", default="initial", optional=False, advanced=True,
                            tooltip="Legacy non-secret workflow field. Queued prompt identity controls new generations."),
            io.String.Input("credential_scope", default="", optional=False, advanced=True,
                            tooltip="Non-secret saved-key handle. The API key itself is never serialized."),
            io.String.Input("billing_activation", default="blocked", optional=False, advanced=True,
                            tooltip="Internal migration guard. Old offline Demo workflows cannot start paid requests automatically."),
        ]
        return io.Schema(
            node_id="MATRIX_Wan3",
            display_name="MATRIX WAN 3.0",
            category="MATRIX LAB/Video Generation",
            description="WaveSpeed WAN 3.0 Standard and Prime. Each new generation is billed.",
            inputs=inputs,
            outputs=[io.Video.Output("video", tooltip="Native ComfyUI VIDEO result.")],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        context = _queue_context()
        return (context.prompt_id, context.node_id, context.list_index)

    @classmethod
    def execute(
        cls, operation: dict, tier, resolution, duration, aspect_ratio,
        enable_audio, generate_audio, enable_prompt_expansion, seed_mode, seed, edit_duration,
        allow_video_materialization, acknowledge_provider_trimming, intent_nonce, credential_scope,
        prompt="", image_variant="Regular", billing_activation="blocked",
    ) -> io.NodeOutput:
        if not isinstance(operation, Mapping):
            raise ContractError("ComfyUI must provide the selected operation and its active media fields as a native operation mapping.")
        operation_name = operation.get("operation")
        values = {
            "operation": operation_name, "tier": tier, "image_variant": image_variant, "prompt": prompt,
            "resolution": resolution, "duration": duration, "aspect_ratio": aspect_ratio,
            "enable_audio": enable_audio, "generate_audio": generate_audio,
            "enable_prompt_expansion": enable_prompt_expansion, "seed_mode": seed_mode,
            "seed": seed, "edit_duration": edit_duration,
            "allow_video_materialization": allow_video_materialization,
            "acknowledge_provider_trimming": acknowledge_provider_trimming,
            "intent_nonce": intent_nonce,
            "credential_scope": credential_scope,
        }
        # API callers and legacy Demo workflows are blocked unless explicitly activated.
        if billing_activation != "wavespeed_v1":
            raise ContractError("Paid generation is blocked for this older Demo workflow. Save a WaveSpeed key in this node to activate billed runs.")
        context = _queue_context()
        index = context.list_index if context.list_index is not None else 0
        queue_id = f"{context.prompt_id}:{index}"
        node_instance = f"{credential_scope}:{context.node_id}:{index}"
        legacy_nonce = intent_nonce
        values["intent_nonce"] = hashlib.sha256(f"matrix-wan3/queue-v1/{queue_id}/{context.node_id}".encode("utf-8")).hexdigest()
        media = _operation_media(operation)
        # Validate route/mode compatibility before media encoding or any upload.
        build_payload(operation=operation_name, tier=tier, variant=image_variant, values=values, media=_media_tokens(media))
        key, _source = resolve_key(credential_scope)

        def check_cancelled():
            try:
                import comfy.model_management
                comfy.model_management.throw_exception_if_processing_interrupted()
            except ImportError:
                return

        result = execute_live(node_id=credential_scope, values=values, media=media, api_key=key,
                              queue_id=queue_id, node_instance=node_instance, legacy_nonce=legacy_nonce,
                              check_cancelled=check_cancelled)
        return io.NodeOutput(result)


NODE_CLASS_MAPPINGS = {"MATRIX_Wan3": MATRIXWan3}
NODE_DISPLAY_NAME_MAPPINGS = {"MATRIX_Wan3": "MATRIX WAN 3.0"}
