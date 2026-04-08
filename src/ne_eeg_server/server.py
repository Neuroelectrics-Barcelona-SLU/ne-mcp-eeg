"""
MCP server entry point — registers EEG analysis tools and starts the transport.

Supports stdio (Claude Desktop) and SSE (web-based agents) transports.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

from ne_eeg_server import tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ne_eeg_server.server")

# ---------------------------------------------------------------------------
# Server-level instructions — sent to the LLM at connection time
# ---------------------------------------------------------------------------
SERVER_INSTRUCTIONS = """\
You are connected to the ne-eeg-server, an MCP server for analyzing local EEG files \
recorded with Neuroelectrics Enobio and Starstim devices.

CRITICAL RULES:

1. This server works with LOCAL EEG FILES ONLY — no cloud access, no patient databases, \
no stimulation, no device management.
2. Supported formats: .easy, .easy.gz, .nedf, .edf
3. ALWAYS use the provided tools — never write custom EEG analysis code.
4. Report exact numerical values from tools. Do not invent data.
5. Distinguish data presentation from clinical interpretation. You are not a medical \
professional. Present the data and note patterns, but do not make clinical diagnoses.
6. If a tool returns an error, say so clearly — do not fill in plausible-sounding values.

AVAILABLE TOOLS (6 total):

1. file_info — Extract metadata from any supported EEG file: format, channels, sample \
rate, duration, device, file size.
   Example: "What format is /path/to/recording.easy?"

2. list_events — Extract all markers/events with timestamps from a recording.
   Example: "Show me the events in /path/to/recording.nedf"

3. signal_quality — Per-channel QC metrics (RMS, kurtosis, event rate, line power, \
PASS/FAIL). Returns JSON.
   Example: "Check the signal quality of /path/to/recording.easy"

4. analyze_eeg — Full spectral analysis: PSD, band powers, ratios, peak alpha. \
Returns JSON + inline PSD plot.
   Example: "Analyze the EEG in /path/to/recording.nedf"

5. generate_qc_report — Generate a branded PDF signal quality report.
   Example: "Generate a QC report for /path/to/recording.easy"

6. generate_analysis_report — Generate a branded PDF spectral/functional analysis report.
   Example: "Create an analysis report for /path/to/recording.easy"

All tools accept: file_path (required), start_time_s and duration_s (optional time window).
Tools 3 and 4 also accept: channels (optional list of 10-20 labels to filter).
"""

server = Server(
    "ne-eeg-server",
    instructions=SERVER_INSTRUCTIONS,
)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="file_info",
        description=(
            "Extract metadata from any supported EEG file (.easy, .easy.gz, .nedf, .edf): "
            "format, channels, sample rate, duration, device, file size."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to an EEG file on disk.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="list_events",
        description=(
            "Extract all markers/events with timestamps from an EEG recording. "
            "Returns event codes, timestamps, and sample indices."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to an EEG file on disk.",
                },
                "start_time_s": {
                    "type": "number",
                    "description": "Start of time window in seconds. Default: 0.",
                    "default": 0,
                },
                "duration_s": {
                    "type": "number",
                    "description": "Duration of time window in seconds. Default: entire recording.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="signal_quality",
        description=(
            "Per-channel signal quality assessment: RMS (raw/notch/filtered), kurtosis, "
            "event rate, line power (50/60 Hz), suspicious PSD peaks, PASS/FAIL flags. "
            "Returns JSON with detailed QC metrics per channel."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to an EEG file on disk.",
                },
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of channels by 10-20 label. All channels if omitted.",
                },
                "start_time_s": {
                    "type": "number",
                    "description": "Start of analysis window in seconds. Default: 0.",
                    "default": 0,
                },
                "duration_s": {
                    "type": "number",
                    "description": "Duration of analysis window in seconds. Default: entire recording.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="analyze_eeg",
        description=(
            "Full spectral analysis of an EEG file. Computes PSD (Welch's method), "
            "band powers (delta/theta/alpha/beta/gamma), alpha/theta ratio, peak alpha "
            "frequency, per-channel QC metrics with PASS/FAIL, and generates a PSD plot. "
            "Returns numerical results + inline PSD plot image. "
            "Supports .easy, .easy.gz, .nedf, and .edf formats."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to an EEG file on disk.",
                },
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subset of channels by 10-20 label. Defaults to first 8.",
                },
                "start_time_s": {
                    "type": "number",
                    "description": "Start of analysis window in seconds. Default: 0.",
                    "default": 0,
                },
                "duration_s": {
                    "type": "number",
                    "description": "Duration of analysis window in seconds. Default: entire recording.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="generate_qc_report",
        description=(
            "Generate a PDF Signal Quality report: per-channel metrics table, "
            "PSD plots, raw and filtered time-series. Branded with Neuroelectrics logo. "
            "Returns the path to the saved PDF."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to an EEG file on disk.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Path for the output PDF. Default: <filename>_qc_report.pdf.",
                },
                "start_time_s": {
                    "type": "number",
                    "description": "Start of analysis window in seconds. Default: 0.",
                    "default": 0,
                },
                "duration_s": {
                    "type": "number",
                    "description": "Duration of analysis window in seconds. Default: entire recording.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="generate_analysis_report",
        description=(
            "Generate a PDF EEG Analysis report: raw traces with markers, PSD overlay, "
            "band power heatmap, alpha reactivity, alpha/theta ratio, spectral summary, "
            "frontal alpha asymmetry. Branded with Neuroelectrics logo. "
            "Returns the path to the saved PDF."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to an EEG file on disk.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Path for the output PDF. Default: <filename>_analysis_report.pdf.",
                },
                "start_time_s": {
                    "type": "number",
                    "description": "Start of analysis window in seconds. Default: 0.",
                    "default": 0,
                },
                "duration_s": {
                    "type": "number",
                    "description": "Duration of analysis window in seconds. Default: entire recording.",
                },
            },
            "required": ["file_path"],
        },
    ),
]


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return TOOL_DEFINITIONS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent | ImageContent]:
    arguments = arguments or {}

    dispatch = {
        "file_info": lambda: tools.file_info(**arguments),
        "list_events": lambda: tools.list_events(**arguments),
        "signal_quality": lambda: tools.signal_quality(**arguments),
        "analyze_eeg": lambda: tools.analyze_eeg(**arguments),
        "generate_qc_report": lambda: tools.generate_qc_report(**arguments),
        "generate_analysis_report": lambda: tools.generate_analysis_report(**arguments),
    }

    handler = dispatch.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        result = handler()

        # For analyze_eeg, return the PSD plot image separately
        if name == "analyze_eeg" and "plot_png_base64" in result:
            plot_data = result.pop("plot_png_base64")
            contents: list[TextContent | ImageContent] = [
                TextContent(type="text", text=json.dumps(result, indent=2, default=str)),
            ]
            if plot_data:
                contents.append(
                    ImageContent(type="image", data=plot_data, mimeType="image/png")
                )
            return contents

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except ValueError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception("Unexpected error in tool %s", name)
        return [TextContent(type="text", text=json.dumps({"error": f"Internal error: {e}"}))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_stdio():
    """Run the server with stdio transport (for Claude Desktop)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    import asyncio

    parser = argparse.ArgumentParser(description="ne-eeg-server: MCP server for EEG analysis")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(run_stdio())
    elif args.transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        import uvicorn

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await server.run(
                    streams[0], streams[1], server.create_initialization_options()
                )

        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )
        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
