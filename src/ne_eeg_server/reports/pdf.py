"""
PDF report generators for EEG QC and EEG Analysis reports.

Style matches Neuroelectrics branded documents: dark header bar,
black titles, teal subtitles, justified body text, clean tables
with muted teal-blue headers and generous whitespace.

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
# Paths & brand colors (matched to NE strategy memo)
# ---------------------------------------------------------------------------
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo-NE.png")

_DARK_NAV = "#2C3E50"       # header bar, section headings
_TABLE_HEAD = "#3A7D8C"     # table header — muted dark teal-blue (from reference)
_TEAL = "#00A5B5"           # subtitles, accents
_TEAL_MUTED = "#7FB5BE"     # header bar second line
_LIGHT_GRAY = "#F7F8F9"     # table alt rows
_TEXT = "#333333"            # body text
_GRAY = "#888888"           # footer, small text
_PASS = "#27ae60"
_FAIL = "#e74c3c"

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 1.5 * inch

# Raw EEG preview: show at most this many seconds in the traces plot
_RAW_PREVIEW_MAX_S = 10.0


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
        "caption": ParagraphStyle(
            "CAP", parent=s["Normal"], fontSize=8, leading=11,
            textColor=colors.HexColor(_GRAY), alignment=TA_LEFT,
            spaceBefore=4, spaceAfter=8, fontName="Helvetica-Oblique",
        ),
    }


# ---------------------------------------------------------------------------
# Header bar & footer
# ---------------------------------------------------------------------------

def _header_footer(canvas, doc, report_type: str, date_str: str, filename: str):
    canvas.saveState()
    w, h = PAGE_W, PAGE_H
    left, right = doc.leftMargin, w - doc.rightMargin

    bar_h = 0.5 * inch
    canvas.setFillColor(colors.HexColor(_DARK_NAV))
    canvas.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)

    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(colors.white)
    canvas.drawString(left, h - 0.28 * inch, "NEUROELECTRICS")

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor(_TEAL_MUTED))
    canvas.drawString(left, h - 0.42 * inch, report_type.upper())

    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.white)
    canvas.drawRightString(right, h - 0.28 * inch, date_str)

    canvas.setStrokeColor(colors.HexColor(_TEAL))
    canvas.setLineWidth(2)
    canvas.line(0, h - bar_h, w, h - bar_h)

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
# Figure / image helpers
# ---------------------------------------------------------------------------

def _fig_to_image(fig, width_inches=6.0, dpi=150, max_height_inches=8.5) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    from PIL import Image as PILImage
    px_w, px_h = PILImage.open(buf).size
    buf.seek(0)
    aspect = px_h / px_w
    img_h = width_inches * aspect
    if img_h > max_height_inches:
        img_h = max_height_inches
        width_inches = max_height_inches / aspect
    return Image(buf, width=width_inches * inch, height=img_h * inch)


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
# Table helper — muted teal-blue header (matching reference PDF)
# ---------------------------------------------------------------------------

def _ne_table(data, col_widths):
    table = Table(data, colWidths=col_widths)
    n_rows = len(data)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_TABLE_HEAD)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(_TEXT)),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor(_TABLE_HEAD)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
    ]
    for i in range(1, n_rows):
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
    original_file_path: Optional[str] = None,
) -> str:
    analyzer = EasyAnalyzer(file_path)
    fs = analyzer.fs
    total_dur = analyzer.get_file_duration()
    n_ch = analyzer.num_channels

    if duration_s is None:
        duration_s = total_dur - start_time_s

    meta = _get_recording_meta(file_path, original_file_path)
    electrodes = meta.get("electrodes", [])
    if not electrodes:
        electrodes = [f"Ch{i+1}" for i in range(n_ch)]
    electrodes = electrodes[:n_ch]

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

        # Title block
        story.append(Spacer(1, 30))
        story.append(Paragraph("EEG Signal Quality Report", st["title"]))
        story.append(Paragraph(
            "Automated per-channel quality assessment with PASS/FAIL thresholds",
            st["subtitle"]))
        story.append(_teal_hr())

        win_dur = duration_s
        story.extend(_build_meta_block(
            meta, st, filename, n_ch, fs, total_dur,
            start_time_s, duration_s, win_dur))
        story.append(_teal_hr())

        total_pass = sum(1 for m in qc_metrics.values() if m.get("pass", False))
        total_ch = len(qc_metrics)
        if total_pass == total_ch:
            qc_text = f'<font color="{_PASS}"><b>ALL {total_ch} CHANNELS PASS</b></font>'
        else:
            qc_text = (
                f'<font color="{_FAIL}"><b>{total_ch - total_pass} of {total_ch} '
                f'channels FAIL</b></font> &nbsp;({total_pass} pass)')
        story.append(Paragraph(qc_text, st["body"]))
        story.append(Spacer(1, 16))

        # 1. Metrics table
        story.append(Paragraph("1. Per-Channel Metrics", st["heading"]))
        story.append(_build_qc_table(qc_metrics, electrodes))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"* = exceeds threshold. RMS in µV. Line power in dB. "
            f"Event threshold: {DEFAULT_EVENT_THRESHOLD_UV:.1f} µV.",
            st["small"]))

        # 2. PSD plots
        for key in sorted(plot_paths.keys()):
            if "psd" in key:
                story.append(PageBreak())
                page_label = key.replace("psd_", "").replace("psd", "Channels 1–8")
                story.append(Paragraph(
                    f"2. Power Spectral Density — {page_label}", st["heading"]))
                story.append(Spacer(1, 6))
                story.append(_img_from_path(plot_paths[key], width_inches=6.0))

        # 3+ Time-series plots
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
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_TABLE_HEAD)),
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
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor(_TABLE_HEAD)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
    ]
    for row_i, ch_idx in enumerate(sorted(qc_metrics.keys()), start=1):
        passed = qc_metrics[ch_idx].get("pass", True)
        if row_i < len(qc_metrics):
            cmds.append(("LINEBELOW", (0, row_i), (-1, row_i), 0.25,
                          colors.HexColor("#E0E0E0")))
        if passed:
            cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i), colors.HexColor(_PASS)))
        else:
            cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i), colors.HexColor(_FAIL)))
        cmds.append(("FONTNAME", (-1, row_i), (-1, row_i), "Helvetica-Bold"))

    table.setStyle(TableStyle(cmds))
    return table


# ===========================================================================
# EEG Analysis Report (redesigned for 8/20/32 channel recordings)
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
    original_file_path: Optional[str] = None,
) -> str:
    meta = _get_recording_meta(file_path, original_file_path)
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
    win_dur = (s1 - s0) / fs

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

    # Pre-compute all PSDs once over the FULL analysis window
    nperseg = min(1024, len(eeg_win))
    psd_cache = {}
    for i in range(n_ch):
        f, psd = signal.welch(eeg_win[:, i], fs=fs, nperseg=nperseg)
        psd_cache[i] = (f, psd)

    # ======= PAGE 1: Title + metadata + recording overview =======
    story.append(Spacer(1, 30))
    story.append(Paragraph("EEG Analysis Report", st["title"]))
    story.append(Paragraph(
        "Spectral analysis, band powers, and functional EEG features",
        st["subtitle"]))
    story.append(_teal_hr())

    # Use electrode labels from metadata if available (preserves original NEDF order)
    if meta.get("electrodes") and len(meta["electrodes"]) == n_ch:
        ch_names = meta["electrodes"]

    story.extend(_build_meta_block(
        meta, st, filename, n_ch, fs, total_dur,
        start_time_s, duration_s, win_dur))
    story.append(_teal_hr())

    # 1. Raw EEG Preview (limited to _RAW_PREVIEW_MAX_S for readability)
    preview_dur = min(win_dur, _RAW_PREVIEW_MAX_S)
    preview_end = s0 + int(preview_dur * fs)
    eeg_preview = eeg_uV[s0:preview_end]
    trig_preview = triggers[s0:preview_end]

    if preview_dur < win_dur:
        preview_label = f"1. Raw EEG Preview (first {preview_dur:.0f} s of {win_dur:.0f} s analysis window)"
    else:
        preview_label = "1. Raw EEG Traces"
    story.append(Paragraph(preview_label, st["heading"]))
    fig_traces = _plot_raw_traces(eeg_preview, trig_preview, ch_names, fs, start_time_s)

    # Build caption with markers and note combined to avoid orphaned text
    trig_map = dict(TRIGGER_MAP)
    if meta.get("trigger_labels"):
        trig_map.update(meta["trigger_labels"])

    caption_parts = [
        f"Figure 1: Demeaned EEG traces ({n_ch} channels, {preview_dur:.0f} s). "
        f"Vertical scale bar shows amplitude in µV. Dashed lines mark event triggers."
    ]

    trig_indices = np.where(trig_win > 0)[0]
    if len(trig_indices) > 0:
        trig_text = ", ".join(
            f"{trig_map.get(trig_win[i], f'T{trig_win[i]}')} @ "
            f"{start_time_s + i/fs:.2f}s"
            for i in trig_indices[:20])
        caption_parts.append(f"Markers: {trig_text}.")

    if preview_dur < win_dur:
        caption_parts.append(
            f"Note: trace shows the first {preview_dur:.0f} s for readability; "
            f"all spectral analyses use the full {win_dur:.0f} s window.")

    story.append(_fig_to_image(fig_traces, width_inches=6.0))
    story.append(Paragraph(" ".join(caption_parts), st["caption"]))

    # ======= PSD Grid — paginated, 8 channels per page =======
    channels_all = list(range(n_ch))
    psd_pages = [channels_all[i:i+8] for i in range(0, len(channels_all), 8)]

    for page_idx, page_channels in enumerate(psd_pages):
        story.append(PageBreak())
        ch_start = page_channels[0] + 1
        ch_end = page_channels[-1] + 1
        ch_labels = [ch_names[c] for c in page_channels]
        story.append(Paragraph(
            f"2. Power Spectral Density — Channels {ch_start}–{ch_end} "
            f"({', '.join(ch_labels)})",
            st["heading"]))
        story.append(Paragraph(
            f"Welch's method, {nperseg}-sample segments, computed over "
            f"full {win_dur:.1f} s analysis window.",
            st["small"]))
        story.append(Spacer(1, 6))
        fig_psd = _plot_psd_grid(psd_cache, page_channels, ch_names, fs)
        story.append(_fig_to_image(fig_psd, width_inches=6.0))
        story.append(Paragraph(
            f"Figure 2.{page_idx + 1}: Power spectral density for channels "
            f"{ch_start}–{ch_end}. "
            f"Shaded bands: Delta (1–4 Hz), Theta (4–8 Hz), Alpha (8–13 Hz), Beta (13–30 Hz).",
            st["caption"]))

    # ======= Spectral Overview: band power heatmap =======
    story.append(PageBreak())
    story.append(Paragraph("3. Spectral Overview", st["heading"]))
    story.append(Paragraph(
        f"Figure 3: Band power heatmap across all {n_ch} channels. "
        f"Color scale shows log10(mean PSD) in each standard frequency band "
        f"(Delta 1–4, Theta 4–8, Alpha 8–13, Beta 13–30, Gamma 30–45 Hz), "
        f"computed over the full {win_dur:.1f} s analysis window. "
        f"Warmer colors indicate higher power.",
        st["body"]))
    fig_heatmap = _plot_band_heatmap(ch_names, psd_cache)
    story.append(_fig_to_image(fig_heatmap, width_inches=5.5))

    # ======= Alpha Analysis =======
    story.append(PageBreak())
    story.append(Paragraph("4. Alpha Analysis", st["heading"]))

    # Alpha/theta ratio
    story.append(Paragraph(
        "Alpha/theta power ratio by channel. Ratio > 1 indicates alpha-dominant activity "
        "(green), ratio < 1 indicates theta-dominant (orange). "
        "Posterior alpha dominance is a marker of normal resting-state EEG.",
        st["body"]))
    fig_atr = _plot_alpha_theta_ratio(ch_names, psd_cache)
    story.append(_fig_to_image(fig_atr, width_inches=6.0))
    story.append(Paragraph(
        "Figure 4: Alpha/theta power ratio per channel. "
        "Green bars indicate alpha-dominant channels (ratio > 1); "
        "orange indicates theta-dominant. Dashed line marks ratio = 1.",
        st["caption"]))
    story.append(Spacer(1, 10))

    # Alpha reactivity (EO/EC) — only if markers present
    eo_indices = np.where(trig_win == 1)[0]
    ec_indices = np.where(trig_win == 2)[0]
    if len(eo_indices) > 0 and len(ec_indices) > 0:
        story.append(Paragraph(
            "Alpha reactivity: comparison of alpha-band (8–13 Hz) power during "
            "Eyes Open vs Eyes Closed segments. Healthy subjects typically show "
            "increased posterior alpha during EC (Berger effect).",
            st["body"]))
        fig_react = _plot_alpha_reactivity(eeg_win, trig_win, ch_names, fs)
        story.append(_fig_to_image(fig_react, width_inches=6.0))
        story.append(Paragraph(
            "Figure 5: Alpha-band (8-13 Hz) power comparison between Eyes Open (red) "
            "and Eyes Closed (blue) segments. Increased posterior alpha during EC "
            "is the normal Berger effect.",
            st["caption"]))
    else:
        story.append(Paragraph(
            "<i>No Eyes Open / Eyes Closed markers detected in this recording. "
            "Alpha reactivity analysis requires trigger codes 1 (EO) and 2 (EC).</i>",
            st["small"]))

    # Frontal alpha asymmetry
    if "F3" in ch_names and "F4" in ch_names:
        f3i, f4i = ch_names.index("F3"), ch_names.index("F4")
        f_, psd3 = psd_cache[f3i]
        _, psd4 = psd_cache[f4i]
        a_mask = (f_ >= 8) & (f_ <= 13)
        if a_mask.any():
            faa = np.log(np.mean(psd4[a_mask])) - np.log(np.mean(psd3[a_mask]))
            interp = "right > left (approach tendency)" if faa > 0 else "left > right (withdrawal tendency)"
            story.append(Spacer(1, 10))
            story.append(Paragraph(
                f"<b>Frontal Alpha Asymmetry</b> (ln F4 − ln F3): {faa:.4f} → {interp}. "
                f"Positive values indicate relatively greater left frontal activity.",
                st["body"]))

    # ======= Summary Tables =======
    story.append(PageBreak())
    story.append(Paragraph("5. Spectral Summary", st["heading"]))
    story.append(Paragraph(
        f"Mean PSD (µV²/Hz) per frequency band, alpha/theta ratio, and peak alpha "
        f"frequency for each channel. Computed over the full {win_dur:.1f} s analysis window.",
        st["body"]))
    story.append(_build_spectral_table(ch_names, psd_cache))
    story.append(Spacer(1, 16))

    story.append(Paragraph("6. Per-Channel Statistics", st["heading"]))
    story.append(Paragraph(
        "Descriptive statistics (µV) for each channel over the analysis window.",
        st["body"]))
    story.append(_build_stats_table(eeg_win, ch_names))

    def on_page(canvas, doc):
        _header_footer(canvas, doc, "EEG Analysis Report", date_str, filename)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return output_path


# ---------------------------------------------------------------------------
# Analysis report plot helpers
# ---------------------------------------------------------------------------

def _plot_raw_traces(eeg_uV, triggers, ch_names, fs, t_offset=0.0):
    n_samples, n_ch = eeg_uV.shape
    time = t_offset + np.arange(n_samples) / fs

    # Demean each channel so traces sit on their baseline
    eeg_dm = eeg_uV - np.mean(eeg_uV, axis=0, keepdims=True)

    fig, ax = plt.subplots(figsize=(10, min(max(3, n_ch * 0.5), 10)))
    spacing = np.max(np.std(eeg_dm, axis=0)) * 5
    if spacing == 0:
        spacing = 1.0
    offsets = np.arange(n_ch) * spacing

    for i, ch in enumerate(ch_names):
        ax.plot(time, eeg_dm[:, i] + offsets[i], linewidth=0.5, color=_DARK_NAV)
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

    # Scale bar: draw a vertical bar showing the amplitude scale
    scale_uv = _nice_scale(spacing * 0.8)
    bar_x = time[-1] + (time[-1] - time[0]) * 0.01
    bar_y0 = offsets[0] - spacing * 0.3
    bar_y1 = bar_y0 + scale_uv
    ax.plot([bar_x, bar_x], [bar_y0, bar_y1], color="black", linewidth=1.5, clip_on=False)
    ax.text(bar_x + (time[-1] - time[0]) * 0.008, (bar_y0 + bar_y1) / 2,
            f"{scale_uv:.0f} µV" if scale_uv >= 1 else f"{scale_uv:.1f} µV",
            fontsize=7, va="center", ha="left", color=_DARK_NAV)

    ax.set_xlabel("Time (s)", fontsize=9)
    ax.set_yticks([])
    ax.set_xlim(time[0], time[-1])
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    plt.tight_layout()
    return fig


def _nice_scale(target_uv: float) -> float:
    """Pick a round scale bar value close to target_uv."""
    nice = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]
    for v in nice:
        if v >= target_uv * 0.5:
            return float(v)
    return float(nice[-1])


# Band shading definitions for PSD plots
_PSD_BANDS = [
    ("Delta", 1, 4, "#4A90D9", 0.12),
    ("Theta", 4, 8, "#27AE60", 0.12),
    ("Alpha", 8, 13, "#E67E22", 0.12),
    ("Beta", 13, 30, "#E74C3C", 0.08),
]


def _plot_psd_grid(psd_cache, channels, ch_names, fs):
    """Plot PSDs on a 2x4 grid (up to 8 channels), using cached PSD data."""
    n_ch = len(channels)
    fig, axes = plt.subplots(2, 4, figsize=(14, 7.5))
    axes = axes.flatten()

    for plot_idx, ch_idx in enumerate(channels[:8]):
        ax = axes[plot_idx]
        f, psd = psd_cache[ch_idx]
        ch_label = ch_names[ch_idx]

        mask = (f >= 0.5) & (f <= 80)
        ax.semilogy(f[mask], psd[mask], linewidth=1.2, color="#0074D9")

        # Band shading with labels on first subplot only
        for band_name, lo, hi, clr, alpha in _PSD_BANDS:
            ax.axvspan(lo, hi, alpha=alpha, color=clr)

        ax.set_xlabel("Frequency (Hz)", fontsize=8)
        ax.set_ylabel(r"PSD ($\mu V^2$/Hz)", fontsize=8)
        ax.set_title(f"{ch_label}", fontsize=10, fontweight="bold", color=_DARK_NAV)
        ax.grid(True, alpha=0.2, linestyle="--")
        ax.set_xlim(0.5, 80)
        ax.tick_params(labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    for idx in range(n_ch, 8):
        axes[idx].axis("off")

    # Band legend on the figure (below the grid)
    from matplotlib.patches import Patch
    legend_patches = [Patch(facecolor=clr, alpha=alpha + 0.1, label=f"{name} ({lo}-{hi} Hz)")
                      for name, lo, hi, clr, alpha in _PSD_BANDS]
    fig.legend(handles=legend_patches, loc="lower center", ncol=4, fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, 0.01))

    plt.tight_layout()
    return fig


def _plot_band_heatmap(ch_names, psd_cache):
    """Band power heatmap — scales well to 8/20/32 channels."""
    n_ch = len(ch_names)
    bp_matrix = np.zeros((n_ch, len(BANDS)))
    for i in range(n_ch):
        f, psd = psd_cache[i]
        for j, (bname, (lo, hi)) in enumerate(BANDS.items()):
            m = (f >= lo) & (f <= hi)
            bp_matrix[i, j] = np.log10(np.mean(psd[m]) + 1e-10) if m.any() else -10

    # Adjust figure height based on channel count
    fig_h = max(3, n_ch * 0.35 + 1.5)
    fig, ax = plt.subplots(figsize=(8, fig_h))
    im = ax.imshow(bp_matrix, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(len(BANDS)))
    ax.set_xticklabels(list(BANDS.keys()), fontsize=9)
    ax.set_yticks(range(n_ch))
    ax.set_yticklabels(ch_names, fontsize=8)
    ax.set_title(r"$\log_{10}$ Band Power ($\mu V^2$/Hz)", fontsize=11, fontweight="bold", color=_DARK_NAV)
    plt.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    plt.tight_layout()
    return fig


def _plot_alpha_theta_ratio(ch_names, psd_cache):
    """Alpha/theta ratio bar chart."""
    n_ch = len(ch_names)
    atr = []
    for i in range(n_ch):
        f, psd = psd_cache[i]
        alpha_m = (f >= 8) & (f <= 13)
        theta_m = (f >= 4) & (f <= 8)
        alpha_p = np.mean(psd[alpha_m]) if alpha_m.any() else 0
        theta_p = np.mean(psd[theta_m]) if theta_m.any() else 0
        atr.append(alpha_p / max(theta_p, 1e-10))

    fig_w = max(6, n_ch * 0.5 + 2)
    fig, ax = plt.subplots(figsize=(fig_w, 3.5))
    bar_colors = [_PASS if r > 1 else "#e67e22" for r in atr]
    ax.bar(ch_names, atr, color=bar_colors, alpha=0.85, width=0.6)
    ax.axhline(1.0, color="#999999", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.set_ylabel("Alpha / Theta Ratio", fontsize=9)
    ax.set_title("Alpha/Theta Ratio by Channel", fontsize=10, fontweight="bold", color=_DARK_NAV)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", labelsize=8)
    plt.tight_layout()
    return fig


def _plot_alpha_reactivity(eeg_uV, triggers, ch_names, fs):
    """Alpha power comparison: Eyes Open vs Eyes Closed."""
    n_ch = len(ch_names)
    n_samples = eeg_uV.shape[0]
    eo_indices = np.where(triggers == 1)[0]
    ec_indices = np.where(triggers == 2)[0]
    seg_len = int(2 * fs)

    eo_start = eo_indices[0]
    ec_start = ec_indices[0]
    eo_alpha, ec_alpha = [], []
    for i in range(n_ch):
        eo_end = min(eo_start + seg_len, n_samples)
        ec_end = min(ec_start + seg_len, n_samples)
        f_eo, psd_eo = signal.welch(eeg_uV[eo_start:eo_end, i], fs=fs,
                                     nperseg=min(512, eo_end - eo_start))
        f_ec, psd_ec = signal.welch(eeg_uV[ec_start:ec_end, i], fs=fs,
                                     nperseg=min(512, ec_end - ec_start))
        m_eo = (f_eo >= 8) & (f_eo <= 13)
        m_ec = (f_ec >= 8) & (f_ec <= 13)
        eo_alpha.append(np.mean(psd_eo[m_eo]) if m_eo.any() else 0)
        ec_alpha.append(np.mean(psd_ec[m_ec]) if m_ec.any() else 0)

    fig_w = max(6, n_ch * 0.6 + 2)
    fig, ax = plt.subplots(figsize=(fig_w, 3.5))
    x = np.arange(n_ch)
    w = 0.35
    ax.bar(x - w/2, eo_alpha, w, label="Eyes Open", color="#e74c3c", alpha=0.8)
    ax.bar(x + w/2, ec_alpha, w, label="Eyes Closed", color="#2980b9", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(ch_names, fontsize=8)
    ax.set_ylabel("Alpha Power (µV²/Hz)", fontsize=9)
    ax.set_title("Alpha Reactivity: Eyes Open vs Eyes Closed", fontsize=10,
                 fontweight="bold", color=_DARK_NAV)
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
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
# Recording metadata extraction
# ---------------------------------------------------------------------------

def _get_recording_meta(easy_path: str, original_file_path: str | None = None) -> dict:
    """Extract all available metadata from the recording.

    If original_file_path points to a .nedf, reads the rich XML header.
    Otherwise falls back to parsing the .info companion file.
    """
    orig = original_file_path or easy_path

    if orig.endswith(".nedf") and os.path.isfile(orig):
        from ne_eeg_server.readers.nedf import read_nedf
        # Read header only — we just need metadata, not the full EEG data
        # But read_nedf reads everything; use its return dict for metadata
        try:
            data = read_nedf(orig)
            return {
                "electrodes": data["electrodes"],
                "device": data.get("device", "Unknown"),
                "num_channels": data["num_channels"],
                "sampling_rate": data["fs"],
                "duration_s": data["duration_s"],
                "start_date": data.get("start_date", ""),
                "step_name": data.get("step_name", ""),
                "device_id": data.get("device_id", ""),
                "software_version": data.get("software_version", ""),
                "firmware_version": data.get("firmware_version", ""),
                "communication_type": data.get("communication_type", ""),
                "line_filter": data.get("line_filter", ""),
                "packets_lost": data.get("packets_lost", 0),
                "eeg_units": data.get("eeg_units", "nV"),
                "trigger_labels": data.get("trigger_labels", {}),
                "format": "nedf",
                "nedf_version": data.get("nedf_version", ""),
            }
        except Exception:
            pass  # Fall through to .info parsing

    # Parse .info file
    from ne_eeg_server.readers.easy import parse_info_file
    info = parse_info_file(easy_path)

    # Derive start date from timestamp if available
    start_date = ""
    if info.get("start_timestamp_ms"):
        import datetime
        try:
            start_date = datetime.datetime.fromtimestamp(
                info["start_timestamp_ms"] / 1000.0
            ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return {
        "electrodes": info.get("electrodes", []),
        "device": info.get("device", "Unknown"),
        "num_channels": info.get("n_channels"),
        "sampling_rate": info.get("sampling_rate"),
        "duration_s": info.get("duration_s"),
        "start_date": start_date,
        "step_name": info.get("step_name", ""),
        "device_id": info.get("device_id", ""),
        "software_version": info.get("software_version", ""),
        "firmware_version": info.get("firmware_version", ""),
        "communication_type": info.get("communication_type", ""),
        "line_filter": info.get("line_filter", ""),
        "packets_lost": info.get("packets_lost", 0),
        "eeg_units": info.get("eeg_units", "nV"),
        "trigger_labels": info.get("trigger_labels", {}),
        "format": "easy",
    }


def _build_meta_block(meta: dict, st: dict, filename: str, n_ch: int,
                      fs: float, total_dur: float, start_time_s: float,
                      duration_s: float, win_dur: float) -> list:
    """Build the metadata block for the title page of a report."""
    items = []
    items.append(Paragraph(f"FILE: {filename}", st["meta"]))

    # Device line
    device_parts = [f"DEVICE: {meta.get('device', 'Unknown')}"]
    if meta.get("device_id"):
        device_parts.append(f"ID: {meta['device_id']}")
    items.append(Paragraph("&nbsp;&nbsp;&nbsp;".join(device_parts), st["meta"]))

    # Recording details
    items.append(Paragraph(
        f"CHANNELS: {n_ch} &nbsp;&nbsp;&nbsp; SAMPLING RATE: {int(fs)} Hz "
        f"&nbsp;&nbsp;&nbsp; FORMAT: {meta.get('format', 'unknown').upper()}"
        + (f" v{meta['nedf_version']}" if meta.get("nedf_version") else ""),
        st["meta"]))

    items.append(Paragraph(
        f"TOTAL DURATION: {total_dur:.1f} s &nbsp;&nbsp;&nbsp; "
        f"ANALYSIS WINDOW: {start_time_s:.1f} – {start_time_s + duration_s:.1f} s "
        f"({win_dur:.1f} s)", st["meta"]))

    # Start date
    if meta.get("start_date"):
        items.append(Paragraph(f"RECORDING DATE: {meta['start_date']}", st["meta"]))

    # Step name
    if meta.get("step_name"):
        items.append(Paragraph(f"STEP: {meta['step_name']}", st["meta"]))

    # Software / firmware
    sw_parts = []
    if meta.get("software_version"):
        sw_parts.append(f"SOFTWARE: {meta['software_version']}")
    if meta.get("firmware_version"):
        sw_parts.append(f"FIRMWARE: {meta['firmware_version']}")
    if meta.get("communication_type"):
        sw_parts.append(f"LINK: {meta['communication_type']}")
    if sw_parts:
        items.append(Paragraph("&nbsp;&nbsp;&nbsp;".join(sw_parts), st["meta"]))

    # Filter / data quality
    extra = []
    if meta.get("line_filter") and meta["line_filter"] != "OFF":
        extra.append(f"LINE FILTER: {meta['line_filter']}")
    if meta.get("packets_lost", 0) > 0:
        extra.append(f"PACKETS LOST: {meta['packets_lost']}")
    if extra:
        items.append(Paragraph("&nbsp;&nbsp;&nbsp;".join(extra), st["meta"]))

    # Trigger labels
    if meta.get("trigger_labels"):
        labels_str = ", ".join(f"{code}={label}" for code, label in
                               sorted(meta["trigger_labels"].items()))
        items.append(Paragraph(f"TRIGGER LABELS: {labels_str}", st["meta"]))

    items.append(Paragraph(
        f"REPORT DATE: {datetime.now().strftime('%B %d, %Y')}", st["meta"]))

    return items


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
