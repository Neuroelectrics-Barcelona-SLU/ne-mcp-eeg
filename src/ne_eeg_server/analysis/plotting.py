"""
Shared EEG plotting helpers (matplotlib).
(G. Ruffini, Jan 2026)
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import signal


def plot_stacked_timeseries(
    data_uv: np.ndarray,
    time_s: np.ndarray,
    channels: List[int],
    *,
    title: str,
    output_path: str,
    scale_uv: float,
    target_rows: Optional[int] = None,
    line_color: str = "#0074D9",
) -> None:
    """Plot stacked time-series traces (one subplot per channel)."""
    if data_uv is None or time_s is None:
        return
    if data_uv.ndim != 2:
        raise ValueError(f"data_uv must be 2D [samples, channels], got shape {getattr(data_uv, 'shape', None)}")
    if len(time_s) != int(data_uv.shape[0]):
        raise ValueError("time_s length must match data_uv samples dimension")
    if len(channels) != int(data_uv.shape[1]):
        raise ValueError("channels length must match data_uv channels dimension")

    num_chans = int(data_uv.shape[1])
    n_rows = int(target_rows) if (target_rows is not None and int(target_rows) > 0) else num_chans
    n_rows = max(n_rows, num_chans)

    fig, axes = plt.subplots(n_rows, 1, figsize=(15, max(4, n_rows * 1.2)), sharex=True)
    if n_rows == 1:
        axes = [axes]

    fig.suptitle(title, fontsize=14, fontweight="bold")

    for i, ax in enumerate(axes):
        if i < num_chans:
            ch_idx = int(channels[i])
            ax.plot(time_s, data_uv[:, i], color=line_color, linewidth=0.8)
            ax.set_ylim(-float(scale_uv), float(scale_uv))
            ax.set_ylabel(f"Ch {ch_idx + 1} (µV)", fontsize=9)
            ax.grid(True, linestyle="--", alpha=0.5)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
        else:
            ax.axis("off")

    if num_chans > 0:
        bottom_ax = axes[num_chans - 1]
        bottom_ax.set_xlabel("Time (s)", fontsize=10)
        bottom_ax.tick_params(axis="x", labelbottom=True)
        for ax in axes[: max(0, num_chans - 1)]:
            ax.tick_params(axis="x", labelbottom=False)

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_psd_grid(
    data_uv: np.ndarray,
    channels: List[int],
    *,
    fs: float,
    output_path: str,
    title: Optional[str] = None,
    resolution_hz: float = 0.5,
    max_freq_hz: float = 100.0,
    y_min: float = 1e-4,
    y_max: float = 1e3,
    ref_line: float = 1.33,
    floor_line: float = 1e-1,
    line_color: str = "#0074D9",
) -> None:
    """Plot PSDs on a 2x4 grid (up to 8 channels per page)."""
    if data_uv is None:
        return
    if data_uv.ndim != 2:
        raise ValueError(f"data_uv must be 2D [samples, channels], got shape {getattr(data_uv, 'shape', None)}")
    if len(channels) != int(data_uv.shape[1]):
        raise ValueError("channels length must match data_uv channels dimension")

    n_ch = int(data_uv.shape[1])
    fig, axes = plt.subplots(2, 4, figsize=(16, 10))
    axes = axes.flatten()

    nfft = int(float(fs) / float(resolution_hz))
    nperseg_base = min(nfft, int(data_uv.shape[0]) // 4)
    if nperseg_base < 64:
        nperseg_base = min(64, int(data_uv.shape[0]) // 2)

    for plot_idx, ch_idx in enumerate(channels[:8]):
        ax = axes[plot_idx]
        x = data_uv[:, plot_idx]
        valid = x[~np.isnan(x)]
        if len(valid) < max(1, int(nperseg_base)):
            ax.text(0.5, 0.5, f"Insufficient data\nfor channel {int(ch_idx) + 1}",
                    ha="center", va="center", transform=ax.transAxes, fontsize=9)
            ax.set_title(f"Channel {int(ch_idx) + 1}", fontsize=10, fontweight="bold")
            ax.axis("off")
            continue

        valid = valid - float(np.mean(valid))
        freqs, psd = signal.welch(valid, fs=float(fs), nperseg=int(nperseg_base),
                                  nfft=int(nfft), window="hann", scaling="density")

        ax.semilogy(freqs, psd, linewidth=1.5, color=line_color)
        ax.set_xlabel("Frequency (Hz)", fontsize=9)
        ax.set_ylabel("PSD (µV²/Hz)", fontsize=9)
        ax.set_title(f"Channel {int(ch_idx) + 1}", fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.set_xlim(0, min(float(max_freq_hz), float(fs) / 2.0))
        ax.set_ylim(float(y_min), float(y_max))
        ax.axhline(float(ref_line), color="red", linestyle="--", linewidth=1.2, alpha=0.7)
        ax.axhline(float(floor_line), color="#808080", linestyle="--", linewidth=1.0, alpha=0.6)

        ax.axvspan(1, 4, alpha=0.1, color="blue")
        ax.axvspan(4, 8, alpha=0.1, color="green")
        ax.axvspan(8, 13, alpha=0.1, color="orange")
        ax.axvspan(13, 30, alpha=0.1, color="red")

    for idx in range(min(8, n_ch), 8):
        axes[idx].axis("off")

    if title:
        fig.suptitle(str(title), fontsize=12, fontweight="bold", y=0.995)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
