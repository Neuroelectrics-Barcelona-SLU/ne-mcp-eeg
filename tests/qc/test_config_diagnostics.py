import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from ne_eeg_server.qc import metrics, classify, labels, load
from ne_eeg_server.qc.config import AnalysisConfig, ReferenceConfig, EventConfig, DiagnosticsConfig
from ne_eeg_server.qc.diagnostics import amplitude_events
from ne_eeg_server.qc.peaks import find_suspicious_psd_peak
from .synthetic import recording, metric_fixture


def test_additive_diagnostics_preserve_every_existing_metric_and_class():
    x, a = recording()
    plain = metrics.compute(x, a, 500, 10, log=None)
    extra = metrics.compute(x, a, 500, 10, log=None, diagnostics=DiagnosticsConfig())
    for key in metrics.KEYS + metrics.EKEYS + ["reference_candidate"]:
        np.testing.assert_array_equal(extra[key], plain[key])
    np.testing.assert_array_equal(classify.classify(extra)["c"], classify.classify(plain)["c"])
    assert all(key not in plain for key in metrics.DKEYS)
    assert all(extra[key].shape == (3, 8) for key in metrics.DKEYS)
    assert (extra["human_events_duration_s"] == 9).all()
    np.testing.assert_array_equal(extra["human_events_per_min"], extra["human_events_count"] * 60 / 9)
    assert extra["diagnostics_config"]["events"]["threshold_uv"] == 100
    assert extra["diagnostics_version"] == 1


def test_known_amplitude_episodes_and_gap_boundary():
    x = np.zeros(1000)
    x[10:20] = 101  # gap of exactly 100 ms joins the next run
    x[120:130] = -101
    x[231:251] = 101  # gap of 101 ms starts a new event
    x[800:819] = 101  # rejected: only 19 above-threshold samples
    x[900:940] = 100  # equality does not cross the threshold
    cfg = EventConfig(threshold_uv=100, min_duration_s=.02, merge_gap_s=.1)
    assert amplitude_events(x, 1000, cfg) == (2, 120., 1.)
    assert amplitude_events(x, 1000, EventConfig(200)) == (0, 0., 1.)
    assert amplitude_events(np.ones(1000) * 101, 1000, cfg) == (1, 60., 1.)
    assert amplitude_events(np.zeros(1000), 1000, cfg) == (0, 0., 1.)


def test_known_off_mains_peak_and_mains_exclusion():
    f = np.arange(0, 250.5, .5)
    p = np.ones(f.size)
    p[f == 23] = 100
    p[f == 50] = 10000
    result = find_suspicious_psd_peak(f, p)
    assert result.freq_hz == 23
    assert result.snr_db == 20
    assert result.count == 1
    assert find_suspicious_psd_peak(f, p, snr_threshold_db=21) is None


def test_diagnostics_on_known_signal():
    fs = 500
    t = np.arange(5000) / fs
    x = 300000 * np.sin(2 * np.pi * 23 * t)
    x += 100000 * np.sin(2 * np.pi * 50 * t)
    m = metrics.compute(x[:, None], None, fs, 10, log=None,
                        diagnostics=DiagnosticsConfig())
    assert m["psd_peak_freq_hz"][0, 0] == 23
    assert m["psd_peak_count"][0, 0] >= 1
    # The 23-Hz crossings merge into one sustained amplitude episode.
    assert m["human_events_count"][0, 0] == 1
    high = metrics.compute(x[:, None], None, fs, 10, log=None,
                           diagnostics=DiagnosticsConfig(events=EventConfig(1000)))
    assert high["human_events_count"][0, 0] == 0


def test_sixty_hz_hum_rail_and_configuration_round_trip():
    fs = 500
    t = np.arange(5000) / fs
    x = 50000000 + 1000 * np.sqrt(2) * (20 * np.sin(2 * np.pi * 10 * t) + 100 * np.sin(2 * np.pi * 60 * t))
    cfg = AnalysisConfig(rail_nv=10_000_000, hum_hz=60, trim_s=0, dc_window_s=2)
    serialized = json.loads(json.dumps(cfg.to_dict()))
    assert AnalysisConfig(**serialized) == cfg
    m = metrics.compute(x[:, None], None, fs, 10, log=None, analysis=serialized)
    assert m["hum_rms"][0, 0] == pytest.approx(100, abs=1e-5)
    assert m["sat_frac"][0, 0] == 1
    assert np.isfinite(m["full_rms"]).all()
    definitions = labels.definitions({"hum_elev": 15}, m["analysis_config"])
    assert "59-61 Hz" in definitions["hum_elevated"][0]
    assert "10 mV" in definitions["saturated"][0]
    assert "2-s DC" in definitions["drift"][0]
    assert "15" in definitions["clean"][1]
    with pytest.raises(FrozenInstanceError):
        cfg.rail_nv = 0


def test_stored_reference_rule_controls_analysis_and_classification():
    x, _ = recording(3)
    cfg = AnalysisConfig(reference=ReferenceConfig(minimum_channels=2, rms_min_uV=5))
    m = metrics.compute(x, None, 500, 10, log=None, analysis=cfg)
    assert np.isfinite(m["corr_med"]).all()
    assert classify.classify(m)["relative_available"].all()
    m["reference_rule"] = {**m["reference_rule"], "rms_min_uV": 1e6}
    assert not metrics.reference_candidates(m).any()
    assert not classify.classify(m)["relative_available"].any()


def test_numpy_settings_remain_json_serializable():
    cfg = AnalysisConfig(rail_nv=np.int64(399000000),
                         reference=ReferenceConfig(minimum_channels=np.int64(4)))
    assert AnalysisConfig(**json.loads(json.dumps(cfg.to_dict()))) == cfg
    diagnostics = DiagnosticsConfig(events=EventConfig(threshold_uv=np.int64(100)))
    assert DiagnosticsConfig(**json.loads(json.dumps(diagnostics.to_dict()))) == diagnostics


@pytest.mark.parametrize("kwargs", [
    {"rail_nv": 0}, {"notch_q": np.nan}, {"band_hz": (40, 1)},
    {"filter_order": True}, {"notch_hz": (50, 50)}, {"hum_hz": 1},
    {"reference": {"minimum_channels": 1}}, {"reference": {"sat_max": 2}},
])
def test_invalid_analysis_configuration(kwargs):
    with pytest.raises(ValueError):
        AnalysisConfig(**kwargs)


@pytest.mark.parametrize("cfg, fs", [
    (AnalysisConfig(), 120), (AnalysisConfig(), 500.5),
    (AnalysisConfig(trim_s=5), 500), (AnalysisConfig(welch_s=11), 500),
    (AnalysisConfig(dc_window_s=6), 500), (AnalysisConfig(hum_half_width_hz=.01), 500),
])
def test_incompatible_sampling_is_rejected(cfg, fs):
    with pytest.raises(ValueError):
        metrics.compute(np.zeros((5000, 1)), None, fs, 10, log=None, analysis=cfg)


@pytest.mark.parametrize("kwargs", [{"threshold_uv": 0}, {"threshold_uv": True},
                                    {"min_duration_s": -1}, {"merge_gap_s": np.inf}])
def test_invalid_event_configuration(kwargs):
    with pytest.raises(ValueError):
        EventConfig(**kwargs)


def test_threshold_validation_and_definitions():
    for overrides in ({"typo": 1}, {"sat": 2}, {"sat": -1}, {"sat": True},
                      {"cm_rms": np.nan}, {"open_rms": "2"}, {"hum_elev": 100}, []):
        with pytest.raises(ValueError):
            classify.resolve_thresholds(overrides)
    m = metric_fixture()
    m["hum_rms"][:] = 12
    assert classify.classify(m, {"hum_elev": 15})["unflagged"].all()
    assert labels.DEFN == classify.DEFN
    assert "common-mode dominated (CMS/DRL)" == labels.LABEL["common_mode"]
    assert "not a verified diagnosis" in labels.DISCLAIMER


@pytest.mark.parametrize("nch, has_acc", [(1, False), (32, True)])
def test_loader_to_metrics_round_trip(tmp_path, nch, has_acc):
    x, acc = recording(nch)
    other = [np.rint(acc).astype(np.int64)] if has_acc else []
    columns = np.column_stack([x, *other, np.zeros(len(x), dtype=np.int64), np.arange(len(x)) * 2])
    easy = tmp_path / "synthetic.easy"
    np.savetxt(easy, columns, fmt="%d", delimiter="\t")
    easy.with_suffix(".info").write_text(
        f"EEG sampling rate: 500\nNumber of EEG channels: {nch}\n"
        f"Accelerometer data: {'ON' if has_acc else 'OFF'}\n"
        "EEG units: nV\nAccelerometer units: mm/s^2\n")
    record = load.read_easy(easy, tmp_path / "cache")
    np.testing.assert_array_equal(record["eeg"], x)
    assert (record["acc"] is not None) == has_acc
    m = metrics.compute(record["eeg"], record["acc"], record["fs"], 10, log=None)
    assert m["excluded_tail_samples"] == 17
    assert m["full_rms"].shape == (3, nch)
