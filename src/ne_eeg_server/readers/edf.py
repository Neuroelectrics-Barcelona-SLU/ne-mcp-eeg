"""
EDF file reader with a two-stage strategy:

1. Try pyedflib (fast, well-tested).
2. On any compliance error, fall back to a built-in permissive EDF parser that
   tolerates non-standard date fields, zero day/month values, ':' separators,
   and other quirks produced by BrainProducts, BioSemi, g.tec, etc.
"""

from __future__ import annotations

import os
import struct

import numpy as np


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_edf(filepath: str) -> dict:
    """Read an EDF/EDF+ file and return normalised EEG data.

    Returns:
        dict with keys:
            eeg_uV      : ndarray [n_samples, n_channels] float32, µV
            markers     : ndarray [n_samples] int64 — EDF+ annotation codes or zeros
            electrodes  : list[str] — channel labels
            fs          : int — sampling rate (Hz)
            num_channels: int
            device      : str
            start_date  : str
            duration_s  : float
    """
    if not os.path.isfile(filepath):
        raise ValueError(f"File not found: {filepath}")

    # --- attempt 1: pyedflib ---
    try:
        import pyedflib
        return _read_via_pyedflib(filepath, pyedflib)
    except ImportError:
        pass  # pyedflib not installed — go straight to fallback
    except Exception:
        pass  # compliance error or other pyedflib failure — use fallback

    # --- attempt 2: built-in permissive parser ---
    return _read_raw_edf(filepath)


# ---------------------------------------------------------------------------
# pyedflib path
# ---------------------------------------------------------------------------

def _read_via_pyedflib(filepath: str, pyedflib) -> dict:
    reader = pyedflib.EdfReader(filepath)
    try:
        n_ch = reader.signals_in_file
        electrodes = [reader.signal_label(i).strip() for i in range(n_ch)]
        fs = int(reader.getSampleFrequency(0))
        n_samples = reader.getNSamples()[0]

        eeg = np.zeros((n_samples, n_ch), dtype="float64")
        for i in range(n_ch):
            eeg[:, i] = reader.readSignal(i)

        start_date = reader.getStartDatetime().strftime("%Y-%m-%d %H:%M:%S")
        device = reader.getEquipment().strip() or "Unknown"

        markers = np.zeros(n_samples, dtype="int64")
        ann = reader.readAnnotations()
        if ann and len(ann[0]) > 0:
            for onset, _, text in zip(ann[0], ann[1], ann[2]):
                idx = int(onset * fs)
                if 0 <= idx < n_samples:
                    try:
                        markers[idx] = int(text)
                    except (ValueError, TypeError):
                        markers[idx] = 1
    finally:
        reader.close()

    return {
        "eeg_uV": eeg.astype("float32"),
        "markers": markers,
        "electrodes": electrodes,
        "fs": fs,
        "num_channels": n_ch,
        "device": device,
        "start_date": start_date,
        "duration_s": n_samples / fs,
    }


# ---------------------------------------------------------------------------
# Built-in permissive EDF parser
# ---------------------------------------------------------------------------

def _read_raw_edf(filepath: str) -> dict:
    """Parse an EDF/EDF+ file without strict header validation."""
    with open(filepath, "rb") as f:
        raw = f.read()

    # ---- fixed header (256 bytes) ----
    hdr = raw[:256]
    start_date = hdr[168:176].decode("latin-1").strip()
    start_time = hdr[176:184].decode("latin-1").strip()
    n_bytes_header = int(hdr[184:192].decode("latin-1").strip())
    n_records = int(hdr[236:244].decode("latin-1").strip())
    record_dur = float(hdr[244:252].decode("latin-1").strip())
    n_signals = int(hdr[252:256].decode("latin-1").strip())

    # ---- per-signal header fields ----
    def _field(offset, width):
        return [
            raw[256 + offset * n_signals + i * width: 256 + offset * n_signals + (i + 1) * width]
            .decode("latin-1").strip()
            for i in range(n_signals)
        ]

    labels       = _field(0,   16)
    phys_dim     = _field(96,   8)
    phys_min     = [float(v) for v in _field(104,  8)]
    phys_max     = [float(v) for v in _field(112,  8)]
    dig_min      = [float(v) for v in _field(120,  8)]
    dig_max      = [float(v) for v in _field(128,  8)]
    n_samp_rec   = [int(v)   for v in _field(216,  8)]
    # reserved per signal (32 bytes each) contains EDF+ annotation marker
    reserved_sig = _field(224, 32)

    # EDF+ annotation channel is labeled "EDF Annotations"
    ann_indices = [i for i, lbl in enumerate(labels) if "annotation" in lbl.lower()]
    eeg_indices = [i for i in range(n_signals) if i not in ann_indices]

    if not eeg_indices:
        raise ValueError("No EEG signal channels found in EDF file.")

    # gain (digital → µV)
    gain = [
        (phys_max[i] - phys_min[i]) / (dig_max[i] - dig_min[i])
        if (dig_max[i] - dig_min[i]) != 0 else 1.0
        for i in range(n_signals)
    ]
    offset_v = [phys_min[i] - gain[i] * dig_min[i] for i in range(n_signals)]

    # sampling rate from first EEG channel
    fs_idx = eeg_indices[0]
    fs = int(round(n_samp_rec[fs_idx] / record_dur)) if record_dur > 0 else n_samp_rec[fs_idx]

    # total samples per channel
    n_samples_total = n_records * n_samp_rec[fs_idx]
    n_ch = len(eeg_indices)

    eeg = np.zeros((n_samples_total, n_ch), dtype="float32")
    markers = np.zeros(n_samples_total, dtype="int64")

    # record size in samples per signal
    record_size = sum(n_samp_rec)

    data_start = n_bytes_header
    for rec in range(n_records):
        rec_offset = data_start + rec * record_size * 2  # int16 = 2 bytes
        sig_offset = 0
        for sig in range(n_signals):
            n = n_samp_rec[sig]
            raw_sig = raw[rec_offset + sig_offset * 2: rec_offset + (sig_offset + n) * 2]
            if sig in eeg_indices:
                ch = eeg_indices.index(sig)
                samples = np.frombuffer(raw_sig, dtype="<i2").astype("float32")
                samples = samples * gain[sig] + offset_v[sig]
                start_s = rec * n_samp_rec[fs_idx]
                eeg[start_s: start_s + n, ch] = samples
            sig_offset += n

    electrodes = [labels[i] for i in eeg_indices]
    # Clean up common label suffixes (e.g. "Fp1-Ref", "EEG Fp1")
    electrodes = [_clean_label(lbl) for lbl in electrodes]

    # Try to parse start_date into a readable string (best-effort)
    start_dt = f"{start_date} {start_time}".replace(".", ":").replace("-", ":")

    return {
        "eeg_uV": eeg,
        "markers": markers,
        "electrodes": electrodes,
        "fs": fs,
        "num_channels": n_ch,
        "device": "Unknown",
        "start_date": start_dt,
        "duration_s": n_samples_total / fs,
    }


def _clean_label(label: str) -> str:
    """Strip common EDF label prefixes/suffixes to get a clean 10-20 name."""
    label = label.strip()
    for prefix in ("EEG ", "eeg "):
        if label.startswith(prefix):
            label = label[len(prefix):]
    # Remove reference suffix like "-Ref", "-REF", "-A1", "-A2", "-Cz"
    for sep in ("-", "_"):
        if sep in label:
            label = label.split(sep)[0]
    return label.strip()
