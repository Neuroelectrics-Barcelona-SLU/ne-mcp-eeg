#!/usr/bin/env python3
"""
Compute absolute and relative band powers per channel.

Also calculates clinical ratios: alpha/theta, delta/alpha, beta/alpha.
Prints a summary table suitable for copy-paste into a clinical report.

Usage:
    python band_power.py [path_to_file.easy]
"""

import os
import sys

import numpy as np
from scipy.signal import welch

from load_easy_file import load_easy

BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta":  (13, 30),
    "gamma": (30, 80),
}


def compute_band_powers(data: np.ndarray, fs: int) -> dict[str, float]:
    """Compute absolute band power (µV²) for each frequency band."""
    freqs, psd = welch(data, fs=fs, nperseg=min(1024, len(data)))
    powers = {}
    for band, (f_low, f_high) in BANDS.items():
        mask = (freqs >= f_low) & (freqs <= f_high)
        powers[band] = float(np.trapezoid(psd[mask], freqs[mask]))
    return powers


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "sample_data", "demo_recording.easy"
    )

    df, meta = load_easy(filepath)
    fs = meta.get("sampling_rate", 500)
    electrodes = meta["electrodes"]

    # Compute band powers for all channels
    all_powers = {}
    for ch in electrodes:
        all_powers[ch] = compute_band_powers(df[ch].values, fs)

    # Print absolute band powers
    print("=" * 80)
    print("ABSOLUTE BAND POWER (µV²)")
    print("=" * 80)
    header = f"{'Channel':<10}" + "".join(f"{b:>10}" for b in BANDS)
    print(header)
    print("-" * 80)
    for ch in electrodes:
        row = f"{ch:<10}" + "".join(f"{all_powers[ch][b]:10.2f}" for b in BANDS)
        print(row)

    # Print relative band powers
    print()
    print("=" * 80)
    print("RELATIVE BAND POWER (%)")
    print("=" * 80)
    print(header)
    print("-" * 80)
    for ch in electrodes:
        total = sum(all_powers[ch].values())
        if total > 0:
            row = f"{ch:<10}" + "".join(
                f"{100 * all_powers[ch][b] / total:10.1f}" for b in BANDS
            )
        else:
            row = f"{ch:<10}" + "".join(f"{'N/A':>10}" for _ in BANDS)
        print(row)

    # Clinical ratios
    print()
    print("=" * 80)
    print("CLINICAL RATIOS")
    print("=" * 80)
    print(f"{'Channel':<10} {'α/θ':>10} {'δ/α':>10} {'β/α':>10}")
    print("-" * 50)
    for ch in electrodes:
        p = all_powers[ch]
        a_t = p["alpha"] / p["theta"] if p["theta"] > 0 else float("inf")
        d_a = p["delta"] / p["alpha"] if p["alpha"] > 0 else float("inf")
        b_a = p["beta"] / p["alpha"] if p["alpha"] > 0 else float("inf")
        print(f"{ch:<10} {a_t:10.2f} {d_a:10.2f} {b_a:10.2f}")


if __name__ == "__main__":
    main()
