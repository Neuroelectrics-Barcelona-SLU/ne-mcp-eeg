"""Tests for MCP tool implementations."""

import os
import pytest

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "reference_scripts", "sample_data")
SAMPLE_EASY = os.path.join(SAMPLE_DIR, "demo_recording.easy")


@pytest.fixture
def sample_easy_path():
    if not os.path.isfile(SAMPLE_EASY):
        pytest.skip("Sample .easy file not found")
    return SAMPLE_EASY


class TestFileInfo:
    def test_file_info(self, sample_easy_path):
        from ne_eeg_server.tools import file_info

        result = file_info(sample_easy_path)

        assert result["format"] == "easy"
        assert result["num_channels"] >= 8
        assert result["sampling_rate_hz"] == 500
        assert result["duration_s"] > 0
        assert result["file_size_bytes"] > 0
        assert len(result["channel_labels"]) == result["num_channels"]

    def test_file_info_missing(self):
        from ne_eeg_server.tools import file_info

        with pytest.raises(ValueError, match="File not found"):
            file_info("/nonexistent/file.easy")

    def test_file_info_unsupported_format(self, tmp_path):
        from ne_eeg_server.tools import file_info

        bad_file = tmp_path / "test.csv"
        bad_file.write_text("1,2,3")

        with pytest.raises(ValueError, match="Unsupported format"):
            file_info(str(bad_file))


class TestListEvents:
    def test_list_events(self, sample_easy_path):
        from ne_eeg_server.tools import list_events

        result = list_events(sample_easy_path)

        assert "num_events" in result
        assert isinstance(result["events"], list)
        assert result["total_duration_s"] > 0


class TestSignalQuality:
    def test_signal_quality(self, sample_easy_path):
        from ne_eeg_server.tools import signal_quality

        result = signal_quality(sample_easy_path)

        assert "qc_summary" in result
        assert result["qc_summary"]["channels_total"] > 0
        assert "per_channel" in result
        assert len(result["per_channel"]) > 0

        # Check each channel has expected fields
        for ch_label, ch_data in result["per_channel"].items():
            assert "pass" in ch_data
            assert "rms_raw_uv" in ch_data
            assert "flags" in ch_data


class TestAnalyzeEeg:
    def test_analyze_eeg(self, sample_easy_path):
        from ne_eeg_server.tools import analyze_eeg

        result = analyze_eeg(sample_easy_path)

        assert "per_channel" in result
        assert len(result["per_channel"]) > 0
        assert "qc_summary" in result

        for ch_label, ch_data in result["per_channel"].items():
            assert "band_powers_uv2" in ch_data
            assert "relative_band_powers_pct" in ch_data
            assert "delta" in ch_data["band_powers_uv2"]
            assert "alpha" in ch_data["band_powers_uv2"]


class TestReports:
    def test_generate_qc_report(self, sample_easy_path, tmp_path):
        from ne_eeg_server.tools import generate_qc_report

        output = str(tmp_path / "test_qc.pdf")
        result = generate_qc_report(sample_easy_path, output_path=output)

        assert result["pdf_path"] == output
        assert os.path.isfile(output)

    def test_generate_analysis_report(self, sample_easy_path, tmp_path):
        from ne_eeg_server.tools import generate_analysis_report

        output = str(tmp_path / "test_analysis.pdf")
        result = generate_analysis_report(sample_easy_path, output_path=output)

        assert result["pdf_path"] == output
        assert os.path.isfile(output)
