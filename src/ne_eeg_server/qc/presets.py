"""Separate bench and ambulatory threshold presets."""
import numpy as np


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

THR = dict(sat=0.01, flat_run_s=1.0, flat_frac=0.5, open_rms=2.0, drift_raw=1500.0, drift_ddc=50.0, cm_corr=0.95, cm_rms=10.0,
           bad_resid_abs=15.0, bad_resid_rel=3.0, bad_rms=150.0, bad_hum_rel=3.0, bad_hum_abs=20.0, motion_acc_rel=3.0, motion_rms=100.0,
           hum_severe=50.0, hum_elev=10.0, hf_rms=8.0)

def resolve_thresholds(overrides=None):
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("threshold overrides must be a JSON object")
    if overrides and set(overrides) - set(THR):
        raise ValueError(f"unknown thresholds: {sorted(set(overrides)-set(THR))}")
    t = dict(THR); t.update(overrides or {})
    for key, value in t.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
            raise ValueError(f"threshold {key} must be a finite nonnegative number")
    for key in ("sat", "flat_frac", "cm_corr"):
        if t[key] > 1: raise ValueError(f"threshold {key} must be between zero and one")
    if t["hum_elev"] > t["hum_severe"]:
        raise ValueError("hum_elev must not exceed hum_severe")
    return t



THRESHOLDS = {"bench": METRICS_DEFAULT_THRESHOLDS, "ambulatory": THR}
