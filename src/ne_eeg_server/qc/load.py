"""Validated .easy/.info loading with a source-specific .npy cache."""
from __future__ import annotations
import hashlib
import os
import re
import numpy as np
import pandas as pd


def channel_names(info: dict, nch: int) -> list[str]:
    labels = info.get("electrodes") or []
    return [str(labels[i]) if i < len(labels) and labels[i] else f"CH{i+1}" for i in range(nch)]


def parse_info(info_path: str) -> dict:
    info = {"electrodes": [], "acc": None, "device": "", "start_ms": None,
            "n_records": None, "packets_lost": None, "metadata_warnings": [], "filters": {}}
    labels = {}
    with open(info_path, errors="replace") as f:
        for line in f:
            s = line.strip()
            match = re.match(r"Channel (\d+):\s*(.*)", s)
            if match:
                idx = int(match[1])
                if idx < 1 or idx in labels:
                    raise ValueError("duplicate or invalid channel number in .info")
                labels[idx] = match[2] or f"CH{idx}"
                continue
            if ":" not in s:
                continue
            key, value = (x.strip() for x in s.split(":", 1))
            if key == "EEG sampling rate": info["fs"] = float(value.split()[0])
            elif key == "Device class": info["device"] = value
            elif key.startswith("StartDate"): info["start_ms"] = int(value) if value else None
            elif key == "Number of records of EEG": info["n_records"] = int(value) if value else None
            elif key == "Number of packets lost": info["packets_lost"] = int(value) if value else None
            elif key == "Accelerometer data":
                if value not in ("ON", "OFF"): raise ValueError("Accelerometer data must be ON or OFF")
                info["acc"] = value == "ON"
            elif key == "Number of EEG channels": info["n_eeg"] = int(value)
            elif key == "EEG units": info["eeg_units"] = value
            elif key == "Accelerometer units": info["acc_units"] = value
            elif key.endswith("filter status"): info["filters"][key] = value
    if "fs" not in info or not np.isfinite(info["fs"]) or info["fs"] <= 0:
        raise ValueError(".info must specify a positive EEG sampling rate")
    if "n_eeg" not in info:
        if not labels or set(labels) != set(range(1, max(labels)+1)):
            raise ValueError(".info needs the EEG channel count or a complete numbered montage")
        info["n_eeg"] = len(labels)
        info["metadata_warnings"].append("EEG channel count inferred from complete numbered montage")
    if info["n_eeg"] < 1 or (labels and max(labels) > info["n_eeg"]):
        raise ValueError(".info channel count and montage disagree")
    info["electrodes"] = [labels.get(i, f"CH{i}") for i in range(1, info["n_eeg"]+1)]
    if info.get("eeg_units", "nV") != "nV":
        raise ValueError("only EEG in nV is supported")
    if "eeg_units" not in info:
        info["metadata_warnings"].append("EEG units absent; standard .easy nV units assumed")
    if info.get("acc_units", "mm/s^2") not in ("mm/s^2", "mm/s²"):
        raise ValueError("only accelerometer data in mm/s^2 is supported")
    return info


def info_path_for(easy_path: str) -> str:
    return os.path.splitext(easy_path)[0] + ".info"


def cache_path_for(easy_path: str, cache_dir: str) -> str:
    st = os.stat(easy_path)
    identity = f"{os.path.realpath(easy_path)}|{st.st_size}|{st.st_mtime_ns}"
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return os.path.join(cache_dir, f"{os.path.basename(easy_path)}.{key}.npy")


def load_easy(easy_path: str, cache_dir: str | None = None) -> np.ndarray:
    """Return samples × columns as int64; cache by full source path, size and ns mtime."""
    cache = cache_path_for(easy_path, cache_dir) if cache_dir else None
    if cache and os.path.exists(cache):
        return np.load(cache, mmap_mode="r", allow_pickle=False)
    arr = pd.read_csv(easy_path, sep="\t", header=None, engine="c", dtype=np.int64).to_numpy()
    if cache:
        os.makedirs(cache_dir, exist_ok=True)
        np.save(cache, arr)
        return np.load(cache, mmap_mode="r", allow_pickle=False)
    return arr


def split_columns(arr: np.ndarray, info: dict) -> dict:
    n_eeg = info["n_eeg"]
    if arr.ndim != 2 or arr.shape[0] == 0 or n_eeg < 1:
        raise ValueError(".easy must be a nonempty samples-by-columns array")
    extra = arr.shape[1] - n_eeg
    if extra not in (2, 5):
        raise ValueError("expected EEG + optional 3-axis accelerometer + trigger + timestamp columns")
    has_acc = extra == 5
    if info.get("acc") is not None and info["acc"] != has_acc:
        raise ValueError("accelerometer declaration disagrees with .easy column count")
    if info.get("acc") is None:
        info["acc"] = has_acc
        info.setdefault("metadata_warnings", []).append("accelerometer presence inferred from column count")
    if has_acc and "acc_units" not in info:
        warning = "accelerometer units absent; standard .easy mm/s^2 units assumed"
        if warning not in info.setdefault("metadata_warnings", []): info["metadata_warnings"].append(warning)
    return {"eeg": arr[:, :n_eeg], "acc": arr[:, n_eeg:n_eeg+3] if has_acc else None,
            "trig": arr[:, -2], "ts": arr[:, -1], "n_eeg": n_eeg}


def read_easy(path: str, cache_dir: str | None = None) -> dict:
    """Read EEG (nV), acceleration (mm/s²), trigger and timestamps (ms)."""
    info = parse_info(info_path_for(path))
    data = split_columns(load_easy(path, cache_dir), info)
    return {**data, "fs": info["fs"], "info": info}
