#!/usr/bin/env python3
"""
Compute and plot power spectral density from a .easy file.

Uses Welch's method (scipy.signal.welch) and marks standard EEG frequency bands
with shaded regions. Saves the plot as a PNG.

Usage:
    python compute_psd.py [path_to_file.easy]
"""

import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import welch

from load_easy_file import load_easy

# EEG frequency bands
BANDS = {
    "delta": (0.5, 4, "#2196F3"),
    "theta": (4, 8, "#4CAF50"),
    "alpha": (8, 13, "#FF9800"),
    "beta":  (13, 30, "#F44336"),
    "gamma": (30, 80, "#9C27B0"),
}


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "sample_data", "demo_recording.easy"
    )

    df, meta = load_easy(filepath)
    fs = meta.get("sampling_rate", 500)
    electrodes = meta["electrodes"]

    # Select channels to plot (up to 4 for readability)
    plot_channels = []
    for preferred in ["Fp1", "F3", "C3", "O1"]:
        if preferred in electrodes:
            plot_channels.append(preferred)
    if not plot_channels:
        plot_channels = electrodes[:4]

    fig, axes = plt.subplots(len(plot_channels), 1, figsize=(10, 3 * len(plot_channels)), sharex=True)
    if len(plot_channels) == 1:
        axes = [axes]

    for ax, ch in zip(axes, plot_channels):
        data = df[ch].values
        freqs, psd = welch(data, fs=fs, nperseg=min(1024, len(data)))

        ax.semilogy(freqs, psd, "k-", linewidth=0.8)

        # Shade frequency bands
        for band_name, (f_low, f_high, color) in BANDS.items():
            ax.axvspan(f_low, f_high, alpha=0.15, color=color, label=band_name)

            # Compute and annotate band power
            mask = (freqs >= f_low) & (freqs <= f_high)
            band_power = np.trapezoid(psd[mask], freqs[mask])

            # Peak in this band
            if mask.any():
                peak_idx = np.argmax(psd[mask])
                peak_freq = freqs[mask][peak_idx]
                peak_pow = psd[mask][peak_idx]

        ax.set_ylabel(f"{ch}\n(µV²/Hz)")
        ax.set_xlim(0, 80)
        ax.grid(True, alpha=0.3)

    axes[0].legend(loc="upper right", fontsize=8, ncol=5)
    axes[-1].set_xlabel("Frequency (Hz)")
    fig.suptitle("Power Spectral Density — Welch's Method", fontsize=12, fontweight="bold")
    plt.tight_layout()

    out_path = os.path.join(os.path.dirname(__file__), "psd_plot.png")
    plt.savefig(out_path, dpi=150)
    print(f"PSD plot saved to {out_path}")

    # Print band power summary
    print("\nBand Power Summary (µV²):")
    print(f"{'Channel':<8}", end="")
    for band in BANDS:
        print(f"{band:>10}", end="")
    print(f"{'peak_Hz':>10}")

    for ch in plot_channels:
        data = df[ch].values
        freqs, psd = welch(data, fs=fs, nperseg=min(1024, len(data)))
        print(f"{ch:<8}", end="")
        for band_name, (f_low, f_high, _) in BANDS.items():
            mask = (freqs >= f_low) & (freqs <= f_high)
            bp = np.trapezoid(psd[mask], freqs[mask])
            print(f"{bp:10.2f}", end="")
        alpha_mask = (freqs >= 8) & (freqs <= 13)
        if alpha_mask.any():
            peak = freqs[alpha_mask][np.argmax(psd[alpha_mask])]
            print(f"{peak:10.1f}")
        else:
            print(f"{'N/A':>10}")


if __name__ == "__main__":
    main()
