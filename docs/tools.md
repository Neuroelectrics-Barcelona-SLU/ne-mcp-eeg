# Tool Reference

All tools operate on local EEG files. No cloud access, no patient data.

## Supported Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Easy | `.easy`, `.easy.gz` | Neuroelectrics native ASCII format (nV, tab-separated) |
| NEDF | `.nedf` | Neuroelectrics Data Format (XML header + 24-bit binary) |
| EDF | `.edf` | European Data Format (via pyedflib) |

## Tools

### 1. `file_info`

Extract metadata from any supported EEG file.

**Parameters:**
- `file_path` (required): Absolute path to an EEG file

**Returns:** format, channels, sample rate, duration, device, file size

---

### 2. `list_events`

Extract all markers/events with timestamps.

**Parameters:**
- `file_path` (required): Absolute path to an EEG file
- `start_time_s` (optional): Start of time window (default: 0)
- `duration_s` (optional): Duration of window (default: entire recording)

**Returns:** list of events with time, code, and sample index

---

### 3. `signal_quality`

Per-channel signal quality assessment with PASS/FAIL flags.

**Parameters:**
- `file_path` (required): Absolute path to an EEG file
- `channels` (optional): List of 10-20 electrode labels to analyze
- `start_time_s` (optional): Start of analysis window (default: 0)
- `duration_s` (optional): Duration of window (default: entire recording)

**Metrics per channel:**
- RMS (raw, notch-filtered, fully filtered) in µV
- Kurtosis (notch-filtered)
- Event rate (events/s above threshold)
- Line power at 50/60 Hz (dB)
- Suspicious PSD peak SNR (dB)
- PASS/FAIL flag with per-metric flags

---

### 4. `analyze_eeg`

Full spectral analysis with PSD plot.

**Parameters:**
- `file_path` (required): Absolute path to an EEG file
- `channels` (optional): List of 10-20 electrode labels (default: first 8)
- `start_time_s` (optional): Start of analysis window (default: 0)
- `duration_s` (optional): Duration of window (default: entire recording)

**Returns:**
- Band powers (absolute µV² and relative %) for delta, theta, alpha, beta, gamma
- Peak alpha frequency (Hz)
- Alpha/theta ratio
- Per-channel QC metrics
- Inline PSD plot (base64 PNG)

---

### 5. `generate_qc_report`

Generate a branded PDF signal quality report.

**Parameters:**
- `file_path` (required): Absolute path to an EEG file
- `output_path` (optional): PDF output path (default: `<filename>_qc_report.pdf`)
- `start_time_s` (optional): Start of analysis window (default: 0)
- `duration_s` (optional): Duration of window (default: entire recording)

**Report contents:**
- Per-channel metrics table with PASS/FAIL highlighting
- PSD plots (8 channels per page)
- Raw and filtered time-series plots

---

### 6. `generate_analysis_report`

Generate a branded PDF spectral analysis report.

**Parameters:**
- `file_path` (required): Absolute path to an EEG file
- `output_path` (optional): PDF output path (default: `<filename>_analysis_report.pdf`)
- `start_time_s` (optional): Start of analysis window (default: 0)
- `duration_s` (optional): Duration of window (default: entire recording)

**Report contents:**
- Raw EEG traces with event markers
- PSD overlay plot
- Band power heatmap
- Alpha reactivity (Eyes Open vs Eyes Closed)
- Alpha/theta ratio by channel
- Spectral summary table
- Frontal alpha asymmetry (if F3/F4 available)
- Per-channel statistics
