"""
PSD Peak Quality-Control helper.
(G. Ruffini, Jan 2026)

Detect "suspicious" narrowband spectral peaks away from power-line noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy import signal


@dataclass(frozen=True)
class PsdPeakResult:
    """Best suspicious peak in a PSD trace."""

    freq_hz: float
    snr_db: float
    count: int


def _odd(n: int) -> int:
    """Return `n` if odd, otherwise the next odd integer."""
    return n if (n % 2 == 1) else (n + 1)


def find_suspicious_psd_peak(
    freqs_hz: np.ndarray,
    psd_linear: np.ndarray,
    *,
    fmin_hz: float = 1.0,
    fmax_hz: float = 100.0,
    exclude_hz: Sequence[float] = (50.0, 60.0, 100.0, 120.0),
    exclude_half_width_hz: float = 1.0,
    baseline_window_hz: float = 5.0,
    snr_threshold_db: float = 12.0,
) -> Optional[PsdPeakResult]:
    """Return the strongest suspicious (off-line) spectral peak or None."""
    try:
        f = np.asarray(freqs_hz, dtype=float)
        p = np.asarray(psd_linear, dtype=float)
        if f.ndim != 1 or p.ndim != 1 or f.size != p.size or f.size < 8:
            return None

        band = (f >= float(fmin_hz)) & (f <= float(fmax_hz))
        if not np.any(band):
            return None

        excl = np.zeros_like(band, dtype=bool)
        for hz in exclude_hz:
            excl |= np.abs(f - float(hz)) <= float(exclude_half_width_hz)
        valid = band & (~excl)
        if np.count_nonzero(valid) < 8:
            return None

        psd_db = 10.0 * np.log10(np.maximum(p, 1e-20))

        df = float(np.nanmedian(np.diff(f[band]))) if np.count_nonzero(band) > 1 else 0.5
        if df <= 0:
            df = 0.5
        win_bins = _odd(int(max(3, round(float(baseline_window_hz) / df))))
        baseline_db = signal.medfilt(psd_db, kernel_size=win_bins)

        snr_db = psd_db - baseline_db
        snr_db[~valid] = -np.inf

        peaks, props = signal.find_peaks(snr_db, height=float(snr_threshold_db))
        if peaks is None or len(peaks) == 0:
            return None

        best_i = int(peaks[np.argmax(snr_db[peaks])])
        return PsdPeakResult(freq_hz=float(f[best_i]), snr_db=float(snr_db[best_i]), count=int(len(peaks)))
    except Exception:
        return None
