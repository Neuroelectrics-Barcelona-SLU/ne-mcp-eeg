"""Deterministic artificial inputs; no participant recordings are used here."""
import numpy as np


def recording(nch=8, fs=500, epoch_s=10):
    n = int(3 * epoch_s * fs) + 17
    t = np.arange(n) / fs
    rng = np.random.default_rng(20261109)
    x = rng.normal(0, 2000, (n, nch))
    for ch in range(nch):
        x[:, ch] += 20000 * np.sin(2 * np.pi * (8 + ch / 3) * t)
    x[:, 0] += 100000000
    if nch > 1:
        x[:, 1] += 140000 * np.sin(2 * np.pi * 50 * t)
    if nch > 4:
        x[:int(epoch_s * fs), 4] = 400000047
    if nch > 5:
        x[:, 5] = 300 * np.sin(2 * np.pi * 50 * t)
    if nch > 6:
        x[int(epoch_s * fs):int(2 * epoch_s * fs), 6] = 0
    if nch > 7:
        x[:, 7] += 3000000 * np.sin(2 * np.pi * .2 * t)
    acc = np.column_stack([250 * np.sqrt(2) * np.sin(2 * np.pi * t),
                           np.zeros(n), np.full(n, 9800.)])
    acc[int(2 * epoch_s * fs):, 0] *= 10
    return np.rint(x).astype(np.int64), acc


def bench_signals():
    t = np.arange(5000) / 500
    return {0: .2 * np.sin(2 * np.pi * 10 * t),
            1: 20 * np.sin(2 * np.pi * 10 * t) + 30 * np.sin(2 * np.pi * 50 * t),
            2: np.zeros(t.size), 3: np.array([1., -1., np.nan, 2.]),
            4: 50 * np.sin(2 * np.pi * 23 * t)}


def metric_fixture(ne=2, nch=4):
    from ne_eeg_server.qc.metrics import KEYS, EKEYS
    m = {k: np.zeros((ne, nch)) for k in KEYS}
    m.update({k: np.zeros(ne) for k in EKEYS})
    m.update(ne=ne, nch=nch, fs=500., epoch_s=30.)
    m["full_rms"][:] = 10.
    return m
