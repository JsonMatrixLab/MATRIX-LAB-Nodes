"""sample.latent-tail: masked latent continuation tail controlled by start sigma.

The block owns the schedule mathematics and the refusal boundary. ComfyUI's own sampling seam
(noise scaling, masked inpaint wrapper, sampler objects) is reached through an injected adapter so
the block stays pure and testable offline. Nothing here loads weights or mutates its inputs.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import torch

__all__ = [
    "BETA57_ALPHA",
    "BETA57_BETA",
    "CORE_SAMPLER_NAMES",
    "CORE_SCHEDULER_NAMES",
    "MAX_TOTAL_STEPS",
    "SCHEDULER_NAMES",
    "START_SIGMA_CEILING",
    "START_SIGMA_WARN",
    "STEPS_MAX",
    "STEPS_MIN",
    "TailError",
    "TailRefusalError",
    "TailSchedule",
    "TailValidationError",
    "beta_schedule",
    "beta57_schedule",
    "configure_factory_tail",
    "execute_utility_operation",
    "flow_sigma_table",
    "latent_tail",
    "resolve_tail_sigmas",
]

_LOG = logging.getLogger("MATRIX.LatentTail")

# Pinned ComfyUI Core inventory (0.33 line); the same list MATRIXSpectralSampler ships.
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
# ComfyUI Core `SCHEDULER_NAMES` (0.33.0, comfy/samplers.py SCHEDULER_HANDLERS order).
CORE_SCHEDULER_NAMES = (
    "simple",
    "sgm_uniform",
    "karras",
    "exponential",
    "ddim_uniform",
    "beta",
    "normal",
    "linear_quadratic",
    "kl_optimal",
)
# `beta57` is computed here (beta distribution quantiles, alpha 0.5 / beta 0.7); no RES4LYF.
SCHEDULER_NAMES = ("beta57", *CORE_SCHEDULER_NAMES)
BETA57_ALPHA = 0.5
BETA57_BETA = 0.7

START_SIGMA_MIN = 0.05
START_SIGMA_MAX = 0.60
START_SIGMA_WARN = 0.35
START_SIGMA_CEILING = 1.0
STEPS_MIN = 1
STEPS_MAX = 12
MAX_TOTAL_STEPS = 256
_FLOAT_DTYPES = frozenset({torch.float16, torch.bfloat16, torch.float32, torch.float64})


class TailError(RuntimeError):
    """Base class for sample.latent-tail failures."""


class TailValidationError(TailError, ValueError):
    """An input violates the contract before any model work."""


class TailRefusalError(TailError):
    """The request is well-formed but outside the accepted tail boundary."""


@dataclass(frozen=True)
class TailSchedule:
    """The resolved sigma tail and the facts that produced it."""

    sigmas: tuple[float, ...]
    total_steps: int
    scheduler: str
    start_sigma: float
    warnings: tuple[str, ...] = ()

    @property
    def steps(self) -> int:
        return len(self.sigmas) - 1

    @property
    def denoise_equivalent(self) -> float:
        return self.steps / self.total_steps

    def report(self) -> str:
        values = ", ".join(f"{value:.3f}" for value in self.sigmas)
        return (
            f"sigmas [{values}] scheduler={self.scheduler} total_steps={self.total_steps} "
            f"denoise_equivalent={self.denoise_equivalent:.3f} requested_start={self.start_sigma:.3f}"
        )


# --- schedule mathematics -----------------------------------------------------------------


def flow_sigma_table(shift: float = 6.0, count: int = 1000) -> tuple[float, ...]:
    """Ascending sigma table of a discrete flow model (`ModelSamplingDiscreteFlow`).

    Index 0 holds t = 1/count and the last index holds t = 1, exactly like the
    `model_sampling.sigmas` buffer ComfyUI builds for `ModelSamplingAuraFlow` shift.
    """
    if not (isinstance(shift, (int, float)) and math.isfinite(shift) and shift > 0):
        raise TailValidationError("shift must be a finite positive number")
    if not (isinstance(count, int) and count >= 2):
        raise TailValidationError("count must be an integer >= 2")
    return tuple(
        shift * t / (1.0 + (shift - 1.0) * t) for t in ((i + 1) / count for i in range(count))
    )


def beta_schedule(
    sigma_table: Sequence[float], steps: int, alpha: float, beta: float
) -> tuple[float, ...]:
    """ComfyUI Core `beta_scheduler` on an explicit ascending sigma table.

    Mirrors comfy/samplers.py: quantiles of the beta distribution over `steps` points select
    timesteps into the table, consecutive duplicates collapse, and the schedule ends at 0.0.
    """
    import numpy
    import scipy.stats

    if not (isinstance(steps, int) and steps >= 1):
        raise TailValidationError("schedule steps must be an integer >= 1")
    total_timesteps = len(sigma_table) - 1
    if total_timesteps < 1:
        raise TailValidationError("sigma table must hold at least two entries")
    ts = 1 - numpy.linspace(0, 1, steps, endpoint=False)
    ts = numpy.rint(scipy.stats.beta.ppf(ts, alpha, beta) * total_timesteps)
    sigs: list[float] = []
    last_t = -1
    for t in ts:
        if t != last_t:
            sigs.append(float(sigma_table[int(t)]))
        last_t = t
    sigs.append(0.0)
    return tuple(sigs)


def beta57_schedule(sigma_table: Sequence[float]) -> Callable[[int], tuple[float, ...]]:
    """Schedule factory for `beta57` over a fixed sigma table."""
    table = tuple(float(value) for value in sigma_table)
    return lambda steps: beta_schedule(table, steps, BETA57_ALPHA, BETA57_BETA)


def _validate_start_sigma(start_sigma: Any) -> float:
    if isinstance(start_sigma, bool) or not isinstance(start_sigma, (int, float)):
        raise TailValidationError("start_sigma must be a number")
    value = float(start_sigma)
    if not math.isfinite(value) or value <= 0.0:
        raise TailValidationError("start_sigma must be finite and positive")
    if value > START_SIGMA_CEILING:
        raise TailRefusalError(
            f"start_sigma {value:.3f} is above the base pass's first sigma "
            f"({START_SIGMA_CEILING:.1f}); a tail cannot restart the base pass"
        )
    return value


def _validate_steps(steps: Any) -> int:
    if isinstance(steps, bool) or not isinstance(steps, int):
        raise TailValidationError("steps must be an integer")
    if not STEPS_MIN <= steps <= STEPS_MAX:
        raise TailValidationError(f"steps must be within {STEPS_MIN}..{STEPS_MAX}")
    return steps


def resolve_tail_sigmas(
    schedule: Callable[[int], Sequence[float]],
    *,
    start_sigma: float,
    steps: int,
    scheduler: str = "beta57",
    max_total_steps: int = MAX_TOTAL_STEPS,
) -> TailSchedule:
    """Find the schedule tail whose first sigma is closest at or below `start_sigma`.

    `schedule(total)` returns the full descending schedule of `total` steps ending at 0.0, exactly
    what `BasicScheduler` computes before it keeps the last `steps + 1` entries. The search runs
    over every total step count from `steps` upward and treats `start_sigma` as a ceiling, so the
    resolved tail is always one that the Core scheduler itself would have produced through
    `steps / denoise` without exceeding the requested noise level. Ties prefer the smaller total
    step count.
    """
    if not callable(schedule):
        raise TailValidationError("schedule must be callable")
    if scheduler not in SCHEDULER_NAMES:
        raise TailValidationError(f"unknown scheduler {scheduler!r}")
    requested = _validate_start_sigma(start_sigma)
    count = _validate_steps(steps)
    if not (isinstance(max_total_steps, int) and max_total_steps >= count):
        raise TailValidationError("max_total_steps must be an integer >= steps")

    best: tuple[float, ...] | None = None
    best_total = 0
    best_distance = math.inf
    rejected: list[str] = []
    for total in range(count, max_total_steps + 1):
        full = tuple(float(value) for value in schedule(total))
        if len(full) < count + 1:
            continue
        tail = full[-(count + 1):]
        if tail[0] > requested + 1e-9:
            continue
        try:
            _validate_tail(tail)
        except TailRefusalError as error:
            # A degraded sigma table (low-precision buffer, duplicate entries) can hand back a
            # tail with equal neighbours for some totals. Skip it, keep the evidence, and let a
            # valid total win. Seen on the RTX 5090 Krea 2 pod, prompt 0a881049 (2026-09-02).
            rejected.append(
                f"total={total} tail={[round(v, 5) for v in tail]} ({error})"
            )
            continue
        distance = requested - tail[0]
        if distance < best_distance - 1e-12:
            best, best_total, best_distance = tail, total, distance
    if rejected:
        _LOG.warning(
            "schedule %r produced %d invalid tail candidate(s); first: %s",
            scheduler, len(rejected), rejected[0],
        )
    if best is None:
        detail = f"; first invalid candidate: {rejected[0]}" if rejected else ""
        raise TailRefusalError(
            f"no valid schedule tail starts at or below start_sigma {requested:.3f}{detail}"
        )

    warnings: list[str] = []
    resolved_start = best[0]
    if resolved_start > START_SIGMA_WARN:
        warnings.append(
            f"resolved normalized-schedule start sigma {resolved_start:.3f} is above "
            f"{START_SIGMA_WARN:.2f}; normalized flow schedules may increase "
            "mid-frequency rewrite risk from here"
        )
    return TailSchedule(
        sigmas=best,
        total_steps=best_total,
        scheduler=scheduler,
        start_sigma=requested,
        warnings=tuple(warnings),
    )


def _validate_tail(sigmas: Sequence[float]) -> None:
    if len(sigmas) < 2:
        raise TailRefusalError("a tail needs at least one step")
    if sigmas[-1] != 0.0:
        raise TailRefusalError("a tail must end at sigma 0")
    if any(not math.isfinite(value) for value in sigmas):
        raise TailRefusalError("tail sigmas must be finite")
    if any(later >= earlier for earlier, later in zip(sigmas, sigmas[1:])):
        raise TailRefusalError("tail sigmas must be strictly decreasing")
    if sigmas[0] > START_SIGMA_CEILING:
        raise TailRefusalError("tail starts above the base pass's first sigma")


# --- latent execution ---------------------------------------------------------------------


def _validate_latent(latent: Any) -> torch.Tensor:
    if not isinstance(latent, Mapping) or "samples" not in latent:
        raise TailValidationError("latent must be a LATENT mapping with 'samples'")
    samples = latent["samples"]
    if not isinstance(samples, torch.Tensor) or samples.ndim not in (4, 5):
        raise TailValidationError(
            "latent samples must be a static-image tensor [B,C,H,W] or [B,C,1,H,W]"
        )
    if samples.ndim == 5 and samples.shape[2] != 1:
        raise TailValidationError(
            "latent samples with multiple temporal frames are unsupported; expected [B,C,1,H,W]"
        )
    if samples.dtype not in _FLOAT_DTYPES:
        raise TailValidationError(f"latent samples dtype {samples.dtype} is not a float dtype")
    if samples.shape[0] < 1 or samples.shape[1] < 1 or samples.shape[-1] < 1 or samples.shape[-2] < 1:
        raise TailValidationError("latent samples must hold at least one batch item, channel, and pixel")
    if not bool(torch.isfinite(samples).all()):
        raise TailValidationError("latent samples must contain only finite values")
    return samples


def _noise_mask(mask: Any, *, latent_batch: int, latent_ndim: int) -> torch.Tensor | None:
    """`SetLatentNoiseMask` semantics: the pixel mask is reshaped, never resized here."""
    if mask is None:
        return None
    if not isinstance(mask, torch.Tensor) or mask.ndim not in (2, 3):
        raise TailValidationError("mask must be a MASK tensor of shape [H,W] or [B,H,W]")
    if mask.dtype not in _FLOAT_DTYPES:
        raise TailValidationError(f"mask dtype {mask.dtype} is not a float dtype")
    if mask.numel() == 0:
        raise TailValidationError("mask is empty")
    mask_batch = 1 if mask.ndim == 2 else mask.shape[0]
    if mask_batch not in (1, latent_batch):
        raise TailValidationError(
            f"mask batch must be 1 or match latent batch {latent_batch}; got {mask_batch}"
        )
    if not bool(torch.isfinite(mask).all()):
        raise TailValidationError("mask must be finite")
    if bool((mask < 0).any()) or bool((mask > 1).any()):
        raise TailValidationError("mask values must lie within [0, 1]")
    if latent_ndim == 5:
        # Core's 3D latent mask path treats a rank-4 mask's leading dimension as time. Keep the
        # explicit singleton time axis so batched still-image masks remain independent.
        return mask.reshape((-1, 1, 1, mask.shape[-2], mask.shape[-1]))
    return mask.reshape((-1, 1, mask.shape[-2], mask.shape[-1]))


def latent_tail(
    *,
    latent: Mapping[str, Any],
    model: Any,
    noise: Any,
    positive: Any,
    mask: Any,
    schedule: TailSchedule,
    sampler_name: str,
    run_sampler: Callable[..., torch.Tensor],
) -> dict[str, Any]:
    """Run one masked tail through the injected sampler seam and return a new LATENT."""
    samples = _validate_latent(latent)
    noise_mask = _noise_mask(mask, latent_batch=samples.shape[0], latent_ndim=samples.ndim)
    if noise_mask is not None and torch.count_nonzero(noise_mask).item() == 0:
        _LOG.info("latent tail skipped: exact-zero mask")
        return latent
    if not isinstance(schedule, TailSchedule):
        raise TailValidationError("schedule must be a TailSchedule")
    if sampler_name not in CORE_SAMPLER_NAMES:
        raise TailValidationError(f"unknown core sampler {sampler_name!r}")
    if model is None or noise is None or positive is None:
        raise TailValidationError("model, noise and positive are required")
    if not callable(getattr(noise, "generate_noise", None)):
        raise TailValidationError("noise must be a NOISE object providing generate_noise")
    if not callable(run_sampler):
        raise TailValidationError("run_sampler must be callable")
    # V2: never mutate the incoming container; drop an inherited mask so ours is the only one.
    payload = {key: value for key, value in latent.items() if key != "noise_mask"}
    sigmas = torch.tensor(schedule.sigmas, dtype=torch.float32)

    for warning in schedule.warnings:
        _LOG.warning("%s", warning)
    _LOG.info("%s", schedule.report())

    result = run_sampler(
        model=model,
        noise=noise,
        positive=positive,
        latent=payload,
        noise_mask=noise_mask,
        sigmas=sigmas,
        sampler_name=sampler_name,
    )
    if not isinstance(result, torch.Tensor):
        raise TailError("sampler seam returned no tensor")
    if tuple(result.shape) != tuple(samples.shape):
        raise TailError(
            f"sampler seam changed the latent geometry {tuple(samples.shape)} -> {tuple(result.shape)}"
        )
    if not bool(torch.isfinite(result).all()):
        raise TailError("sampler seam returned non-finite latent values")
    out = dict(payload)
    out["samples"] = result
    return out


# --- factory seam -------------------------------------------------------------------------

_SCHEDULE_FACTORY: Callable[[Any, str], Callable[[int], Sequence[float]]] | None = None
_RUN_SAMPLER: Callable[..., torch.Tensor] | None = None


def configure_factory_tail(
    schedule_factory: Callable[[Any, str], Callable[[int], Sequence[float]]],
    run_sampler: Callable[..., torch.Tensor],
) -> None:
    """Install the pack bootstrap's real ComfyUI schedule and sampling adapters.

    `schedule_factory(model, scheduler_name)` returns `schedule(total_steps)`; `run_sampler`
    receives model, noise, positive, latent, noise_mask, sigmas and sampler_name and returns the
    finished samples tensor.
    """
    global _SCHEDULE_FACTORY, _RUN_SAMPLER
    if not callable(schedule_factory) or not callable(run_sampler):
        raise TypeError("factory tail adapters must be callable")
    _SCHEDULE_FACTORY = schedule_factory
    _RUN_SAMPLER = run_sampler


def execute_utility_operation(item):
    """Factory seam for the compiled MATRIX_LatentTail node."""
    if not isinstance(item, dict):
        raise TailValidationError("sample.latent-tail requires an input mapping")
    required = ("model", "noise", "positive", "latent")
    missing = [name for name in required if name not in item]
    if missing:
        raise TailValidationError("missing latent tail input(s): " + ", ".join(missing))
    samples = _validate_latent(item["latent"])
    noise_mask = _noise_mask(
        item.get("mask"), latent_batch=samples.shape[0], latent_ndim=samples.ndim
    )
    if noise_mask is not None and torch.count_nonzero(noise_mask).item() == 0:
        _LOG.info("latent tail skipped: exact-zero mask")
        return (item["latent"],)
    if _SCHEDULE_FACTORY is None or _RUN_SAMPLER is None:
        raise TailValidationError(
            "sample.latent-tail runtime adapters are not configured by the pack bootstrap"
        )
    scheduler = item.get("scheduler", "beta57")
    if scheduler not in SCHEDULER_NAMES:
        raise TailValidationError(f"unknown scheduler {scheduler!r}")
    schedule = resolve_tail_sigmas(
        _SCHEDULE_FACTORY(item["model"], scheduler),
        start_sigma=item.get("start_sigma", 0.26),
        steps=item.get("steps", 3),
        scheduler=scheduler,
    )
    out = latent_tail(
        latent=item["latent"],
        model=item["model"],
        noise=item["noise"],
        positive=item["positive"],
        mask=item.get("mask"),
        schedule=schedule,
        sampler_name=item.get("sampler_name", "euler_ancestral"),
        run_sampler=_RUN_SAMPLER,
    )
    return (out,)
