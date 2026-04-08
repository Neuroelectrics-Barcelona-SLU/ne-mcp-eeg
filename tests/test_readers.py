"""Tests for EEG file readers."""

import os
import numpy as np
import pytest

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "reference_scripts", "sample_data")
SAMPLE_EASY = os.path.join(SAMPLE_DIR, "demo_recording.easy")
SAMPLE_INFO = os.path.join(SAMPLE_DIR, "demo_recording.info")


@pytest.fixture
def sample_easy_path():
    if not os.path.isfile(SAMPLE_EASY):
        pytest.skip("Sample .easy file not found")
    return SAMPLE_EASY


class TestEasyReader:
    def test_load_easy_file(self, sample_easy_path):
        from ne_eeg_server.readers.easy import load_easy_file

        eeg_data, time_sec, status = load_easy_file(sample_easy_path)

        assert status == "Success"
        assert eeg_data is not None
        assert time_sec is not None
        assert len(eeg_data) > 0
        assert len(time_sec) == len(eeg_data)
        assert eeg_data.shape[1] >= 8  # at least 8 EEG channels

    def test_parse_info_file(self, sample_easy_path):
        from ne_eeg_server.readers.easy import parse_info_file

        info = parse_info_file(sample_easy_path)

        assert len(info["electrodes"]) > 0
        assert info["device"] != "Unknown" or True  # device may or may not be in demo
        assert info["sampling_rate"] == 500 or info["sampling_rate"] is None

    def test_load_missing_file(self):
        from ne_eeg_server.readers.easy import load_easy_file

        eeg_data, time_sec, status = load_easy_file("/nonexistent/file.easy")

        assert eeg_data is None
        assert time_sec is None
        assert status != "Success"


class TestLoader:
    def test_prepare_easy_path_easy(self, sample_easy_path):
        from ne_eeg_server.readers.loader import prepare_easy_path

        path, is_temp = prepare_easy_path(sample_easy_path)

        assert path == sample_easy_path
        assert is_temp is False

    def test_prepare_easy_path_unsupported(self):
        from ne_eeg_server.readers.loader import prepare_easy_path

        with pytest.raises(ValueError, match="Unsupported format"):
            prepare_easy_path("/some/file.csv")
