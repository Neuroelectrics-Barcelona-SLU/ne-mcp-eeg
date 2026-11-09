"""Failure-mode classes for channel-epochs, segments and blocks."""
from __future__ import annotations
import numpy as np
from .metrics import reference_candidates, REFERENCE_RULE
from .presets import THR, resolve_thresholds
from .labels import CLS, CODE, COL, GROUPS, SEQ_GREENS, LABEL, DISCLAIMER, DEFN, definitions

def classify(M: dict, thr: dict = THR) -> dict:
    thr = resolve_thresholds(thr)
    ne, nch = M["ne"], M["nch"]
    if ne < 1 or nch < 1:
        raise ValueError("classification requires at least one complete channel-epoch")
    for key in ("sat_frac", "flat_frac", "const_run_s", "raw_rms", "full_rms", "hum_rms", "hf_rms", "ddc_mV"):
        if np.shape(M[key]) != (ne, nch) or not np.isfinite(M[key]).all():
            raise ValueError(f"missing, nonfinite or misaligned primary metric: {key}")
    sat, flat, run, raw, full = M["sat_frac"], M["flat_frac"], M["const_run_s"], M["raw_rms"], M["full_rms"]
    hum, hf, resid, cc, ddc = M["hum_rms"], M["hf_rms"], M["resid_rms"], M["corr_common"], M["ddc_mV"]
    acc_base = np.nanpercentile(M["acc_1s_max"], 10) if np.isfinite(M["acc_1s_max"]).any() else np.nan
    motion_available = bool(np.isfinite(acc_base) and acc_base > 0)
    motion_ep = (M["acc_1s_max"] > thr["motion_acc_rel"] * acc_base) if motion_available else np.zeros(ne, bool)
    peers = reference_candidates(M)
    relative_available = peers.sum(axis=1) >= REFERENCE_RULE["minimum_channels"]
    cm_ep = relative_available & (M["corr_med"] >= thr["cm_corr"]) & (M["cm_rms"] >= thr["cm_rms"])
    med_resid = np.full((ne, 1), np.nan); med_hum = np.full((ne, 1), np.nan)
    for i in np.flatnonzero(relative_available):
        rr = resid[i, peers[i]]
        if np.isfinite(rr).all(): med_resid[i, 0] = np.median(rr)
        med_hum[i, 0] = np.median(hum[i, peers[i]])
    c = np.full((ne, nch), CODE["clean"], int)
    c[hum > thr["hum_elev"]] = CODE["hum_elevated"]; c[hum > thr["hum_severe"]] = CODE["hum_severe"]; c[hf > thr["hf_rms"]] = CODE["hf_noise"]
    c[motion_ep[:, None] & (full > thr["motion_rms"])] = CODE["motion"]
    bad = (np.nan_to_num(resid, nan=0) > np.nan_to_num(np.maximum(thr["bad_resid_abs"], thr["bad_resid_rel"] * med_resid), nan=np.inf)) | (full > thr["bad_rms"]) | ((hum > thr["bad_hum_rel"] * med_hum) & (hum > thr["bad_hum_abs"]))
    c[bad] = CODE["bad_channel"]
    c[cm_ep[:, None] & (np.nan_to_num(cc, nan=0) >= thr["cm_corr"])] = CODE["common_mode"]
    raw_nohum = np.sqrt(np.maximum(raw ** 2 - np.nan_to_num(hum, nan=0.0) ** 2, 0.0))
    c[(raw_nohum >= thr["drift_raw"]) | (np.abs(ddc) >= thr["drift_ddc"])] = CODE["drift"]
    c[full < thr["open_rms"]] = CODE["open_input"]
    c[(run >= thr["flat_run_s"]) | (flat >= thr["flat_frac"])] = CODE["flatline"]
    c[sat >= thr["sat"]] = CODE["saturated"]
    return {"c": c, "screen_pass": c <= CODE["hum_elevated"], "unflagged": c == CODE["clean"], "motion_ep": motion_ep, "cm_ep": cm_ep, "acc_base": acc_base,
            "motion_available": motion_available, "relative_available": relative_available}

def segments(c: np.ndarray) -> list[tuple[int, int, str]]:
    """Exact runs of the channel-count rule; no relabeling of short runs."""
    ne, nch = c.shape
    nsat = (c == CODE["saturated"]).sum(axis=1); nopen = (c == CODE["open_input"]).sum(axis=1); ndrift = (c == CODE["drift"]).sum(axis=1)
    state = np.where((nsat + ndrift) >= (nch + 1) // 2, 1, np.where((nopen >= 0.7 * nch) & (nsat == 0), 2, 0))
    runs, i = [], 0
    while i < ne:
        j = i
        while j + 1 < ne and state[j + 1] == state[i]: j += 1
        runs.append([i, j + 1, int(state[i])]); i = j + 1
    names = {0: "SIGNAL", 1: "DRIFT/SAT", 2: "OPEN"}
    return [(a, b, names[s]) for a, b, s in runs]

def blocks(c: np.ndarray, R: dict, M: dict, block_s: float = 600.0) -> dict:
    """Aggregate channel-epochs into fixed blocks: class fractions, dominant class per channel, screen-pass statistics."""
    if not np.isfinite(block_s) or block_s < M["epoch_s"] or not np.isclose(block_s / M["epoch_s"], round(block_s / M["epoch_s"]), rtol=0, atol=1e-9):
        raise ValueError("block_s must be a positive integer multiple of epoch_s")
    ne, nch = c.shape; per = int(round(block_s / M["epoch_s"])); nb = int(np.ceil(ne / per))
    frac = np.zeros((nb, len(CLS))); dom = np.zeros((nb, nch), int); screen_pass_pct = np.zeros(nb); n_screen_pass_med = np.zeros(nb)
    hum_med = np.full(nb, np.nan); motion_n = np.zeros(nb, int); cm_n = np.zeros(nb, int)
    for b in range(nb):
        sl = slice(b * per, min(ne, (b + 1) * per)); cb = c[sl]
        frac[b] = np.bincount(cb.ravel(), minlength=len(CLS)) / cb.size
        dom[b] = [np.bincount(cb[:, ch], minlength=len(CLS)).argmax() for ch in range(nch)]
        screen_pass_pct[b] = 100 * R["screen_pass"][sl].mean(); n_screen_pass_med[b] = np.median(R["screen_pass"][sl].sum(axis=1))
        hum_med[b] = np.nanmedian(M["hum_rms"][sl]); motion_n[b] = int(R["motion_ep"][sl].sum()); cm_n[b] = int(R["cm_ep"][sl].sum())
    return {"block_s": block_s, "per": per, "nb": nb, "start_s": np.arange(nb) * per * M["epoch_s"],
            "end_s": np.minimum((np.arange(nb) + 1) * per, ne) * M["epoch_s"],
            "frac": frac, "dom": dom, "screen_pass_pct": screen_pass_pct, "n_screen_pass_med": n_screen_pass_med, "hum_med": hum_med, "motion_n": motion_n, "cm_n": cm_n}


def channel_verdicts(c: np.ndarray, segs=None) -> tuple[list[int], list[int]]:
    """Channels in a given class for more than half of all analyzed epochs."""
    railed = [ch for ch in range(c.shape[1]) if (c[:, ch] == CODE["saturated"]).mean() > 0.5]
    outliers = [ch for ch in range(c.shape[1]) if (c[:, ch] == CODE["bad_channel"]).mean() > 0.5]
    return railed, outliers
