"""Generated ComfyUI runtime adapters; regenerate instead of hand-editing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading


_EXPECTED_REGISTRY_SHA256 = 'ab1955cfe5e8d05b832a4f63cae121d9afd6f74d3a9048b0107cf634659cada8'
_HAS_EYE = False
_HAS_DETAIL = False
_HAS_SPECTRAL = True
_HAS_TAIL = True
_HAS_CROP_TAIL = True
_HAS_OUTPUT_STAGE = True
_HAS_SKIN = True
_HAS_EYE_MASK = True
_HAS_SAVE = True
_BOOTSTRAPPED = False
_BOOTSTRAP_LOCK = threading.Lock()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_registry():
    path = Path(__file__).with_name("runtime-assets.json")
    if not path.is_file():
        raise RuntimeError(f"compiled runtime asset registry is missing: {path}")
    observed = _sha256(path)
    if observed != _EXPECTED_REGISTRY_SHA256:
        raise RuntimeError(
            "compiled runtime asset registry hash mismatch: "
            f"expected {_EXPECTED_REGISTRY_SHA256}, observed {observed}"
        )
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"compiled runtime asset registry is unreadable: {exc}") from exc
    if registry.get("schema") != "matrix-lab.comfyui-runtime-assets/v1":
        raise RuntimeError("compiled runtime asset registry has an unsupported schema")
    if not isinstance(registry.get("assets"), dict):
        raise RuntimeError("compiled runtime asset registry has no assets mapping")
    return registry


def _asset_by_role(registry, role):
    matches = [entry for entry in registry["assets"].values() if entry.get("role") == role]
    if len(matches) != 1:
        raise RuntimeError(f"compiled runtime asset registry requires exactly one {role!r} entry")
    return dict(matches[0])


def _declared_asset_roots(folder_paths, folder_name):
    """Return configured roots, or the clean-pack native root for this asset kind."""
    try:
        roots = tuple(Path(root).resolve() for root in folder_paths.get_folder_paths(folder_name))
    except Exception:
        roots = ()
    if roots:
        return roots
    models_dir = getattr(folder_paths, "models_dir", None)
    if not isinstance(models_dir, (str, Path)):
        return ()
    native_suffixes = {
        "ultralytics_bbox": ("ultralytics", "bbox"),
        "sams": ("sams",),
        "onnx": ("onnx",),
    }
    suffix = native_suffixes.get(folder_name)
    if suffix is None:
        return ()
    return ((Path(models_dir) / Path(*suffix)).resolve(),)


def _verified_asset(folder_paths, entry):
    folder_name = entry.get("folder_name")
    relative = Path(str(entry.get("relative_path", "")))
    if (
        not isinstance(folder_name, str)
        or not folder_name
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        raise RuntimeError(f"runtime asset {entry.get('logical_id')!r} has an unsafe path contract")
    roots = _declared_asset_roots(folder_paths, folder_name)
    if not roots:
        raise RuntimeError(
            f"ComfyUI folder_paths has no configured {folder_name!r} model root and "
            "no declared native asset root"
        )
    candidates = []
    for root in roots:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            candidates.append((root, candidate))
    if len(candidates) != 1:
        raise RuntimeError(
            f"runtime asset {entry.get('logical_id')!r} must resolve exactly once through "
            f"folder_paths[{folder_name!r}], observed {len(candidates)}"
        )
    root, path = candidates[0]
    expected_size = entry.get("byte_size")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 1:
        raise RuntimeError(f"runtime asset {entry.get('logical_id')!r} has no valid byte size")
    observed_size = path.stat().st_size
    if observed_size != expected_size:
        raise RuntimeError(
            f"runtime asset {entry.get('logical_id')!r} size mismatch: "
            f"expected {expected_size}, observed {observed_size}"
        )
    expected_hash = str(entry.get("sha256", "")).lower()
    observed_hash = _sha256(path)
    if observed_hash != expected_hash:
        raise RuntimeError(
            f"runtime asset {entry.get('logical_id')!r} sha256 mismatch: "
            f"expected {expected_hash}, observed {observed_hash}"
        )
    return root, path


class _ComfyModelManager:
    def __init__(self, model_management):
        self._management = model_management
        self._devices = {}

    def runtime(self, entry, image):
        del entry, image
        device = self._management.get_torch_device()
        name = str(device)
        self._devices[name] = device
        return name, "fp32"

    def supports_dtype(self, device, dtype, entry):
        return device in self._devices and dtype == "fp32" and dtype in entry["allowed_dtypes"]

    def preflight_vram(self, required_bytes, device):
        available = self._management.get_free_memory(self._devices[device])
        if isinstance(available, tuple):
            available = available[0]
        if int(available) < int(required_bytes):
            raise RuntimeError(
                f"detector VRAM preflight refused: required={required_bytes}, available={available}"
            )

    def prepare_image(self, image, device, dtype):
        del dtype
        import torch
        return image.to(device=self._devices[device], dtype=torch.float32, non_blocking=True)

    def release_transients(self):
        self._management.soft_empty_cache()


class _UltralyticsSamModel:
    def __init__(self, yolo, predictor, *, device, labels, stride):
        self._yolo = yolo
        self._predictor = predictor
        self._device = device
        self._lock = threading.RLock()
        self.task = "bbox"
        self.labels = tuple(labels)
        self.stride = int(stride)

    def predict(self, canvas, **controls):
        import torch
        threshold = float(controls.pop("threshold", 0.3))
        with self._lock:
            results = self._yolo.predict(
                source=canvas[..., :3].permute(2, 0, 1).unsqueeze(0).float(),
                conf=threshold,
                verbose=False,
                device=self._device,
            )
        if not results:
            return {
                "boxes": torch.empty((0, 4)),
                "scores": torch.empty((0,)),
                "class_ids": torch.empty((0,), dtype=torch.int64),
            }
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return {
                "boxes": torch.empty((0, 4)),
                "scores": torch.empty((0,)),
                "class_ids": torch.empty((0,), dtype=torch.int64),
            }
        xyxy = boxes.xyxy.detach().to(device="cpu", dtype=torch.float32)
        scores = boxes.conf.detach().to(device="cpu", dtype=torch.float32)
        class_ids = boxes.cls.detach().to(device="cpu", dtype=torch.int64)
        return {
            "boxes": xyxy,
            "scores": scores,
            "class_ids": class_ids,
            "original_indices": torch.arange(len(xyxy), dtype=torch.int64),
        }

    def refine(self, image, box, **controls):
        import numpy as np
        import torch
        config = controls.get("config")
        expansion = int(getattr(config, "sam_bbox_expansion", 0))
        height, width = image.shape[:2]
        x1, y1, x2, y2 = box
        prompt_box = np.asarray(
            [
                max(0.0, x1 - expansion),
                max(0.0, y1 - expansion),
                min(float(width), x2 + expansion),
                min(float(height), y2 + expansion),
            ],
            dtype=np.float32,
        )
        pixels = (
            image[..., :3].detach().to(device="cpu", dtype=torch.float32)
            .clamp(0, 1).mul(255).round().to(torch.uint8).numpy()
        )
        with self._lock:
            self._predictor.set_image(pixels)
            masks, scores, _ = self._predictor.predict(
                box=prompt_box,
                multimask_output=True,
            )
        if len(masks) == 0:
            return torch.zeros((height, width), dtype=torch.float32)
        return torch.from_numpy(masks[int(np.argmax(scores))]).to(torch.float32)


def _eye_loader(sam_path):
    def load(path, entry, device, dtype):
        del dtype
        try:
            from ultralytics import YOLO
            from segment_anything import SamPredictor, sam_model_registry
        except ImportError as exc:
            raise RuntimeError(
                "detect.eye-bbox requires the pod's ultralytics and segment_anything runtimes"
            ) from exc
        model_type = "vit_b" if "vit_b" in sam_path.name.casefold() else None
        if model_type is None or model_type not in sam_model_registry:
            raise RuntimeError(f"unsupported retained SAM checkpoint name: {sam_path.name}")
        yolo = YOLO(str(path))
        sam = sam_model_registry[model_type](checkpoint=str(sam_path))
        sam.to(device=device)
        sam.eval()
        return _UltralyticsSamModel(
            yolo,
            SamPredictor(sam),
            device=device,
            labels=entry["labels"],
            stride=entry["stride"],
        )
    return load


def _detail_sampler(nodes, comfy_sample, comfy_samplers):
    if not callable(getattr(nodes, "common_ksampler", None)) or not callable(
        getattr(comfy_sample, "sample", None)
    ):
        raise RuntimeError("ComfyUI common_ksampler/comfy.sample ABI is unavailable")
    if any(
        not callable(getattr(comfy_sample, name, None))
        for name in ("fix_empty_latent_channels", "prepare_noise")
    ) or not callable(getattr(comfy_samplers, "beta_scheduler", None)):
        raise RuntimeError("ComfyUI beta57 scheduler adapter ABI is unavailable")

    def sample(
        latent,
        *,
        model,
        positive,
        negative,
        seed,
        steps,
        cfg,
        sampler_name,
        scheduler,
        denoise,
        noise_mask,
        force_inpaint,
        inpaint_model,
        callback,
    ):
        del force_inpaint, inpaint_model
        payload = {"samples": latent}
        if noise_mask is not None:
            payload["noise_mask"] = noise_mask
        if scheduler == "beta57":
            latent_image = comfy_sample.fix_empty_latent_channels(model, latent)
            noise = comfy_sample.prepare_noise(latent_image, seed)
            schedule_steps = steps if denoise > 0.9999 else int(steps / denoise)
            sigmas = comfy_samplers.beta_scheduler(
                model.get_model_object("model_sampling"),
                schedule_steps,
                alpha=0.5,
                beta=0.7,
            )[-(steps + 1):]
            returned = comfy_sample.sample(
                model,
                noise,
                steps,
                cfg,
                sampler_name,
                "beta",
                positive,
                negative,
                latent_image,
                denoise=denoise,
                noise_mask=noise_mask,
                sigmas=sigmas,
                callback=(lambda *args: callback()) if callback is not None else None,
                seed=seed,
            )
            return returned
        if callback is not None:
            callback()
        result = nodes.common_ksampler(
            model,
            seed,
            steps,
            cfg,
            sampler_name,
            scheduler,
            positive,
            negative,
            payload,
            denoise=denoise,
        )
        if callback is not None:
            callback()
        returned = result[0] if isinstance(result, tuple) else result
        return returned["samples"] if isinstance(returned, dict) else returned

    return sample


def _tail_adapters(comfy_samplers, comfy_sample, model_management):
    """Exact SamplerCustomAdvanced + BasicGuider seam for sample.latent-tail."""
    for name in ("CFGGuider", "sampler_object", "beta_scheduler", "calculate_sigmas"):
        if not callable(getattr(comfy_samplers, name, None)):
            raise RuntimeError(f"ComfyUI {name} ABI is unavailable for sample.latent-tail")
    if not callable(getattr(comfy_samplers.CFGGuider, "inner_set_conds", None)):
        raise RuntimeError("ComfyUI CFGGuider.inner_set_conds ABI is unavailable")
    if not callable(getattr(comfy_sample, "fix_empty_latent_channels", None)):
        raise RuntimeError("ComfyUI fix_empty_latent_channels ABI is unavailable")

    def _exact_flow_table(model_sampling):
        """Recompute the model's sigma table in float64 from its own sigma() formula.

        Core's beta_scheduler indexes ``model_sampling.sigmas``; after a model load that buffer
        can sit in the model's low-precision compute dtype,
        where neighbouring low sigmas collapse to equal values and the tail is no longer strictly
        decreasing. Returns None when the object is
        not a discrete-flow sampling with a scalar shift and multiplier.
        """
        import logging
        import torch
        log = logging.getLogger("MATRIX.LatentTail")
        sigmas = getattr(model_sampling, "sigmas", None)
        shift = getattr(model_sampling, "shift", None)
        multiplier = getattr(model_sampling, "multiplier", None)
        sigma_fn = getattr(model_sampling, "sigma", None)
        if sigmas is None or not callable(sigma_fn) or not isinstance(shift, (int, float)):
            return None
        if not isinstance(multiplier, (int, float)) or multiplier <= 0:
            return None
        count = int(sigmas.shape[0])
        if count < 2:
            return None
        try:
            timesteps = (torch.arange(1, count + 1, dtype=torch.float64) / count) * multiplier
            table = sigma_fn(timesteps.to(device=sigmas.device)).detach().to("cpu", torch.float64)
        except Exception as exc:  # noqa: BLE001 - fall back to Core's table
            log.warning("exact flow sigma table unavailable (%s); using Core buffer", exc)
            return None
        values = [float(value) for value in table.tolist()]
        if any(later <= earlier for earlier, later in zip(values, values[1:])):
            return None
        log.info(
            "flow sigma table recomputed in float64 (shift=%s, %d entries, Core buffer dtype %s)",
            shift, count, sigmas.dtype,
        )
        return values

    def schedule_factory(model, scheduler):
        model_sampling = model.get_model_object("model_sampling")
        if scheduler == "beta57":
            import logging
            log = logging.getLogger("MATRIX.LatentTail")
            try:
                from .sample_latent_tail import beta57_schedule
            except ImportError as exc:  # test doubles without the block's schedule
                log.warning("beta57 path: Core beta_scheduler (block schedule unavailable: %s)", exc)
                beta57_schedule = None
            exact = _exact_flow_table(model_sampling) if beta57_schedule is not None else None
            if exact is not None:
                log.info("beta57 path: exact float64 flow table + block beta57")
                own = beta57_schedule(exact)
                return lambda total: [float(value) for value in own(total)]
            log.warning(
                "beta57 path: Core beta_scheduler on model_sampling buffer (type %s, sigmas dtype %s)",
                type(model_sampling).__name__, getattr(getattr(model_sampling, "sigmas", None), "dtype", None),
            )
            return lambda total: [
                float(value)
                for value in comfy_samplers.beta_scheduler(
                    model_sampling, total, alpha=0.5, beta=0.7
                )
            ]
        return lambda total: [
            float(value)
            for value in comfy_samplers.calculate_sigmas(model_sampling, scheduler, total)
        ]

    def run_sampler(*, model, noise, positive, latent, noise_mask, sigmas, sampler_name):
        latent_image = comfy_sample.fix_empty_latent_channels(model, latent["samples"])
        seeded = dict(latent)
        seeded["samples"] = latent_image
        noise_tensor = noise.generate_noise(seeded)
        guider = comfy_samplers.CFGGuider(model)
        guider.inner_set_conds({"positive": positive})
        guider.set_cfg(1.0)
        sampler = comfy_samplers.sampler_object(sampler_name)
        callback = None
        disable_pbar = False
        try:
            import latent_preview

            callback = latent_preview.prepare_callback(model, int(sigmas.shape[-1]) - 1, {})
        except Exception:
            callback = None
        try:
            import comfy.utils as comfy_utils

            disable_pbar = not bool(getattr(comfy_utils, "PROGRESS_BAR_ENABLED", True))
        except Exception:
            disable_pbar = False
        samples = guider.sample(
            noise_tensor,
            latent_image,
            sampler,
            sigmas,
            denoise_mask=noise_mask,
            callback=callback,
            disable_pbar=disable_pbar,
            seed=getattr(noise, "seed", None),
        )
        intermediate = getattr(model_management, "intermediate_device", None)
        if callable(intermediate):
            samples = samples.to(intermediate())
        return samples

    return schedule_factory, run_sampler


def _crop_tail_adapters(schedule_factory, run_sampler):
    """VAE encode/decode plus the configured latent tail for sample.crop-tail-paste."""
    from .sample_latent_tail import latent_tail, resolve_tail_sigmas

    def encode(vae, pixels):
        return {"samples": vae.encode(pixels[:, :, :, :3])}

    def decode(vae, latent):
        images = vae.decode(latent["samples"])
        if len(images.shape) == 5:
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        return images

    def run_tail(model, noise, positive, latent, mask, start_sigma, steps, sampler_name, scheduler):
        schedule = resolve_tail_sigmas(
            schedule_factory(model, scheduler),
            start_sigma=start_sigma,
            steps=steps,
            scheduler=scheduler,
        )
        return latent_tail(
            latent=latent,
            model=model,
            noise=noise,
            positive=positive,
            mask=mask,
            schedule=schedule,
            sampler_name=sampler_name,
            run_sampler=run_sampler,
        )

    return encode, decode, run_tail


def _output_stage_adapters(schedule_factory, run_sampler):
    """VAE, latent-tail and Core detail-upscale seams for sample.output-stage."""
    from .sample_latent_tail import latent_tail, resolve_tail_sigmas

    def encode(vae, pixels):
        return {"samples": vae.encode(pixels[:, :, :, :3])}

    def decode_tiled(vae, latent, tile, overlap):
        images = vae.decode_tiled(
            latent["samples"], tile_x=tile, tile_y=tile, overlap=overlap
        )
        if len(images.shape) == 5:
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        return images

    def tail(model, noise, positive, latent, sigmas, sampler_name):
        schedule = resolve_tail_sigmas(
            schedule_factory(model, sigmas.scheduler),
            start_sigma=sigmas.ceiling,
            steps=sigmas.steps,
            scheduler=sigmas.scheduler,
        )
        result = latent_tail(
            latent=latent,
            model=model,
            noise=noise,
            positive=positive,
            mask=None,
            schedule=schedule,
            sampler_name=sampler_name,
            run_sampler=run_sampler,
        )
        return result, schedule

    def upscale_with_model(upscale_model, image):
        import torch
        try:
            from comfy_extras.nodes_upscale_model import ImageUpscaleWithModel
        except ImportError as exc:
            raise RuntimeError("ComfyUI ImageUpscaleWithModel ABI is unavailable") from exc
        result = ImageUpscaleWithModel().upscale(upscale_model, image)
        # Core 0.33 returns an io.NodeOutput (v3 schema) whose .args carry the tensors; older
        # Core returned a tuple.
        if isinstance(result, torch.Tensor):
            return result
        args = getattr(result, "args", None)
        if isinstance(args, (tuple, list)) and args:
            return args[0]
        if isinstance(result, (tuple, list)) and result:
            return result[0]
        return result

    return encode, decode_tiled, tail, upscale_with_model


def _lazy_onnx_session(folder_paths, role, providers):
    """Resolve, verify and open one registered ONNX asset on first use, then cache it."""
    state = {}

    def session():
        if "session" not in state:
            registry = _load_registry()
            entry = _asset_by_role(registry, role)
            folder_name = entry.get("folder_name")
            try:
                roots = folder_paths.get_folder_paths(folder_name)
            except Exception:
                roots = []
            if not roots and callable(getattr(folder_paths, "add_model_folder_path", None)):
                import os
                # ComfyUI Core registers no `onnx` folder; bind the standard models/onnx path once.
                folder_paths.add_model_folder_path(
                    folder_name, os.path.join(folder_paths.models_dir, folder_name)
                )
            _, path = _verified_asset(folder_paths, entry)
            try:
                import onnxruntime
            except ImportError as exc:
                raise RuntimeError("mask.skin-region requires the onnxruntime package") from exc
            available = set(onnxruntime.get_available_providers())
            chosen = [name for name in providers if name in available] or ["CPUExecutionProvider"]
            state["session"] = onnxruntime.InferenceSession(str(path), providers=chosen)
        return state["session"]

    return session


def _skin_adapters(folder_paths):
    """ONNX sessions for the registered human-parts and person segmentation assets."""
    parts_session = _lazy_onnx_session(
        folder_paths, "skin-parts", ("CUDAExecutionProvider", "CPUExecutionProvider")
    )
    person_session = _lazy_onnx_session(folder_paths, "person-seg", ("CPUExecutionProvider",))

    def _run(session, prepared):
        import numpy as np
        if hasattr(prepared, "detach"):
            prepared = prepared.detach().to("cpu", copy=False).numpy()
        array = np.ascontiguousarray(np.asarray(prepared, dtype=np.float32))
        name = session.get_inputs()[0].name
        return session.run(None, {name: array})[0]

    def segment_parts(prepared):
        return _run(parts_session(), prepared)

    def segment_person(prepared):
        return _run(person_session(), prepared)

    return segment_parts, segment_person


def _eye_mask_adapters(folder_paths, model_management):
    """Own ultralytics call and SAM refinement for mask.eye-region (no Impact code path)."""
    import threading
    import weakref

    state = {"predictor_lock": threading.RLock()}

    def _models():
        if "yolo" not in state:
            registry = _load_registry()
            bbox_entry = _asset_by_role(registry, "eye-bbox")
            sam_entry = _asset_by_role(registry, "eye-segm")
            _, bbox_path = _verified_asset(folder_paths, bbox_entry)
            _, sam_path = _verified_asset(folder_paths, sam_entry)
            try:
                from ultralytics import YOLO
                from segment_anything import SamPredictor, sam_model_registry
            except ImportError as exc:
                raise RuntimeError(
                    "mask.eye-region requires the ultralytics and segment_anything runtimes"
                ) from exc
            device = model_management.get_torch_device()
            sam = sam_model_registry["vit_b"](checkpoint=str(sam_path))
            sam.to(device=device)
            sam.eval()
            state["logical_id"] = bbox_entry["logical_id"]
            state["yolo"] = YOLO(str(bbox_path))
            state["predictor"] = SamPredictor(sam)
            state["device"] = device
            state["image_ref"] = None
            state["image_snapshot"] = None
        return state

    def detect(detector_id, image_rgb_uint8, *, conf, imgsz):
        import numpy as np
        models = _models()
        if detector_id != models["logical_id"]:
            raise RuntimeError(
                f"detector {detector_id!r} is not the registered eye asset "
                f"{models['logical_id']!r}"
            )
        results = models["yolo"].predict(
            source=np.ascontiguousarray(image_rgb_uint8),
            conf=float(conf),
            imgsz=int(imgsz),
            device=models["device"],
            verbose=False,
            max_det=300,
        )
        boxes = results[0].boxes
        return (
            boxes.xyxy.detach().cpu().numpy().astype(np.float32),
            boxes.conf.detach().cpu().numpy().astype(np.float32),
            boxes.cls.detach().cpu().numpy().astype(np.int64),
        )

    def refine(image_rgb_uint8, box_xyxy, point_xy):
        import numpy as np
        models = _models()
        pixels = np.ascontiguousarray(image_rgb_uint8)
        with models["predictor_lock"]:
            image_ref = models["image_ref"]
            cached_image = image_ref() if image_ref is not None else None
            snapshot = models["image_snapshot"]
            unchanged = (
                cached_image is image_rgb_uint8
                and snapshot is not None
                and snapshot.shape == pixels.shape
                and snapshot.dtype == pixels.dtype
                and np.array_equal(snapshot, pixels)
            )
            if not unchanged:
                models["predictor"].set_image(pixels)
                models["image_ref"] = weakref.ref(image_rgb_uint8)
                models["image_snapshot"] = pixels.copy()
            masks, scores, _ = models["predictor"].predict(
                point_coords=np.asarray([point_xy], dtype=np.float32),
                point_labels=np.asarray([1], dtype=np.int64),
                box=np.asarray(box_xyxy, dtype=np.float32),
                multimask_output=True,
            )
        if len(masks) == 0:
            return np.zeros(pixels.shape[:2], dtype=np.float32)
        return masks[int(np.argmax(scores))].astype(np.float32)

    return detect, refine


def bootstrap_runtime():
    global _BOOTSTRAPPED
    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            return
        try:
            import comfy.model_management as model_management
            import comfy.sample as comfy_sample
            import comfy.samplers as comfy_samplers
            import folder_paths
            import nodes
        except ImportError as exc:
            raise RuntimeError("compiled processing pack requires a real ComfyUI runtime") from exc

        if _HAS_EYE:
            registry = _load_registry()
            bbox_entry = _asset_by_role(registry, "eye-bbox")
            sam_entry = _asset_by_role(registry, "eye-segm")
            bbox_root, _ = _verified_asset(folder_paths, bbox_entry)
            _, sam_path = _verified_asset(folder_paths, sam_entry)
            from .detect_eye_bbox import EyeBBoxProvider, configure_factory_provider
            configure_factory_provider(
                EyeBBoxProvider(
                    registry={bbox_entry["logical_id"]: bbox_entry},
                    model_root=bbox_root,
                    loader=_eye_loader(sam_path),
                    model_manager=_ComfyModelManager(model_management),
                    interrupt_check=lambda *args: model_management.throw_exception_if_processing_interrupted(),
                )
            )

        if _HAS_DETAIL:
            from .sample_detail_region import configure_factory_sampler
            configure_factory_sampler(_detail_sampler(nodes, comfy_sample, comfy_samplers))

        if _HAS_SPECTRAL:
            wrapper = getattr(comfy_samplers, "KSAMPLER", None)
            if not callable(wrapper):
                raise RuntimeError("ComfyUI KSAMPLER ABI is unavailable")
            native_sampler_factory = getattr(comfy_samplers, "sampler_object", None)
            if not callable(native_sampler_factory):
                raise RuntimeError("ComfyUI native sampler_object ABI is unavailable")
            from .sample_spectral_hires import configure_factory_sampler_wrapper
            configure_factory_sampler_wrapper(wrapper, native_sampler_factory)

        if _HAS_TAIL or _HAS_CROP_TAIL or _HAS_OUTPUT_STAGE:
            tail_adapters = _tail_adapters(comfy_samplers, comfy_sample, model_management)
            if _HAS_TAIL:
                from .sample_latent_tail import configure_factory_tail
                configure_factory_tail(*tail_adapters)
            if _HAS_CROP_TAIL:
                from .sample_crop_tail_paste import configure_factory_crop_tail
                configure_factory_crop_tail(*_crop_tail_adapters(*tail_adapters))
            if _HAS_OUTPUT_STAGE:
                from .sample_output_stage import configure_factory_output_stage
                configure_factory_output_stage(*_output_stage_adapters(*tail_adapters))

        if _HAS_SKIN:
            from .mask_skin_region import configure_factory_segmenters
            configure_factory_segmenters(*_skin_adapters(folder_paths))

        if _HAS_EYE_MASK:
            from .mask_eye_region import configure_factory_eye_seams
            configure_factory_eye_seams(*_eye_mask_adapters(folder_paths, model_management))

        if _HAS_SAVE:
            from .io_save_clean import configure_factory_io

            def allocate(prefix, width, height):
                return folder_paths.get_save_image_path(
                    prefix,
                    folder_paths.get_output_directory(),
                    width,
                    height,
                )

            configure_factory_io(
                allocate,
                model_management.throw_exception_if_processing_interrupted,
            )

        _BOOTSTRAPPED = True


__all__ = ["bootstrap_runtime"]
