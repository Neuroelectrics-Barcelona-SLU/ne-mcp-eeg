"""Validated, serializable settings for ambulatory analysis and diagnostics."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from numbers import Real, Integral
import math


def _number(name, value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")


def _settings_dict(config):
    """Convert accepted numeric scalar types to JSON-compatible Python values."""
    def native(value):
        if isinstance(value, dict):
            return {key: native(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(native(item) for item in value)
        if isinstance(value, Integral):
            return int(value)
        if isinstance(value, Real):
            return float(value)
        return value
    return native(asdict(config))


@dataclass(frozen=True)
class ReferenceConfig:
    sat_max: float = .01
    flat_frac_max: float = .5
    constant_run_max_s: float = 1.
    rms_min_uV: float = 2.
    minimum_channels: int = 4

    def __post_init__(self):
        for name in ("sat_max", "flat_frac_max", "constant_run_max_s", "rms_min_uV"):
            _number(name, getattr(self, name))
        if self.sat_max > 1 or self.flat_frac_max > 1:
            raise ValueError("reference fractions must be between zero and one")
        if isinstance(self.minimum_channels, bool) or not isinstance(self.minimum_channels, Integral) or self.minimum_channels < 2:
            raise ValueError("minimum_channels must be an integer of at least two")


@dataclass(frozen=True)
class AnalysisConfig:
    rail_nv: float = 399_000_000
    band_hz: tuple[float, float] = (1., 40.)
    filter_order: int = 4
    notch_hz: tuple[float, ...] = (50., 60.)
    notch_q: float = 30.
    hum_hz: float = 50.
    hum_half_width_hz: float = 1.
    hf_hz: tuple[float, float] = (30., 45.)
    welch_s: float = 2.
    trim_s: float = .5
    dc_window_s: float = 5.
    reference: ReferenceConfig = field(default_factory=ReferenceConfig)

    def __post_init__(self):
        if isinstance(self.reference, dict):
            object.__setattr__(self, "reference", ReferenceConfig(**self.reference))
        if not isinstance(self.reference, ReferenceConfig):
            raise ValueError("reference must be a ReferenceConfig or its dictionary")
        for name in ("rail_nv", "notch_q", "hum_hz", "hum_half_width_hz", "welch_s", "dc_window_s"):
            _number(name, getattr(self, name), positive=True)
        _number("trim_s", self.trim_s)
        if isinstance(self.filter_order, bool) or not isinstance(self.filter_order, Integral) or self.filter_order < 1:
            raise ValueError("filter_order must be a positive integer")
        for name in ("band_hz", "hf_hz", "notch_hz"):
            try:
                values = tuple(getattr(self, name))
            except TypeError as exc:
                raise ValueError(f"{name} must be a sequence of frequencies") from exc
            for value in values:
                _number(name, value, positive=True)
            if name != "notch_hz" and (len(values) != 2 or values[0] >= values[1]):
                raise ValueError(f"{name} must contain increasing lower and upper frequencies")
            if name == "notch_hz" and len(set(values)) != len(values):
                raise ValueError("notch_hz must not repeat a frequency")
            object.__setattr__(self, name, values)
        if self.hum_hz <= self.hum_half_width_hz:
            raise ValueError("the hum band must start above zero Hz")

    def validate_sampling(self, fs, epoch_s):
        _number("fs", fs, positive=True)
        _number("epoch_s", epoch_s, positive=True)
        high = max(*self.notch_hz, self.band_hz[1], self.hf_hz[1], self.hum_hz + self.hum_half_width_hz)
        if fs != int(fs) or fs <= 2 * high:
            raise ValueError("fs must be a whole number above twice the highest configured frequency")
        if epoch_s < 10 or not math.isclose(epoch_s * fs, round(epoch_s * fs), rel_tol=0, abs_tol=1e-8):
            raise ValueError("epoch_s must be at least 10 s with an integer number of samples")
        if self.dc_window_s * 2 > epoch_s or int(self.dc_window_s * fs) < 1:
            raise ValueError("DC windows must contain samples and fit without overlap in the epoch")
        if int(epoch_s * fs) - 2 * int(self.trim_s * fs) < 2:
            raise ValueError("edge trimming must retain at least two samples")
        if self.welch_s > epoch_s or int(self.welch_s * fs) < 8:
            raise ValueError("Welch window must contain at least eight samples and fit in the epoch")

    def to_dict(self):
        return _settings_dict(self)


@dataclass(frozen=True)
class EventConfig:
    threshold_uv: float = 100.
    min_duration_s: float = .02
    merge_gap_s: float = .1

    def __post_init__(self):
        _number("threshold_uv", self.threshold_uv, positive=True)
        _number("min_duration_s", self.min_duration_s)
        _number("merge_gap_s", self.merge_gap_s)


@dataclass(frozen=True)
class DiagnosticsConfig:
    peak_snr_db: float = 12.
    events: EventConfig = field(default_factory=EventConfig)

    def __post_init__(self):
        _number("peak_snr_db", self.peak_snr_db)
        if isinstance(self.events, dict):
            object.__setattr__(self, "events", EventConfig(**self.events))
        if not isinstance(self.events, EventConfig):
            raise ValueError("events must be an EventConfig or its dictionary")

    def to_dict(self):
        return _settings_dict(self)


def analysis_config(value=None):
    """Resolve a dataclass or persisted configuration without mutating it."""
    if value is None:
        return AnalysisConfig()
    if isinstance(value, dict):
        return AnalysisConfig(**value)
    if not isinstance(value, AnalysisConfig):
        raise ValueError("analysis must be an AnalysisConfig or its dictionary")
    return value
