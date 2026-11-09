"""Additive spectral prominence and amplitude-episode measurements."""
from __future__ import annotations

import math
import numpy as np
from .config import DiagnosticsConfig, EventConfig
from .peaks import find_suspicious_psd_peak

DIAGNOSTICS_VERSION = 1
DKEYS = ["psd_peak_freq_hz", "psd_peak_snr_db", "psd_peak_count",
         "human_events_count", "human_events_per_min", "human_events_duration_s"]


def amplitude_events(x_uv, fs, config: EventConfig | None = None):
    """Count merged absolute-amplitude episodes; return count, events/min, seconds."""
    cfg = EventConfig() if config is None else config
    if not isinstance(cfg, EventConfig):
        raise ValueError("config must be an EventConfig")
    x = np.asarray(x_uv, dtype=float)
    if x.ndim != 1 or not x.size or not np.isfinite(x).all():
        raise ValueError("events require a nonempty finite one-dimensional signal")
    if isinstance(fs, bool) or not np.isfinite(fs) or fs <= 0:
        raise ValueError("fs must be positive and finite")
    above = np.abs(x) > cfg.threshold_uv
    edges = np.flatnonzero(np.diff(np.r_[False, above, False]))
    minimum = max(1, math.ceil(cfg.min_duration_s * fs))
    gap = math.floor(cfg.merge_gap_s * fs)
    count, last_end, samples = 0, None, 0
    for start, end in zip(edges[::2], edges[1::2]):
        if last_end is not None and start - last_end > gap:
            count += samples >= minimum
            samples = 0
        samples += int(end - start)
        last_end = end
    count += samples >= minimum
    duration = x.size / fs
    return int(count), float(count * 60 / duration), float(duration)


def epoch_diagnostics(freqs, psd, filtered_uv, fs, config: DiagnosticsConfig):
    """Use the existing epoch PSD and retained band signal, without refiltering."""
    nch = filtered_uv.shape[1]
    out = {k: np.full(nch, np.nan) for k in DKEYS}
    for ch in range(nch):
        best = find_suspicious_psd_peak(freqs, psd[:, ch], snr_threshold_db=0.)
        flagged = find_suspicious_psd_peak(freqs, psd[:, ch], snr_threshold_db=config.peak_snr_db)
        out["psd_peak_freq_hz"][ch] = best.freq_hz if best else np.nan
        out["psd_peak_snr_db"][ch] = best.snr_db if best else np.nan
        out["psd_peak_count"][ch] = flagged.count if flagged else 0
        count, rate, duration = amplitude_events(filtered_uv[:, ch], fs, config.events)
        out["human_events_count"][ch] = count
        out["human_events_per_min"][ch] = rate
        out["human_events_duration_s"][ch] = duration
    return out
