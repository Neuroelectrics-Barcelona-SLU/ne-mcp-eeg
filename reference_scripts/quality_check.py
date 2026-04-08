#!/usr/bin/env python3
"""
Signal quality check for a .easy recording.

Checks each channel for:
  - Flatline detection (zero variance over windows)
  - Excessive noise (std > threshold)
  - 50/60 Hz line noise (spectral peak)
  - Signal clipping (values near ADC rail)

Prints a per-channel quality report: GOOD / FAIR / POOR with reason.

Usage:
    python quality_check.py [path_to_file.easy]
"""

import os
import sys

import numpy as np
from scipy.signal import welch

from load_easy_file import load_easy

# Thresholds
FLATLINE_STD_UV = 0.5       # below this → flatline
NOISE_STD_UV = 100.0        # above this → excessive noise
LINE_NOISE_RATIO = 5.0      # spectral peak at 50/60 Hz vs neighbors
CLIPPING_UV = 3200.0        # near 24-bit rail at gain=12 → ~3.2 mV


def check_channel(data: np.ndarray, fs: int) -> tuple[str, list[str]]:
    """Return (quality_level, list_of_reasons)."""
    issues = []
    std = np.std(data)

    # Flatline
    if std < FLATLINE_STD_UV:
        issues.append(f"Flatline detected (std={std:.2f} µV)")

    # Excessive noise
    if std > NOISE_STD_UV:
        issues.append(f"Excessive noise (std={std:.1f} µV, threshold={NOISE_STD_UV})")

    # Line noise check (50 Hz and 60 Hz)
    freqs, psd = welch(data, fs=fs, nperseg=min(1024, len(data)))
    for line_freq in [50.0, 60.0]:
        mask = (freqs >= line_freq - 1) & (freqs <= line_freq + 1)
        neighbor_mask = (
            ((freqs >= line_freq - 5) & (freqs <= line_freq - 2)) |
            ((freqs >= line_freq + 2) & (freqs <= line_freq + 5))
        )
        if mask.any() and neighbor_mask.any():
            peak = np.max(psd[mask])
            bg = np.mean(psd[neighbor_mask])
            if bg > 0 and peak / bg > LINE_NOISE_RATIO:
                issues.append(f"{int(line_freq)} Hz line noise (ratio={peak/bg:.1f}x)")

    # Clipping
    if np.max(np.abs(data)) > CLIPPING_UV:
        issues.append(f"Possible clipping (max={np.max(np.abs(data)):.1f} µV)")

    if not issues:
        return "GOOD", ["Signal within normal limits"]
    elif len(issues) == 1 and "line noise" in issues[0].lower():
        return "FAIR", issues
    else:
        return "POOR", issues


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "sample_data", "demo_recording.easy"
    )

    df, meta = load_easy(filepath)
    fs = meta.get("sampling_rate", 500)
    electrodes = meta["electrodes"]

    print("=" * 70)
    print("EEG SIGNAL QUALITY REPORT")
    print("=" * 70)
    print(f"File: {os.path.basename(filepath)}")
    print(f"Channels: {len(electrodes)}, Duration: {meta['duration_s']:.1f}s")
    print("-" * 70)
    print(f"{'Channel':<10} {'Quality':<8} {'Details'}")
    print("-" * 70)

    reject_list = []
    for ch in electrodes:
        data = df[ch].values
        quality, reasons = check_channel(data, fs)
        status_marker = {"GOOD": "+", "FAIR": "~", "POOR": "!"}[quality]
        print(f"  [{status_marker}] {ch:<7} {quality:<8} {'; '.join(reasons)}")
        if quality == "POOR":
            reject_list.append(ch)

    print("-" * 70)
    if reject_list:
        print(f"Suggested channels to reject: {', '.join(reject_list)}")
    else:
        print("All channels passed quality check.")


if __name__ == "__main__":
    main()
