"""
EDF file reader using pyedflib.

Provides a consistent interface matching the .easy and .nedf readers.
"""

from __future__ import annotations

import os

import numpy as np


def read_edf(filepath: str) -> dict:
    """Read an EDF file and return a dict with EEG data and metadata.

    Returns:
        dict with keys:
            eeg_uV: ndarray [n_samples, n_channels] in µV
            markers: ndarray [n_samples] (int) — zeros (EDF has no inline markers)
            electrodes: list[str] — channel labels
            fs: int — sampling rate (from first channel)
            num_channels: int
            device: str
            start_date: str
            duration_s: float
    """
    try:
        import pyedflib
    except ImportError:
        raise ImportError(
            "pyedflib is required for EDF support. Install with: pip install pyedflib"
        )

    if not os.path.isfile(filepath):
        raise ValueError(f"File not found: {filepath}")

    reader = pyedflib.EdfReader(filepath)
    try:
        n_channels = reader.signals_in_file
        electrodes = [reader.signal_label(i).strip() for i in range(n_channels)]
        fs = int(reader.getSampleFrequency(0))

        # Read all channels
        n_samples = reader.getNSamples()[0]
        eeg_data = np.zeros((n_samples, n_channels), dtype="float64")
        for i in range(n_channels):
            eeg_data[:, i] = reader.readSignal(i)

        # EDF stores physical values — assume µV (most common for EEG)
        # The physical dimension from the header tells us the unit
        duration_s = n_samples / fs

        start_date = reader.getStartDatetime().strftime("%Y-%m-%d %H:%M:%S")
        device = reader.getEquipment().strip() or "Unknown"

        markers = np.zeros(n_samples, dtype="int64")

        # Try to extract annotations as markers
        annotations = reader.readAnnotations()
        if annotations and len(annotations[0]) > 0:
            for onset, _, text in zip(annotations[0], annotations[1], annotations[2]):
                sample_idx = int(onset * fs)
                if 0 <= sample_idx < n_samples:
                    try:
                        markers[sample_idx] = int(text)
                    except (ValueError, TypeError):
                        # Non-numeric annotation — assign code 1
                        markers[sample_idx] = 1

    finally:
        reader.close()

    return {
        "eeg_uV": eeg_data.astype("float32"),
        "markers": markers,
        "electrodes": electrodes,
        "fs": fs,
        "num_channels": n_channels,
        "device": device,
        "start_date": start_date,
        "duration_s": duration_s,
    }
