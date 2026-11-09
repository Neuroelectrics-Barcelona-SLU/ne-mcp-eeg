"""Shared interpretive vocabulary; reports must include DISCLAIMER."""
from .presets import resolve_thresholds

CLS = ["clean", "hum_elevated", "hum_severe", "hf_noise", "motion", "bad_channel", "common_mode", "drift", "open_input", "flatline", "saturated"]
CODE = {c: i for i, c in enumerate(CLS)}
COL = {"clean": "#186a3b", "hum_elevated": "#4fbf7f", "hum_severe": "#c9a227", "hf_noise": "#7d6608", "motion": "#8e44ad", "bad_channel": "#c0392b",
       "common_mode": "#2874a6", "drift": "#d35400", "open_input": "#bdbdbd", "flatline": "#e0e0e0", "saturated": "#000000"}
# Chromatic classes validated for colorblind separation (dataviz validate_palette.js, 2026-11-09); the three no-signal classes are neutral by design.
GROUPS = [("usable", ["clean", "hum_elevated"], "#186a3b"), ("hum > 50 µV / HF noise", ["hum_severe", "hf_noise"], "#c9a227"), ("bad channel", ["bad_channel"], "#c0392b"),
          ("common-mode (CMS/DRL)", ["common_mode"], "#2874a6"), ("drift / motion", ["drift", "motion"], "#d35400"), ("open input", ["open_input", "flatline"], "#bdbdbd"), ("saturated", ["saturated"], "#000000")]
SEQ_GREENS = ["#6cbd8a", "#2e9a5e", "#1e8449", "#145a32"]
LABEL = {"clean": "clean", "hum_elevated": "usable, hum 10–50 µV", "hum_severe": "hum above 50 µV", "hf_noise": "HF/EMG noise", "motion": "motion artifact",
         "bad_channel": "bad channel (outlier)", "common_mode": "common-mode dominated (CMS/DRL)", "drift": "drift", "open_input": "open input (no EEG band)",
         "flatline": "digital flatline", "saturated": "saturated at rail"}
DISCLAIMER = 'Class names such as "saturated at rail", "open input", "common-mode dominated (CMS/DRL)", "never connected" and "usable" are interpretive names for measured signal patterns: each names the most common cause of the pattern, not a verified diagnosis of this recording. The thresholds are provisional and have not been validated against labeled connection states, and no test here establishes that physiological EEG is present. Usable means passing the artifact screen (clean, or 50 Hz power between 10 and 50 µV) and nothing more.'

def definitions(thr=None):
    t = resolve_thresholds(thr)
    return {
        "saturated": ("fraction of raw samples with |v| ≥ 399 mV", f"≥ {100*t['sat']:g}%"),
        "flatline": ("identical consecutive samples; near-rail class has precedence", f"run ≥ {t['flat_run_s']:g} s or repeated differences ≥ {100*t['flat_frac']:g}%"),
        "open_input": ("1-40 Hz standard deviation after notch and edge trim", f"< {t['open_rms']:g} µV"),
        "drift": ("raw RMS minus estimated hum power, or absolute first-to-last 5-s DC change", f"≥ {t['drift_raw']:g} µV or ≥ {t['drift_ddc']:g} mV"),
        "common_mode": ("epoch median pairwise correlation and median-signal RMS; channel correlation to that signal", f"≥ {t['cm_corr']:g}, ≥ {t['cm_rms']:g} µV; channel ≥ {t['cm_corr']:g}"),
        "bad_channel": ("residual vs eligible peers, or band RMS, or hum vs eligible peers", f"> max({t['bad_resid_abs']:g} µV, {t['bad_resid_rel']:g}× peer median); > {t['bad_rms']:g} µV; > {t['bad_hum_rel']:g}× peer median and > {t['bad_hum_abs']:g} µV"),
        "motion": ("largest 1-s acceleration RMS vs recording baseline; channel band RMS", f"> {t['motion_acc_rel']:g}× baseline; > {t['motion_rms']:g} µV"),
        "hf_noise": ("raw Welch RMS in 30-45 Hz", f"> {t['hf_rms']:g} µV"),
        "hum_severe": ("raw Welch RMS in 49-51 Hz", f"> {t['hum_severe']:g} µV"),
        "hum_elevated": ("raw Welch RMS in 49-51 Hz", f"> {t['hum_elev']:g} and ≤ {t['hum_severe']:g} µV"),
        "clean": ("no preceding criterion met; optional tests may be unavailable", f"hum ≤ {t['hum_elev']:g} µV"),
    }

DEFN = definitions()

