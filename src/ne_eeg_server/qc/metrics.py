"""Per-channel, per-epoch metrics on a long .easy recording."""
from __future__ import annotations
from dataclasses import asdict
import numpy as np
from scipy import signal, stats
from ne_eeg_server import __version__
from .config import AnalysisConfig, ReferenceConfig, DiagnosticsConfig, analysis_config
from .diagnostics import DKEYS, DIAGNOSTICS_VERSION, epoch_diagnostics

# NumPy 1.x compatibility; the operation and summation order are unchanged.
_trapezoid = np.trapezoid if hasattr(np, "trapezoid") else np.trapz

RAIL_NV = AnalysisConfig().rail_nv
METRICS_VERSION = 2
REFERENCE_RULE = asdict(ReferenceConfig())
KEYS = ["sat_frac", "flat_frac", "const_run_s", "dc_mV", "ddc_mV", "raw_rms", "full_rms", "hum_rms", "hum_db", "hf_rms", "hf_psd", "kurt", "resid_rms", "corr_common"]
EKEYS = ["corr_med", "cm_rms", "cm_hum", "acc_rms", "acc_1s_max", "n_cand"]

def reference_rule(M):
    """Validate stored analysis-stage eligibility; older files use the defaults."""
    r = dict(M.get("reference_rule", REFERENCE_RULE))
    return asdict(ReferenceConfig(**r))

def reference_candidates(M, rule=None):
    """Analysis-stage eligibility, separate from report-stage thresholds."""
    r = reference_rule(M) if rule is None else rule
    return ((M["sat_frac"] < r["sat_max"]) & (M["full_rms"] >= r["rms_min_uV"])
            & (M["flat_frac"] < r["flat_frac_max"]) & (M["const_run_s"] < r["constant_run_max_s"]))

def _filters(fs, config=None):
    cfg = analysis_config(config)
    sos_bp = signal.butter(cfg.filter_order, cfg.band_hz, btype="bandpass", fs=fs, output="sos")
    notches = [signal.tf2sos(*signal.iirnotch(hz, cfg.notch_q, fs)) for hz in cfg.notch_hz]
    return sos_bp, np.vstack(notches) if notches else None

def compute(eeg_nV, acc, fs: float, epoch_s: float = 30.0, log=print, *,
            analysis: AnalysisConfig | None = None, diagnostics: DiagnosticsConfig | None = None) -> dict:
    """Compute complete-epoch metrics in µV/mV from nV EEG and optional mm/s² acceleration."""
    cfg = analysis_config(analysis)
    cfg.validate_sampling(fs, epoch_s)
    if isinstance(diagnostics, dict):
        diagnostics = DiagnosticsConfig(**diagnostics)
    if diagnostics is not None and not isinstance(diagnostics, DiagnosticsConfig):
        raise ValueError("diagnostics must be a DiagnosticsConfig or its dictionary")
    eeg_nV = np.asarray(eeg_nV)
    if eeg_nV.ndim != 2 or eeg_nV.shape[1] == 0:
        raise ValueError("EEG must have shape (samples, channels) with at least one channel")
    n, nch = eeg_nV.shape; L = int(epoch_s * fs); ne = n // L
    if ne == 0:
        raise ValueError("recording is shorter than one complete epoch")
    if acc is not None:
        acc = np.asarray(acc)
        if acc.shape != (n, 3):
            raise ValueError("accelerometer must contain three columns aligned to the EEG samples")
    sos_bp, sos_n = _filters(fs, cfg)
    rule = cfg.to_dict()["reference"]
    trim = int(cfg.trim_s * fs)
    dc_samples = int(cfg.dc_window_s * fs)
    nperseg = int(cfg.welch_s * fs)
    frequencies = np.fft.rfftfreq(nperseg, 1 / fs)
    hb = (frequencies >= cfg.hum_hz - cfg.hum_half_width_hz) & (frequencies <= cfg.hum_hz + cfg.hum_half_width_hz)
    hf = (frequencies >= cfg.hf_hz[0]) & (frequencies <= cfg.hf_hz[1])
    if hb.sum() < 2 or hf.sum() < 2:
        raise ValueError("Welch resolution must provide at least two bins in each integrated band")
    M = {k: np.full((ne, nch), np.nan) for k in KEYS}; E = {k: np.full(ne, np.nan) for k in EKEYS}
    D = {k: np.full((ne, nch), np.nan) for k in DKEYS} if diagnostics is not None else {}
    for i in range(ne):
        sl = slice(i * L, (i + 1) * L); v = np.asarray(eeg_nV[sl], dtype=np.float64)
        if not np.isfinite(v).all():
            raise ValueError(f"nonfinite EEG value in epoch {i}")
        x = v / 1000.0; dc = x.mean(axis=0); x = x - dc
        M["dc_mV"][i] = dc / 1000.0; M["ddc_mV"][i] = (v[-dc_samples:].mean(axis=0) - v[:dc_samples].mean(axis=0)) / 1e6
        M["sat_frac"][i] = (np.abs(v) >= cfg.rail_nv).mean(axis=0)
        d0 = np.diff(v, axis=0) == 0; M["flat_frac"][i] = d0.mean(axis=0)
        for c in range(nch):
            if d0[:, c].any():
                p = np.concatenate([[False], d0[:, c], [False]]); e = np.flatnonzero(p[1:] != p[:-1]); M["const_run_s"][i, c] = (e[1::2] - e[::2]).max() / fs
            else: M["const_run_s"][i, c] = 0.0
        M["raw_rms"][i] = np.sqrt((x ** 2).mean(axis=0))
        y = signal.sosfiltfilt(sos_bp, x, axis=0)
        if sos_n is not None: y = signal.sosfiltfilt(sos_n, y, axis=0)
        if trim: y = y[trim:-trim]
        M["full_rms"][i] = y.std(axis=0); M["kurt"][i] = stats.kurtosis(y, axis=0, fisher=False)
        f, P = signal.welch(x, fs=fs, nperseg=nperseg, axis=0)
        M["hum_rms"][i] = np.sqrt(_trapezoid(P[hb], f[hb], axis=0)); M["hum_db"][i] = 10 * np.log10(np.maximum(P[hb].max(axis=0), 1e-20))
        M["hf_rms"][i] = np.sqrt(_trapezoid(P[hf], f[hf], axis=0)); M["hf_psd"][i] = np.median(P[hf], axis=0)
        if diagnostics is not None:
            for key, values in epoch_diagnostics(f, P, y, fs, diagnostics).items(): D[key][i] = values
        cand = np.flatnonzero(reference_candidates({k: M[k][i] for k in ("sat_frac", "full_rms", "flat_frac", "const_run_s")}, rule)); E["n_cand"][i] = len(cand)
        if len(cand) >= rule["minimum_channels"]:
            ref = np.median(y[:, cand], axis=1); E["cm_rms"][i] = ref.std()
            C = np.corrcoef(y[:, cand].T); E["corr_med"][i] = np.median(C[np.triu_indices(len(cand), 1)])
            M["resid_rms"][i] = (y - ref[:, None]).std(axis=0)
            sd = y.std(axis=0); ref_sd = ref.std()
            M["corr_common"][i] = [np.corrcoef(y[:, c], ref)[0, 1] if sd[c] > 0 and ref_sd > 0 else np.nan for c in range(nch)]
            xm = np.median(x[:, cand], axis=1); fm, Pm = signal.welch(xm, fs=fs, nperseg=nperseg); E["cm_hum"][i] = np.sqrt(_trapezoid(Pm[hb], fm[hb]))
        if acc is not None:
            a = np.array(acc[sl], dtype=np.float64, copy=True)
            if not np.isfinite(a).all():
                raise ValueError(f"nonfinite accelerometer value in epoch {i}")
            a -= a.mean(axis=0); m = np.sqrt((a ** 2).sum(axis=1))
            E["acc_rms"][i] = np.sqrt((m ** 2).mean()); E["acc_1s_max"][i] = np.sqrt((m[:(len(m) // int(fs)) * int(fs)].reshape(-1, int(fs)) ** 2).mean(axis=1)).max()
        if log and i % 200 == 0: log(f"  epoch {i}/{ne}")
    extra = {"diagnostics_version": DIAGNOSTICS_VERSION, "diagnostics_config": diagnostics.to_dict()} if diagnostics is not None else {}
    return {"metrics_version": METRICS_VERSION, "epoch_s": epoch_s, "ne": ne, "nch": nch, "fs": fs,
            "qc_version": __version__, "analysis_config": cfg.to_dict(), **extra,
            "reference_rule": rule, "reference_candidate": reference_candidates(M, rule),
            "total_samples": n, "analyzed_samples": ne * L, "excluded_tail_samples": n - ne * L, **M, **E, **D}
