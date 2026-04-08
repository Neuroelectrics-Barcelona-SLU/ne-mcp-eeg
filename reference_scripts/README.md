# Reference Scripts

Standalone Python scripts showing the **traditional NE EEG workflow** — load `.easy` files, compute spectral features, run quality checks. These represent the "old way" of working with NE data that the MCP server is modernizing.

Each script is self-contained and runnable against the included sample data.

## Scripts

| Script | Description |
|--------|-------------|
| `load_easy_file.py` | Load a `.easy` file + `.info` metadata, print summary, access channels by 10-20 label |
| `compute_psd.py` | Compute and plot power spectral density (Welch's method) with frequency band shading |
| `quality_check.py` | Per-channel signal quality assessment: flatline, noise, line noise, clipping |
| `band_power.py` | Compute absolute/relative band powers and clinical ratios (alpha/theta, delta/alpha) |

## Requirements

```bash
pip install numpy scipy matplotlib pandas
```

## Usage

```bash
cd reference_scripts
python load_easy_file.py
python compute_psd.py
python quality_check.py
python band_power.py
```

All scripts use `sample_data/demo_recording.easy` by default.

## Sample Data

`sample_data/demo_recording.easy` — synthetic 8-channel, 10-second recording at 500 S/s:
- Channels: Fp1, Fp2, F3, F4, C3, C4, O1, O2
- Contains alpha rhythm (~10 Hz) in occipital channels, frontal theta, a few artifact samples
- Companion `.info` file with metadata

## Relationship to MCP Server

These scripts show what researchers do manually today. The MCP server provides the same insights (and more) through a conversational agent interface — no scripting required.

For the Python library behind `.easy` file reading, see [NEPy](https://github.com/Neuroelectrics/NEPy).
