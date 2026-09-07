"""Device-aware spectral progressive sampling for ComfyUI latent tensors."""

from __future__ import annotations

import importlib
import inspect
import math
from collections.abc import Callable
from typing import Any

import torch


class SpectralHiresError(RuntimeError):
    """Base class for visible failures owned by this block."""


class SpectralValidationError(SpectralHiresError):
    """The saved configuration or sampler input violates the contract."""


class SpectralNumericError(SpectralHiresError):
    """The transition equation cannot be evaluated safely in fp32."""


class UnsupportedLatentDtypeError(SpectralValidationError):
    """The latent dtype is outside the declared equivalence surface."""


class SpectralDeviceError(SpectralHiresError):
    """A device transfer or allocation failed during spectral work."""


class SpectralWorkspaceError(SpectralDeviceError):
    """The declared workspace ceiling would be exceeded."""


class FinalLatentContractError(SpectralHiresError):
    """A solver returned a tensor that is not the promised latent."""


_TRANSFORMS = frozenset({"dct", "dwt", "fft"})
_MODES = frozenset({"delta_optimal", "manual"})
CORE_SAMPLER_NAMES = (
    "euler",
    "euler_cfg_pp",
    "euler_ancestral",
    "euler_ancestral_cfg_pp",
    "heun",
    "heunpp2",
    "exp_heun_2_x0",
    "exp_heun_2_x0_sde",
    "dpm_2",
    "dpm_2_ancestral",
    "lms",
    "dpm_fast",
    "dpm_adaptive",
    "dpmpp_2s_ancestral",
    "dpmpp_2s_ancestral_cfg_pp",
    "dpmpp_sde",
    "dpmpp_sde_gpu",
    "dpmpp_2m",
    "dpmpp_2m_cfg_pp",
    "dpmpp_2m_sde",
    "dpmpp_2m_sde_gpu",
    "dpmpp_2m_sde_heun",
    "dpmpp_2m_sde_heun_gpu",
    "dpmpp_3m_sde",
    "dpmpp_3m_sde_gpu",
    "ddpm",
    "lcm",
    "ipndm",
    "ipndm_v",
    "deis",
    "res_multistep",
    "res_multistep_cfg_pp",
    "res_multistep_ancestral",
    "res_multistep_ancestral_cfg_pp",
    "gradient_estimation",
    "gradient_estimation_cfg_pp",
    "er_sde",
    "seeds_2",
    "seeds_3",
    "sa_solver",
    "sa_solver_pece",
    "ddim",
    "uni_pc",
    "uni_pc_bh2",
)
SPECTRAL_SAMPLER_NAMES = ("euler", "euler_ancestral")
_MODEL_PRESETS = {
    "flux": (203.615097, 1.915461),
    "wan21": (219.484718, 2.422687),
}
_KNOWN_MULTISTEP = frozenset(
    {
        "lms",
        "deis",
        "ipndm",
        "ipndm_v",
        "dpmpp_2m",
        "dpmpp_2m_sde",
        "dpmpp_3m_sde",
    }
)
_UNSUPPORTED_DIRECT_DTYPES = frozenset(
    dtype
    for dtype in (
        getattr(torch, "float8_e4m3fn", None),
        getattr(torch, "float8_e5m2", None),
        getattr(torch, "float8_e4m3fnuz", None),
        getattr(torch, "float8_e5m2fnuz", None),
    )
    if dtype is not None
)
_SUPPORTED_LATENT_DTYPES = frozenset({torch.float16, torch.bfloat16, torch.float32})
_FACTORY_SAMPLER_WRAPPER: Callable[[Callable[..., torch.Tensor]], Any] | None = None
_FACTORY_NATIVE_SAMPLER_FACTORY: Callable[[str], Any] | None = None


def _randn(shape: tuple[int, ...], *, generator: torch.Generator, device: torch.device) -> torch.Tensor:
    return torch.randn(shape, generator=generator, device=device, dtype=torch.float32)


def _empty(shape: tuple[int, ...], *, device: torch.device) -> torch.Tensor:
    return torch.empty(shape, device=device, dtype=torch.float32)


def _parse_csv(name: str, text: str) -> tuple[float, ...]:
    if not isinstance(text, str):
        raise SpectralValidationError(f"{name} must be a comma-separated string")
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise SpectralValidationError(f"{name} must contain at least one value")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise SpectralValidationError(f"{name} contains a non-numeric value") from exc


def _default_sampler_resolver(name: str) -> Callable[..., torch.Tensor]:
    if name in {"dpm_fast", "dpm_adaptive", "lcm"}:
        raise KeyError(name)
    sampling = importlib.import_module("comfy.k_diffusion.sampling")
    sampler = getattr(sampling, f"sample_{name}")
    if not callable(sampler):
        raise KeyError(name)
    return sampler


def _dct_matrix(length: int, device: torch.device) -> torch.Tensor:
    n = torch.arange(length, device=device, dtype=torch.float32)
    k = torch.arange(length, device=device, dtype=torch.float32).unsqueeze(1)
    matrix = torch.cos(math.pi * (n + 0.5) * k / length)
    matrix[0].mul_(math.sqrt(1.0 / length))
    if length > 1:
        matrix[1:].mul_(math.sqrt(2.0 / length))
    return matrix


def _dct_reduce(
    value: torch.Tensor,
    target_height: int,
    target_width: int,
    interrupt_check: Callable[[], None],
) -> torch.Tensor:
    interrupt_check()
    work = value.float()
    height_matrix = _dct_matrix(value.shape[-2], value.device)
    width_matrix = _dct_matrix(value.shape[-1], value.device)
    interrupt_check()
    coefficients = torch.einsum(
        "ih,bchw,jw->bcij", height_matrix, work, width_matrix
    )[..., :target_height, :target_width]
    interrupt_check()
    inverse_height = _dct_matrix(target_height, value.device).T
    inverse_width = _dct_matrix(target_width, value.device).T
    return torch.einsum(
        "hi,bcij,wj->bchw", inverse_height, coefficients, inverse_width
    )


def _dct_expand(
    value: torch.Tensor,
    target_height: int,
    target_width: int,
    sigma: float,
    generator: torch.Generator,
    interrupt_check: Callable[[], None],
) -> torch.Tensor:
    interrupt_check()
    height_matrix = _dct_matrix(value.shape[-2], value.device)
    width_matrix = _dct_matrix(value.shape[-1], value.device)
    low = torch.einsum(
        "ih,bchw,jw->bcij", height_matrix, value.float(), width_matrix
    )
    coefficients = _randn(
        (*value.shape[:-2], target_height, target_width),
        generator=generator,
        device=value.device,
    ).mul_(sigma)
    coefficients[..., : value.shape[-2], : value.shape[-1]] = low
    interrupt_check()
    inverse_height = _dct_matrix(target_height, value.device).T
    inverse_width = _dct_matrix(target_width, value.device).T
    return torch.einsum(
        "hi,bcij,wj->bchw", inverse_height, coefficients, inverse_width
    )


def _dwt_expand(
    value: torch.Tensor,
    sigma: float,
    generator: torch.Generator,
    interrupt_check: Callable[[], None],
) -> torch.Tensor:
    interrupt_check()
    details = _randn(
        (3,) + tuple(value.shape), generator=generator, device=value.device
    ).mul_(sigma)
    ll = value.float()
    lh, hl, hh = details.unbind(0)
    output = _empty(
        (*value.shape[:-2], value.shape[-2] * 2, value.shape[-1] * 2),
        device=value.device,
    )
    interrupt_check()
    output[..., 0::2, 0::2] = (ll + lh + hl + hh) * 0.5
    output[..., 0::2, 1::2] = (ll - lh + hl - hh) * 0.5
    output[..., 1::2, 0::2] = (ll + lh - hl - hh) * 0.5
    output[..., 1::2, 1::2] = (ll - lh - hl + hh) * 0.5
    return output


def _fft_expand(
    value: torch.Tensor,
    target_height: int,
    target_width: int,
    sigma: float,
    generator: torch.Generator,
    interrupt_check: Callable[[], None],
) -> torch.Tensor:
    interrupt_check()
    low = torch.fft.fftshift(
        torch.fft.fft2(value.float(), norm="ortho"), dim=(-2, -1)
    )
    noise = _randn(
        (*value.shape[:-2], target_height, target_width),
        generator=generator,
        device=value.device,
    )
    coefficients = torch.fft.fftshift(
        torch.fft.fft2(noise, norm="ortho"), dim=(-2, -1)
    ).mul_(sigma)
    height_start = (target_height - value.shape[-2]) // 2
    width_start = (target_width - value.shape[-1]) // 2
    coefficients[
        ...,
        height_start : height_start + value.shape[-2],
        width_start : width_start + value.shape[-1],
    ] = low
    interrupt_check()
    return torch.fft.ifft2(
        torch.fft.ifftshift(coefficients, dim=(-2, -1)), norm="ortho"
    ).real


class SpectralHiresSampler:
    """Configured callable used at the ComfyUI ``SAMPLER`` seam."""

    def __init__(
        self,
        *,
        base_sampler_name: str,
        base_sampler: Callable[..., torch.Tensor],
        transform: str,
        mode: str,
        model_preset: str,
        scales: tuple[float, ...],
        delta: float,
        manual_sigmas: tuple[float, ...],
        spectrum_A: float,
        spectrum_beta: float,
        seed: int,
        interrupt_check: Callable[[], None],
        workspace_limit_bytes: int | None,
    ) -> None:
        self.base_sampler_name = base_sampler_name
        self.base_sampler = base_sampler
        self.transform = transform
        self.mode = mode
        self.model_preset = model_preset
        self.scales = scales
        self.delta = delta
        self.manual_sigmas = manual_sigmas
        self.spectrum_A = spectrum_A
        self.spectrum_beta = spectrum_beta
        self.seed = seed
        self.interrupt_check = interrupt_check
        self.workspace_limit_bytes = workspace_limit_bytes
        self.last_transition_steps: tuple[int, ...] = ()
        self.last_transition_seeds: tuple[int, ...] = ()
        self._active_workspace: list[str] = []

    def transition_thresholds(self, height: int, width: int) -> tuple[float, ...]:
        if self.mode == "manual":
            return self.manual_sigmas
        amplitude, beta = (
            (self.spectrum_A, self.spectrum_beta)
            if self.model_preset == "custom"
            else _MODEL_PRESETS[self.model_preset]
        )
        omega_max = min(height, width) / 2.0
        if omega_max <= 0:
            raise SpectralValidationError("latent spatial dimensions must be positive")
        thresholds = []
        fp32_log_min = math.log(torch.finfo(torch.float32).tiny)
        for scale in self.scales[:-1]:
            omega = scale * omega_max
            log_power = math.log(amplitude) - beta * math.log(omega)
            if log_power <= fp32_log_min:
                raise SpectralNumericError(
                    "spectrum amplitude is not numerically positive at this resolution"
                )
            if log_power > 709.0:
                log_denominator = 2.0 * log_power
            else:
                power = math.exp(log_power)
                remainder = 1.0 + power - self.delta
                if remainder <= 0 or not math.isfinite(remainder):
                    raise SpectralNumericError("spectral threshold denominator is invalid")
                log_denominator = log_power + math.log(remainder)
            exponent = 0.5 * (math.log(self.delta) - log_denominator)
            if exponent > 709.0:
                raise SpectralNumericError("spectral threshold calculation overflowed")
            root = math.exp(exponent)
            threshold = 1.0 / (1.0 + root)
            if not math.isfinite(threshold):
                raise SpectralNumericError("spectral threshold is non-finite")
            thresholds.append(threshold)
        return tuple(thresholds)

    def _validate_latent(self, value: torch.Tensor) -> None:
        if not isinstance(value, torch.Tensor):
            raise SpectralValidationError("latent must be a torch.Tensor")
        if value.ndim == 5 and value.shape[2] > 1:
            raise SpectralValidationError(
                "video sampling is out of contract for sample.spectral-hires; "
                f"observed shape {tuple(value.shape)}"
            )
        if value.ndim == 5 and value.shape[2] == 1:
            pass
        elif value.ndim != 4:
            raise SpectralValidationError(
                "image sampler requires BCHW or single-frame BCTHW; "
                f"observed shape {tuple(value.shape)}"
            )
        if value.dtype in _UNSUPPORTED_DIRECT_DTYPES:
            raise UnsupportedLatentDtypeError(
                f"direct fp8 latent dtype {value.dtype} is unsupported"
            )
        if value.dtype not in _SUPPORTED_LATENT_DTYPES:
            raise UnsupportedLatentDtypeError(
                f"latent dtype {value.dtype} is unsupported; expected fp16, bf16, or fp32"
            )
        if value.shape[0] < 1 or value.shape[1] < 1:
            raise SpectralValidationError(
                "latent must hold at least one batch item and channel"
            )
        if value.shape[-2] < 1 or value.shape[-1] < 1:
            raise SpectralValidationError("latent spatial dimensions must be positive")
        if not bool(torch.isfinite(value).all()):
            raise SpectralNumericError("latent must contain only finite values")

    def _validate_sigmas(
        self, sigmas: torch.Tensor, *, require_terminal_zero: bool = True
    ) -> None:
        if not isinstance(sigmas, torch.Tensor) or sigmas.ndim != 1:
            raise SpectralValidationError("sigma schedule must be a rank-one tensor")
        if len(sigmas) < 2:
            raise SpectralValidationError(
                "multi-stage sampling requires at least two sigma values"
            )
        if not bool(torch.isfinite(sigmas).all()):
            raise SpectralValidationError("sigma schedule must be finite")
        if not bool(((sigmas >= 0) & (sigmas <= 1)).all()):
            raise SpectralValidationError(
                "sigma schedule must stay in normalized flow-time range [0,1]"
            )
        if not bool((sigmas[:-1] > sigmas[1:]).all()):
            raise SpectralValidationError("sigma schedule must be strictly descending")
        if require_terminal_zero and float(sigmas[-1]) != 0.0:
            raise SpectralValidationError("sigma schedule must end exactly at zero")

    def _geometry(self, height: int, width: int) -> tuple[tuple[int, int], ...]:
        stages = tuple(
            (round(scale * height), round(scale * width)) for scale in self.scales
        )
        if any(stage_height < 1 or stage_width < 1 for stage_height, stage_width in stages):
            raise SpectralValidationError("a rounded scale produces an empty spatial stage")
        if self.transform == "dwt":
            for current, target in zip(stages, stages[1:]):
                if target != (current[0] * 2, current[1] * 2):
                    raise SpectralValidationError(
                        "DWT rounding shape drift: each declared target must exactly double both axes"
                    )
        if stages[-1] != (height, width):
            raise SpectralValidationError("final stage does not equal full latent geometry")
        return stages

    def _transition_steps(self, sigmas: torch.Tensor, height: int, width: int) -> tuple[int, ...]:
        thresholds = self.transition_thresholds(height, width)
        steps: list[int] = []
        for threshold in thresholds:
            step = next(
                (
                    index
                    for index in range(len(sigmas) - 1)
                    if float(sigmas[index]) <= threshold
                ),
                None,
            )
            if step is None:
                raise SpectralValidationError(
                    "requested transition is unreachable before the terminal sigma"
                )
            if steps and step <= steps[-1]:
                raise SpectralValidationError(
                    "transition thresholds collide or are not ordered on this schedule"
                )
            steps.append(step)
        return tuple(steps)

    def _check_workspace(self, value: torch.Tensor) -> None:
        if self.workspace_limit_bytes is None:
            return
        batch_planes = value.shape[0] * value.shape[1]
        height, width = value.shape[-2:]
        estimated = int(
            batch_planes * height * width * 4 * 8
            + (height * height + width * width) * 4
        )
        if estimated > self.workspace_limit_bytes:
            raise SpectralWorkspaceError(
                "spectral workspace refused: "
                f"requested limit={self.workspace_limit_bytes} bytes, current=0 bytes, "
                f"estimated={estimated} bytes"
            )

    @staticmethod
    def _validate_result(
        value: Any,
        *,
        shape: tuple[int, ...],
        dtype: torch.dtype,
        device: torch.device,
    ) -> None:
        if not isinstance(value, torch.Tensor):
            raise FinalLatentContractError("base sampler did not return a tensor")
        differences = []
        if tuple(value.shape) != shape:
            differences.append(f"shape={tuple(value.shape)} expected={shape}")
        if value.dtype != dtype:
            differences.append(f"dtype={value.dtype} expected={dtype}")
        if value.device != device:
            differences.append(f"device={value.device} expected={device}")
        if differences:
            raise FinalLatentContractError(
                "malformed latent returned by base sampler: " + "; ".join(differences)
            )
        if not bool(torch.isfinite(value).all()):
            raise SpectralNumericError("base sampler returned a non-finite latent")

    def _expand(
        self,
        value: torch.Tensor,
        target: tuple[int, int],
        sigma: float,
        seed: int,
    ) -> torch.Tensor:
        generator = torch.Generator(device=value.device)
        generator.manual_seed(seed)
        if self.transform == "dwt":
            return _dwt_expand(value, sigma, generator, self.interrupt_check)
        if self.transform == "dct":
            return _dct_expand(
                value, target[0], target[1], sigma, generator, self.interrupt_check
            )
        return _fft_expand(
            value, target[0], target[1], sigma, generator, self.interrupt_check
        )

    def _transform_or_raise(self, operation: Callable[[], torch.Tensor]) -> torch.Tensor:
        try:
            return operation()
        except RuntimeError as exc:
            message = str(exc).lower()
            if "out of memory" in message or "alloc" in message:
                raise SpectralDeviceError(
                    f"spectral device allocation failed: {exc}"
                ) from exc
            raise

    @torch.no_grad()
    def sample(
        self,
        model: Any,
        x: torch.Tensor,
        sigmas: torch.Tensor,
        *,
        extra_args: dict[str, Any] | None = None,
        callback: Callable[[dict[str, Any]], None] | None = None,
        disable: bool | None = None,
    ) -> torch.Tensor:
        self.last_transition_steps = ()
        self.last_transition_seeds = ()
        self._validate_latent(x)
        single_frame_bcthw = x.ndim == 5
        spatial_x = x.squeeze(2) if single_frame_bcthw else x
        original_shape = tuple(x.shape)
        original_dtype = x.dtype
        original_device = x.device

        if len(self.scales) == 1:
            result = self.base_sampler(
                model,
                x,
                sigmas,
                extra_args=extra_args,
                callback=callback,
                disable=disable,
            )
            self._validate_result(
                result,
                shape=original_shape,
                dtype=original_dtype,
                device=original_device,
            )
            return result

        self._validate_sigmas(sigmas)
        stages = self._geometry(spatial_x.shape[-2], spatial_x.shape[-1])
        steps = self._transition_steps(sigmas, spatial_x.shape[-2], spatial_x.shape[-1])
        seeds = tuple(self.seed + 10_000 * number for number in range(1, len(steps) + 1))
        self.last_transition_steps = steps
        self.last_transition_seeds = seeds
        self._check_workspace(spatial_x)

        self._active_workspace.append("spectral-fp32")
        last_callback_index = -1

        def callback_for(offset: int) -> Callable[[dict[str, Any]], None] | None:
            if callback is None:
                return None

            def rebased(info: dict[str, Any]) -> None:
                nonlocal last_callback_index
                updated = dict(info)
                global_index = offset + int(updated["i"])
                if global_index <= last_callback_index:
                    raise SpectralValidationError(
                        "base sampler callback indices are not strictly monotonic"
                    )
                last_callback_index = global_index
                updated["i"] = global_index
                callback(updated)

            return rebased

        try:
            self.interrupt_check()
            current = self._transform_or_raise(
                lambda: _dct_reduce(
                    spatial_x, stages[0][0], stages[0][1], self.interrupt_check
                )
            ).to(dtype=original_dtype)
            segment_start = 0
            aligned_start_sigma: float | None = None
            for transition_number, (step, target, transition_seed) in enumerate(
                zip(steps, stages[1:], seeds), start=1
            ):
                segment_sigmas = sigmas[segment_start : step + 1]
                if aligned_start_sigma is not None:
                    segment_sigmas = segment_sigmas.clone()
                    segment_sigmas[0] = aligned_start_sigma
                self._validate_sigmas(
                    segment_sigmas, require_terminal_zero=False
                )
                solver_current = current.unsqueeze(2) if single_frame_bcthw else current
                solver_result = self.base_sampler(
                    model,
                    solver_current,
                    segment_sigmas,
                    extra_args=extra_args,
                    callback=callback_for(segment_start),
                    disable=disable,
                )
                expected_stage = stages[transition_number - 1]
                self._validate_result(
                    solver_result,
                    shape=(*original_shape[:-2], *expected_stage),
                    dtype=original_dtype,
                    device=original_device,
                )
                current = solver_result.squeeze(2) if single_frame_bcthw else solver_result
                self.interrupt_check()
                transition_sigma = float(sigmas[step])
                ratio = self.scales[transition_number] / self.scales[transition_number - 1]
                expanded = self._transform_or_raise(
                    lambda: self._expand(
                        current, target, transition_sigma, transition_seed
                    )
                )
                kappa = ratio / (1.0 + (ratio - 1.0) * transition_sigma)
                current = expanded.mul(kappa).to(dtype=original_dtype)
                expected_expanded_shape = (*spatial_x.shape[:-2], *target)
                self._validate_result(
                    current,
                    shape=expected_expanded_shape,
                    dtype=original_dtype,
                    device=original_device,
                )
                segment_start = step
                aligned_start_sigma = transition_sigma * kappa

            final_sigmas = sigmas[segment_start:].clone()
            final_sigmas[0] = aligned_start_sigma
            self._validate_sigmas(final_sigmas)
            solver_current = current.unsqueeze(2) if single_frame_bcthw else current
            solver_result = self.base_sampler(
                model,
                solver_current,
                final_sigmas,
                extra_args=extra_args,
                callback=callback_for(segment_start),
                disable=disable,
            )
            self._validate_result(
                solver_result,
                shape=original_shape,
                dtype=original_dtype,
                device=original_device,
            )
            return solver_result
        finally:
            self._active_workspace.clear()

    __call__ = sample


def create_spectral_hires_sampler(
    *,
    base_sampler: str,
    transform: str,
    mode: str,
    model_preset: str,
    scales: str,
    delta: float,
    manual_sigmas: str,
    spectrum_A: float,
    spectrum_beta: float,
    seed: int,
    sampler_resolver: Callable[[str], Callable[..., torch.Tensor]] | None = None,
    interrupt_check: Callable[[], None] | None = None,
    workspace_limit_bytes: int | None = None,
) -> SpectralHiresSampler:
    """Validate widgets and return one configured spectral sampler."""

    if transform not in _TRANSFORMS:
        raise SpectralValidationError(f"unknown spectral transform {transform!r}")
    if mode not in _MODES:
        raise SpectralValidationError(f"unknown transition mode {mode!r}")
    if model_preset not in {*_MODEL_PRESETS, "custom"}:
        raise SpectralValidationError(f"unknown model preset {model_preset!r}")

    parsed_scales = _parse_csv("scales", scales)
    for index, scale in enumerate(parsed_scales):
        if not math.isfinite(scale) or not 0.0 < scale <= 1.0:
            raise SpectralValidationError(
                f"scale at index {index} must be finite and in (0,1]; got {scale!r}"
            )
    if any(left >= right for left, right in zip(parsed_scales, parsed_scales[1:])):
        raise SpectralValidationError("scales must be strictly increasing")
    if not math.isclose(parsed_scales[-1], 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise SpectralValidationError("scales must end at full resolution 1.0")
    if transform == "dwt":
        for left, right in zip(parsed_scales, parsed_scales[1:]):
            if not math.isclose(right / left, 2.0, rel_tol=0.0, abs_tol=1e-6):
                raise SpectralValidationError(
                    "DWT requires every adjacent scale ratio to equal 2"
                )

    parsed_manual: tuple[float, ...] = ()
    if mode == "manual":
        parsed_manual = _parse_csv("manual_sigmas", manual_sigmas)
        if len(parsed_manual) != len(parsed_scales) - 1:
            raise SpectralValidationError(
                "manual_sigmas count must equal the number of transitions"
            )
        if any(
            not math.isfinite(value) or not 0.0 < value < 1.0
            for value in parsed_manual
        ):
            raise SpectralValidationError(
                "manual_sigmas must be finite and strictly inside (0,1)"
            )
        if any(left <= right for left, right in zip(parsed_manual, parsed_manual[1:])):
            raise SpectralValidationError("manual_sigmas must be strictly decreasing")
    elif not math.isfinite(delta) or not 0.0001 <= delta <= 0.5:
        raise SpectralValidationError("delta must be finite and in [0.0001,0.5]")

    if mode == "delta_optimal" and model_preset == "custom":
        if not math.isfinite(spectrum_A) or spectrum_A <= 0.0:
            raise SpectralValidationError("custom spectrum_A must be finite and positive")
        if not math.isfinite(spectrum_beta) or not 0.0 <= spectrum_beta <= 10.0:
            raise SpectralValidationError("custom spectrum_beta must be finite and in [0,10]")

    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2_147_483_647:
        raise SpectralValidationError("spectral seed must be an integer in [0,2147483647]")
    if workspace_limit_bytes is not None and workspace_limit_bytes < 0:
        raise SpectralValidationError("workspace ceiling cannot be negative")
    if base_sampler in _KNOWN_MULTISTEP:
        raise SpectralValidationError(
            f"multistep sampler {base_sampler!r} has no declared restart semantics"
        )

    resolver = sampler_resolver or _default_sampler_resolver
    try:
        resolved_sampler = resolver(base_sampler)
    except (AttributeError, ImportError, KeyError) as exc:
        raise SpectralValidationError(
            f"unknown base sampler {base_sampler!r}; no fallback is allowed"
        ) from exc
    if not callable(resolved_sampler):
        raise SpectralValidationError(f"base sampler {base_sampler!r} is not callable")
    try:
        inspect.signature(resolved_sampler).bind_partial(
            None, None, None, extra_args={}, callback=None, disable=None
        )
    except (TypeError, ValueError) as exc:
        raise SpectralValidationError(
            f"base sampler {base_sampler!r} has an incompatible callable signature"
        ) from exc

    return SpectralHiresSampler(
        base_sampler_name=base_sampler,
        base_sampler=resolved_sampler,
        transform=transform,
        mode=mode,
        model_preset=model_preset,
        scales=parsed_scales,
        delta=float(delta),
        manual_sigmas=parsed_manual,
        spectrum_A=float(spectrum_A),
        spectrum_beta=float(spectrum_beta),
        seed=seed,
        interrupt_check=interrupt_check or (lambda: None),
        workspace_limit_bytes=workspace_limit_bytes,
    )


def create_matrix_spectral_sampler(
    *,
    base_sampler: str,
    transform: str,
    mode: str,
    model_preset: str,
    scales: str,
    delta: float,
    manual_sigmas: str,
    spectrum_A: float,
    spectrum_beta: float,
    seed: int,
    sampler_wrapper: Callable[[Callable[..., torch.Tensor]], Any],
    native_sampler_factory: Callable[[str], Any],
    sampler_resolver: Callable[[str], Callable[..., torch.Tensor]] | None = None,
    interrupt_check: Callable[[], None] | None = None,
    workspace_limit_bytes: int | None = None,
) -> Any:
    """Return the exact native sampler or one proof-gated spectral wrapper."""

    if base_sampler not in CORE_SAMPLER_NAMES:
        raise SpectralValidationError(f"unknown core sampler {base_sampler!r}")
    if not callable(native_sampler_factory):
        raise TypeError("native sampler factory must be callable")
    if not callable(sampler_wrapper):
        raise TypeError("spectral sampler wrapper must be callable")

    parsed_scales = _parse_csv("scales", scales)
    if parsed_scales == (1.0,):
        return native_sampler_factory(base_sampler)
    if base_sampler not in SPECTRAL_SAMPLER_NAMES:
        raise SpectralValidationError(
            f"sampler {base_sampler!r} is available in native scales=1.0 mode but has no "
            "proved spectral restart contract"
        )

    configured = create_spectral_hires_sampler(
        base_sampler=base_sampler,
        transform=transform,
        mode=mode,
        model_preset=model_preset,
        scales=scales,
        delta=delta,
        manual_sigmas=manual_sigmas,
        spectrum_A=spectrum_A,
        spectrum_beta=spectrum_beta,
        seed=seed,
        sampler_resolver=sampler_resolver,
        interrupt_check=interrupt_check,
        workspace_limit_bytes=workspace_limit_bytes,
    )
    return sampler_wrapper(configured)


def configure_factory_sampler_wrapper(
    wrapper: Callable[[Callable[..., torch.Tensor]], Any],
    native_sampler_factory: Callable[[str], Any] | None = None,
) -> None:
    """Install ComfyUI's spectral wrapper and exact native sampler selector."""
    global _FACTORY_NATIVE_SAMPLER_FACTORY, _FACTORY_SAMPLER_WRAPPER
    if not callable(wrapper):
        raise TypeError("factory sampler wrapper must be callable")
    if native_sampler_factory is not None and not callable(native_sampler_factory):
        raise TypeError("native sampler factory must be callable")
    _FACTORY_SAMPLER_WRAPPER = wrapper
    _FACTORY_NATIVE_SAMPLER_FACTORY = native_sampler_factory


def execute_utility_operation(item):
    """Factory seam returning the SAMPLER object used by core advanced sampling."""
    if not isinstance(item, dict):
        raise SpectralValidationError("sample.spectral-hires requires an input mapping")
    if _FACTORY_SAMPLER_WRAPPER is None:
        raise SpectralValidationError(
            "sample.spectral-hires runtime KSAMPLER adapter is not configured by the pack bootstrap"
        )
    if _FACTORY_NATIVE_SAMPLER_FACTORY is None:
        raise SpectralValidationError(
            "sample.spectral-hires native sampler factory is not configured by the pack bootstrap"
        )
    sampler = create_matrix_spectral_sampler(
        base_sampler=item.get("base_sampler", "euler"),
        transform=item.get("transform", "dwt"),
        mode=item.get("mode", "delta_optimal"),
        model_preset=item.get("model_preset", "custom"),
        scales=item.get("scales", "0.5,1.0"),
        delta=item.get("delta", 0.01),
        manual_sigmas=item.get("manual_sigmas", "0.85"),
        spectrum_A=item.get("spectrum_a", 203.615097),
        spectrum_beta=item.get("spectrum_beta", 1.37),
        seed=item.get("spectral_seed", 1088164640),
        sampler_wrapper=_FACTORY_SAMPLER_WRAPPER,
        native_sampler_factory=_FACTORY_NATIVE_SAMPLER_FACTORY,
    )
    return (sampler,)


__all__ = [
    "CORE_SAMPLER_NAMES",
    "FinalLatentContractError",
    "SpectralDeviceError",
    "SpectralHiresError",
    "SpectralHiresSampler",
    "SpectralNumericError",
    "SpectralValidationError",
    "SpectralWorkspaceError",
    "SPECTRAL_SAMPLER_NAMES",
    "create_matrix_spectral_sampler",
    "UnsupportedLatentDtypeError",
    "configure_factory_sampler_wrapper",
    "create_spectral_hires_sampler",
    "execute_utility_operation",
]
