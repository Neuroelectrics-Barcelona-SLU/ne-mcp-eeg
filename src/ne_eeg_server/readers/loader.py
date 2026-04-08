"""
Unified file loader for .easy, .nedf, and .edf formats.

For .easy files: returns the path as-is (the analysis pipeline handles them directly).
For .nedf files: reads the binary data, writes a temporary .easy + .info pair,
and returns the temp .easy path so the existing EasyAnalyzer pipeline works unchanged.
For .edf files: reads via pyedflib, writes a temporary .easy + .info pair.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np


def prepare_easy_path(file_path: str, tmpdir: str | None = None) -> tuple[str, bool]:
    """Ensure the file is available as a .easy + .info pair.

    Args:
        file_path: Path to a .easy, .nedf, or .edf file.
        tmpdir: If provided, temp files go here (caller manages cleanup).

    Returns:
        (easy_path, is_temp): the path to the .easy file, and whether it's a temp file.
    """
    if file_path.endswith(".easy") or file_path.endswith(".easy.gz"):
        return file_path, False

    if file_path.endswith(".nedf"):
        return _nedf_to_easy(file_path, tmpdir), True

    if file_path.endswith(".edf"):
        return _edf_to_easy(file_path, tmpdir), True

    raise ValueError(
        f"Unsupported format: {file_path}. "
        f"Supported formats: .easy, .easy.gz, .nedf, .edf"
    )


def _nedf_to_easy(nedf_path: str, tmpdir: str | None = None) -> str:
    """Convert a .nedf file to a temporary .easy + .info pair."""
    from ne_eeg_server.readers.nedf import read_nedf

    data = read_nedf(nedf_path)

    if tmpdir is None:
        tmpdir = tempfile.mkdtemp(prefix="ne_eeg_")

    basename = os.path.splitext(os.path.basename(nedf_path))[0]
    easy_path = os.path.join(tmpdir, f"{basename}.easy")
    info_path = os.path.join(tmpdir, f"{basename}.info")

    _write_easy_info_pair(data, easy_path, info_path, basename)
    return easy_path


def _edf_to_easy(edf_path: str, tmpdir: str | None = None) -> str:
    """Convert an .edf file to a temporary .easy + .info pair."""
    from ne_eeg_server.readers.edf import read_edf

    data = read_edf(edf_path)

    if tmpdir is None:
        tmpdir = tempfile.mkdtemp(prefix="ne_eeg_")

    basename = os.path.splitext(os.path.basename(edf_path))[0]
    easy_path = os.path.join(tmpdir, f"{basename}.easy")
    info_path = os.path.join(tmpdir, f"{basename}.info")

    _write_easy_info_pair(data, easy_path, info_path, basename)
    return easy_path


def _write_easy_info_pair(data: dict, easy_path: str, info_path: str, basename: str) -> None:
    """Write .easy + .info files from a reader data dict."""
    eeg_uV = data["eeg_uV"]
    markers = data["markers"]
    n_samples, n_ch = eeg_uV.shape
    fs = data["fs"]
    electrodes = data["electrodes"]

    # Convert µV back to nV for .easy format
    eeg_nV = (eeg_uV * 1000.0).astype(np.int64)

    # Build timestamp column
    start_ts_ms = int(data.get("start_date_unix_ms", 0))
    if start_ts_ms == 0:
        import datetime
        try:
            dt = datetime.datetime.strptime(data["start_date"], "%Y-%m-%d %H:%M:%S")
            start_ts_ms = int(dt.timestamp() * 1000)
        except Exception:
            start_ts_ms = 1555686945081  # fallback

    timestamps = start_ts_ms + (np.arange(n_samples) * (1000.0 / fs)).astype(np.int64)

    # Fake accelerometer (zeros)
    acc = np.zeros((n_samples, 3), dtype=int)

    with open(easy_path, "w") as f:
        for i in range(n_samples):
            row = "\t".join(str(int(eeg_nV[i, ch])) for ch in range(n_ch))
            row += f"\t{acc[i,0]}\t{acc[i,1]}\t{acc[i,2]}"
            row += f"\t{int(markers[i])}\t{int(timestamps[i])}"
            f.write(row + "\n")

    with open(info_path, "w") as f:
        f.write("Step Details\n")
        f.write("Info Version: 1.2\n")
        f.write(f"Step name: {basename}\n")
        f.write(f"StartDate (firstEEGtimestamp): {start_ts_ms}\n")
        f.write(f"Device class: {data.get('device', 'Unknown')}\n")
        f.write("Communication type: WiFi\n")
        f.write("Software's version: NIC v2.0\n")
        f.write("Firmware's version: unknown\n")
        f.write("Operative system: unknown\n")
        f.write("SDCard Filename: NONE\n")
        f.write("Additional channel: NONE\n")
        f.write("\n")
        f.write("EEG Settings\n")
        f.write(f"Total number of channels: {n_ch}\n")
        f.write(f"Number of EEG channels: {n_ch}\n")
        f.write(f"Number of records of EEG: {n_samples}\n")
        f.write(f"EEG sampling rate: {fs} Samples/second\n")
        f.write(f"EEG recording configured duration (s): {int(data.get('duration_s', n_samples / fs))}\n")
        f.write("Number of packets lost: 0\n")
        f.write("Line filter status: OFF\n")
        f.write("FIR filter status: OFF\n")
        f.write("EOG correction filter status: OFF\n")
        f.write("Reference filter status: OFF\n")
        f.write("EEG units: nV\n")
        f.write("EEG electrode montage: \n")
        for i, label in enumerate(electrodes, 1):
            f.write(f"\tChannel {i}: {label}\n")
        f.write("Accelerometer data: ON\n")
