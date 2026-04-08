"""
Easy File Analyzer - Backend Processing Logic
(G. Ruffini, Jan 2026)

Main EasyAnalyzer class for .easy files: loads recordings, extracts time windows,
applies filtering, generates plots, and computes per-channel QC metrics.
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import signal
from scipy.signal import iirnotch, tf2sos
from typing import Optional, Tuple, List, Dict

from ne_eeg_server.analysis.metrics_defaults import METRICS_DEFAULT_THRESHOLDS, DEFAULT_EVENT_THRESHOLD_UV
from ne_eeg_server.analysis.qc import calculate_channel_metrics_from_signals
from ne_eeg_server.analysis.plotting import plot_stacked_timeseries, plot_psd_grid
from ne_eeg_server.readers.easy import load_easy_file


# ==============================================================================
# FILTERING FUNCTIONS
# ==============================================================================

def apply_filtering(data: np.ndarray, fs: float = 500.0) -> np.ndarray:
    """Apply filtering cascade: 1-40 Hz bandpass + 50/60 Hz notch filters."""
    low_cut = 1.0
    high_cut = 40.0
    filter_order = 4

    sos_bandpass = signal.butter(filter_order, [low_cut, high_cut], btype='bandpass',
                                 fs=fs, output='sos')

    notch_q = 30.0
    b50, a50 = iirnotch(50.0, notch_q, fs)
    b60, a60 = iirnotch(60.0, notch_q, fs)
    sos_notch_50 = tf2sos(b50, a50)
    sos_notch_60 = tf2sos(b60, a60)

    if data.ndim == 1:
        filtered = signal.sosfiltfilt(sos_bandpass, data)
        filtered = signal.sosfiltfilt(sos_notch_50, filtered)
        filtered = signal.sosfiltfilt(sos_notch_60, filtered)
    else:
        filtered = signal.sosfiltfilt(sos_bandpass, data, axis=0)
        filtered = signal.sosfiltfilt(sos_notch_50, filtered, axis=0)
        filtered = signal.sosfiltfilt(sos_notch_60, filtered, axis=0)

    return filtered


def remove_edge_transients(data: np.ndarray, fs: float = 500.0) -> np.ndarray:
    """Remove edge transients after filtering (0.5 seconds from each edge)."""
    transient_samples = int(0.5 * fs)

    if len(data) > 2 * transient_samples:
        trimmed = data[transient_samples:-transient_samples]
        padded = np.full(len(data), np.nan)
        padded[transient_samples:-transient_samples] = trimmed
        return padded
    else:
        return data


def calculate_rms(data: np.ndarray) -> float:
    """Calculate RMS (Root Mean Square) amplitude in µV."""
    return np.sqrt(np.mean(data**2))


# ==============================================================================
# MAIN ANALYZER CLASS
# ==============================================================================

class EasyAnalyzer:
    """Main analyzer class for .easy files."""

    def __init__(self, file_path: str, fs: float = 500.0):
        self.file_path = file_path
        self.fs = fs
        self.eeg_data = None
        self.time_sec = None
        self.total_channels = 0
        self.num_channels = 0
        self.status = None

        self.eeg_data, self.time_sec, self.status = load_easy_file(file_path)

        if self.eeg_data is not None:
            self.total_channels = int(self.eeg_data.shape[1])
            self.num_channels = int(self._infer_effective_num_channels(self.eeg_data))
            self.eeg_data = self.eeg_data.iloc[:, :self.num_channels].copy()
        else:
            raise ValueError(f"Failed to load .easy file: {self.status}")

    @staticmethod
    def _infer_effective_num_channels(eeg_data: pd.DataFrame) -> int:
        """Infer the *effective* number of EEG channels from data content."""
        n = int(eeg_data.shape[1])
        if n <= 8:
            return n

        def has_any_nonzero(col_idx: int) -> bool:
            if col_idx >= n:
                return False
            col = eeg_data.iloc[:, col_idx].to_numpy()
            return np.any(np.nan_to_num(col, nan=0.0) != 0)

        if has_any_nonzero(20):
            return min(32, n)
        if has_any_nonzero(8):
            return min(20, n)
        return 8

    def get_file_duration(self) -> float:
        """Get the total duration of the loaded file in seconds."""
        if self.time_sec is None or len(self.time_sec) == 0:
            return 0.0
        return self.time_sec[-1] - self.time_sec[0]

    def validate_time_window(self, start_time: float, duration: float) -> Tuple[bool, str]:
        """Validate that the requested time window is within file bounds."""
        if self.eeg_data is None or self.time_sec is None:
            return False, "No data loaded. Please load a file first."

        total_duration = self.get_file_duration()

        if start_time < 0:
            return False, f"Start time ({start_time:.1f}s) cannot be negative."
        if start_time >= total_duration:
            return False, f"Start time ({start_time:.1f}s) is beyond file duration ({total_duration:.1f}s)."
        if duration <= 0:
            return False, f"Duration ({duration:.1f}s) must be positive."

        end_time = start_time + duration
        if end_time > total_duration:
            return False, (
                f"Requested window ({start_time:.1f}s to {end_time:.1f}s) exceeds "
                f"file duration ({total_duration:.1f}s). Available: 0.0s to {total_duration:.1f}s."
            )

        return True, ""

    def extract_time_window(self, start_time: float, duration: float) -> Tuple[pd.DataFrame, np.ndarray]:
        """Extract a time window from the loaded data."""
        if self.eeg_data is None:
            raise ValueError("No data loaded.")

        is_valid, error_msg = self.validate_time_window(start_time, duration)
        if not is_valid:
            raise ValueError(error_msg)

        start_idx = int(start_time * self.fs)
        end_idx = int((start_time + duration) * self.fs)

        start_idx = max(0, start_idx)
        end_idx = min(len(self.eeg_data), end_idx)

        if start_idx >= end_idx:
            raise ValueError(f"Invalid time window: start_idx ({start_idx}) >= end_idx ({end_idx})")

        eeg_window = self.eeg_data.iloc[start_idx:end_idx].copy()
        time_window = self.time_sec[start_idx:end_idx]

        return eeg_window, time_window

    def process_window(self, start_time: float, duration: float,
                       channel_groups: Optional[List[List[int]]] = None) -> Dict:
        """Process a time window: extract, filter, and prepare data for plotting."""
        eeg_window, time_window = self.extract_time_window(start_time, duration)

        rms_values = {}
        data_nv = eeg_window.iloc[:, :self.num_channels].values
        raw_uv = data_nv / 1000.0
        raw_demeaned = raw_uv - np.mean(raw_uv, axis=0, keepdims=True)

        filtered_cols = []
        for ch_idx in range(raw_demeaned.shape[1]):
            x = raw_demeaned[:, ch_idx]
            y = apply_filtering(x, self.fs)
            y = remove_edge_transients(y, self.fs)
            filtered_cols.append(y)
            valid = y[~np.isnan(y)]
            if len(valid) > 0:
                rms_values[ch_idx] = float(np.sqrt(np.mean(valid ** 2)))

        filtered = np.vstack(filtered_cols).T

        return {
            'raw_data': raw_demeaned,
            'filtered_data': filtered,
            'time': time_window,
            'rms_values': rms_values,
            'num_channels': self.num_channels,
            'total_channels': self.total_channels,
        }

    def calculate_channel_metrics(
        self,
        event_threshold_uv: float = DEFAULT_EVENT_THRESHOLD_UV,
        thresholds: Optional[dict] = None,
        window_start_s: Optional[float] = None,
        window_duration_s: Optional[float] = None,
    ) -> Dict[int, Dict]:
        """Compute per-channel QC metrics over a selected analysis window."""
        if self.eeg_data is None or len(self.eeg_data) == 0:
            return {}

        fs = float(self.fs)

        data_src = self.eeg_data
        if window_start_s is not None and window_duration_s is not None:
            try:
                eeg_window, _time_window = self.extract_time_window(
                    float(window_start_s), float(window_duration_s))
                data_src = eeg_window
            except Exception:
                data_src = self.eeg_data

        x_uv_raw = (data_src.to_numpy(dtype=float) / 1000.0)
        raw_means = {int(ch): float(np.mean(x_uv_raw[:, ch])) for ch in range(int(self.num_channels))}
        x_uv = x_uv_raw - np.mean(x_uv_raw, axis=0, keepdims=True)

        signals: Dict[int, np.ndarray] = {}
        for ch in range(int(self.num_channels)):
            signals[int(ch)] = x_uv[:, ch]

        return calculate_channel_metrics_from_signals(
            signals,
            fs=float(fs),
            event_threshold_uv=float(event_threshold_uv),
            thresholds=thresholds,
            raw_means_uv=raw_means,
        )

    def generate_plots(self, results: Dict, output_dir: str, basename: str) -> Dict[str, str]:
        """Generate and save plots for a processed window."""
        os.makedirs(output_dir, exist_ok=True)

        plot_paths = {}
        time_window = results['time']

        num_channels = int(results.get('num_channels', self.num_channels))
        channels_all = list(range(num_channels))

        ts_pages = [channels_all[:16], channels_all[16:32]]
        ts_pages = [p for p in ts_pages if p]

        raw_full = results['raw_data']
        filtered_full = results['filtered_data']

        for page_idx, page_channels in enumerate(ts_pages, start=1):
            page_suffix = "" if page_idx == 1 else f"_page{page_idx}"
            pad_to_16 = 16 if (len(ts_pages) > 1 and len(page_channels) < 16) else None

            raw_path = os.path.join(output_dir, f"{basename}_raw{page_suffix}.png")
            plot_stacked_timeseries(
                raw_full[:, page_channels], time_window, page_channels,
                title=f"Raw Data - Channels {page_channels[0]+1}-{page_channels[-1]+1}",
                output_path=raw_path, scale_uv=10.0, target_rows=pad_to_16,
            )
            plot_paths[f'raw_page{page_idx}'] = raw_path

            filtered_path = os.path.join(output_dir, f"{basename}_filtered{page_suffix}.png")
            plot_stacked_timeseries(
                filtered_full[:, page_channels], time_window, page_channels,
                title=f"Filtered 1-40 Hz + 50/60 Hz Notch - Channels {page_channels[0]+1}-{page_channels[-1]+1}",
                output_path=filtered_path, scale_uv=5.0, target_rows=pad_to_16,
            )
            plot_paths[f'filtered_page{page_idx}'] = filtered_path

        psd_pages = [channels_all[i:i+8] for i in range(0, len(channels_all), 8)]
        for page_idx, page_channels in enumerate(psd_pages, start=1):
            page_suffix = "" if page_idx == 1 else f"_page{page_idx}"
            psd_path = os.path.join(output_dir, f"{basename}_psd{page_suffix}.png")
            plot_psd_grid(
                raw_full[:, page_channels], page_channels,
                fs=float(self.fs), output_path=psd_path,
                title=(
                    f"Power Spectral Density - Channels {page_channels[0]+1}-{page_channels[-1]+1}\n"
                    f"Resolution: 0.5 Hz, Sampling Rate: {self.fs} Hz"
                ),
                resolution_hz=0.5, max_freq_hz=100.0, y_min=1e-4, y_max=1e3, ref_line=1.33,
            )
            plot_paths[f'psd_page{page_idx}'] = psd_path

        return plot_paths
