"""Queue-driven live execution with durable intent and prediction recovery."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping

from .catalog import ContractError, build_payload
from .identity import credential_scope, generation_intent, request_identity
from .journal import SubmissionUncertain, TaskJournal
from .media import MediaError, PreparedMedia, flatten_reference_images, prepare_audio, prepare_image, prepare_video
from .private_storage import private_directory, private_file
from .transport import TransportError, WaveSpeedClient
from .uploads import UploadCache


class RunError(RuntimeError):
    pass


@contextmanager
def _result_lock(result_dir: Path, identity: str, check_cancelled=None):
    """Serialize finalization for one prediction across processes; crashes release SQLite locks."""
    lock_path = result_dir / "locks" / f"{identity}.sqlite3"
    private_file(lock_path)
    with closing(sqlite3.connect(lock_path, timeout=0.1, isolation_level=None)) as con:
        while True:
            if check_cancelled:
                check_cancelled()
            try:
                con.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
        try:
            yield
        finally:
            con.rollback()


def media_slots(*, operation: str, image, last_image, video, reference_images, reference_videos, reference_audios) -> dict[str, list[Any] | Any]:
    # Preserve every connected role so backend route validation can name incompatible wires.
    return {"image": image, "last_image": last_image, "video": video,
            "reference_images": [x for x in reference_images if x is not None],
            "reference_videos": [x for x in reference_videos if x is not None],
            "reference_audios": [x for x in reference_audios if x is not None]}


def _media_tokens(media: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for name, value in media.items():
        if isinstance(value, list):
            result[name] = [f"prepared://{name}/{i}" for i, item in enumerate(value) if item is not None]
        elif value is not None:
            result[name] = f"prepared://{name}"
    return result


def _prepare_media(media: Mapping[str, Any], *, allow_video_materialization: bool, operation: str, acknowledge_provider_trimming: bool) -> tuple[dict[str, Any], list[PreparedMedia], dict[str, Any]]:
    media = dict(media)
    if media.get("reference_images"):
        # Count all flattened frames before encoding any media, preserving the
        # caller's reference-slot order and each IMAGE batch's frame order.
        media["reference_images"] = flatten_reference_images(media["reference_images"], maximum=10)
    resources: dict[str, Any] = {}
    prepared: list[PreparedMedia] = []
    digests: dict[str, Any] = {}
    try:
        for name, value in media.items():
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            output = []
            hashes = []
            for index, item in enumerate(values):
                if item is None:
                    continue
                slot = f"{name}-{index + 1}"
                if name in ("image", "last_image", "reference_images"):
                    asset = prepare_image(item, slot=slot)
                elif name in ("reference_audios",):
                    asset = prepare_audio(item, slot=slot)
                elif name in ("video", "reference_videos"):
                    asset = prepare_video(item, slot=slot, allow_materialization=allow_video_materialization)
                    if name == "video" and operation == "Edit Video" and asset.duration < 1 and not acknowledge_provider_trimming:
                        asset.cleanup()
                        raise MediaError("Edit normalizes subsecond input to one second. Acknowledge this provider duration adjustment to continue.")
                    if name == "video" and operation == "Edit Video" and asset.duration > 15 and not acknowledge_provider_trimming:
                        asset.cleanup()
                        raise MediaError("Edit processes only the first 15 seconds of a longer source. Acknowledge the documented trimming to continue.")
                    if name == "video" and operation == "Extend Video" and asset.duration > 120 and not acknowledge_provider_trimming:
                        asset.cleanup()
                        raise MediaError("Extend retains only the last 120 seconds of a longer source. Acknowledge the documented trimming to continue.")
                    if name == "reference_videos":
                        if not (1 <= asset.duration <= 15):
                            asset.cleanup()
                            raise MediaError(f"{slot} reference video must be 1 to 15 seconds; it is {asset.duration:.3f} seconds.")
                        if not (240 <= asset.width <= 4096 and 240 <= asset.height <= 4096):
                            asset.cleanup()
                            raise MediaError(f"{slot} reference video dimensions must each be 240 to 4096 pixels.")
                        if max(asset.width / asset.height, asset.height / asset.width) > 8:
                            asset.cleanup()
                            raise MediaError(f"{slot} reference video aspect ratio must not exceed 8:1.")
                        if asset.size > 100_000_000:
                            asset.cleanup()
                            raise MediaError(f"{slot} exceeds the conservative 100,000,000-byte reference-video threshold.")
                else:
                    raise MediaError(f"Unsupported media role: {name}.")
                prepared.append(asset)
                output.append(asset)
                hashes.append({"sha256": asset.sha256, "duration": asset.duration, "width": asset.width, "height": asset.height})
            resources[name] = output if isinstance(value, list) else (output[0] if output else None)
            digests[name] = hashes if isinstance(value, list) else (hashes[0] if hashes else None)
        if digests.get("reference_audios"):
            duration = sum(float(item.get("duration") or 0) for item in digests["reference_audios"])
            if duration > 15:
                raise MediaError(f"Combined reference audio duration is {duration:.3f}s; the limit is 15s.")
        if digests.get("reference_videos"):
            duration = sum(float(item.get("duration") or 0) for item in digests["reference_videos"])
            if duration > 15:
                raise MediaError(f"Combined reference video duration is {duration:.3f}s; the limit is 15s.")
        return resources, prepared, digests
    except Exception:
        for asset in prepared:
            asset.cleanup()
        raise


def _substitute_uploaded(payload: dict, media_resources: Mapping[str, Any], urls: Mapping[int, str]) -> dict:
    result = dict(payload)
    for field, resource in media_resources.items():
        if resource is None or field not in result:
            continue
        if isinstance(resource, list):
            result[field] = [urls[id(item)] for item in resource]
        else:
            result[field] = urls[id(resource)]
    return result


def _user_data_dir() -> Path:
    try:
        import folder_paths
        root = Path(folder_paths.get_user_directory())
    except Exception as exc:
        raise RunError("Cannot resolve ComfyUI's user-data directory; no task data was written.") from exc
    return root / "matrix-wan3"


def _native_video_from_file(path: Path):
    from comfy_api.latest import InputImpl
    _probe_video(path)
    return InputImpl.VideoFromFile(str(path))


def _probe_video(path: Path) -> str:
    """Decode every frame without retaining tensors; verify duration/FPS/audio and return SHA-256."""
    import av

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    with av.open(str(path), mode="r") as container:
        videos = [stream for stream in container.streams if stream.type == "video"]
        audios = [stream for stream in container.streams if stream.type == "audio"]
        if len(videos) != 1 or len(audios) > 1:
            raise RunError("Completed result must contain exactly one video stream and at most one audio stream.")
        stream = videos[0]
        fps = stream.average_rate or stream.base_rate or stream.guessed_rate
        duration = float(stream.duration * stream.time_base) if stream.duration and stream.time_base else float(container.duration / av.time_base) if container.duration else 0.0
        if stream.width < 1 or stream.height < 1 or fps is None or float(fps) <= 0 or duration <= 0:
            raise RunError("Completed result has invalid dimensions, frame rate, or duration.")
        if audios and (not audios[0].rate or audios[0].rate <= 0):
            raise RunError("Completed result has invalid audio sample-rate metadata.")
        frame_count, audio_frames = 0, 0
        # Demux once: separate decode calls would consume audio packets while reading video.
        for frame in container.decode(*videos, *audios):
            if isinstance(frame, av.VideoFrame):
                if frame.width < 1 or frame.height < 1:
                    raise RunError("Completed result contains an invalid video frame.")
                frame_count += 1
            elif isinstance(frame, av.AudioFrame):
                if frame.samples < 1:
                    raise RunError("Completed result contains an empty audio frame.")
                audio_frames += frame.samples
        if frame_count == 0:
            raise RunError("Completed result contains no decodable video frames.")
        if audios and audio_frames == 0:
            raise RunError("Completed result declares audio but has no decodable audio samples.")
    return digest.hexdigest()


def _completed_output(data: dict) -> str:
    status = str(data.get("status", "")).lower()
    if status in {"failed", "error", "cancelled", "canceled", "deleted"}:
        raise RunError(f"WaveSpeed task ended with status {status or 'unknown'}; it was not resubmitted.")
    if status not in {"completed", "succeeded", "success", "finished"}:
        raise RunError("WaveSpeed task is not complete yet; rerun to resume polling the existing prediction ID.")
    outputs = data.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 1 or not isinstance(outputs[0], str) or not outputs[0]:
        raise RunError("Completed prediction must return exactly one output URL; no output was selected.")
    return outputs[0]


def execute_live(*, node_id, values: dict, media: dict, api_key: str, journal: TaskJournal | None = None,
                 client_factory: Callable[[str], WaveSpeedClient] = WaveSpeedClient, user_data_dir: Path | None = None,
                 sleep: Callable[[float], None] = time.sleep, poll_interval: float = 1.0, max_polls: int = 600,
                 check_cancelled: Callable[[], None] | None = None, progress: Callable[[str], None] | None = None,
                 queue_id: str | None = None, node_instance: str | None = None, legacy_nonce: str | None = None):
    client = client_factory(api_key)
    route, payload_template = build_payload(
        operation=values["operation"], tier=values["tier"], variant=values.get("image_variant", "Regular"),
        values=values, media=_media_tokens(media),
    )
    resources, prepared, digests = _prepare_media(
        media, allow_video_materialization=values.get("allow_video_materialization", False),
        operation=values["operation"], acknowledge_provider_trimming=values.get("acknowledge_provider_trimming", False),
    )
    try:
        if progress:
            progress("Validate")
        if check_cancelled:
            check_cancelled()
        if values["operation"] == "Reference to Video" and digests.get("reference_videos"):
            reference_seconds = sum(float(item.get("duration") or 0) for item in digests["reference_videos"])
            if reference_seconds + payload_template["duration"] > 30:
                raise MediaError("Reference-video time plus generated duration cannot exceed 30 seconds.")
        user_data_dir = user_data_dir or _user_data_dir()
        private_directory(user_data_dir)
        active_journal = journal or TaskJournal(user_data_dir / "tasks.sqlite3")
        nonce = values["intent_nonce"]
        if queue_id is not None:
            if not node_instance:
                raise ContractError("Queued run is missing its stable node identity; submission is blocked.")
            nonce = active_journal.bind_queue(node_key=node_instance, queue_id=queue_id,
                                              proposed_nonce=nonce, legacy_nonce=legacy_nonce)
        # Media URLs are transient and signed; the identity binds content digests instead.
        intent = generation_intent(route=route.model_id, payload=payload_template, media_digests=digests, nonce=nonce)
        scope = credential_scope(api_key)
        identity = request_identity(route=route.model_id, payload=payload_template, media_digests=digests, nonce=nonce, scope=scope)
        record = active_journal.get_or_create(identity, intent, request={"route": route.model_id, "payload_template": payload_template}, media=digests, nonce=nonce)
        if record.identity != identity:
            raise SubmissionUncertain("An earlier request from this node is still unresolved with different inputs or credentials. Resume it unchanged; no second billable POST was sent.")
        if record.status == "failed":
            raise RunError("This prediction has a recorded terminal or invalid outcome; replay cannot restart it.")
        if record.status == "complete":
            result_dir = user_data_dir / "results"
            private_directory(result_dir)
            with _result_lock(result_dir, identity, check_cancelled):
                current = active_journal.intent(identity)
                if current.status == "complete":
                    result_path = Path(current.result_path or "")
                    if result_path.is_file():
                        try:
                            if _probe_video(result_path) == current.result_sha256:
                                return _native_video_from_file(result_path)
                        except Exception:
                            pass
                    # A corrupt or missing local artifact can only recover through the existing ID.
                    if not current.prediction_id:
                        raise RunError("The completed local video is missing or corrupt and has no prediction ID for recovery.")
                    active_journal.recover_result(identity)
        if record.status in ("submitting", "indeterminate") and not record.prediction_id:
            raise SubmissionUncertain("The submit response was ambiguous. This intent is blocked from another POST.")

        if record.prediction_id:
            prediction_id = record.prediction_id
        else:
            if check_cancelled:
                check_cancelled()
            if progress:
                progress("Prepare media")
            if record.payload_json:
                frozen_template = json.loads(record.payload_json)
            else:
                frozen_template = dict(payload_template)
            if not record.payload_json and frozen_template.get("seed") == -1:
                # The chosen fixed value is journaled before upload and reused after restart.
                import secrets
                frozen_template["seed"] = secrets.randbelow(9_999) + 1
            frozen_template = active_journal.freeze_payload(identity, frozen_template)
            urls: dict[int, str] = {}
            upload_cache = UploadCache(user_data_dir / "uploads.sqlite3")
            for index, asset in enumerate(prepared):
                if check_cancelled:
                    check_cancelled()
                if progress:
                    progress(f"Upload {index + 1}/{len(prepared)}")
                urls[id(asset)] = upload_cache.get_or_upload(
                    asset, scope,
                    lambda: client.upload(asset, account_scope=scope, check_cancelled=check_cancelled),
                    check_cancelled=check_cancelled,
                )
            payload = _substitute_uploaded(frozen_template, resources, urls)
            if set(payload) - route.allowed or route.required - set(payload):
                raise ContractError("The frozen payload does not match the selected route contract.")
            if check_cancelled:
                check_cancelled()
            if not active_journal.claim_submit(identity, payload):
                current = active_journal.intent(identity)
                if current.prediction_id:
                    prediction_id = current.prediction_id
                else:
                    raise SubmissionUncertain("Another worker claimed this intent or its response is uncertain; no second POST was sent.")
            else:
                try:
                    if progress:
                        progress("Submit once")
                    prediction_id = client.submit(route.model_id, payload)
                except Exception as exc:
                    active_journal.mark(identity, "indeterminate", detail=type(exc).__name__)
                    raise SubmissionUncertain("WaveSpeed submit did not return a trustworthy prediction ID. The intent is blocked from retry.") from exc
                active_journal.record_prediction(identity, prediction_id)

        for attempt in range(max_polls):
            if check_cancelled:
                check_cancelled()
            if progress:
                progress("Poll existing prediction")
            active_journal.mark(identity, "polling")
            result = client.poll(prediction_id)
            status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
            if status in {"queued", "created", "processing", "running", "in_progress", "pending"}:
                sleep(poll_interval)
                continue
            if status not in {"completed", "succeeded", "success", "finished", "failed", "error", "cancelled", "canceled", "deleted"}:
                active_journal.mark(identity, "accepted", detail="unrecognized provider status; prediction retained")
                raise RunError("WaveSpeed returned an unrecognized task status. The prediction ID is retained; rerun only to resume polling this ID.")
            try:
                output_url = _completed_output(result)
            except RunError:
                # Never store raw provider status/error text, which can contain reflected inputs.
                active_journal.mark(identity, "failed", detail="terminal provider failure or invalid completed output")
                raise
            active_journal.mark(identity, "downloading")
            if check_cancelled:
                check_cancelled()
            if progress:
                progress("Download result")
            result_dir = user_data_dir / "results"
            private_directory(result_dir)
            final_path = result_dir / f"{identity}.mp4"
            partial_path = result_dir / f"{identity}.download"
            with _result_lock(result_dir, identity, check_cancelled):
                current = active_journal.intent(identity)
                if current.status == "failed":
                    raise RunError("This prediction has a recorded terminal outcome; no second download was started.")
                if current.status == "complete" and final_path.is_file():
                    try:
                        if _probe_video(final_path) == current.result_sha256:
                            return _native_video_from_file(final_path)
                    except Exception:
                        pass
                    active_journal.recover_result(identity)
                try:
                    client.download_result(output_url, partial_path, check_cancelled=check_cancelled)
                    result_sha256 = _probe_video(partial_path)
                    os.replace(partial_path, final_path)
                    private_file(final_path)
                    active_journal.mark(identity, "complete", result_path=str(final_path), result_sha256=result_sha256)
                    return _native_video_from_file(final_path)
                finally:
                    partial_path.unlink(missing_ok=True)
        active_journal.mark(identity, "accepted", detail="poll deadline; prediction retained")
        raise RunError("Polling reached its local deadline. The prediction ID is retained; rerun only to resume this ID.")
    except (ContractError, MediaError, TransportError):
        raise
    finally:
        for asset in prepared:
            asset.cleanup()
