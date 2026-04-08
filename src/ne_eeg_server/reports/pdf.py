"""
PDF report generators for EEG QC and EEG Analysis reports.

Style matches Neuroelectrics branded documents: dark header bar,
black titles, teal subtitles, justified body text, clean tables
with teal headers and generous whitespace.

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
    HRFlowable,
)

from ne_eeg_server.analysis.analyzer import EasyAnalyzer
from ne_eeg_server.analysis.metrics_defaults import DEFAULT_EVENT_THRESHOLD_UV

# ---------------------------------------------------------------------------
# Paths & brand colors
# ---------------------------------------------------------------------------
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo-NE.png")

_DARK_NAV = "#2C3E50"       # header bar, section headings
_TEAL = "#00A5B5"           # subtitles, accents, table headers
_TEAL_MUTED = "#7FB5BE"     # header bar second line
_LIGHT_GRAY = "#F7F8F9"     # table alt rows
_TEXT = "#333333"            # body text
_GRAY = "#888888"            # footer, small text
_PASS = "#27ae60"
_FAIL = "#e74c3c"

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 1.5 * inch  # usable width with margins


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _styles():
    s = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "T", parent=s["Heading1"], fontSize=24, leading=30,
            textColor=colors.HexColor(_DARK_NAV), spaceAfter=4, spaceBefore=0,
            fontName="Helvetica-Bold", alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ST", parent=s["Normal"], fontSize=12, leading=16,
            textColor=colors.HexColor(_TEAL), spaceAfter=8,
            fontName="Helvetica", alignment=TA_LEFT,
        ),
        "heading": ParagraphStyle(
            "H", parent=s["Heading2"], fontSize=16, leading=22,
            textColor=colors.HexColor(_DARK_NAV), spaceAfter=10, spaceBefore=24,
            fontName="Helvetica-Bold", alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "B", parent=s["Normal"], fontSize=10, leading=14, spaceAfter=8,
            textColor=colors.HexColor(_TEXT), alignment=TA_JUSTIFY,
        ),
        "meta": ParagraphStyle(
            "M", parent=s["Normal"], fontSize=9.5, leading=14, spaceAfter=2,
            textColor=colors.HexColor(_TEXT), alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "SM", parent=s["Normal"], fontSize=8, leading=11,
            textColor=colors.HexColor(_GRAY),
        ),
    }


# ---------------------------------------------------------------------------
# Header bar & footer (matching NE strategy memo)
# ---------------------------------------------------------------------------

def _header_footer(canvas, doc, report_type: str, date_str: str, filename: str):
    canvas.saveState()
    w, h = PAGE_W, PAGE_H
    left, right = doc.leftMargin, w - doc.rightMargin

    # --- Dark header bar ---
    bar_h = 0.5 * inch
    canvas.setFillColor(colors.HexColor(_DARK_NAV))
    canvas.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)

    # "NEUROELECTRICS" — white, bold
    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(colors.white)
    canvas.drawString(left, h - 0.28 * inch, "NEUROELECTRICS")

    # Report type — muted teal, smaller
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor(_TEAL_MUTED))
    canvas.drawString(left, h - 0.42 * inch, report_type.upper())

    # Date — white, right-aligned
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.white)
    canvas.drawRightString(right, h - 0.28 * inch, date_str)

    # Thin teal accent line below bar
    canvas.setStrokeColor(colors.HexColor(_TEAL))
    canvas.setLineWidth(2)
    canvas.line(0, h - bar_h, w, h - bar_h)

    # --- Footer ---
    fy = 0.35 * inch
    canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
    canvas.setLineWidth(0.5)
    canvas.line(left, fy + 10, right, fy + 10)

    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.HexColor(_GRAY))
    canvas.drawString(left, fy, f"Neuroelectrics  \u2022  {filename}")
    canvas.drawRightString(right, fy, f"Page {doc.page}")

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Figure helper — true aspect ratio from saved PNG
# ---------------------------------------------------------------------------

def _fig_to_image(fig, width_inches=6.0, dpi=150) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    from PIL import Image as PILImage
    px_w, px_h = PILImage.open(buf).size
    buf.seek(0)
    return Image(buf, width=width_inches * inch, height=width_inches * (px_h / px_w) * inch)


def _img_from_path(path: str, width_inches: float = 6.0) -> Image:
    from PIL import Image as PILImage
    px_w, px_h = PILImage.open(path).size
    return Image(path, width=width_inches * inch, height=width_inches * (px_h / px_w) * inch)


def _teal_hr():
    return HRFlowable(
        width="100%", thickness=1.5, color=colors.HexColor(_TEAL),
        spaceBefore=8, spaceAfter=12,
    )


# ---------------------------------------------------------------------------
# Table helper — teal header, left-aligned body, generous padding
# ---------------------------------------------------------------------------

def _ne_table(data, col_widths):
    table = Table(data, colWidths=col_widths)
    n_rows = len(data)
    cmds = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_TEAL)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(_TEXT)),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),   # first col left
        ("ALIGN", (1, 0), (-1, -1), "CENTER"), # rest centered
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        # Lines
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor(_TEAL)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
    ]
    # Subtle row separators + alternating background
    for i in range(1, n_rows):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(_LIGHT_GRAY)))
        if i < n_rows - 1:
            cmds.append(("LINEBELOW", (0, i), (-1, i), 0.25, colors.HexColor("#E0E0E0")))

    table.setStyle(TableStyle(cmds))
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
    analyzer = EasyAnalyzer(file_path)
    fs = analyzer.fs
    total_dur = analyzer.get_file_duration()
    n_ch = analyzer.num_channels

    if duration_s is None:
        duration_s = total_dur - start_time_s

    electrodes = _parse_electrodes(file_path, n_ch)
    device = _parse_device(file_path)

    results = analyzer.process_window(start_time_s, duration_s)
    qc_metrics = analyzer.calculate_channel_metrics(
        window_start_s=start_time_s, window_duration_s=duration_s,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        plot_paths = analyzer.generate_plots(results, tmpdir, "qc")

        date_str = datetime.now().strftime("%B %Y")
        filename = os.path.basename(file_path)
        if output_path is None:
            output_path = file_path.replace(".easy", "_qc_report.pdf")

        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            topMargin=0.75 * inch, bottomMargin=0.6 * inch,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        )
        st = _styles()
        story = []

        # --- Title block (no logo in body — it lives in the header bar) ---
        story.append(Spacer(1, 30))
        story.append(Paragraph("EEG Signal Quality Report", st["title"]))
        story.append(Paragraph(
            "Automated per-channel quality assessment with PASS/FAIL thresholds",
            st["subtitle"],
        ))
        story.append(_teal_hr())

        # Metadata
        story.append(Paragraph(f"FILE: {filename}", st["meta"]))
        story.append(Paragraph(f"DEVICE: {device}", st["meta"]))
        story.append(Paragraph(
            f"CHANNELS: {n_ch} &nbsp;&nbsp;&nbsp; SAMPLING RATE: {int(fs)} Hz",
            st["meta"]))
        story.append(Paragraph(
            f"DURATION: {total_dur:.1f} s &nbsp;&nbsp;&nbsp; "
            f"WINDOW: {start_time_s:.1f} – {start_time_s + duration_s:.1f} s",
            st["meta"]))
        story.append(Paragraph(
            f"DATE: {datetime.now().strftime('%B %d, %Y')}", st["meta"]))
        story.append(_teal_hr())

        # QC summary
        total_pass = sum(1 for m in qc_metrics.values() if m.get("pass", False))
        total_ch = len(qc_metrics)
        if total_pass == total_ch:
            qc_text = (f'<font color="{_PASS}"><b>ALL {total_ch} CHANNELS PASS</b></font>')
        else:
            qc_text = (
                f'<font color="{_FAIL}"><b>{total_ch - total_pass} of {total_ch} '
                f'channels FAIL</b></font> &nbsp;({total_pass} pass)')
        story.append(Paragraph(qc_text, st["body"]))
        story.append(Spacer(1, 16))

        # --- 1. Metrics table ---
        story.append(Paragraph("1. Per-Channel Metrics", st["heading"]))
        story.append(_build_qc_table(qc_metrics, electrodes))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"* = exceeds threshold. RMS in µV. Line power in dB. "
            f"Event threshold: {DEFAULT_EVENT_THRESHOLD_UV:.1f} µV.",
            st["small"],
        ))

        # --- 2. PSD plots ---
        for key in sorted(plot_paths.keys()):
            if "psd" in key:
                story.append(PageBreak())
                page_label = key.replace("psd_", "").replace("psd", "Channels 1–8")
                story.append(Paragraph(
                    f"2. Power Spectral Density — {page_label}", st["heading"]))
                story.append(Spacer(1, 6))
                story.append(_img_from_path(plot_paths[key], width_inches=6.0))

        # --- 3+ Time-series plots ---
        sec = 3
        for key in sorted(plot_paths.keys()):
            if "raw" in key or "filtered" in key:
                story.append(PageBreak())
                label = key.replace("_", " ").replace("page", "— page").title()
                story.append(Paragraph(f"{sec}. {label}", st["heading"]))
                story.append(Spacer(1, 6))
                story.append(_img_from_path(plot_paths[key], width_inches=6.0))
                sec += 1

        def on_page(canvas, doc):
            _header_footer(canvas, doc, "EEG Signal Quality Report", date_str, filename)

        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

    return output_path


def _build_qc_table(qc_metrics: dict, electrodes: list[str]) -> Table:
    header = ["Channel", "Mean\n(µV)", "RMS raw\n(µV)", "RMS notch\n(µV)",
              "RMS filt\n(µV)", "Line\n50/60 (dB)", "Kurtosis", "Events\n(/s)", "Result"]

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

    cw = CONTENT_W / 9
    col_widths = [cw * 1.1] + [cw] * 7 + [cw * 0.9]
    table = Table(data, colWidths=col_widths)

    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_TEAL)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(_TEXT)),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor(_TEAL)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
    ]

    for row_i, ch_idx in enumerate(sorted(qc_metrics.keys()), start=1):
        passed = qc_metrics[ch_idx].get("pass", True)
        # Row separators
        if row_i < len(qc_metrics):
            cmds.append(("LINEBELOW", (0, row_i), (-1, row_i), 0.25,
                          colors.HexColor("#E0E0E0")))
        # PASS/FAIL styling
        if passed:
            cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i),
                          colors.HexColor(_PASS)))
        else:
            cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i),
                          colors.HexColor(_FAIL)))
        cmds.append(("FONTNAME", (-1, row_i), (-1, row_i), "Helvetica-Bold"))

    table.setStyle(TableStyle(cmds))
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
    eeg_uV, triggers, timestamps, ch_names = _load_easy_raw(file_path)
    n_samples, n_ch = eeg_uV.shape
    fs = 500
    total_dur = n_samples / fs

    if duration_s is None:
        duration_s = total_dur - start_time_s

    s0 = int(start_time_s * fs)
    s1 = min(s0 + int(duration_s * fs), n_samples)
    eeg_win = eeg_uV[s0:s1]
    trig_win = triggers[s0:s1]

    if output_path is None:
        output_path = file_path.replace(".easy", "_analysis_report.pdf")

    date_str = datetime.now().strftime("%B %Y")
    filename = os.path.basename(file_path)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=0.75 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    st = _styles()
    story = []

    # Pre-compute all PSDs once
    nperseg = min(1024, len(eeg_win))
    psd_cache = {}
    for i in range(n_ch):
        f, psd = signal.welch(eeg_win[:, i], fs=fs, nperseg=nperseg)
        psd_cache[i] = (f, psd)

    # --- Title block ---
    story.append(Spacer(1, 30))
    story.append(Paragraph("EEG Analysis Report", st["title"]))
    story.append(Paragraph(
        "Spectral analysis, band powers, and functional EEG features",
        st["subtitle"],
    ))
    story.append(_teal_hr())

    device = _parse_device(file_path)
    story.append(Paragraph(f"FILE: {filename}", st["meta"]))
    story.append(Paragraph(
        f"DEVICE: {device} &nbsp;&nbsp;&nbsp; CHANNELS: {n_ch} &nbsp;&nbsp;&nbsp; "
        f"SAMPLING RATE: {fs} Hz", st["meta"]))
    story.append(Paragraph(
        f"DURATION: {total_dur:.1f} s &nbsp;&nbsp;&nbsp; "
        f"WINDOW: {start_time_s:.1f} – {start_time_s + duration_s:.1f} s",
        st["meta"]))
    story.append(Paragraph(
        f"DATE: {datetime.now().strftime('%B %d, %Y')}", st["meta"]))
    story.append(_teal_hr())

    # --- 1. Raw EEG traces ---
    story.append(Paragraph("1. Raw EEG Traces", st["heading"]))
    fig_traces = _plot_raw_traces(eeg_win, trig_win, ch_names, fs, start_time_s)
    story.append(_fig_to_image(fig_traces, width_inches=6.0))

    trig_indices = np.where(trig_win > 0)[0]
    if len(trig_indices) > 0:
        trig_text = ", ".join(
            f"{TRIGGER_MAP.get(trig_win[i], f'T{trig_win[i]}')} @ "
            f"{start_time_s + i/fs:.2f}s"
            for i in trig_indices[:20])
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Markers: {trig_text}", st["small"]))

    # --- 2. Spectral Analysis ---
    story.append(PageBreak())
    story.append(Paragraph("2. Spectral Analysis", st["heading"]))
    fig_spectral = _plot_spectral_panels(eeg_win, ch_names, fs, psd_cache)
    story.append(_fig_to_image(fig_spectral, width_inches=6.0))
    story.append(Spacer(1, 14))

    # --- 3. Alpha Analysis ---
    story.append(Paragraph("3. Alpha Analysis", st["heading"]))
    fig_alpha = _plot_alpha_panels(eeg_win, trig_win, ch_names, fs, psd_cache)
    story.append(_fig_to_image(fig_alpha, width_inches=6.0))

    # --- 4. Spectral Summary ---
    story.append(PageBreak())
    story.append(Paragraph("4. Spectral Summary", st["heading"]))
    story.append(_build_spectral_table(ch_names, psd_cache))
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
                f"Frontal Alpha Asymmetry (ln F4 − ln F3): "
                f"<b>{faa:.4f}</b> → {interp}", st["body"]))

    # --- 5. Per-Channel Statistics ---
    story.append(Spacer(1, 16))
    story.append(Paragraph("5. Per-Channel Statistics", st["heading"]))
    story.append(_build_stats_table(eeg_win, ch_names))

    def on_page(canvas, doc):
        _header_footer(canvas, doc, "EEG Analysis Report", date_str, filename)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return output_path


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _plot_raw_traces(eeg_uV, triggers, ch_names, fs, t_offset=0.0):
    n_samples, n_ch = eeg_uV.shape
    time = t_offset + np.arange(n_samples) / fs

    fig, ax = plt.subplots(figsize=(10, max(3, n_ch * 0.5)))
    spacing = np.max(np.std(eeg_uV, axis=0)) * 5
    offsets = np.arange(n_ch) * spacing

    for i, ch in enumerate(ch_names):
        ax.plot(time, eeg_uV[:, i] + offsets[i], linewidth=0.5, color=_DARK_NAV)
        ax.text(time[0] - (time[-1] - time[0]) * 0.02, offsets[i], ch,
                fontsize=8, va="center", ha="right", fontweight="bold", color=_DARK_NAV)

    for idx in np.where(triggers > 0)[0]:
        t = t_offset + idx / fs
        code = triggers[idx]
        label = TRIGGER_MAP.get(code, f"T{code}")
        clr = "#e74c3c" if code == 1 else "#2980b9"
        ax.axvline(t, color=clr, alpha=0.6, linestyle="--", linewidth=0.8)
        ax.text(t + 0.05, offsets[-1] + spacing * 0.5, label,
                color=clr, fontsize=7, fontweight="bold")

    ax.set_xlabel("Time (s)", fontsize=9)
    ax.set_yticks([])
    ax.set_xlim(time[0], time[-1])
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
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
    ax_psd.set_title("Power Spectral Density", fontsize=10, fontweight="bold", color=_DARK_NAV)
    ax_psd.legend(fontsize=6, ncol=max(1, n_ch // 4), loc="upper right")
    ax_psd.set_xlim(1, 45)
    ax_psd.spines["top"].set_visible(False)
    ax_psd.spines["right"].set_visible(False)

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
    ax_hm.set_title("log₁₀ Band Power", fontsize=10, fontweight="bold", color=_DARK_NAV)
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
                       color=_DARK_NAV)
    ax_react.spines["top"].set_visible(False)
    ax_react.spines["right"].set_visible(False)

    atr = []
    for i in range(n_ch):
        f, psd = psd_cache[i]
        alpha_m = (f >= 8) & (f <= 13)
        theta_m = (f >= 4) & (f <= 8)
        alpha_p = np.mean(psd[alpha_m]) if alpha_m.any() else 0
        theta_p = np.mean(psd[theta_m]) if theta_m.any() else 0
        atr.append(alpha_p / max(theta_p, 1e-10))

    bar_colors = [_PASS if r > 1 else "#e67e22" for r in atr]
    ax_ratio.bar(ch_names, atr, color=bar_colors, alpha=0.85)
    ax_ratio.axhline(1.0, color="#999999", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_ratio.set_ylabel("Alpha / Theta Ratio", fontsize=9)
    ax_ratio.set_title("Alpha/Theta Ratio", fontsize=10, fontweight="bold", color=_DARK_NAV)
    ax_ratio.spines["top"].set_visible(False)
    ax_ratio.spines["right"].set_visible(False)

    plt.tight_layout()
    return fig


def _build_spectral_table(ch_names, psd_cache) -> Table:
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
            row.append(f"{f[alpha_m][np.argmax(psd[alpha_m])]:.1f}")
        else:
            row.append("—")
        data.append(row)

    cw = CONTENT_W / len(header)
    col_widths = [cw * 1.2] + [cw] * (len(header) - 1)
    return _ne_table(data, col_widths)


def _build_stats_table(eeg_uV, ch_names) -> Table:
    header = ["Channel", "Mean (µV)", "Std (µV)", "Min (µV)", "Max (µV)", "Pk-Pk (µV)"]
    data = [header]
    for i, ch in enumerate(ch_names):
        d = eeg_uV[:, i]
        data.append([ch, f"{np.mean(d):.1f}", f"{np.std(d):.1f}",
                      f"{np.min(d):.1f}", f"{np.max(d):.1f}", f"{np.ptp(d):.1f}"])

    cw = CONTENT_W / 6
    col_widths = [cw * 1.2] + [cw] * 5
    return _ne_table(data, col_widths)


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
