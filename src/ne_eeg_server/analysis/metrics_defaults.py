"""
Shared defaults for EEG metric computation.
(G. Ruffini, Jan 2026)

Single source of truth for:
  - the default *event* threshold used to count over-threshold events on notch-only data
  - default per-channel metric thresholds used to flag out-of-range values (PASS/FAIL, highlighting)
"""

from __future__ import annotations

# Default threshold for counting contiguous over-threshold events on notch-only data (µV).
DEFAULT_EVENT_THRESHOLD_UV: float = 5.0

# Default thresholds for per-channel metrics.
METRICS_DEFAULT_THRESHOLDS: dict[str, float] = {
    "rms_raw_min_uv": 0.01,
    "rms_raw_max_uv": 1.5,
    "rms_notch_max_uv": 1.0,
    "rms_full_max_uv": 0.5,
    "mean_abs_max_uv": 2000.0,
    "kurtosis_notch_max": 5.0,
    "events_notch_rate_max_hz": 10.0,
    "line_power_db_max": 1.2,
    "psd_peak_snr_min_db": 12.0,
}
