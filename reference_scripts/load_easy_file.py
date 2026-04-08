#!/usr/bin/env python3
"""
Load a .easy file — the traditional NE EEG workflow.

Demonstrates:
  - Parsing the ASCII tab-separated .easy format (values in nanovolts)
  - Reading the companion .info file for metadata (device, channels, sampling rate)
  - Accessing channels by 10-20 position label
  - Printing a formatted summary

Usage:
    python load_easy_file.py [path_to_file.easy]
"""

import os
import sys

import numpy as np
import pandas as pd


def parse_info_file(info_path: str) -> dict:
    """Parse a .info companion file and return metadata dict."""
    meta = {"electrodes": [], "acc_data": False}
    if not os.path.exists(info_path):
        print(f"Warning: .info file not found at {info_path}")
        return meta

    with open(info_path) as f:
        for line in f:
            line = line.rstrip()
            if "Channel " in line:
                meta["electrodes"].append(line.split()[-1])
            elif "EEG sampling rate:" in line and "Effective" not in line:
                meta["sampling_rate"] = int(float(line.split(":")[1].strip().split()[0]))
            elif "Device class:" in line:
                meta["device"] = line.split(":", 1)[1].strip()
            elif "StartDate" in line:
                meta["start_timestamp_ms"] = int(line.split(":")[1].strip())
            elif "Number of records of EEG:" in line:
                meta["num_records"] = int(line.split(":")[1].strip())
            elif "Accelerometer data: ON" in line:
                meta["acc_data"] = True
            elif "EEG units:" in line:
                meta["units"] = line.split(":")[1].strip()
    return meta


def load_easy(filepath: str) -> tuple[pd.DataFrame, dict]:
    """Load a .easy file + companion .info, return (DataFrame in µV, metadata)."""
    info_path = filepath.replace(".easy", ".info")
    meta = parse_info_file(info_path)

    df = pd.read_csv(filepath, sep="\t", header=None)

    n_cols = df.shape[1]
    electrodes = meta.get("electrodes", [])
    has_acc = meta.get("acc_data", False)

    # Determine channel count from column structure
    if has_acc:
        n_channels = n_cols - 5  # channels + 3 acc + marker + timestamp
    else:
        n_channels = n_cols - 2  # channels + marker + timestamp

    # Use electrode labels from .info, or generate defaults
    if not electrodes:
        electrodes = [f"Ch{i+1}" for i in range(n_channels)]

    # Name columns
    if has_acc:
        df.columns = electrodes + ["ax", "ay", "az", "markers", "unix_time"]
    else:
        df.columns = electrodes + ["markers", "unix_time"]

    # Convert EEG from nV to µV
    df[electrodes] = df[electrodes] / 1000.0

    meta["electrodes"] = electrodes
    meta["n_channels"] = n_channels
    meta["n_samples"] = len(df)
    fs = meta.get("sampling_rate", 500)
    meta["duration_s"] = meta["n_samples"] / fs

    return df, meta


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "sample_data", "demo_recording.easy"
    )

    print(f"Loading: {filepath}\n")
    df, meta = load_easy(filepath)

    # Summary
    print("=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)
    print(f"  Device:        {meta.get('device', 'Unknown')}")
    print(f"  Channels:      {meta['n_channels']}")
    print(f"  Labels:        {', '.join(meta['electrodes'])}")
    print(f"  Samples:       {meta['n_samples']}")
    print(f"  Sampling rate: {meta.get('sampling_rate', 500)} S/s")
    print(f"  Duration:      {meta['duration_s']:.1f} s")
    print(f"  Units:         µV (converted from {meta.get('units', 'nV')})")
    print()

    # First 10 samples
    print("First 10 samples (µV):")
    print(df[meta["electrodes"]].head(10).to_string(float_format="%.2f"))
    print()

    # Channel access by label
    ch = "O1" if "O1" in meta["electrodes"] else meta["electrodes"][0]
    print(f"Accessing channel '{ch}':")
    data = df[ch].values
    print(f"  Mean:  {np.mean(data):.2f} µV")
    print(f"  Std:   {np.std(data):.2f} µV")
    print(f"  Min:   {np.min(data):.2f} µV")
    print(f"  Max:   {np.max(data):.2f} µV")


if __name__ == "__main__":
    main()
