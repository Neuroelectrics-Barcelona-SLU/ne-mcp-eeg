"""
Tool implementations for the ne-eeg-server MCP server.

Six tools for local EEG file analysis — no cloud, no patients, no stimulation.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from typing import Any

import numpy as np
from scipy.signal import welch

from ne_eeg_server.constants import ALL_VALID_POSITIONS

logger = logging.getLogger("ne_eeg_server.tools")

# Frequency bands used for spectral analysis
BANDS = {
    "delta": (0.5, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0), "gamma": (30.0, 80.0),
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _validate_eeg_path(file_path: str) -> None:
    """Shared validation for EEG file tools."""
    valid_exts = (".easy", ".easy.gz", ".nedf", ".edf")
    if not any(file_path.endswith(ext) for ext in valid_exts):
        raise ValueError(
            f"Unsupported format: {file_path}. Supported: .easy, .easy.gz, .nedf, .edf"
        )
    if not os.path.isfile(file_path):
        raise ValueError(f"File not found: {file_path}")


def _prepare_analyzer(file_path: str, tmpdir: str):
    """Prepare an EasyAnalyzer from any supported format."""
    from ne_eeg_server.readers.loader import prepare_easy_path
    from ne_eeg_server.analysis.analyzer import EasyAnalyzer

    easy_path, _is_temp = prepare_easy_path(file_path, tmpdir)

    # Parse electrode labels from .info
    info_path = easy_path.replace(".easy.gz", ".info").replace(".easy", ".info")
    electrodes: list[str] = []
    device = "Unknown"

    if os.path.isfile(info_path):
        with open(info_path) as f:
            for line in f:
                line = line.rstrip()
                if "Channel " in line:
                    electrodes.append(line.split()[-1])
                elif "Device class:" in line:
                    device = line.split(":", 1)[1].strip()

    analyzer = EasyAnalyzer(easy_path)

    if not electrodes:
        electrodes = [f"Ch{i+1}" for i in range(analyzer.num_channels)]
    electrodes = electrodes[:analyzer.num_channels]

    return analyzer, electrodes, device, easy_path


# ---------------------------------------------------------------------------
# 1. file_info
# ---------------------------------------------------------------------------

def file_info(
    file_path: str,
    start_time_s: float = 0.0,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Extract metadata from any supported NE EEG file."""
    logger.info("file_info: path=%s", file_path)
    _validate_eeg_path(file_path)

    file_size = os.path.getsize(file_path)

    # Detect format
    if file_path.endswith(".edf"):
        fmt = "edf"
    elif file_path.endswith(".nedf"):
        fmt = "nedf"
    elif file_path.endswith(".easy.gz"):
        fmt = "easy.gz"
    else:
        fmt = "easy"

    with tempfile.TemporaryDirectory(prefix="ne_eeg_") as tmpdir:
        analyzer, electrodes, device, _ = _prepare_analyzer(file_path, tmpdir)

        return {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "format": fmt,
            "num_channels": analyzer.num_channels,
            "channel_labels": electrodes,
            "sampling_rate_hz": int(analyzer.fs),
            "duration_s": round(analyzer.get_file_duration(), 2),
            "device": device,
            "file_size_bytes": file_size,
        }


# ---------------------------------------------------------------------------
# 2. list_events
# ---------------------------------------------------------------------------

def list_events(
    file_path: str,
    start_time_s: float = 0.0,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Extract all markers/events with timestamps from a recording."""
    logger.info("list_events: path=%s", file_path)
    _validate_eeg_path(file_path)

    with tempfile.TemporaryDirectory(prefix="ne_eeg_") as tmpdir:
        from ne_eeg_server.readers.loader import prepare_easy_path
        easy_path, _ = prepare_easy_path(file_path, tmpdir)

        # Load raw data to get trigger column
        data = np.loadtxt(easy_path)
        n_cols = data.shape[1]
        n_eeg = n_cols - 5
        triggers = data[:, n_eeg + 3].astype(int)
        timestamps_ms = data[:, n_eeg + 4]

        fs = 500
        n_samples = len(triggers)
        total_duration = n_samples / fs

        # Apply time window
        if duration_s is None:
            duration_s = total_duration - start_time_s
        s0 = int(start_time_s * fs)
        s1 = min(s0 + int(duration_s * fs), n_samples)

        triggers_win = triggers[s0:s1]

        # Find non-zero triggers
        event_indices = np.where(triggers_win > 0)[0]
        events = []
        for idx in event_indices:
            abs_idx = s0 + idx
            events.append({
                "time_s": round(abs_idx / fs, 3),
                "code": int(triggers_win[idx]),
                "sample_index": int(abs_idx),
            })

    return {
        "file": os.path.basename(file_path),
        "total_duration_s": round(total_duration, 1),
        "window": {
            "start_s": start_time_s,
            "end_s": round(start_time_s + duration_s, 1),
        },
        "num_events": len(events),
        "events": events,
    }


# ---------------------------------------------------------------------------
# 3. signal_quality
# ---------------------------------------------------------------------------

def signal_quality(
    file_path: str,
    channels: list[str] | None = None,
    start_time_s: float = 0.0,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Per-channel QC metrics with PASS/FAIL flags."""
    logger.info("signal_quality: path=%s channels=%s", file_path, channels)
    _validate_eeg_path(file_path)

    with tempfile.TemporaryDirectory(prefix="ne_eeg_") as tmpdir:
        analyzer, electrodes, device, _ = _prepare_analyzer(file_path, tmpdir)

        fs = analyzer.fs
        total_duration = analyzer.get_file_duration()

        if duration_s is None:
            duration_s = total_duration - start_time_s

        is_valid, err = analyzer.validate_time_window(start_time_s, duration_s)
        if not is_valid:
            raise ValueError(err)

        qc_metrics = analyzer.calculate_channel_metrics(
            window_start_s=start_time_s,
            window_duration_s=duration_s,
        )

    # Filter to requested channels
    if channels:
        label_to_idx = {label: i for i, label in enumerate(electrodes)}
        missing = [ch for ch in channels if ch not in label_to_idx]
        if missing:
            raise ValueError(f"Channels not found: {missing}. Available: {electrodes}")
        selected = {label_to_idx[ch]: ch for ch in channels}
    else:
        selected = {i: electrodes[i] for i in range(len(electrodes))}

    per_channel = {}
    for ch_idx, ch_label in selected.items():
        qc = qc_metrics.get(ch_idx, {})
        if not qc:
            continue
        per_channel[ch_label] = {
            "pass": qc.get("pass"),
            "rms_raw_uv": round(qc.get("raw_rms_uv", 0), 2),
            "rms_notch_uv": round(qc.get("notch_rms_uv", 0), 2),
            "rms_filtered_uv": round(qc.get("full_rms_uv", 0), 2),
            "mean_uv": round(qc.get("mean_uv", 0), 1),
            "kurtosis": round(qc.get("notch_kurtosis", 0), 2),
            "event_rate_hz": round(qc.get("notch_events_rate_hz", 0), 2),
            "line_power_db": round(qc.get("line_power_db", float("nan")), 1),
            "psd_peak_snr_db": round(qc.get("psd_peak_snr_db", float("nan")), 1),
            "flags": qc.get("flags", {}),
        }

    total_pass = sum(1 for v in per_channel.values() if v.get("pass", False))
    total_ch = len(per_channel)

    return {
        "file": os.path.basename(file_path),
        "device": device,
        "sampling_rate_hz": int(fs),
        "total_channels": analyzer.num_channels,
        "channel_labels": electrodes,
        "analysis_window": {
            "start_s": start_time_s,
            "end_s": round(start_time_s + duration_s, 1),
            "duration_s": round(duration_s, 1),
        },
        "qc_summary": {
            "channels_passed": total_pass,
            "channels_total": total_ch,
            "all_pass": total_pass == total_ch,
        },
        "per_channel": per_channel,
    }


# ---------------------------------------------------------------------------
# 4. analyze_eeg
# ---------------------------------------------------------------------------

def analyze_eeg(
    file_path: str,
    channels: list[str] | None = None,
    start_time_s: float = 0.0,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Full spectral analysis: PSD, band powers, ratios, peak alpha, QC, and PSD plot."""
    logger.info("analyze_eeg: path=%s channels=%s", file_path, channels)
    _validate_eeg_path(file_path)

    with tempfile.TemporaryDirectory(prefix="ne_eeg_") as tmpdir:
        analyzer, electrodes, device, _ = _prepare_analyzer(file_path, tmpdir)

        fs = analyzer.fs
        total_duration = analyzer.get_file_duration()

        if duration_s is None:
            duration_s = total_duration - start_time_s

        is_valid, err = analyzer.validate_time_window(start_time_s, duration_s)
        if not is_valid:
            raise ValueError(err)

        results = analyzer.process_window(start_time_s, duration_s)
        qc_metrics = analyzer.calculate_channel_metrics(
            window_start_s=start_time_s,
            window_duration_s=duration_s,
        )

        # Select channels
        if channels:
            label_to_idx = {label: i for i, label in enumerate(electrodes)}
            missing = [ch for ch in channels if ch not in label_to_idx]
            if missing:
                raise ValueError(f"Channels not found: {missing}. Available: {electrodes}")
            selected_indices = [label_to_idx[ch] for ch in channels]
            plot_channels = channels
        else:
            selected_indices = list(range(min(8, analyzer.num_channels)))
            plot_channels = [electrodes[i] for i in selected_indices]

        # Per-channel spectral analysis
        raw_data = results["raw_data"]
        nperseg = min(1024, raw_data.shape[0])
        channel_results = {}

        for ch_label, ch_idx in zip(plot_channels, selected_indices):
            data = raw_data[:, ch_idx]
            freqs, psd = welch(data, fs=fs, nperseg=nperseg)

            band_powers = {}
            for band_name, (f_low, f_high) in BANDS.items():
                mask = (freqs >= f_low) & (freqs <= f_high)
                band_powers[band_name] = round(float(np.trapezoid(psd[mask], freqs[mask])), 3)

            total_power = sum(band_powers.values())
            relative_powers = {
                b: round(100 * p / total_power, 1) if total_power > 0 else 0
                for b, p in band_powers.items()
            }

            alpha_mask = (freqs >= 8) & (freqs <= 13)
            peak_alpha_hz = float(freqs[alpha_mask][np.argmax(psd[alpha_mask])]) if alpha_mask.any() else None

            qc = qc_metrics.get(ch_idx, {})
            channel_results[ch_label] = {
                "mean_uv": round(float(np.mean(data)), 2),
                "std_uv": round(float(np.std(data)), 2),
                "band_powers_uv2": band_powers,
                "relative_band_powers_pct": relative_powers,
                "peak_alpha_frequency_hz": round(peak_alpha_hz, 1) if peak_alpha_hz else None,
                "alpha_theta_ratio": round(
                    band_powers["alpha"] / band_powers["theta"], 2
                ) if band_powers["theta"] > 0 else None,
                "qc": {
                    "pass": qc.get("pass"),
                    "rms_raw_uv": round(qc.get("raw_rms_uv", 0), 2),
                    "rms_notch_uv": round(qc.get("notch_rms_uv", 0), 2),
                    "rms_filtered_uv": round(qc.get("full_rms_uv", 0), 2),
                    "kurtosis": round(qc.get("notch_kurtosis", 0), 2),
                    "event_rate_hz": round(qc.get("notch_events_rate_hz", 0), 2),
                    "line_power_db": round(qc.get("line_power_db", float("nan")), 1),
                    "psd_peak_snr_db": round(qc.get("psd_peak_snr_db", float("nan")), 1),
                    "flags": qc.get("flags", {}),
                } if qc else None,
            }

        # Generate PSD plot
        plot_paths = analyzer.generate_plots(results, tmpdir, "mcp_analysis")
        psd_images = []
        for key in sorted(plot_paths.keys()):
            if "psd" in key:
                path = plot_paths[key]
                with open(path, "rb") as f:
                    psd_images.append(base64.b64encode(f.read()).decode("ascii"))

    total_pass = sum(1 for m in qc_metrics.values() if m.get("pass", False))
    total_channels_qc = len(qc_metrics)

    return {
        "file": os.path.basename(file_path),
        "device": device,
        "sampling_rate_hz": int(fs),
        "total_channels": analyzer.num_channels,
        "channel_labels": electrodes,
        "total_duration_s": round(total_duration, 1),
        "analysis_window": {
            "start_s": start_time_s,
            "end_s": round(start_time_s + duration_s, 1),
            "duration_s": round(duration_s, 1),
        },
        "channels_analyzed": plot_channels,
        "per_channel": channel_results,
        "qc_summary": {
            "channels_passed": total_pass,
            "channels_total": total_channels_qc,
            "all_pass": total_pass == total_channels_qc,
        },
        "plot_png_base64": psd_images[0] if psd_images else None,
        "additional_plots_base64": psd_images[1:] if len(psd_images) > 1 else [],
    }


# ---------------------------------------------------------------------------
# 5. generate_qc_report
# ---------------------------------------------------------------------------

def generate_qc_report(
    file_path: str,
    output_path: str | None = None,
    start_time_s: float = 0.0,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Generate a Signal Quality PDF report."""
    logger.info("generate_qc_report: path=%s", file_path)
    _validate_eeg_path(file_path)

    from ne_eeg_server.readers.loader import prepare_easy_path
    from ne_eeg_server.reports.pdf import generate_qc_report as _gen_qc

    with tempfile.TemporaryDirectory(prefix="ne_eeg_") as tmpdir:
        easy_path, is_temp = prepare_easy_path(file_path, tmpdir)
        pdf_path = _gen_qc(easy_path, output_path, start_time_s, duration_s,
                           original_file_path=file_path)

    return {
        "report_type": "Signal Quality (QC)",
        "file_analyzed": os.path.basename(file_path),
        "pdf_path": pdf_path,
        "message": f"QC report saved to {pdf_path}",
    }


# ---------------------------------------------------------------------------
# 6. generate_analysis_report
# ---------------------------------------------------------------------------

def generate_analysis_report(
    file_path: str,
    output_path: str | None = None,
    start_time_s: float = 0.0,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """Generate a functional EEG Analysis PDF report."""
    logger.info("generate_analysis_report: path=%s", file_path)
    _validate_eeg_path(file_path)

    from ne_eeg_server.readers.loader import prepare_easy_path
    from ne_eeg_server.reports.pdf import generate_analysis_report as _gen_analysis

    with tempfile.TemporaryDirectory(prefix="ne_eeg_") as tmpdir:
        easy_path, is_temp = prepare_easy_path(file_path, tmpdir)
        pdf_path = _gen_analysis(easy_path, output_path, start_time_s, duration_s,
                                 original_file_path=file_path)

    return {
        "report_type": "EEG Analysis",
        "file_analyzed": os.path.basename(file_path),
        "pdf_path": pdf_path,
        "message": f"Analysis report saved to {pdf_path}",
    }
