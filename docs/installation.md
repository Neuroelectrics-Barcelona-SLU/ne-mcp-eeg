# ne-mcp-eeg — Installation Guide

## Prerequisites

| Requirement | Version | Download |
|---|---|---|
| Python | ≥ 3.10 | [python.org/downloads](https://www.python.org/downloads/) |
| Claude Desktop **or** Claude Code | latest | [claude.ai/download](https://claude.ai/download) |

---

## Windows

### 1 — Install the package

Open **PowerShell** or **Command Prompt**:

```powershell
git clone https://github.com/Neuroelectrics-Barcelona-SLU/ne-mcp-eeg.git
cd ne-mcp-eeg
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

> **Tip:** If `python` is not recognised, try `py` instead.

### 2 — Find your Python path

You will need the full path to the Python binary inside the venv:

```powershell
(Get-Command python).Source
```

Example output: `C:\Users\YourName\ne-mcp-eeg\.venv\Scripts\python.exe`  
Copy this — you will need it in the next step.

### 3a — Connect to Claude Desktop

Open (or create) the config file at:

```
%APPDATA%\Claude\claude_desktop_config.json
```

Add the following, replacing the path with your actual Python path from step 2:

```json
{
  "mcpServers": {
    "ne-mcp-eeg": {
      "command": "C:\\Users\\YourName\\ne-mcp-eeg\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ne_eeg_server.server"]
    }
  }
}
```

> **Note:** Use double backslashes `\\` in JSON on Windows.

Restart Claude Desktop. The six EEG tools will appear in the tool picker.

### 3b — Connect to Claude Code (alternative)

```powershell
claude mcp add ne-mcp-eeg -- C:\Users\YourName\ne-mcp-eeg\.venv\Scripts\python.exe -m ne_eeg_server.server
```

---

## macOS

### 1 — Install the package

Open **Terminal**:

```bash
git clone https://github.com/Neuroelectrics-Barcelona-SLU/ne-mcp-eeg.git
cd ne-mcp-eeg
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2 — Find your Python path

```bash
which python
```

Example output: `/Users/yourname/ne-mcp-eeg/.venv/bin/python`  
Copy this — you will need it in the next step.

### 3a — Connect to Claude Desktop

Open (or create) the config file at:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Add the following, replacing the path with your actual Python path from step 2:

```json
{
  "mcpServers": {
    "ne-mcp-eeg": {
      "command": "/Users/yourname/ne-mcp-eeg/.venv/bin/python",
      "args": ["-m", "ne_eeg_server.server"]
    }
  }
}
```

Restart Claude Desktop. The six EEG tools will appear in the tool picker.

### 3b — Connect to Claude Code (alternative)

```bash
claude mcp add ne-mcp-eeg -- /Users/yourname/ne-mcp-eeg/.venv/bin/python -m ne_eeg_server.server
```

---

## Verify the installation

Once connected, ask Claude:

> *"Get file info for /path/to/my/recording.easy"*

Claude will call the `file_info` tool and return the file metadata. If you don't have a recording handy, use the included demo file:

```
ne-mcp-eeg/reference_scripts/sample_data/demo_recording.easy
```

---

## Supported file formats

| Format | Extension |
|---|---|
| Neuroelectrics native | `.easy`, `.easy.gz` |
| Neuroelectrics binary | `.nedf` |
| European Data Format | `.edf` |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `python` not found on Windows | Use `py` instead, or install Python from [python.org](https://python.org) |
| `python3` not found on macOS | Install via Homebrew: `brew install python` |
| Tools not showing in Claude Desktop | Check the config file path and JSON syntax, then restart Claude Desktop |
| EDF file fails to load | The built-in fallback parser handles most non-compliant EDF files automatically |
| `pip install` errors | Make sure the venv is activated before running pip |
