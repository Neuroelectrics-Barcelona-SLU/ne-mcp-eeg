#!/usr/bin/env python3
"""
Generate a synthetic demo_recording.easy and demo_recording.info file.

8 channels, 10 seconds, 500 S/s. Contains:
- Alpha rhythm (~10 Hz) in occipital channels (O1, O2)
- Theta activity in frontal channels (Fp1, Fp2)
- A few artifact samples
- All values in nanovolts (nV) as per NE .easy format
"""

import numpy as np
import os

CHANNELS = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2"]
FS = 500
DURATION_S = 10
N_SAMPLES = FS * DURATION_S
BASE_TIMESTAMP_MS = 1724760000000  # arbitrary Unix ms

rng = np.random.RandomState(12345)
t = np.arange(N_SAMPLES) / FS

# Build per-channel signals (in µV, then convert to nV)
signals_uv = {}
for ch in CHANNELS:
    # Background noise: ~5 µV
    sig = rng.randn(N_SAMPLES) * 5.0

    if ch in ("O1", "O2"):
        # Strong alpha rhythm ~10 Hz, amplitude ~20 µV
        sig += 20.0 * np.sin(2 * np.pi * 10.0 * t + rng.uniform(0, 2 * np.pi))
        # Some beta
        sig += 3.0 * np.sin(2 * np.pi * 22.0 * t)
    elif ch in ("Fp1", "Fp2"):
        # Frontal theta ~6 Hz, amplitude ~12 µV
        sig += 12.0 * np.sin(2 * np.pi * 6.0 * t + rng.uniform(0, 2 * np.pi))
        # Eye blink artifacts at a few points
        for blink_t in [1.5, 4.2, 7.8]:
            idx = int(blink_t * FS)
            width = int(0.15 * FS)
            blink = 80.0 * np.exp(-0.5 * ((np.arange(width) - width // 2) / (width / 6)) ** 2)
            sig[idx:idx + width] += blink
    elif ch in ("F3", "F4"):
        sig += 8.0 * np.sin(2 * np.pi * 7.5 * t + rng.uniform(0, 2 * np.pi))
    elif ch in ("C3", "C4"):
        # Mu rhythm ~10 Hz, moderate
        sig += 10.0 * np.sin(2 * np.pi * 10.5 * t + rng.uniform(0, 2 * np.pi))

    signals_uv[ch] = sig

# Convert to nV (integer, as in real .easy files)
signals_nv = {ch: (sig * 1000).astype(np.int64) for ch, sig in signals_uv.items()}

# Accelerometer: near-zero (stationary subject)
acc_x = (rng.randn(N_SAMPLES) * 10).astype(int)
acc_y = (rng.randn(N_SAMPLES) * 10).astype(int)
acc_z = (9810 + rng.randn(N_SAMPLES) * 10).astype(int)  # ~1g in mm/s²

# Markers: all zero except at a few events
markers = np.zeros(N_SAMPLES, dtype=int)
markers[int(1.0 * FS)] = 1  # eyes open
markers[int(5.0 * FS)] = 2  # eyes closed
markers[int(8.0 * FS)] = 1  # eyes open

# Timestamps
timestamps = BASE_TIMESTAMP_MS + (np.arange(N_SAMPLES) * 2).astype(np.int64)  # 2ms spacing

# Write .easy file
out_dir = os.path.dirname(os.path.abspath(__file__))
easy_path = os.path.join(out_dir, "demo_recording.easy")
with open(easy_path, "w") as f:
    for i in range(N_SAMPLES):
        row = [str(signals_nv[ch][i]) for ch in CHANNELS]
        row.extend([str(acc_x[i]), str(acc_y[i]), str(acc_z[i])])
        row.append(str(markers[i]))
        row.append(str(timestamps[i]))
        f.write("\t".join(row) + "\n")

# Write .info file
info_path = os.path.join(out_dir, "demo_recording.info")
with open(info_path, "w") as f:
    f.write("Step Details\n")
    f.write("Info Version: 1.2\n")
    f.write("Step name: demo_recording\n")
    f.write(f"StartDate (firstEEGtimestamp): {BASE_TIMESTAMP_MS}\n")
    f.write("Device class: ENOBIO\n")
    f.write("Communication type: Bluetooth\n")
    f.write("Device ID: NE-BT(DEMO-0001)\n")
    f.write("Software's version: NIC v2.1.4.0\n")
    f.write("Firmware's version: 2.8.4\n")
    f.write("Operative system: macOS\n")
    f.write("SDCard Filename: NONE\n")
    f.write("Additional channel: NONE\n")
    f.write("\n")
    f.write("EEG Settings\n")
    f.write(f"Total number of channels: {len(CHANNELS)}\n")
    f.write(f"Number of EEG channels: {len(CHANNELS)}\n")
    f.write(f"Number of records of EEG: {N_SAMPLES}\n")
    f.write(f"EEG sampling rate: {FS} Samples/second\n")
    f.write(f"Effective EEG sampling rate: {FS}.000000 Samples/second\n")
    f.write(f"EEG recording configured duration (s): {DURATION_S}\n")
    f.write("Number of packets lost: 0\n")
    f.write("Line filter status: OFF\n")
    f.write("FIR filter status: OFF\n")
    f.write("EOG correction filter status: OFF\n")
    f.write("Reference filter status: OFF\n")
    f.write("EEG units: nV\n")
    f.write("EEG montage: \n")
    for i, ch in enumerate(CHANNELS, 1):
        f.write(f"\tChannel {i}: {ch}\n")
    f.write("Accelerometer data: ON\n")
    f.write("\n")
    f.write("Number of channels of Accelerometer: 3\n")
    f.write(f"Accelerometer sampling rate: 100 Samples/second\n")
    f.write("Accelerometer units: mm/s^2\n")
    f.write("\n")
    f.write("Trigger information:\n")
    f.write("\tCode\tDescription\n")
    f.write("\t1\tEO\n")
    f.write("\t2\tEC\n")

print(f"Generated {easy_path}")
print(f"Generated {info_path}")
print(f"Samples: {N_SAMPLES}, Channels: {len(CHANNELS)}, Duration: {DURATION_S}s")
