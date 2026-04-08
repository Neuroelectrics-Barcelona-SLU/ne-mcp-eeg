<p align="center">
  <img src="docs/logo-NE.png" alt="Neuroelectrics" width="300">
</p>

<h1 align="center">ne-mcp-eeg</h1>

<p align="center">
  An open-source <a href="https://modelcontextprotocol.io/">Model Context Protocol (MCP)</a> server for EEG analysis with Neuroelectrics data formats.
</p>

<p align="center">
  Analyze EEG recordings locally — no cloud, no patient data, no stimulation.<br>
  Signal processing tools exposed via MCP for use with Claude, ChatGPT, Gemini, and any MCP-compatible client.
</p>

---

## Supported formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Easy | `.easy`, `.easy.gz` | Neuroelectrics native ASCII format |
| NEDF | `.nedf` | Neuroelectrics Data Format (24-bit binary) |
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
git clone https://github.com/giulioruffini/ne-mcp-eeg.git
cd ne-mcp-eeg
pip install -e ".[dev]"
```

## Usage with Claude Desktop

Add to your Claude Desktop config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ne-mcp-eeg": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "ne_eeg_server.server"]
    }
  }
}
```

Then ask Claude to analyze your EEG files:

> "Analyze the signal quality of /path/to/recording.easy"
> "Generate a spectral analysis report for /path/to/recording.nedf"

## Usage with Claude Code

```bash
claude mcp add ne-mcp-eeg -- /path/to/your/venv/bin/python -m ne_eeg_server.server
```

## Usage with ChatGPT

ChatGPT supports MCP servers via the **Actions** feature with an SSE transport. Run the server in SSE mode:

```bash
ne-eeg-server --transport sse --port 8080
```

Then configure a ChatGPT Custom GPT action pointing to `http://localhost:8080/sse`. See the [OpenAI MCP documentation](https://platform.openai.com/docs/guides/tools-mcp) for detailed setup instructions.

## Usage with Google Gemini

Gemini supports MCP servers in [Google AI Studio](https://ai.google.dev/gemini-api/docs/mcp) and via the Gemini API. Run the server in SSE mode:

```bash
ne-eeg-server --transport sse --port 8080
```

In Google AI Studio, add an MCP tool server with the URL `http://localhost:8080/sse`. The six EEG analysis tools will appear automatically.

For the Gemini API, connect via the MCP client SDK — see [Gemini MCP documentation](https://ai.google.dev/gemini-api/docs/mcp).

## Usage with other MCP clients

Any MCP-compatible client can connect to this server. Two transport modes are available:

| Transport | Use case | Command |
|-----------|----------|---------|
| **stdio** | Local desktop apps (Claude Desktop, Claude Code) | `python -m ne_eeg_server.server` |
| **SSE** | Web-based clients, remote agents | `ne-eeg-server --transport sse --port 8080` |

For stdio, the client launches the server process directly. For SSE, you run the server first and point the client to the HTTP endpoint.

## Development

```bash
git clone https://github.com/giulioruffini/ne-mcp-eeg.git
cd ne-mcp-eeg
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
