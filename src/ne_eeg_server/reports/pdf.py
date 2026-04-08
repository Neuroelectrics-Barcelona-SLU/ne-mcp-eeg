"""
PDF report generators for EEG QC and EEG Analysis reports.

Two report types:
  - QC Report: per-channel signal quality (RMS, kurtosis, event rate, line power,
    PASS/FAIL flags) + PSD plots.
  - Analysis Report: functional EEG analysis (raw traces with markers, PSD overlay,
    band power heatmap, alpha reactivity EO/EC, alpha/theta ratio).

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
from matplotlib.gridspec import GridSpec
from scipy import signal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak,
    KeepTogether,
)

from ne_eeg_server.analysis.analyzer import EasyAnalyzer
from ne_eeg_server.analysis.metrics_defaults import DEFAULT_EVENT_THRESHOLD_UV

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo-NE.png")

# ---------------------------------------------------------------------------
# Shared styles
# ---------------------------------------------------------------------------
_NE_BLUE = "#007bff"
_NE_GRAY = "#808080"


def _build_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "NETitle", parent=styles["Heading1"],
        fontSize=18, textColor=colors.HexColor(_NE_BLUE),
        spaceAfter=4, alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "NESubtitle", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor(_NE_GRAY),
        spaceAfter=12, alignment=TA_CENTER,
    )
    heading_style = ParagraphStyle(
        "NEHeading", parent=styles["Heading2"],
        fontSize=13, textColor=colors.HexColor(_NE_BLUE),
        spaceAfter=6, spaceBefore=14,
    )
    body_style = ParagraphStyle(
        "NEBody", parent=styles["Normal"],
        fontSize=9, leading=12, spaceAfter=4,
    )
    small_style = ParagraphStyle(
        "NESmall", parent=styles["Normal"],
        fontSize=7, leading=9, textColor=colors.HexColor("#555555"),
    )
    return styles, title_style, subtitle_style, heading_style, body_style, small_style


def _header_footer(canvas, doc, report_title: str, gen_ts: str, filename: str):
    """Draw consistent NE header/footer on every page."""
    canvas.saveState()
    w, h = A4
    left, right = doc.leftMargin, w - doc.rightMargin

    if os.path.isfile(_LOGO_PATH):
        canvas.drawImage(_LOGO_PATH, left, h - 0.6 * inch, width=0.8 * inch,
                         height=0.3 * inch, preserveAspectRatio=True, mask="auto")

    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor(_NE_GRAY))
    canvas.drawCentredString((left + right) / 2, h - 0.35 * inch, report_title)

    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(right, h - 0.35 * inch, gen_ts)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor(_NE_GRAY))
    canvas.drawString(left, 0.3 * inch, f"File: {filename}")
    canvas.drawCentredString((left + right) / 2, 0.3 * inch, f"Page {doc.page}")
    canvas.drawRightString(right, 0.3 * inch, "neuroelectrics.com")
    canvas.restoreState()


def _fig_to_image(fig, width_inches=6.5, dpi=150) -> Image:
    """Convert a matplotlib figure to a ReportLab Image flowable."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    fig_w, fig_h = fig.get_size_inches()
    aspect = fig_h / fig_w
    img = Image(buf, width=width_inches * inch, height=width_inches * aspect * inch)
    return img


# ===========================================================================
# QC Report
# ===========================================================================

def generate_qc_report(
    file_path: str,
    output_path: Optional[str] = None,
    start_time_s: float = 0.0,
    duration_s: Optional[float] = None,
) -> str:
    """Generate a Signal Quality PDF report for a .easy file.

    Returns the path to the generated PDF.
    """
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

        gen_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = os.path.basename(file_path)

        if output_path is None:
            output_path = file_path.replace(".easy", "_qc_report.pdf")

        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            topMargin=0.75 * inch, bottomMargin=0.6 * inch,
            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        )

        styles, title_s, subtitle_s, heading_s, body_s, small_s = _build_styles()
        story = []

        if os.path.isfile(_LOGO_PATH):
            story.append(Image(_LOGO_PATH, width=1.8 * inch, height=0.7 * inch))
            story.append(Spacer(1, 6))

        story.append(Paragraph("EEG Signal Quality Report", title_s))
        story.append(Paragraph(
            f"{filename} &nbsp;|&nbsp; {n_ch} channels &nbsp;|&nbsp; "
            f"{int(fs)} Hz &nbsp;|&nbsp; {total_duration:.1f} s total &nbsp;|&nbsp; "
            f"Window: {start_time_s:.1f}–{start_time_s + duration_s:.1f} s",
            subtitle_s,
        ))
        story.append(Paragraph(f"Generated: {gen_ts}", subtitle_s))
        story.append(Spacer(1, 12))

        total_pass = sum(1 for m in qc_metrics.values() if m.get("pass", False))
        summary_color = "#28a745" if total_pass == len(qc_metrics) else "#dc3545"
        story.append(Paragraph(
            f'<b>QC Summary:</b> <font color="{summary_color}">'
            f'{total_pass}/{len(qc_metrics)} channels PASS</font>',
            body_s,
        ))
        story.append(Spacer(1, 8))

        story.append(Paragraph("Per-Channel Metrics", heading_s))
        story.append(_build_qc_table(qc_metrics, electrodes))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "* = flagged value (exceeds threshold). "
            "RMS values in µV. Line power in dB. "
            f"Event threshold: {DEFAULT_EVENT_THRESHOLD_UV:.1f} µV.",
            small_s,
        ))

        for key in sorted(plot_paths.keys()):
            if "psd" in key:
                story.append(PageBreak())
                page_label = key.replace("psd_", "").replace("psd", "Channels 1-8")
                story.append(Paragraph(f"Power Spectral Density — {page_label}", heading_s))
                img = Image(plot_paths[key], width=6.5 * inch, height=4.5 * inch)
                story.append(img)

        for key in sorted(plot_paths.keys()):
            if "raw" in key or "filtered" in key:
                story.append(PageBreak())
                label = key.replace("_", " ").title()
                story.append(Paragraph(label, heading_s))
                img = Image(plot_paths[key], width=6.5 * inch, height=7.5 * inch)
                story.append(img)

        def _on_page(canvas, doc):
            _header_footer(canvas, doc, "EEG Signal Quality Report", gen_ts, filename)

        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    return output_path


def _build_qc_table(qc_metrics: dict, electrodes: list[str]) -> Table:
    """Build the per-channel QC metrics table."""
    header = ["Ch", "Mean\n(µV)", "RMS raw\n(µV)", "RMS notch\n(µV)",
              "RMS filt\n(µV)", "Line 50/60\n(dB)", "Kurt\n(notch)",
              "Events\n(/s)", "PASS/\nFAIL"]

    data = [header]
    for ch_idx in sorted(qc_metrics.keys()):
        m = qc_metrics[ch_idx]
        flags = m.get("flags", {})
        passed = m.get("pass", True)
        label = electrodes[ch_idx] if ch_idx < len(electrodes) else f"Ch{ch_idx+1}"

        def fmt(val, digits=1, flag_key=None):
            if val is None or (isinstance(val, float) and val != val):
                return ""
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

    col_widths = [0.4*inch, 0.55*inch, 0.65*inch, 0.65*inch, 0.65*inch,
                  0.7*inch, 0.55*inch, 0.55*inch, 0.55*inch]
    table = Table(data, colWidths=col_widths)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_NE_BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]

    for row_i, ch_idx in enumerate(sorted(qc_metrics.keys()), start=1):
        passed = qc_metrics[ch_idx].get("pass", True)
        bg = colors.HexColor("#d4edda") if passed else colors.HexColor("#f8d7da")
        fg = colors.HexColor("#155724") if passed else colors.HexColor("#721c24")
        style_cmds.append(("BACKGROUND", (-1, row_i), (-1, row_i), bg))
        style_cmds.append(("TEXTCOLOR", (-1, row_i), (-1, row_i), fg))
        style_cmds.append(("FONTNAME", (-1, row_i), (-1, row_i), "Helvetica-Bold"))

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
    """Generate a functional EEG Analysis PDF report for a .easy file.

    Returns the path to the generated PDF.
    """
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

    gen_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = os.path.basename(file_path)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=0.75 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )

    styles, title_s, subtitle_s, heading_s, body_s, small_s = _build_styles()
    story = []

    if os.path.isfile(_LOGO_PATH):
        story.append(Image(_LOGO_PATH, width=1.8 * inch, height=0.7 * inch))
        story.append(Spacer(1, 6))

    story.append(Paragraph("EEG Analysis Report", title_s))

    device = _parse_device(file_path)
    story.append(Paragraph(
        f"{filename} &nbsp;|&nbsp; {device} &nbsp;|&nbsp; {n_ch} channels &nbsp;|&nbsp; "
        f"{fs} Hz &nbsp;|&nbsp; {total_duration:.1f} s total &nbsp;|&nbsp; "
        f"Window: {start_time_s:.1f}–{start_time_s + duration_s:.1f} s",
        subtitle_s,
    ))
    story.append(Paragraph(f"Generated: {gen_ts}", subtitle_s))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Raw EEG Traces with Event Markers", heading_s))
    fig_traces = _plot_raw_traces(eeg_win, trig_win, ch_names, fs, start_time_s)
    story.append(_fig_to_image(fig_traces, width_inches=6.5))
    story.append(Spacer(1, 4))

    trig_indices = np.where(trig_win > 0)[0]
    if len(trig_indices) > 0:
        trig_text = ", ".join(
            f"{TRIGGER_MAP.get(trig_win[i], f'T{trig_win[i]}')} @ "
            f"{start_time_s + i/fs:.2f}s"
            for i in trig_indices[:20]
        )
        story.append(Paragraph(f"<b>Markers detected:</b> {trig_text}", small_s))
    story.append(Spacer(1, 6))

    story.append(PageBreak())
    story.append(Paragraph("Spectral Analysis", heading_s))
    fig_spectral = _plot_spectral_panels(eeg_win, ch_names, fs)
    story.append(_fig_to_image(fig_spectral, width_inches=6.5))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Alpha Analysis", heading_s))
    fig_alpha = _plot_alpha_panels(eeg_win, trig_win, ch_names, fs)
    story.append(_fig_to_image(fig_alpha, width_inches=6.5))
    story.append(Spacer(1, 8))

    story.append(PageBreak())
    story.append(Paragraph("Spectral Summary", heading_s))
    story.append(_build_spectral_table(eeg_win, ch_names, fs))
    story.append(Spacer(1, 6))

    if "F3" in ch_names and "F4" in ch_names:
        f3i, f4i = ch_names.index("F3"), ch_names.index("F4")
        f_, psd3 = signal.welch(eeg_win[:, f3i], fs=fs, nperseg=min(1024, len(eeg_win)))
        _, psd4 = signal.welch(eeg_win[:, f4i], fs=fs, nperseg=min(1024, len(eeg_win)))
        a_mask = (f_ >= 8) & (f_ <= 13)
        if a_mask.any():
            faa = np.log(np.mean(psd4[a_mask])) - np.log(np.mean(psd3[a_mask]))
            interp = "right > left (approach)" if faa > 0 else "left > right (withdrawal)"
            story.append(Paragraph(
                f"<b>Frontal Alpha Asymmetry</b> (ln F4 − ln F3): {faa:.4f} → {interp}",
                body_s,
            ))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Per-Channel Statistics", heading_s))
    story.append(_build_stats_table(eeg_win, ch_names))

    def _on_page(canvas, doc):
        _header_footer(canvas, doc, "EEG Analysis Report", gen_ts, filename)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return output_path


# ---------------------------------------------------------------------------
# Analysis report plot helpers
# ---------------------------------------------------------------------------

def _plot_raw_traces(eeg_uV, triggers, ch_names, fs, t_offset=0.0):
    n_samples, n_ch = eeg_uV.shape
    time = t_offset + np.arange(n_samples) / fs

    fig, ax = plt.subplots(figsize=(10, max(3, n_ch * 0.45)))
    spacing = np.max(np.std(eeg_uV, axis=0)) * 5
    offsets = np.arange(n_ch) * spacing

    for i, ch in enumerate(ch_names):
        ax.plot(time, eeg_uV[:, i] + offsets[i], linewidth=0.4, color="#2c3e50")
        ax.text(time[0] - (time[-1] - time[0]) * 0.02, offsets[i], ch,
                fontsize=8, va="center", ha="right", fontweight="bold")

    for idx in np.where(triggers > 0)[0]:
        t = t_offset + idx / fs
        code = triggers[idx]
        label = TRIGGER_MAP.get(code, f"T{code}")
        color = "#e74c3c" if code == 1 else "#2980b9"
        ax.axvline(t, color=color, alpha=0.7, linestyle="--", linewidth=1.0)
        ax.text(t + 0.05, offsets[-1] + spacing * 0.5, label,
                color=color, fontsize=8, fontweight="bold")

    ax.set_xlabel("Time (s)", fontsize=9)
    ax.set_yticks([])
    ax.set_xlim(time[0], time[-1])
    ax.set_title("Raw EEG Traces (µV) with Event Markers", fontsize=10, fontweight="bold")
    plt.tight_layout()
    return fig


def _plot_spectral_panels(eeg_uV, ch_names, fs):
    n_ch = eeg_uV.shape[1]
    fig, (ax_psd, ax_hm) = plt.subplots(1, 2, figsize=(12, 4.5))

    cmap_colors = plt.cm.viridis(np.linspace(0.1, 0.9, n_ch))
    for i, ch in enumerate(ch_names):
        f, psd = signal.welch(eeg_uV[:, i], fs=fs, nperseg=min(1024, len(eeg_uV)))
        mask = (f >= 1) & (f <= 45)
        ax_psd.semilogy(f[mask], psd[mask], label=ch, color=cmap_colors[i], linewidth=1.0)

    for sym, ((lo, hi), col) in BAND_SHADING.items():
        ax_psd.axvspan(lo, hi, alpha=0.25, color=col)
        ylim = ax_psd.get_ylim()
        ax_psd.text((lo + hi) / 2, ylim[1] * 0.3, sym, ha="center", fontsize=10, alpha=0.6)

    ax_psd.set_xlabel("Frequency (Hz)", fontsize=9)
    ax_psd.set_ylabel("PSD (µV²/Hz)", fontsize=9)
    ax_psd.set_title("Power Spectral Density", fontsize=10, fontweight="bold")
    ax_psd.legend(fontsize=6, ncol=max(1, n_ch // 4), loc="upper right")
    ax_psd.set_xlim(1, 45)

    bp_matrix = np.zeros((n_ch, len(BANDS)))
    for i in range(n_ch):
        f, psd = signal.welch(eeg_uV[:, i], fs=fs, nperseg=min(1024, len(eeg_uV)))
        for j, (bname, (lo, hi)) in enumerate(BANDS.items()):
            m = (f >= lo) & (f <= hi)
            bp_matrix[i, j] = np.log10(np.mean(psd[m]) + 1e-10) if m.any() else -10

    im = ax_hm.imshow(bp_matrix, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax_hm.set_xticks(range(len(BANDS)))
    ax_hm.set_xticklabels(list(BANDS.keys()), fontsize=8)
    ax_hm.set_yticks(range(n_ch))
    ax_hm.set_yticklabels(ch_names, fontsize=8)
    ax_hm.set_title("log₁₀ Band Power (µV²/Hz)", fontsize=10, fontweight="bold")
    plt.colorbar(im, ax=ax_hm, shrink=0.8)

    plt.tight_layout()
    return fig


def _plot_alpha_panels(eeg_uV, triggers, ch_names, fs):
    n_ch = eeg_uV.shape[1]
    fig, (ax_react, ax_ratio) = plt.subplots(1, 2, figsize=(12, 4))

    eo_indices = np.where(triggers == 1)[0]
    ec_indices = np.where(triggers == 2)[0]
    seg_len = int(2 * fs)

    if len(eo_indices) > 0 and len(ec_indices) > 0:
        eo_start = eo_indices[0]
        ec_start = ec_indices[0]
        eo_alpha, ec_alpha = [], []

        for i in range(n_ch):
            f_eo, psd_eo = signal.welch(
                eeg_uV[eo_start:eo_start + seg_len, i], fs=fs,
                nperseg=min(512, seg_len),
            )
            f_ec, psd_ec = signal.welch(
                eeg_uV[ec_start:ec_start + seg_len, i], fs=fs,
                nperseg=min(512, seg_len),
            )
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
        ax_react.legend(fontsize=8)
    else:
        ax_react.text(0.5, 0.5, "No EO/EC triggers found", ha="center", va="center",
                      transform=ax_react.transAxes, fontsize=11, color="gray")

    ax_react.set_title("Alpha Reactivity: EO vs EC", fontsize=10, fontweight="bold")

    atr = []
    for i in range(n_ch):
        f, psd = signal.welch(eeg_uV[:, i], fs=fs, nperseg=min(1024, len(eeg_uV)))
        alpha_m = (f >= 8) & (f <= 13)
        theta_m = (f >= 4) & (f <= 8)
        alpha_p = np.mean(psd[alpha_m]) if alpha_m.any() else 0
        theta_p = np.mean(psd[theta_m]) if theta_m.any() else 0
        atr.append(alpha_p / max(theta_p, 1e-10))

    bar_colors = ["#27ae60" if r > 1 else "#e67e22" for r in atr]
    ax_ratio.bar(ch_names, atr, color=bar_colors, alpha=0.85)
    ax_ratio.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_ratio.set_ylabel("Alpha / Theta Ratio", fontsize=9)
    ax_ratio.set_title("Alpha/Theta Ratio by Channel", fontsize=10, fontweight="bold")
    ax_ratio.text(0.02, 0.95, "Green = α dominant\nOrange = θ dominant",
                  transform=ax_ratio.transAxes, fontsize=7, va="top")

    plt.tight_layout()
    return fig


def _build_spectral_table(eeg_uV, ch_names, fs) -> Table:
    """Build per-channel spectral summary table."""
    header = ["Ch"] + list(BANDS.keys()) + ["α/θ", "Peak α (Hz)"]
    data = [header]

    for i, ch in enumerate(ch_names):
        f, psd = signal.welch(eeg_uV[:, i], fs=fs, nperseg=min(1024, len(eeg_uV)))
        row = [ch]
        for bname, (lo, hi) in BANDS.items():
            m = (f >= lo) & (f <= hi)
            row.append(f"{np.mean(psd[m]):.2f}" if m.any() else "—")

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
    col_w = [0.5*inch] + [0.7*inch] * (n_cols - 1)
    table = Table(data, colWidths=col_w)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_NE_BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _build_stats_table(eeg_uV, ch_names) -> Table:
    """Build per-channel descriptive statistics table."""
    header = ["Ch", "Mean (µV)", "Std (µV)", "Min (µV)", "Max (µV)", "Pk-Pk (µV)"]
    data = [header]
    for i, ch in enumerate(ch_names):
        d = eeg_uV[:, i]
        data.append([
            ch,
            f"{np.mean(d):.1f}", f"{np.std(d):.1f}",
            f"{np.min(d):.1f}", f"{np.max(d):.1f}", f"{np.ptp(d):.1f}",
        ])

    table = Table(data, colWidths=[0.5*inch] + [0.85*inch] * 5)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_NE_BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


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
    data = np.loadtxt(filepath)
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
    eeg_uV = data[:, :n_eeg] / 1000.0
    triggers = data[:, n_eeg + 3].astype(int)
    timestamps = data[:, n_eeg + 4]
    return eeg_uV, triggers, timestamps, ch_names
