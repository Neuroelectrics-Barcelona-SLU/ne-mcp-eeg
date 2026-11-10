"""Binary and tool-boundary checks using artificial inputs only.

The NEDF 1.4 layout is checked against MNE's independent reader:
https://github.com/mne-tools/mne-python/blob/main/mne/io/nedf/nedf.py
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from ne_eeg_server.qc import metrics, classify, load
from ne_eeg_server.readers.nedf import read_nedf
from ne_eeg_server.readers.loader import prepare_easy_path
from ne_eeg_server.tools import signal_quality
from ne_eeg_server.analysis.analyzer import EasyAnalyzer
from .test_compatibility import assert_same

FIXTURES = Path(__file__).parent / "fixtures"


def write_nedf(path, counts, *, fs=500, acc=False, extra=False, version="1.4", markers=None):
    """Pack explicit signed integers; no production reader helpers are used."""
    n, nch = counts.shape
    if markers is None:
        markers = np.zeros(n, dtype=int)
    montage = "".join(f"<Channel{i}>CH{i}</Channel{i}>" for i in range(1, nch + 1))
    settings = (f"<TotalNumberOfChannels>{nch}</TotalNumberOfChannels>"
                f"<EEGSamplingRate>{fs}</EEGSamplingRate>"
                f"<NumberOfRecordsOfEEG>{n}</NumberOfRecordsOfEEG>"
                f"<EEGMontage>{montage}</EEGMontage>")
    if version == "1.4":
        fields = (f"<EEGSettings>{settings}</EEGSettings><StepDetails>"
                  "<DeviceClass>ENOBIO</DeviceClass>"
                  "<StartDate_firstEEGTimestamp>1700000000000</StartDate_firstEEGTimestamp>"
                  "</StepDetails>"
                  f"<AccelerometerData>{'ON' if acc else 'OFF'}</AccelerometerData>"
                  f"<NumberOfChannelsOfAccelerometer>{3 if acc else 0}</NumberOfChannelsOfAccelerometer>"
                  + ("<STIMSettings/>" if extra else ""))
    else:
        fields = settings + "<StartDateEEG>1700000000000</StartDateEEG>"
    header = f'<?xml version="1.0"?><NEDF><NEDFversion>{version}</NEDFversion>{fields}</NEDF>'.encode()
    data = bytearray(header.ljust(10240, b"\0"))
    for sample, row in enumerate(counts):
        if acc and sample % 5 == 0:
            data.extend(bytes.fromhex("0001 ffff 1234"))
        for count in row:
            data.extend(int(count).to_bytes(3, "big", signed=True))
        if extra:
            data.extend(b"\x01\x02\x03" * (2 * nch))
        data.extend(int(markers[sample]).to_bytes(4, "big", signed=True))
    path.write_bytes(data)
    return bytes(data)


@pytest.mark.parametrize("nch,acc,extra,version", [
    (1, False, False, "1.4"), (8, True, False, "1.4"),
    (32, True, True, "1.4"), (32, False, True, "1.4"),
    (1, False, False, "1.2"),
])
def test_nedf_signed_scaling_track_alignment_and_partial_block(tmp_path, nch, acc, extra, version):
    counts = np.resize(np.array([0, 1, -1, 8388607, -8388608, 256, -256]), (11, nch))
    markers = np.resize(np.array([0, 1, -1, 2147483647, -2147483648]), 11)
    path = tmp_path / "synthetic.nedf"
    write_nedf(path, counts, acc=acc, extra=extra, version=version, markers=markers)
    data = read_nedf(str(path))
    np.testing.assert_allclose(data["eeg_uV"], counts * (2.4e6 / (6 * 8388607)), rtol=1e-7, atol=1e-7)
    np.testing.assert_array_equal(data["markers"], markers)
    assert data["electrodes"] == [f"CH{i}" for i in range(1, nch + 1)]
    assert data["duration_s"] == 11 / 500


@pytest.mark.parametrize("mutation", ["short_header", "truncated_payload", "extra_payload", "missing_rate", "zero_rate", "bad_montage", "unsupported_version"])
def test_corrupt_nedf_fails_with_a_useful_error(tmp_path, mutation):
    path = tmp_path / "bad.nedf"
    content = write_nedf(path, np.zeros((11, 1), dtype=int))
    if mutation == "short_header": content = content[:100]
    elif mutation == "truncated_payload": content = content[:-1]
    elif mutation == "extra_payload": content += b"\0"
    else:
        header = content[:10240].split(b"\0", 1)[0]
        if mutation == "missing_rate": header = header.replace(b"<EEGSamplingRate>500</EEGSamplingRate>", b"")
        elif mutation == "zero_rate": header = header.replace(b">500<", b">0<")
        elif mutation == "bad_montage": header = header.replace(b"Channel1", b"Channel2")
        elif mutation == "unsupported_version": header = header.replace(b">1.4<", b">9.9<")
        content = header.ljust(10240, b"\0") + content[10240:]
    path.write_bytes(content)
    with pytest.raises(ValueError, match="NEDF"):
        read_nedf(str(path))


@pytest.mark.parametrize("fs", [250, 1000])
def test_non500_nedf_to_core_and_signal_quality(tmp_path, fs):
    t = np.arange(10 * fs) / fs
    counts = np.rint(np.sqrt(2) * 20 * np.sin(2 * np.pi * 10 * t) / (2.4e6 / (6 * 8388607))).astype(int)
    path = tmp_path / "non500.nedf"
    write_nedf(path, counts[:, None], fs=fs)
    data = read_nedf(str(path))
    m = metrics.compute(data["eeg_uV"].astype(float) * 1000, None, data["fs"], 10, log=None)
    assert m["full_rms"][0, 0] == pytest.approx(20, abs=.15)
    assert np.isnan(m["acc_rms"]).all()
    assert not classify.classify(m)["motion_available"]
    converted, is_temp = prepare_easy_path(str(path), str(tmp_path))
    assert is_temp
    assert EasyAnalyzer(converted).fs == fs
    result = signal_quality(str(path), start_time_s=2, duration_s=4)
    assert result["sampling_rate_hz"] == fs
    assert result["per_channel"]["CH1"]["rms_filtered_uv"] == pytest.approx(20, abs=.15)


@pytest.mark.parametrize("fs", [250, 1000])
def test_one_channel_easy_without_accelerometer_and_sampling_metadata(tmp_path, fs):
    t = np.arange(10 * fs) / fs
    eeg = np.rint(20000 * np.sqrt(2) * np.sin(2 * np.pi * 10 * t)).astype(int)
    path = tmp_path / "no_acc.easy"
    np.savetxt(path, np.column_stack([eeg, np.zeros(len(t), int), np.rint(t * 1000).astype(int)]), fmt="%d", delimiter="\t")
    path.with_suffix(".info").write_text(f"EEG sampling rate: {fs}.0\nNumber of EEG channels: 1\nChannel 1: Cz\n")
    recording = load.read_easy(path)
    assert recording["acc"] is None
    m = metrics.compute(recording["eeg"], None, recording["fs"], 10, log=None)
    assert m["full_rms"][0, 0] == pytest.approx(20, abs=.15)
    result = signal_quality(str(path), duration_s=8)
    assert result["sampling_rate_hz"] == fs
    assert result["per_channel"]["Cz"]["rms_filtered_uv"] == pytest.approx(20, abs=.15)


def test_invalid_declared_sampling_rate_is_not_silently_replaced(tmp_path):
    path = tmp_path / "invalid.easy"
    path.write_text("0\t0\t0\t0\t0\t0\n")
    for rate in ("0", "nan", "bad"):
        path.with_suffix(".info").write_text(f"EEG sampling rate: {rate}\n")
        with pytest.raises(ValueError, match="sampling rate"):
            EasyAnalyzer(str(path))


@pytest.mark.parametrize("case", ["whole", "window"])
def test_full_nic_signal_quality_matches_pre_extraction_output(case):
    manifest = json.loads((FIXTURES / "signal_quality_manifest.json").read_text())
    path = Path(__file__).parents[2] / "reference_scripts/sample_data/demo_recording.easy"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sample_sha256"]
    assert hashlib.sha256(path.with_suffix(".info").read_bytes()).hexdigest() == manifest["info_sha256"]
    expected = json.loads((FIXTURES / "signal_quality_v1.json").read_text())[case]
    actual = signal_quality(str(path), **manifest["cases"][case])
    assert_same(actual, expected)
    # The tool serializes rounded quantities: compare every returned value exactly.
    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
