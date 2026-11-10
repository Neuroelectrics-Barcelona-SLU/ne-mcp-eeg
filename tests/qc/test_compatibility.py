"""Compare the shared core with outputs captured before the extraction."""
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import pytest
import scipy

from ne_eeg_server.qc import metrics, classify
from ne_eeg_server.qc.bench import calculate_channel_metrics_from_signals
from .synthetic import recording, bench_signals

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
EXACT_ENVIRONMENT = (
    MANIFEST["python"] == platform.python_version()
    and MANIFEST["numpy"] == np.__version__
    and MANIFEST["scipy"] == scipy.__version__
    and MANIFEST["platform"] == sys.platform
    and MANIFEST["machine"] == platform.machine()
)


def assert_same(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_same(actual[key], expected[key])
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            assert_same(a, e)
    elif isinstance(expected, (float, int, np.ndarray)):
        np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10, equal_nan=True)
    else:
        assert actual == expected


@pytest.mark.parametrize("nch", [1, 8, 32])
def test_ambulatory_reference(nch):
    x, acc = recording(nch)
    m = metrics.compute(x, acc if nch == 8 else None, 500, 10, log=None)
    r = classify.classify(m)
    b = classify.blocks(r["c"], r, m, 20)
    reference = dict(np.load(FIXTURES / "ambulatory_v2.npz", allow_pickle=False))
    reference.update(json.loads((FIXTURES / "ambulatory_v2.json").read_text()))
    prefix = f"ch{nch}__"
    for name, result in (("m", m), ("r", r), ("b", b)):
        for key, expected in reference.items():
            if key.startswith(prefix + name + "__"):
                actual = result[key.split("__")[-1]]
                if EXACT_ENVIRONMENT and isinstance(expected, np.ndarray):
                    np.testing.assert_array_equal(actual, expected)
                # A constant nV input can leave a sub-roundoff band signal after
                # demeaning/filtering. Its normalized moments are undefined;
                # their finite numerical residue depends on the platform.
                # Keep the frozen algorithm, and compare every meaningful value.
                if name == "m" and key.split("__")[-1] in ("kurt", "corr_common"):
                    constant = reference[prefix + "m__flat_frac"] == 1
                    assert (m["full_rms"][constant] < 1e-9).all()
                    actual, expected = actual[~constant], expected[~constant]
                assert_same(actual, expected)
                if isinstance(expected, np.ndarray) and expected.dtype.kind in "biu":
                    np.testing.assert_array_equal(actual, expected)
    assert_same(classify.segments(r["c"]), reference[prefix + "segments"])


def test_bench_reference_and_adapter():
    from ne_eeg_server.analysis.qc import calculate_channel_metrics_from_signals as legacy
    assert legacy is calculate_channel_metrics_from_signals
    actual = legacy(bench_signals(), raw_means_uv={i: 10 * i for i in range(5)})
    expected = json.loads((FIXTURES / "bench_v1.json").read_text())
    assert_same({str(k): v for k, v in actual.items()}, expected)


def test_core_imports_without_mcp_or_plotting():
    script = '''
import sys
from ne_eeg_server.qc import metrics, classify, load, bench, peaks, labels
assert not any(k == 'mcp' or k.startswith('mcp.') for k in sys.modules)
assert 'matplotlib' not in sys.modules
assert 'reportlab' not in sys.modules
'''
    subprocess.run([sys.executable, "-c", script], check=True)
