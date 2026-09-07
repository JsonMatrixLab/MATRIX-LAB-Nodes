"""Pre-call token exposure reservation and post-call settlement."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

_MILLION = Decimal(1_000_000)


class InvalidTokenPrices(ValueError):
    error_class = "local_validation"


@dataclass(frozen=True)
class TokenPrices:
    provider: str
    model: str
    pricing_version: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal | None = None

    def __post_init__(self) -> None:
        rates = (
            self.input_usd_per_million,
            self.output_usd_per_million,
            self.cached_input_usd_per_million,
        )
        if any(rate is not None and not isinstance(rate, Decimal) for rate in rates):
            raise InvalidTokenPrices("token prices must use Decimal")
        if any(rate is not None and rate < 0 for rate in rates):
            raise InvalidTokenPrices("token prices must not be negative")


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class TokenSettlement:
    provider: str
    model: str
    pricing_version: str
    input_tokens: int
    fresh_input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    actual_usd: Decimal


class SpendLimitExceeded(RuntimeError):
    error_class = "insufficient_funds_or_quota"


class LiveModeRefused(RuntimeError):
    error_class = "local_validation"


class InvalidTokenUsage(ValueError):
    error_class = "empty_or_malformed_success"


class TokenLedger:
    """One explicit run/account ledger with atomic reservations."""

    def __init__(self, *, run_id: str, account: str, ceiling_usd: Decimal) -> None:
        self.run_id = run_id
        self.account = account
        self.ceiling_usd = Decimal(ceiling_usd)
        self._reserved_usd = Decimal(0)
        self._spent_usd = Decimal(0)
        self._lock = Lock()

    @property
    def reserved_usd(self) -> Decimal:
        with self._lock:
            return self._reserved_usd

    @property
    def spent_usd(self) -> Decimal:
        with self._lock:
            return self._spent_usd

    def reserve(
        self,
        *,
        prices: TokenPrices,
        input_token_upper_bound: int | None,
        max_output_tokens: int,
    ) -> "TokenReservation":
        if input_token_upper_bound is None or input_token_upper_bound < 0:
            raise LiveModeRefused(
                "Live LLM mode requires a non-negative safe input token upper bound."
            )
        if max_output_tokens <= 0:
            raise LiveModeRefused(
                "Live LLM mode requires a positive maximum output token bound."
            )
        input_rate = max(
            prices.input_usd_per_million,
            prices.cached_input_usd_per_million
            if prices.cached_input_usd_per_million is not None
            else prices.input_usd_per_million,
        )
        exposure = (
            Decimal(input_token_upper_bound) * input_rate
            + Decimal(max_output_tokens) * prices.output_usd_per_million
        ) / _MILLION
        with self._lock:
            projected = self._spent_usd + self._reserved_usd + exposure
            if projected > self.ceiling_usd:
                raise SpendLimitExceeded(
                    f"Token reservation {exposure} USD would make run {self.run_id} "
                    f"reach {projected} USD above ceiling {self.ceiling_usd} USD."
                )
            self._reserved_usd += exposure
        return TokenReservation(
            ledger=self,
            prices=prices,
            reserved_usd=exposure,
        )

    def _settle(
        self,
        *,
        reserved_usd: Decimal,
        prices: TokenPrices,
        usage: TokenUsage,
    ) -> TokenSettlement:
        if min(
            usage.input_tokens,
            usage.output_tokens,
            usage.cached_input_tokens,
        ) < 0:
            raise InvalidTokenUsage("reported token counts must not be negative")
        if usage.cached_input_tokens > usage.input_tokens:
            raise InvalidTokenUsage(
                "reported cached input tokens exceed total input tokens"
            )
        fresh_input_tokens = usage.input_tokens - usage.cached_input_tokens
        cached_rate = prices.cached_input_usd_per_million
        if usage.cached_input_tokens and cached_rate is None:
            raise ValueError(
                "reported cached input tokens require a catalogue cached-input price"
            )
        actual = (
            Decimal(fresh_input_tokens) * prices.input_usd_per_million
            + Decimal(usage.cached_input_tokens) * (cached_rate or Decimal(0))
            + Decimal(usage.output_tokens) * prices.output_usd_per_million
        ) / _MILLION
        with self._lock:
            self._reserved_usd -= reserved_usd
            self._spent_usd += actual
        return TokenSettlement(
            provider=prices.provider,
            model=prices.model,
            pricing_version=prices.pricing_version,
            input_tokens=usage.input_tokens,
            fresh_input_tokens=fresh_input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            actual_usd=actual,
        )


class TokenReservation:
    """A single pre-call reservation that can settle exactly once."""

    def __init__(
        self,
        *,
        ledger: TokenLedger,
        prices: TokenPrices,
        reserved_usd: Decimal,
    ) -> None:
        self._ledger = ledger
        self._prices = prices
        self.reserved_usd = reserved_usd
        self._settled = False

    def settle(self, usage: TokenUsage) -> TokenSettlement:
        if self._settled:
            raise RuntimeError("token reservation is already settled")
        settlement = self._ledger._settle(
            reserved_usd=self.reserved_usd,
            prices=self._prices,
            usage=usage,
        )
        self._settled = True
        return settlement


__all__ = [
    "InvalidTokenPrices",
    "InvalidTokenUsage",
    "LiveModeRefused",
    "SpendLimitExceeded",
    "TokenLedger",
    "TokenPrices",
    "TokenReservation",
    "TokenSettlement",
    "TokenUsage",
]
