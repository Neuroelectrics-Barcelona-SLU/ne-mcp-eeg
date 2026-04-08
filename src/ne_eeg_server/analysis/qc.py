"""
EEG QC Core — shared signal quality metrics.
(G. Ruffini, Jan 2026)
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from scipy import signal
from scipy.signal import iirnotch, tf2sos
from scipy.stats import kurtosis as _kurtosis

from ne_eeg_server.analysis.metrics_defaults import METRICS_DEFAULT_THRESHOLDS, DEFAULT_EVENT_THRESHOLD_UV
from ne_eeg_server.analysis.psd_peak_qc import find_suspicious_psd_peak


def _merge_thresholds(overrides: Optional[dict]) -> dict:
    thr = dict(METRICS_DEFAULT_THRESHOLDS)
    if overrides:
        for k, v in dict(overrides).items():
            thr[k] = v
    return thr


def _design_filters(fs: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (sos_bandpass, sos_notch_50, sos_notch_60) for the canonical pipeline."""
    low_cut = 1.0
    high_cut = 40.0
    filter_order = 4
    sos_bandpass = signal.butter(filter_order, [low_cut, high_cut], btype="bandpass", fs=fs, output="sos")

    notch_q = 30.0
    b50, a50 = iirnotch(50.0, notch_q, fs)
    b60, a60 = iirnotch(60.0, notch_q, fs)
    sos_notch_50 = tf2sos(b50, a50)
    sos_notch_60 = tf2sos(b60, a60)
    return sos_bandpass, sos_notch_50, sos_notch_60


def _contiguous_event_count(above: np.ndarray) -> int:
    """Count contiguous True segments (rising edges)."""
    above = np.asarray(above, dtype=bool)
    if above.size == 0:
        return 0
    return int((1 if above[0] else 0) + np.sum(above[1:] & ~above[:-1]))


def _max_line_power_db(x_uv_1d: np.ndarray, fs: float, *, resolution_hz: float = 0.5) -> float:
    """Maximum PSD (dB re 1 µV²/Hz) near 50 Hz or 60 Hz on RAW demeaned data."""
    try:
        x = np.asarray(x_uv_1d, dtype=float)
        x = x[np.isfinite(x)]
        if x.size < 8 or fs <= 0:
            return float("nan")

        nfft = int(max(8, round(float(fs) / float(resolution_hz))))
        nperseg = int(min(nfft, x.size))
        freqs, psd = signal.welch(x, fs=fs, nperseg=nperseg, nfft=nfft,
                                  detrend="constant", scaling="density")
        psd = np.asarray(psd, dtype=float)
        if psd.size == 0:
            return float("nan")

        psd_db = 10.0 * np.log10(np.maximum(psd, 1e-20))

        def peak_near(target_hz: float) -> float:
            m = np.abs(freqs - float(target_hz)) <= float(resolution_hz)
            if np.any(m):
                return float(np.nanmax(psd_db[m]))
            idx = int(np.nanargmin(np.abs(freqs - float(target_hz))))
            return float(psd_db[idx])

        return float(max(peak_near(50.0), peak_near(60.0)))
    except Exception:
        return float("nan")


def _suspicious_peak_metrics(x_uv_1d: np.ndarray, fs: float, *, snr_flag_db: float) -> Tuple[float, float, int]:
    """Return (best_peak_freq_hz, best_peak_snr_db, flagged_peak_count)."""
    try:
        x = np.asarray(x_uv_1d, dtype=float)
        x = x[np.isfinite(x)]
        if x.size < 8 or fs <= 0:
            return float("nan"), float("nan"), 0

        resolution_hz = 0.5
        nfft = int(max(8, round(float(fs) / resolution_hz)))
        nperseg = int(min(nfft, x.size))
        freqs, psd = signal.welch(x, fs=fs, nperseg=nperseg, nfft=nfft,
                                  detrend="constant", scaling="density")

        best = find_suspicious_psd_peak(freqs, psd, snr_threshold_db=0.0)
        flagged = find_suspicious_psd_peak(freqs, psd, snr_threshold_db=float(snr_flag_db))

        peak_freq = float(best.freq_hz) if best else float("nan")
        peak_snr = float(best.snr_db) if best else float("nan")
        peak_count = int(flagged.count) if flagged else 0
        return peak_freq, peak_snr, peak_count
    except Exception:
        return float("nan"), float("nan"), 0


def calculate_channel_metrics_from_signals(
    signals_uv: Dict[int, np.ndarray],
    *,
    fs: float = 500.0,
    event_threshold_uv: float = DEFAULT_EVENT_THRESHOLD_UV,
    thresholds: Optional[dict] = None,
    raw_means_uv: Optional[Dict[int, float]] = None,
) -> Dict[int, Dict]:
    """Compute per-channel QC metrics on provided RAW demeaned signals (µV)."""
    thr = _merge_thresholds(thresholds)
    fs = float(fs or 0.0)
    if fs <= 0:
        fs = 500.0

    sos_bandpass, sos_notch_50, sos_notch_60 = _design_filters(fs)
    transient_samples = int(0.5 * fs)

    out: Dict[int, Dict] = {}
    for ch_idx, x_in in (signals_uv or {}).items():
        try:
            x_uv = np.asarray(x_in, dtype=float)
        except Exception:
            continue

        x_uv = x_uv[np.isfinite(x_uv)]
        if x_uv.size == 0:
            continue

        raw_rms = float(np.sqrt(np.mean(x_uv ** 2)))
        duration_sec = float(x_uv.size) / fs if fs else 0.0
        mean_uv = float(raw_means_uv.get(int(ch_idx))) if raw_means_uv else float(np.mean(x_uv))

        line_db = _max_line_power_db(x_uv, fs)
        peak_snr_thr = float(thr.get("psd_peak_snr_min_db", thr.get("psd_peak_snr_max_db", 12.0)))
        peak_freq_hz, peak_snr_db, peak_count = _suspicious_peak_metrics(x_uv, fs, snr_flag_db=peak_snr_thr)

        try:
            x_notch = signal.sosfiltfilt(sos_notch_50, x_uv)
            x_notch = signal.sosfiltfilt(sos_notch_60, x_notch)
        except Exception:
            x_notch = np.asarray(x_uv, dtype=float)

        notch_rms = float(np.sqrt(np.mean(x_notch ** 2))) if x_notch.size else float("nan")
        notch_k = float(_kurtosis(x_notch, fisher=False, bias=False)) if x_notch.size >= 4 else float("nan")

        above = np.abs(x_notch) > float(event_threshold_uv)
        n_events = _contiguous_event_count(above)
        event_rate_hz = (float(n_events) / duration_sec) if duration_sec > 0 else float("nan")

        try:
            y = signal.sosfiltfilt(sos_bandpass, x_uv)
            y = signal.sosfiltfilt(sos_notch_50, y)
            y = signal.sosfiltfilt(sos_notch_60, y)
        except Exception:
            y = np.asarray(x_uv, dtype=float)

        if y.size > 2 * transient_samples:
            y = y[transient_samples:-transient_samples]
        y = y[np.isfinite(y)]
        full_rms = float(np.sqrt(np.mean(y ** 2))) if y.size else float("nan")

        raw_min_uv = float(thr.get("rms_raw_min_uv", 0.0))
        mean_abs_max = float(thr.get("mean_abs_max_uv", 0.0))
        flags = {
            "raw_rms_uv": (raw_rms >= float(thr["rms_raw_max_uv"])) or (raw_min_uv > 0.0 and raw_rms < raw_min_uv),
            "notch_rms_uv": (not np.isnan(notch_rms)) and (notch_rms >= float(thr["rms_notch_max_uv"])),
            "full_rms_uv": (not np.isnan(full_rms)) and (full_rms >= float(thr["rms_full_max_uv"])),
            "mean_uv": (mean_abs_max > 0.0) and (abs(mean_uv) >= mean_abs_max),
            "notch_kurtosis": (not np.isnan(notch_k)) and (notch_k >= float(thr["kurtosis_notch_max"])),
            "notch_events_rate_hz": (not np.isnan(event_rate_hz)) and (event_rate_hz >= float(thr["events_notch_rate_max_hz"])),
            "line_power_db": (not np.isnan(line_db)) and (line_db >= float(thr["line_power_db_max"])),
            "psd_peak_snr_db": (not np.isnan(peak_snr_db)) and (peak_snr_db >= float(peak_snr_thr)),
        }
        passed = not any(bool(v) for v in flags.values())

        out[int(ch_idx)] = {
            "raw_rms_uv": raw_rms,
            "notch_rms_uv": notch_rms,
            "full_rms_uv": full_rms,
            "mean_uv": mean_uv,
            "notch_kurtosis": notch_k,
            "notch_events_count": int(n_events),
            "notch_events_rate_hz": event_rate_hz,
            "metrics_duration_sec": duration_sec,
            "line_power_db": line_db,
            "psd_peak_freq_hz": peak_freq_hz,
            "psd_peak_snr_db": peak_snr_db,
            "psd_peak_count": int(peak_count),
            "event_threshold_uv": float(event_threshold_uv),
            "thresholds": dict(thr),
            "flags": flags,
            "pass": bool(passed),
        }

    return out
