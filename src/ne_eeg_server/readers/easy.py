"""
.easy + .info file parser for Neuroelectrics Enobio/Starstim recordings.

Extracted from analyze_easy.py for reuse across the server.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np
import pandas as pd


def load_easy_file(file_path: str) -> Tuple[Optional[pd.DataFrame], Optional[np.ndarray], str]:
    """Load an Enobio/Starstim .easy file.

    Returns:
        tuple: (eeg_data, time_sec, status_message)
            - eeg_data: DataFrame with EEG channels (columns: 0, 1, ..., N-1)
            - time_sec: Array of timestamps in seconds (starting from 0)
            - status_message: "Success" or error message
    """
    try:
        df = pd.read_csv(file_path, sep=None, header=None, engine='python', on_bad_lines='skip')

        if isinstance(df, pd.Series):
            df = df.to_frame().T

        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.dropna()

        if df.shape[1] <= 5:
            return None, None, f"Too few columns ({df.shape[1]})"

        num_eeg_chans = df.shape[1] - 5
        eeg_data = df.iloc[:, 0:num_eeg_chans]
        timestamps = df.iloc[:, -1]

        if isinstance(eeg_data, pd.Series):
            eeg_data = eeg_data.to_frame()

        if len(timestamps) > 0:
            start_time = timestamps.values[0]
            time_sec = (timestamps.values - start_time) / 1000.0
        else:
            return None, None, "Empty timestamp column"

        return eeg_data, time_sec, "Success"

    except Exception as e:
        return None, None, str(e)


def parse_info_file(file_path: str) -> dict:
    """Parse a .info companion file and return metadata.

    Args:
        file_path: Path to the .easy file (the .info path is derived from it).

    Returns:
        dict with keys: electrodes, device, sampling_rate, duration_s, n_channels, n_samples
    """
    info_path = file_path.replace(".easy.gz", ".info").replace(".easy", ".info")
    result = {
        "electrodes": [],
        "device": "Unknown",
        "sampling_rate": None,
        "duration_s": None,
        "n_channels": None,
        "n_samples": None,
    }

    if not os.path.isfile(info_path):
        return result

    with open(info_path) as f:
        for line in f:
            line = line.rstrip()
            if "Channel " in line and ":" in line:
                result["electrodes"].append(line.split()[-1])
            elif "Device class:" in line:
                result["device"] = line.split(":", 1)[1].strip()
            elif "EEG sampling rate:" in line:
                try:
                    result["sampling_rate"] = int(line.split(":")[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            elif "Number of EEG channels:" in line:
                try:
                    result["n_channels"] = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif "Number of records of EEG:" in line:
                try:
                    result["n_samples"] = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif "EEG recording configured duration" in line:
                try:
                    result["duration_s"] = float(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass

    return result
