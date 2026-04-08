"""Tests for the MCP server setup."""

import pytest


def test_server_exists():
    from ne_eeg_server.server import server
    assert server is not None


def test_tool_definitions():
    from ne_eeg_server.server import TOOL_DEFINITIONS

    assert len(TOOL_DEFINITIONS) == 6

    tool_names = {t.name for t in TOOL_DEFINITIONS}
    expected = {
        "file_info", "list_events", "signal_quality",
        "analyze_eeg", "generate_qc_report", "generate_analysis_report",
    }
    assert tool_names == expected


def test_server_instructions_no_stim():
    from ne_eeg_server.server import SERVER_INSTRUCTIONS

    lower = SERVER_INSTRUCTIONS.lower()
    assert "stimulation" not in lower or "no stimulation" in lower
    assert "patient" not in lower or "no patient" in lower
