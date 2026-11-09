"""Compatibility adapter for the original bench QC API."""
from ne_eeg_server.qc.bench import (
    calculate_channel_metrics_from_signals, _merge_thresholds, _design_filters,
    _contiguous_event_count, _max_line_power_db, _suspicious_peak_metrics,
)
from ne_eeg_server.qc.presets import METRICS_DEFAULT_THRESHOLDS, DEFAULT_EVENT_THRESHOLD_UV
from ne_eeg_server.qc.peaks import find_suspicious_psd_peak
