# ne-eeg-server

An open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for EEG analysis with Neuroelectrics data formats.

Analyze EEG recordings locally — no cloud, no patient data, no stimulation. Just signal processing tools exposed via MCP for use with Claude Desktop and other MCP clients.

## Supported formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Easy | `.easy`, `.easy.gz` | Neuroelectrics Easy file format |
| NEDF | `.nedf` | Neuroelectrics Data Format |
| EDF | `.edf` | European Data Format |

## Tools

| Tool | Description |
|------|-------------|
| `file_info` | Extract metadata: format, channels, sample rate, duration, device |
| `list_events` | Extract markers/events with timestamps |
| `signal_quality` | Per-channel QC (RMS, kurtosis, line noise, PASS/FAIL) |
| `analyze_eeg` | Spectral analysis: PSD, band powers, ratios, peak alpha |
| `generate_qc_report` | Generate PDF signal quality report |
| `generate_analysis_report` | Generate PDF spectral/functional analysis report |

## Installation

```bash
pip install ne-eeg-server
```

Or install from source:

```bash
git clone https://github.com/Neuroelectrics/ne-eeg-server.git
cd ne-eeg-server
pip install -e ".[dev]"
```

## Usage with Claude Desktop

Add to your Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ne-eeg-server": {
      "command": "ne-eeg-server",
      "args": []
    }
  }
}
```

Then ask Claude to analyze your EEG files:

> "Analyze the signal quality of /path/to/recording.easy"
> "Generate a spectral analysis report for /path/to/recording.nedf"

## Usage with Claude Code

```bash
claude mcp add ne-eeg-server -- ne-eeg-server
```

## Development

```bash
git clone https://github.com/Neuroelectrics/ne-eeg-server.git
cd ne-eeg-server
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
