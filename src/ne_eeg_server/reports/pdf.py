"""
PDF report generators for EEG QC and EEG Analysis reports.

Two report types:
  - QC Report: per-channel signal quality metrics + PSD plots.
  - Analysis Report: spectral analysis, band powers, alpha reactivity.

Style matches Neuroelectrics branded documents (dark teal header bar,
teal section headings, clean tables with generous whitespace).

Authors: G. Ruffini / Neuroelectrics, 2026
"""

from __future__ import annotations

import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import signal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
    KeepTogether, HRFlowable,
)

from ne_eeg_server.analysis.analyzer import EasyAnalyzer
from ne_eeg_server.analysis.metrics_defaults import DEFAULT_EVENT_THRESHOLD_UV

# ---------------------------------------------------------------------------
# Paths & brand colors (matching NE strategy memo style)
# ---------------------------------------------------------------------------
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo-NE.png")

_NE_DARK_TEAL = "#2C3E50"
_NE_TEAL = "#00A5B5"
_NE_LIGHT_TEAL = "#E8F6F8"
_NE_GRAY = "#808080"
_NE_LIGHT_GRAY = "#F5F5F5"
_NE_TEXT = "#333333"
_NE_PASS_GREEN = "#27ae60"
_NE_FAIL_RED = "#e74c3c"

PAGE_W, PAGE_H = A4


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _build_styles():
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "NETitle", parent=styles["Heading1"],
        fontSize=22, leading=28, textColor=colors.HexColor(_NE_DARK_TEAL),
        spaceAfter=2, spaceBefore=20, alignment=TA_LEFT,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "NESubtitle", parent=styles["Normal"],
        fontSize=11, leading=15, textColor=colors.HexColor(_NE_TEAL),
        spaceAfter=16, alignment=TA_LEFT,
        fontName="Helvetica",
    )
    heading_style = ParagraphStyle(
        "NEHeading", parent=styles["Heading2"],
        fontSize=14, leading=18, textColor=colors.HexColor(_NE_TEAL),
        spaceAfter=8, spaceBefore=18,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "NEBody", parent=styles["Normal"],
        fontSize=9, leading=13, spaceAfter=6,
        textColor=colors.HexColor(_NE_TEXT),
        alignment=TA_JUSTIFY,
    )
    small_style = ParagraphStyle(
        "NESmall", parent=styles["Normal"],
        fontSize=7.5, leading=10, textColor=colors.HexColor(_NE_GRAY),
    )
    meta_style = ParagraphStyle(
        "NEMeta", parent=styles["Normal"],
        fontSize=9, leading=12, spaceAfter=3,
        textColor=colors.HexColor(_NE_TEXT),
    )
    return {
        "base": styles, "title": title_style, "subtitle": subtitle_style,
        "heading": heading_style, "body": body_style, "small": small_style,
        "meta": meta_style,
    }


# ---------------------------------------------------------------------------
# Header / footer (dark teal bar like NE strategy memos)
# ---------------------------------------------------------------------------

def _header_footer(canvas, doc, report_type: str, gen_ts: str, filename: str):
    canvas.saveState()
    w, h = PAGE_W, PAGE_H

    # Dark teal header bar
    bar_h = 0.45 * inch
    canvas.setFillColor(colors.HexColor(_NE_DARK_TEAL))
    canvas.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)

    # "NEUROELECTRICS" in white on the bar
    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(colors.white)
    canvas.drawString(doc.leftMargin, h - 0.3 * inch, "NEUROELECTRICS")

    # Report type below in smaller text
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#AABBCC"))
    canvas.drawString(doc.leftMargin, h - 0.41 * inch, report_type.upper())

    # Date on the right
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.white)
    canvas.drawRightString(w - doc.rightMargin, h - 0.3 * inch, gen_ts)

    # Thin teal accent line below header
    canvas.setStrokeColor(colors.HexColor(_NE_TEAL))
    canvas.setLineWidth(1.5)
    canvas.line(doc.leftMargin, h - bar_h - 2, w - doc.rightMargin, h - bar_h - 2)

    # Footer
    left = doc.leftMargin
    right = w - doc.rightMargin
    footer_y = 0.35 * inch

    # Thin line above footer
    canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
    canvas.setLineWidth(0.5)
    canvas.line(left, footer_y + 8, right, footer_y + 8)

    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor(_NE_GRAY))
    canvas.drawString(left, footer_y, f"Neuroelectrics  •  {filename}")
    canvas.drawCentredString((left + right) / 2, footer_y, f"Page {doc.page}")
    canvas.drawRightString(right, footer_y, "neuroelectrics.com")

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Figure helper — preserves actual aspect ratio
# ---------------------------------------------------------------------------

def _fig_to_image(fig, width_inches=6.2, dpi=150) -> Image:
    """Convert a matplotlib figure to a ReportLab Image, preserving true aspect ratio."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)

    # Read actual pixel dimensions from the saved PNG to get true aspect ratio
    from PIL import Image as PILImage
    pil_img = PILImage.open(buf)
    px_w, px_h = pil_img.size
    aspect = px_h / px_w
    buf.seek(0)

    img = Image(buf, width=width_inches * inch, height=width_inches * aspect * inch)
    return img


def _ne_hr():
    """Horizontal rule in NE teal."""
    return HRFlowable(
        width="100%", thickness=1, color=colors.HexColor(_NE_TEAL),
        spaceBefore=6, spaceAfter=10,
    )


# ---------------------------------------------------------------------------
# Table builder helper
# ---------------------------------------------------------------------------

def _ne_table(data, col_widths, has_pass_col=False):
    """Build a branded NE table with teal header and alternating rows."""
    table = Table(data, colWidths=col_widths)

    style_cmds = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_NE_DARK_TEAL)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Grid
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor(_NE_TEAL)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("LINEAFTER", (0, 0), (-2, -1), 0.25, colors.HexColor("#E0E0E0")),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]

    # Alternating row backgrounds
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(_NE_LIGHT_GRAY)))

    table.setStyle(TableStyle(style_cmds))
    return table


# ===========================================================================
# QC Report
# ===========================================================================

def generate_qc_report(
    file_path: str,
    output_path: Optional[str] = None,
    start_time_s: float = 0.0,
    duration_s: Optional[float] = None,
) -> str:
    """Generate a Signal Quality PDF report. Returns the path to the PDF."""
    analyzer = EasyAnalyzer(file_path)
    fs = analyzer.fs
    total_duration = analyzer.get_file_duration()
    n_ch = analyzer.num_channels

    if duration_s is None:
        duration_s = total_duration - start_time_s

    electrodes = _parse_electrodes(file_path, n_ch)

    results = analyzer.process_window(start_time_s, duration_s)
    qc_metrics = analyzer.calculate_channel_metrics(
        window_start_s=start_time_s, window_duration_s=duration_s,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        plot_paths = analyzer.generate_plots(results, tmpdir, "qc")

        gen_ts = datetime.now().strftime("%B %d, %Y")
        filename = os.path.basename(file_path)

        if output_path is None:
            output_path = file_path.replace(".easy", "_qc_report.pdf")

        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            topMargin=0.7 * inch, bottomMargin=0.6 * inch,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        )

        s = _build_styles()
        story = []

        # Title block
        story.append(Spacer(1, 12))
        if os.path.isfile(_LOGO_PATH):
            story.append(Image(_LOGO_PATH, width=1.6 * inch, height=0.6 * inch,
                               hAlign="LEFT"))
            story.append(Spacer(1, 10))

        story.append(Paragraph("EEG Signal Quality Report", s["title"]))
        story.append(Paragraph(
            f"Automated per-channel quality assessment with PASS/FAIL thresholds",
            s["subtitle"],
        ))
        story.append(_ne_hr())

        # Metadata block
        meta_items = [
            f"<b>File:</b> {filename}",
            f"<b>Device:</b> {_parse_device(file_path)}",
            f"<b>Channels:</b> {n_ch} &nbsp;&nbsp; <b>Sampling rate:</b> {int(fs)} Hz",
            f"<b>Duration:</b> {total_duration:.1f} s total &nbsp;&nbsp; "
            f"<b>Window:</b> {start_time_s:.1f} – {start_time_s + duration_s:.1f} s",
            f"<b>Generated:</b> {gen_ts}",
        ]
        for item in meta_items:
            story.append(Paragraph(item, s["meta"]))
        story.append(Spacer(1, 12))

        # QC Summary
        total_pass = sum(1 for m in qc_metrics.values() if m.get("pass", False))
        total_ch = len(qc_metrics)
        if total_pass == total_ch:
            summary_html = (
                f'<font color="{_NE_PASS_GREEN}"><b>ALL {total_ch} CHANNELS PASS</b></font>'
            )
        else:
            summary_html = (
                f'<font color="{_NE_FAIL_RED}"><b>{total_ch - total_pass} of {total_ch} '
                f'channels FAIL</b></font> &nbsp;({total_pass} pass)'
            )
        story.append(Paragraph(f"QC Result: {summary_html}", s["body"]))
        story.append(Spacer(1, 10))

        # Metrics table
        story.append(Paragraph("1. Per-Channel Metrics", s["heading"]))
        story.append(_build_qc_table(qc_metrics, electrodes))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "* = flagged (exceeds threshold). RMS in µV. Line power in dB. "
            f"Event threshold: {DEFAULT_EVENT_THRESHOLD_UV:.1f} µV.",
            s["small"],
        ))

        # PSD plots
        for key in sorted(plot_paths.keys()):
            if "psd" in key:
                story.append(PageBreak())
                page_label = key.replace("psd_", "").replace("psd", "Channels 1–8")
                story.append(Paragraph(f"2. Power Spectral Density — {page_label}", s["heading"]))
                story.append(Spacer(1, 4))
                story.append(_fig_to_image(
                    _open_saved_fig(plot_paths[key]), width_inches=6.2
                ) if False else _img_from_path(plot_paths[key], width_inches=6.2))

        # Time-series plots
        section_num = 3
        for key in sorted(plot_paths.keys()):
            if "raw" in key or "filtered" in key:
                story.append(PageBreak())
                label = key.replace("_", " ").replace("page", "— page").title()
                story.append(Paragraph(f"{section_num}. {label}", s["heading"]))
                story.append(Spacer(1, 4))
                story.append(_img_from_path(plot_paths[key], width_inches=6.2))
                section_num += 1

        def _on_page(canvas, doc):
            _header_footer(canvas, doc, "EEG Signal Quality Report", gen_ts, filename)

        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    return output_path


def _img_from_path(path: str, width_inches: float = 6.2) -> Image:
    """Load a saved PNG and create an Image flowable preserving aspect ratio."""
    from PIL import Image as PILImage
    pil_img = PILImage.open(path)
    px_w, px_h = pil_img.size
    aspect = px_h / px_w
    return Image(path, width=width_inches * inch, height=width_inches * aspect * inch)


def _build_qc_table(qc_metrics: dict, electrodes: list[str]) -> Table:
    """Build the per-channel QC metrics table with NE styling."""
    header = ["Ch", "Mean\n(µV)", "RMS raw\n(µV)", "RMS notch\n(µV)",
              "RMS filt\n(µV)", "Line\n50/60 (dB)", "Kurtosis\n(notch)",
              "Events\n(/s)", "Result"]

    data = [header]
    for ch_idx in sorted(qc_metrics.keys()):
        m = qc_metrics[ch_idx]
        flags = m.get("flags", {})
        passed = m.get("pass", True)
        label = electrodes[ch_idx] if ch_idx < len(electrodes) else f"Ch{ch_idx+1}"

        def fmt(val, digits=1, flag_key=None):
            if val is None or (isinstance(val, float) and val != val):
                return "—"
            s = f"{val:.{digits}f}"
            if flag_key and flags.get(flag_key):
                s += "*"
            return s

        data.append([
            label,
            fmt(m.get("mean_uv"), 0, "mean_uv"),
            fmt(m.get("raw_rms_uv"), 1, "raw_rms_uv"),
            fmt(m.get("notch_rms_uv"), 1, "notch_rms_uv"),
            fmt(m.get("full_rms_uv"), 1, "full_rms_uv"),
            fmt(m.get("line_power_db"), 1, "line_power_db"),
            fmt(m.get("notch_kurtosis"), 1, "notch_kurtosis"),
            fmt(m.get("notch_events_rate_hz"), 1, "notch_events_rate_hz"),
            "PASS" if passed else "FAIL",
        ])

    w = (PAGE_W - 1.5 * inch) / 9  # distribute evenly
    col_widths = [w * 0.8] + [w] * 7 + [w * 1.2]
    table = Table(data, colWidths=col_widths)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_NE_DARK_TEAL)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor(_NE_TEAL)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    for row_i, ch_idx in enumerate(sorted(qc_metrics.keys()), start=1):
        passed = qc_metrics[ch_idx].get("pass", True)
        # Subtle row alternation
        if row_i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, row_i), (-2, row_i),
                               colors.HexColor(_NE_LIGHT_GRAY)))
        # PASS/FAIL cell
        if passed:
            style_cmds.append(("BACKGROUND", (-1, row_i), (-1, row_i),
                               colors.HexColor("#E8F5E9")))
            style_cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i),
                               colors.HexColor(_NE_PASS_GREEN)))
        else:
            style_cmds.append(("BACKGROUND", (-1, row_i), (-1, row_i),
                               colors.HexColor("#FFEBEE")))
            style_cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i),
                               colors.HexColor(_NE_FAIL_RED)))
        style_cmds.append(("FONTNAME", (-1, row_i), (-1, row_i), "Helvetica-Bold"))

    # Bottom border
    style_cmds.append(("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CCCCCC")))

    table.setStyle(TableStyle(style_cmds))
    return table


# ===========================================================================
# EEG Analysis Report
# ===========================================================================

BANDS = {
    "Delta": (1, 4), "Theta": (4, 8), "Alpha": (8, 13),
    "Beta": (13, 30), "Gamma": (30, 45),
}

BAND_SHADING = {
    "δ": ((1, 4), "#ecf0f1"), "θ": ((4, 8), "#d5f4e6"),
    "α": ((8, 13), "#fdebd0"), "β": ((13, 30), "#d6eaf8"),
}

TRIGGER_MAP = {1: "EO", 2: "EC"}


def generate_analysis_report(
    file_path: str,
    output_path: Optional[str] = None,
    start_time_s: float = 0.0,
    duration_s: Optional[float] = None,
) -> str:
    """Generate a functional EEG Analysis PDF report. Returns PDF path."""
    eeg_uV, triggers, timestamps, ch_names = _load_easy_raw(file_path)
    n_samples, n_ch = eeg_uV.shape
    fs = 500
    total_duration = n_samples / fs

    if duration_s is None:
        duration_s = total_duration - start_time_s

    s0 = int(start_time_s * fs)
    s1 = min(s0 + int(duration_s * fs), n_samples)
    eeg_win = eeg_uV[s0:s1]
    trig_win = triggers[s0:s1]

    if output_path is None:
        output_path = file_path.replace(".easy", "_analysis_report.pdf")

    gen_ts = datetime.now().strftime("%B %d, %Y")
    filename = os.path.basename(file_path)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=0.7 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )

    st = _build_styles()
    story = []

    # Pre-compute all PSDs once (avoids redundant computation)
    nperseg = min(1024, len(eeg_win))
    psd_cache = {}
    for i in range(n_ch):
        f, psd = signal.welch(eeg_win[:, i], fs=fs, nperseg=nperseg)
        psd_cache[i] = (f, psd)

    # --- Title page ---
    story.append(Spacer(1, 12))
    if os.path.isfile(_LOGO_PATH):
        story.append(Image(_LOGO_PATH, width=1.6 * inch, height=0.6 * inch, hAlign="LEFT"))
        story.append(Spacer(1, 10))

    story.append(Paragraph("EEG Analysis Report", st["title"]))
    story.append(Paragraph(
        "Spectral analysis, band powers, and functional EEG features",
        st["subtitle"],
    ))
    story.append(_ne_hr())

    device = _parse_device(file_path)
    meta_items = [
        f"<b>File:</b> {filename}",
        f"<b>Device:</b> {device} &nbsp;&nbsp; <b>Channels:</b> {n_ch} &nbsp;&nbsp; "
        f"<b>Sampling rate:</b> {fs} Hz",
        f"<b>Duration:</b> {total_duration:.1f} s total &nbsp;&nbsp; "
        f"<b>Window:</b> {start_time_s:.1f} – {start_time_s + duration_s:.1f} s",
        f"<b>Generated:</b> {gen_ts}",
    ]
    for item in meta_items:
        story.append(Paragraph(item, st["meta"]))
    story.append(Spacer(1, 14))

    # --- 1. Raw EEG traces ---
    story.append(Paragraph("1. Raw EEG Traces", st["heading"]))
    fig_traces = _plot_raw_traces(eeg_win, trig_win, ch_names, fs, start_time_s)
    story.append(_fig_to_image(fig_traces, width_inches=6.2))

    trig_indices = np.where(trig_win > 0)[0]
    if len(trig_indices) > 0:
        trig_text = ", ".join(
            f"{TRIGGER_MAP.get(trig_win[i], f'T{trig_win[i]}')} @ "
            f"{start_time_s + i/fs:.2f}s"
            for i in trig_indices[:20]
        )
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Markers:</b> {trig_text}", st["small"]))

    # --- 2. Spectral Analysis (PSD + heatmap) ---
    story.append(PageBreak())
    story.append(Paragraph("2. Spectral Analysis", st["heading"]))
    fig_spectral = _plot_spectral_panels(eeg_win, ch_names, fs, psd_cache)
    story.append(_fig_to_image(fig_spectral, width_inches=6.2))
    story.append(Spacer(1, 10))

    # --- 3. Alpha Analysis ---
    story.append(Paragraph("3. Alpha Analysis", st["heading"]))
    fig_alpha = _plot_alpha_panels(eeg_win, trig_win, ch_names, fs, psd_cache)
    story.append(_fig_to_image(fig_alpha, width_inches=6.2))

    # --- 4. Spectral Summary Table ---
    story.append(PageBreak())
    story.append(Paragraph("4. Spectral Summary", st["heading"]))
    story.append(_build_spectral_table(ch_names, fs, psd_cache))
    story.append(Spacer(1, 10))

    # Frontal alpha asymmetry
    if "F3" in ch_names and "F4" in ch_names:
        f3i, f4i = ch_names.index("F3"), ch_names.index("F4")
        f_, psd3 = psd_cache[f3i]
        _, psd4 = psd_cache[f4i]
        a_mask = (f_ >= 8) & (f_ <= 13)
        if a_mask.any():
            faa = np.log(np.mean(psd4[a_mask])) - np.log(np.mean(psd3[a_mask]))
            interp = "right > left (approach)" if faa > 0 else "left > right (withdrawal)"
            story.append(Paragraph(
                f"<b>Frontal Alpha Asymmetry</b> (ln F4 − ln F3): {faa:.4f} → {interp}",
                st["body"],
            ))

    # --- 5. Per-Channel Statistics ---
    story.append(Spacer(1, 14))
    story.append(Paragraph("5. Per-Channel Statistics", st["heading"]))
    story.append(_build_stats_table(eeg_win, ch_names))

    def _on_page(canvas, doc):
        _header_footer(canvas, doc, "EEG Analysis Report", gen_ts, filename)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return output_path


# ---------------------------------------------------------------------------
# Analysis report plot helpers (optimized: accept psd_cache)
# ---------------------------------------------------------------------------

def _plot_raw_traces(eeg_uV, triggers, ch_names, fs, t_offset=0.0):
    n_samples, n_ch = eeg_uV.shape
    time = t_offset + np.arange(n_samples) / fs

    fig, ax = plt.subplots(figsize=(10, max(3, n_ch * 0.5)))
    spacing = np.max(np.std(eeg_uV, axis=0)) * 5
    offsets = np.arange(n_ch) * spacing

    for i, ch in enumerate(ch_names):
        ax.plot(time, eeg_uV[:, i] + offsets[i], linewidth=0.5, color="#2c3e50")
        ax.text(time[0] - (time[-1] - time[0]) * 0.02, offsets[i], ch,
                fontsize=8, va="center", ha="right", fontweight="bold", color="#2c3e50")

    for idx in np.where(triggers > 0)[0]:
        t = t_offset + idx / fs
        code = triggers[idx]
        label = TRIGGER_MAP.get(code, f"T{code}")
        color = "#e74c3c" if code == 1 else "#2980b9"
        ax.axvline(t, color=color, alpha=0.6, linestyle="--", linewidth=0.8)
        ax.text(t + 0.05, offsets[-1] + spacing * 0.5, label,
                color=color, fontsize=7, fontweight="bold")

    ax.set_xlabel("Time (s)", fontsize=9)
    ax.set_yticks([])
    ax.set_xlim(time[0], time[-1])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    plt.tight_layout()
    return fig


def _plot_spectral_panels(eeg_uV, ch_names, fs, psd_cache):
    n_ch = eeg_uV.shape[1]
    fig, (ax_psd, ax_hm) = plt.subplots(1, 2, figsize=(11, 4),
                                         gridspec_kw={"width_ratios": [1.2, 1]})

    cmap_colors = plt.cm.viridis(np.linspace(0.15, 0.85, n_ch))
    for i, ch in enumerate(ch_names):
        f, psd = psd_cache[i]
        mask = (f >= 1) & (f <= 45)
        ax_psd.semilogy(f[mask], psd[mask], label=ch, color=cmap_colors[i], linewidth=1.0)

    for sym, ((lo, hi), col) in BAND_SHADING.items():
        ax_psd.axvspan(lo, hi, alpha=0.2, color=col)
        ylim = ax_psd.get_ylim()
        ax_psd.text((lo + hi) / 2, ylim[1] * 0.3, sym, ha="center", fontsize=9, alpha=0.5)

    ax_psd.set_xlabel("Frequency (Hz)", fontsize=9)
    ax_psd.set_ylabel("PSD (µV²/Hz)", fontsize=9)
    ax_psd.set_title("Power Spectral Density", fontsize=10, fontweight="bold", color="#2c3e50")
    ax_psd.legend(fontsize=6, ncol=max(1, n_ch // 4), loc="upper right")
    ax_psd.set_xlim(1, 45)
    ax_psd.spines["top"].set_visible(False)
    ax_psd.spines["right"].set_visible(False)

    # Band power heatmap
    bp_matrix = np.zeros((n_ch, len(BANDS)))
    for i in range(n_ch):
        f, psd = psd_cache[i]
        for j, (bname, (lo, hi)) in enumerate(BANDS.items()):
            m = (f >= lo) & (f <= hi)
            bp_matrix[i, j] = np.log10(np.mean(psd[m]) + 1e-10) if m.any() else -10

    im = ax_hm.imshow(bp_matrix, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax_hm.set_xticks(range(len(BANDS)))
    ax_hm.set_xticklabels(list(BANDS.keys()), fontsize=8)
    ax_hm.set_yticks(range(n_ch))
    ax_hm.set_yticklabels(ch_names, fontsize=8)
    ax_hm.set_title("log₁₀ Band Power", fontsize=10, fontweight="bold", color="#2c3e50")
    plt.colorbar(im, ax=ax_hm, shrink=0.8, pad=0.02)

    plt.tight_layout()
    return fig


def _plot_alpha_panels(eeg_uV, triggers, ch_names, fs, psd_cache):
    n_ch = eeg_uV.shape[1]
    fig, (ax_react, ax_ratio) = plt.subplots(1, 2, figsize=(11, 3.5))

    eo_indices = np.where(triggers == 1)[0]
    ec_indices = np.where(triggers == 2)[0]
    seg_len = int(2 * fs)

    if len(eo_indices) > 0 and len(ec_indices) > 0:
        eo_start = eo_indices[0]
        ec_start = ec_indices[0]
        eo_alpha, ec_alpha = [], []

        for i in range(n_ch):
            f_eo, psd_eo = signal.welch(
                eeg_uV[eo_start:eo_start + seg_len, i], fs=fs, nperseg=min(512, seg_len))
            f_ec, psd_ec = signal.welch(
                eeg_uV[ec_start:ec_start + seg_len, i], fs=fs, nperseg=min(512, seg_len))
            m_eo = (f_eo >= 8) & (f_eo <= 13)
            m_ec = (f_ec >= 8) & (f_ec <= 13)
            eo_alpha.append(np.mean(psd_eo[m_eo]) if m_eo.any() else 0)
            ec_alpha.append(np.mean(psd_ec[m_ec]) if m_ec.any() else 0)

        x = np.arange(n_ch)
        w = 0.35
        ax_react.bar(x - w/2, eo_alpha, w, label="Eyes Open", color="#e74c3c", alpha=0.8)
        ax_react.bar(x + w/2, ec_alpha, w, label="Eyes Closed", color="#2980b9", alpha=0.8)
        ax_react.set_xticks(x)
        ax_react.set_xticklabels(ch_names, fontsize=8)
        ax_react.set_ylabel("Alpha Power (µV²/Hz)", fontsize=9)
        ax_react.legend(fontsize=7)
    else:
        ax_react.text(0.5, 0.5, "No EO/EC triggers found", ha="center", va="center",
                      transform=ax_react.transAxes, fontsize=10, color="#999999")

    ax_react.set_title("Alpha Reactivity: EO vs EC", fontsize=10, fontweight="bold",
                       color="#2c3e50")
    ax_react.spines["top"].set_visible(False)
    ax_react.spines["right"].set_visible(False)

    # Alpha/Theta ratio from cached PSDs
    atr = []
    for i in range(n_ch):
        f, psd = psd_cache[i]
        alpha_m = (f >= 8) & (f <= 13)
        theta_m = (f >= 4) & (f <= 8)
        alpha_p = np.mean(psd[alpha_m]) if alpha_m.any() else 0
        theta_p = np.mean(psd[theta_m]) if theta_m.any() else 0
        atr.append(alpha_p / max(theta_p, 1e-10))

    bar_colors = [_NE_PASS_GREEN if r > 1 else "#e67e22" for r in atr]
    ax_ratio.bar(ch_names, atr, color=bar_colors, alpha=0.85)
    ax_ratio.axhline(1.0, color="#999999", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_ratio.set_ylabel("Alpha / Theta Ratio", fontsize=9)
    ax_ratio.set_title("Alpha/Theta Ratio", fontsize=10, fontweight="bold", color="#2c3e50")
    ax_ratio.spines["top"].set_visible(False)
    ax_ratio.spines["right"].set_visible(False)

    plt.tight_layout()
    return fig


def _build_spectral_table(ch_names, fs, psd_cache) -> Table:
    """Build per-channel spectral summary table using cached PSDs."""
    header = ["Channel"] + list(BANDS.keys()) + ["α/θ", "Peak α (Hz)"]
    data = [header]

    for i, ch in enumerate(ch_names):
        f, psd = psd_cache[i]
        row = [ch]
        for bname, (lo, hi) in BANDS.items():
            m = (f >= lo) & (f <= hi)
            row.append(f"{np.mean(psd[m]):.3f}" if m.any() else "—")

        alpha_m = (f >= 8) & (f <= 13)
        theta_m = (f >= 4) & (f <= 8)
        alpha_p = np.mean(psd[alpha_m]) if alpha_m.any() else 0
        theta_p = np.mean(psd[theta_m]) if theta_m.any() else 0
        row.append(f"{alpha_p / max(theta_p, 1e-10):.2f}")

        if alpha_m.any():
            peak = f[alpha_m][np.argmax(psd[alpha_m])]
            row.append(f"{peak:.1f}")
        else:
            row.append("—")

        data.append(row)

    n_cols = len(header)
    avail = PAGE_W - 1.5 * inch
    col_w = [avail * 0.12] + [avail * 0.11] * (n_cols - 1)
    return _ne_table(data, col_w)


def _build_stats_table(eeg_uV, ch_names) -> Table:
    """Build per-channel descriptive statistics table."""
    header = ["Channel", "Mean (µV)", "Std (µV)", "Min (µV)", "Max (µV)", "Pk-Pk (µV)"]
    data = [header]
    for i, ch in enumerate(ch_names):
        d = eeg_uV[:, i]
        data.append([
            ch,
            f"{np.mean(d):.1f}", f"{np.std(d):.1f}",
            f"{np.min(d):.1f}", f"{np.max(d):.1f}", f"{np.ptp(d):.1f}",
        ])

    avail = PAGE_W - 1.5 * inch
    col_w = [avail * 0.15] + [avail * 0.17] * 5
    return _ne_table(data, col_w)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_electrodes(file_path: str, n_ch: int) -> list[str]:
    info_path = file_path.replace(".easy.gz", ".info").replace(".easy", ".info")
    electrodes = []
    if os.path.isfile(info_path):
        with open(info_path) as f:
            for line in f:
                if "Channel " in line.rstrip():
                    electrodes.append(line.split()[-1])
    if not electrodes:
        electrodes = [f"Ch{i+1}" for i in range(n_ch)]
    return electrodes[:n_ch]


def _parse_device(file_path: str) -> str:
    info_path = file_path.replace(".easy.gz", ".info").replace(".easy", ".info")
    if os.path.isfile(info_path):
        with open(info_path) as f:
            for line in f:
                if "Device class:" in line:
                    return line.split(":", 1)[1].strip()
    return "Unknown device"


def _load_easy_raw(filepath: str):
    """Load .easy file returning raw arrays (for analysis report)."""
    import pandas as pd
    df = pd.read_csv(filepath, sep="\t", header=None)
    data = df.values
    n_cols = data.shape[1]

    info_path = Path(filepath).with_suffix(".info")
    ch_names = []
    if info_path.exists():
        with open(info_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("Channel") and ":" in line:
                    ch_names.append(line.split(":")[1].strip())

    if not ch_names:
        n_eeg = n_cols - 5
        ch_names = [f"Ch{i+1}" for i in range(n_eeg)]

    n_eeg = len(ch_names)
    eeg_uV = data[:, :n_eeg].astype(float) / 1000.0
    triggers = data[:, n_eeg + 3].astype(int)
    timestamps = data[:, n_eeg + 4]
    return eeg_uV, triggers, timestamps, ch_names
