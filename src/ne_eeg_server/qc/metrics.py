"""Per-channel, per-epoch metrics on a long .easy recording."""
from __future__ import annotations
import numpy as np
from scipy import signal, stats

RAIL_NV = 399_000_000
METRICS_VERSION = 2
REFERENCE_RULE = {"sat_max": 0.01, "flat_frac_max": 0.5, "constant_run_max_s": 1.0, "rms_min_uV": 2.0, "minimum_channels": 4}
KEYS = ["sat_frac", "flat_frac", "const_run_s", "dc_mV", "ddc_mV", "raw_rms", "full_rms", "hum_rms", "hum_db", "hf_rms", "hf_psd", "kurt", "resid_rms", "corr_common"]
EKEYS = ["corr_med", "cm_rms", "cm_hum", "acc_rms", "acc_1s_max", "n_cand"]

def reference_candidates(M):
    """Fixed analysis-stage eligibility, separate from report-stage thresholds."""
    r = REFERENCE_RULE
    return ((M["sat_frac"] < r["sat_max"]) & (M["full_rms"] >= r["rms_min_uV"])
            & (M["flat_frac"] < r["flat_frac_max"]) & (M["const_run_s"] < r["constant_run_max_s"]))

def _filters(fs):
    sos_bp = signal.butter(4, [1, 40], btype="bandpass", fs=fs, output="sos")
    b50, a50 = signal.iirnotch(50.0, 30.0, fs); b60, a60 = signal.iirnotch(60.0, 30.0, fs)
    return sos_bp, np.vstack([signal.tf2sos(b50, a50), signal.tf2sos(b60, a60)])

def compute(eeg_nV, acc, fs: float, epoch_s: float = 30.0, log=print) -> dict:
    if not np.isfinite(fs) or fs <= 120 or fs != int(fs):
        raise ValueError("fs must be an integer above 120 Hz for the 50/60 Hz filters")
    if not np.isfinite(epoch_s) or epoch_s < 10 or not np.isclose(epoch_s * fs, round(epoch_s * fs), rtol=0, atol=1e-8):
        raise ValueError("epoch_s must be at least 10 s and contain an integer number of samples")
    if eeg_nV.ndim != 2 or eeg_nV.shape[1] == 0:
        raise ValueError("EEG must have shape (samples, channels) with at least one channel")
    n, nch = eeg_nV.shape; L = int(epoch_s * fs); ne = n // L
    if ne == 0:
        raise ValueError("recording is shorter than one complete epoch")
    if acc is not None and acc.shape != (n, 3):
        raise ValueError("accelerometer must contain three columns aligned to the EEG samples")
    sos_bp, sos_n = _filters(fs)
    M = {k: np.full((ne, nch), np.nan) for k in KEYS}; E = {k: np.full(ne, np.nan) for k in EKEYS}
    for i in range(ne):
        sl = slice(i * L, (i + 1) * L); v = np.asarray(eeg_nV[sl], dtype=np.float64)
        if not np.isfinite(v).all():
            raise ValueError(f"nonfinite EEG value in epoch {i}")
        x = v / 1000.0; dc = x.mean(axis=0); x = x - dc
        M["dc_mV"][i] = dc / 1000.0; M["ddc_mV"][i] = (v[-int(5 * fs):].mean(axis=0) - v[:int(5 * fs)].mean(axis=0)) / 1e6
        M["sat_frac"][i] = (np.abs(v) >= RAIL_NV).mean(axis=0)
        d0 = np.diff(v, axis=0) == 0; M["flat_frac"][i] = d0.mean(axis=0)
        for c in range(nch):
            if d0[:, c].any():
                p = np.concatenate([[False], d0[:, c], [False]]); e = np.flatnonzero(p[1:] != p[:-1]); M["const_run_s"][i, c] = (e[1::2] - e[::2]).max() / fs
            else: M["const_run_s"][i, c] = 0.0
        M["raw_rms"][i] = np.sqrt((x ** 2).mean(axis=0))
        y = signal.sosfiltfilt(sos_bp, x, axis=0); y = signal.sosfiltfilt(sos_n, y, axis=0)[int(0.5 * fs):-int(0.5 * fs)]
        M["full_rms"][i] = y.std(axis=0); M["kurt"][i] = stats.kurtosis(y, axis=0, fisher=False)
        f, P = signal.welch(x, fs=fs, nperseg=int(2 * fs), axis=0); hb = (f >= 49) & (f <= 51); hf = (f >= 30) & (f <= 45)
        M["hum_rms"][i] = np.sqrt(np.trapezoid(P[hb], f[hb], axis=0)); M["hum_db"][i] = 10 * np.log10(np.maximum(P[hb].max(axis=0), 1e-20))
        M["hf_rms"][i] = np.sqrt(np.trapezoid(P[hf], f[hf], axis=0)); M["hf_psd"][i] = np.median(P[hf], axis=0)
        cand = np.flatnonzero(reference_candidates({k: M[k][i] for k in ("sat_frac", "full_rms", "flat_frac", "const_run_s")})); E["n_cand"][i] = len(cand)
        if len(cand) >= REFERENCE_RULE["minimum_channels"]:
            ref = np.median(y[:, cand], axis=1); E["cm_rms"][i] = ref.std()
            C = np.corrcoef(y[:, cand].T); E["corr_med"][i] = np.median(C[np.triu_indices(len(cand), 1)])
            M["resid_rms"][i] = (y - ref[:, None]).std(axis=0)
            sd = y.std(axis=0); ref_sd = ref.std()
            M["corr_common"][i] = [np.corrcoef(y[:, c], ref)[0, 1] if sd[c] > 0 and ref_sd > 0 else np.nan for c in range(nch)]
            xm = np.median(x[:, cand], axis=1); fm, Pm = signal.welch(xm, fs=fs, nperseg=int(2 * fs)); E["cm_hum"][i] = np.sqrt(np.trapezoid(Pm[hb], fm[hb]))
        if acc is not None:
            a = np.array(acc[sl], dtype=np.float64, copy=True)
            if not np.isfinite(a).all():
                raise ValueError(f"nonfinite accelerometer value in epoch {i}")
            a -= a.mean(axis=0); m = np.sqrt((a ** 2).sum(axis=1))
            E["acc_rms"][i] = np.sqrt((m ** 2).mean()); E["acc_1s_max"][i] = np.sqrt((m[:(len(m) // int(fs)) * int(fs)].reshape(-1, int(fs)) ** 2).mean(axis=1)).max()
        if log and i % 200 == 0: log(f"  epoch {i}/{ne}")
    return {"metrics_version": METRICS_VERSION, "epoch_s": epoch_s, "ne": ne, "nch": nch, "fs": fs,
            "reference_rule": dict(REFERENCE_RULE), "reference_candidate": reference_candidates(M),
            "total_samples": n, "analyzed_samples": ne * L, "excluded_tail_samples": n - ne * L, **M, **E}
