# ne-eeg-server

**Public, open-source MCP server for EEG analysis with Neuroelectrics data formats.**

GitHub repo: `Neuroelectrics/ne-eeg-server`
License: Apache-2.0

## Scope — STRICTLY EEG ONLY

This server provides local EEG file analysis tools via the Model Context Protocol.
It operates on files on disk. There is no cloud/platform access, no patient database,
no stimulation, no protocol management.

### NEVER include any of the following:
- `.neprot` parsing, writing, schema, or any reference to stimulation protocols
- Stimulation-related tools (`program_stimulation_session`, `get_stimulation_report`)
- Stimulation models (`StimProtocol`, `ElectrodeConfig`, `StimModality`, montage config)
- Platform/cloud tools (`list_patients`, `list_sessions`, `get_eeg_session`, `get_biomarkers`, `get_latent_embedding`, `get_device_status`)
- Patient data models (`Patient`, `PATIENTS`, demographics)
- Device fleet management (`DEVICES`, `DeviceStatus`)
- Embedding/foundation model tools
- Any API endpoints, auth tokens, or cloud credentials
- The `data/` directory from the original server (patients.py, sessions.py, biomarkers.py, embeddings.py, protocols.py, devices.py)
- Safety limits related to stimulation (`MAX_CURRENT_PER_ELECTRODE_UA`, `MAX_TOTAL_CURRENT_UA`, `STIM_WAVEFORM_FORMULA`)
- The `models.py` stimulation classes: `StimProtocol`, `ElectrodeConfig`, `StimModality`, `StimulationReport`, `ScheduledSession`, `ImpedanceCheck`, `Questionnaire`

## Source material

The code is adapted from the internal `neuroelectrics-mcp-demo` server at:
`/Users/giulio/Desktop/NE MCP Server/neuroelectrics-mcp-demo/`

### Files to COPY and adapt (EEG analysis core):
```
src/ne_mcp/eeg_analysis/analyze_easy.py    → src/ne_eeg_server/analysis/analyzer.py
src/ne_mcp/eeg_analysis/eeg_plotting.py    → src/ne_eeg_server/analysis/plotting.py
src/ne_mcp/eeg_analysis/eeg_qc_core.py     → src/ne_eeg_server/analysis/qc.py
src/ne_mcp/eeg_analysis/file_loader.py      → src/ne_eeg_server/readers/loader.py
src/ne_mcp/eeg_analysis/nedf_reader.py      → src/ne_eeg_server/readers/nedf.py
src/ne_mcp/eeg_analysis/pdf_reports.py      → src/ne_eeg_server/reports/pdf.py
src/ne_mcp/eeg_analysis/metrics_defaults.py → src/ne_eeg_server/analysis/metrics_defaults.py
src/ne_mcp/eeg_analysis/psd_peak_qc.py      → src/ne_eeg_server/analysis/psd_peak_qc.py
src/ne_mcp/eeg_analysis/logo-NE.png         → src/ne_eeg_server/reports/logo-NE.png
```

### Files to COPY and strip (remove stimulation content):
```
src/ne_mcp/constants.py  → src/ne_eeg_server/constants.py
  KEEP: electrode positions (10-20, 10-10), FREQ_BANDS, SAMPLING_RATE_HZ,
        RESOLUTION_BITS, BANDWIDTH_HZ, PRECISION_UV, DEVICE_CHANNELS,
        EASY_FILE_UNITS, NV_TO_UV, ACCELEROMETER_*, LSL_OUTLETS,
        FILE_FORMATS, FILE_FORMAT_DESCRIPTIONS
  REMOVE: MAX_CURRENT_PER_ELECTRODE_UA, MAX_TOTAL_CURRENT_UA,
          IMPEDANCE_ABORT_THRESHOLD_KOHM, STIM_WAVEFORM_FORMULA, BATTERY_LIFE_HOURS
```

### Files to REWRITE from scratch:
```
server.py   — new MCP server with only EEG tools (5-6 tools, no stim)
tools.py    — only EEG file analysis tool implementations
models.py   — only EEG-relevant Pydantic models (no stim classes)
```

### Files to NOT copy at all:
```
src/ne_mcp/data/          — entire directory (patients, sessions, protocols, etc.)
```

### Reference scripts to adapt:
```
reference_scripts/load_easy_file.py   — keep
reference_scripts/compute_psd.py      — keep
reference_scripts/band_power.py       — keep
reference_scripts/quality_check.py    — keep
reference_scripts/sample_data/        — keep (demo .easy + .info + generator)
```

## Target repo structure

```
ne-eeg-server/
├── README.md
├── LICENSE                        # Apache 2.0
├── CLAUDE.md                      # this file
├── pyproject.toml
├── .gitignore
├── .github/
│   └── workflows/
│       └── test.yml
├── src/
│   └── ne_eeg_server/
│       ├── __init__.py
│       ├── server.py              # MCP server entry point (stdio + SSE)
│       ├── tools.py               # Tool implementations (EEG only)
│       ├── constants.py           # Electrode positions, freq bands, file formats
│       ├── readers/
│       │   ├── __init__.py
│       │   ├── loader.py          # Unified file loader (format detection + normalization)
│       │   ├── easy.py            # .easy + .info parser (extracted from analyze_easy.py)
│       │   ├── nedf.py            # .nedf parser (from nedf_reader.py)
│       │   └── edf.py             # .edf parser (new, via pyedflib)
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── analyzer.py        # Main EasyAnalyzer class (from analyze_easy.py)
│       │   ├── qc.py              # QC metrics engine (from eeg_qc_core.py)
│       │   ├── plotting.py        # Plot generation (from eeg_plotting.py)
│       │   ├── metrics_defaults.py
│       │   └── psd_peak_qc.py
│       └── reports/
│           ├── __init__.py
│           ├── pdf.py             # PDF report generation (from pdf_reports.py)
│           └── logo-NE.png
├── reference_scripts/
│   ├── README.md
│   ├── load_easy_file.py
│   ├── compute_psd.py
│   ├── band_power.py
│   ├── quality_check.py
│   └── sample_data/
│       ├── demo_recording.easy
│       ├── demo_recording.info
│       └── generate_demo.py
├── tests/
│   ├── __init__.py
│   ├── test_server.py
│   ├── test_tools.py
│   └── test_readers.py
└── docs/
    └── tools.md
```

## MCP Tools to implement (6 tools)

| # | Tool | Description |
|---|------|-------------|
| 1 | `file_info` | **NEW.** Extract metadata from any NE EEG file: format, channels, sample rate, duration, device, montage, file size. Works with .easy, .nedf, .edf |
| 2 | `list_events` | **NEW.** Extract all markers/events with timestamps from a recording |
| 3 | `signal_quality` | Per-channel QC metrics (RMS, kurtosis, event rate, line power, PASS/FAIL). Returns JSON. Based on existing `analyze_easy_file` QC pipeline |
| 4 | `analyze_eeg` | Full spectral analysis: PSD, band powers, ratios, peak alpha. Returns JSON + inline PSD plot. Based on existing `analyze_easy_file` |
| 5 | `generate_qc_report` | PDF signal quality report. Based on existing `generate_qc_report` |
| 6 | `generate_analysis_report` | PDF spectral/functional analysis report. Based on existing `generate_analysis_report` |

All tools accept: `file_path` (required), `start_time_s`, `duration_s` (optional time window).
Tools 3 and 4 also accept: `channels` (optional list of 10-20 labels).

## Tech stack

- Python ≥ 3.10
- `mcp` SDK (≥ 1.0.0)
- `numpy`, `scipy` (signal processing)
- `matplotlib` (plotting)
- `reportlab` (PDF generation)
- `pyedflib` (EDF/NEDF reading — add as new dependency)
- `pydantic` (data models, ≥ 2.0)

## Server instructions (for LLM grounding)

The server instructions should emphasize:
1. This server works with LOCAL EEG FILES ONLY — no cloud, no patients, no stimulation
2. Supported formats: .easy, .easy.gz, .nedf, .edf
3. Always use the tools — never write custom EEG analysis code
4. Report exact numerical values from tools, do not invent data
5. Distinguish data presentation from clinical interpretation

## Build order

1. Scaffold: `pyproject.toml`, `README.md`, `.gitignore`, directory structure
2. Copy & adapt readers: `easy.py`, `nedf.py`, `loader.py` — add `edf.py`
3. Copy & adapt analysis: `analyzer.py`, `qc.py`, `plotting.py`, `psd_peak_qc.py`
4. Copy & adapt reports: `pdf.py` + logo
5. Write new tools: `file_info`, `list_events` (new), adapt existing analysis/report tools
6. Write server.py with stripped-down tool registry
7. Copy & adapt constants.py (remove stim constants)
8. Write tests
9. Write README with installation, Claude Desktop config, and tool reference
10. Final audit: `grep -r stim`, `grep -r protocol`, `grep -r patient`, `grep -r neprot`
__