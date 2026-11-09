# Shared EEG quality-control API, version 1

The `ne_eeg_server.qc` package owns the numerical QC routines used by the bench
and ambulatory pipelines. It imports no MCP, plotting, or report code. The package
release is `ne-mcp-eeg` 0.2.0; the existing `analysis.qc` entry point forwards to
the bench adapter. Classification thresholds remain provisional, and passing the
artifact screen does not establish that physiological EEG is present.

## The two presets preserve their metric definitions

`qc.presets.THRESHOLDS["ambulatory"]` supplies the eleven-class artifact screen.
`THRESHOLDS["bench"]` supplies the existing shorted-input pass/fail thresholds.
These dictionaries are for different functions and are not interchangeable.
Bench band RMS is a root mean square; ambulatory `full_rms` is a standard
deviation after filtering and trimming. Bench kurtosis uses notch-only data and
bias correction; ambulatory kurtosis uses the trimmed band signal without bias
correction. Bench line power is the maximum PSD near 50 or 60 Hz; ambulatory hum
is integrated power around the configured mains frequency, 50 Hz by default.

```python
from ne_eeg_server.qc import metrics, classify, load, labels
from ne_eeg_server.qc.config import AnalysisConfig, DiagnosticsConfig, EventConfig
from ne_eeg_server.qc.bench import calculate_channel_metrics_from_signals

recording = load.read_easy("recording.easy", cache_dir="cache")
M = metrics.compute(recording["eeg"], recording["acc"], recording["fs"],
                    epoch_s=30., log=None,
                    analysis=AnalysisConfig(), diagnostics=DiagnosticsConfig())
R = classify.classify(M)  # ambulatory preset; optional threshold overrides
S = classify.segments(R["c"])
B = classify.blocks(R["c"], R, M, block_s=600.)
```

## Input, output, and provenance

`compute(eeg_nV, acc, fs, epoch_s=30., log=print, *, analysis=None,
diagnostics=None)` accepts samples by channels in nV and optional aligned samples
by three acceleration axes in mm/s². It requires a whole-number sample rate above
twice the highest configured filter frequency, epochs of at least ten seconds,
and finite samples in each analyzed epoch. Complete epochs are analyzed; the
excluded tail count is reported. Missing acceleration and fewer than four eligible
reference channels remain unassessed in the corresponding metrics and flags.

The legacy `KEYS`, `EKEYS`, array shapes, class codes, precedence, and
`metrics_version=2` remain stable. Arrays are at the top level of `M`; channel
metrics have shape `(ne, nch)` and epoch metrics `(ne,)`. RMS amplitudes are in µV,
DC metrics in mV, PSD in µV²/Hz, `hum_db` in dB relative to 1 µV²/Hz, acceleration
in mm/s², and constant-run duration in seconds. Fractions and correlations are
dimensionless; kurtosis uses the Pearson convention.

New metadata records `qc_version`, `analysis_config`, and optional
`diagnostics_config` and `diagnostics_version`. `AnalysisConfig` is a frozen
dataclass with `rail_nv`, `band_hz`, `filter_order`, `notch_hz`, `notch_q`,
`hum_hz`, `hum_half_width_hz`, `hf_hz`, `welch_s`, `trim_s`, `dc_window_s`, and
`reference`. `ReferenceConfig` records `sat_max`, `flat_frac_max`,
`constant_run_max_s`, `rms_min_uV`, and `minimum_channels`. Defaults reproduce the
reviewed version-2 calculation, including the 399 mV rail cutoff, 1–40 Hz fourth
order bandpass, 50/60 Hz Q=30 notches, two-second Welch windows, half-second edge
trim, and five-second DC windows. Configuration is validated before calculation.
Classification uses `M["reference_rule"]`, including its minimum-channel count;
legacy metrics without that field use the default rule. Configuration changes
require recomputation. Reporting threshold changes do not.

`resolve_thresholds(overrides=None)` validates ambulatory overrides.
`definitions(thr=None, analysis=None)` describes the actual settings; `analysis`
accepts an `AnalysisConfig` or its stored dictionary. `labels` exports `CLS`,
`CODE`, `LABEL`, `COL`, `GROUPS`, `SEQ_GREENS`, `DEFN`, `DISCLAIMER`, and
`definitions`; the historical names also remain available from `classify`.
`LABEL`, `GROUPS`, and `DEFN` describe the default preset; nondefault reports must
display their settings and use `definitions` for numerical criteria. Every
report using these interpretive labels includes `DISCLAIMER`.

`segments(c)` returns half-open epoch intervals with SIGNAL / DRIFT/SAT / OPEN
names. `blocks` requires an integral number of epochs per block and reports the
actual end of a partial final block. `channel_verdicts` keeps its existing API.

`load.read_easy(path, cache_dir=None)` requires the matching `.info` file and
returns `eeg`, `acc`, `trig`, `ts`, `n_eeg`, `fs`, and `info`. Timestamps are in ms.
The existing `load_easy`, `parse_info`, `split_columns`, `channel_names`,
`info_path_for`, and `cache_path_for` helpers remain available. The cache uses
source path, size, and modification time; it is not a content checksum.
Other formats use the existing readers. Their µV EEG arrays must be converted
to nV at this boundary. An absent or unaligned accelerometer must be passed as
`None`, including when a reader discards it.

## Diagnostics are additive and opt-in

With `diagnostics=None`, `compute` emits only the established metric arrays.
`DiagnosticsConfig()` adds the arrays listed in `metrics.DKEYS`, all with shape
`(ne, nch)`: `psd_peak_freq_hz`, `psd_peak_snr_db`, `psd_peak_count`,
`human_events_count`, `human_events_per_min`, and `human_events_duration_s`.
They do not enter the eleven-class decision or alter any existing metric.

Peak diagnostics reuse `qc.peaks.find_suspicious_psd_peak` on the raw demeaned
Welch PSD. They report the strongest local peak above the median spectral
baseline and count peaks above `peak_snr_db` (default 12 dB), excluding mains
bands at 50/60 Hz and their 100/120 Hz harmonics. The detector's historical name
is retained; it measures prominence, not peak width or a verified artifact.
Physiological rhythms can produce these peaks. `peak_snr_db` is configurable.

`EventConfig(threshold_uv=100., min_duration_s=.02, merge_gap_s=.1)` defines
human-scale amplitude episodes on the same filtered, trimmed signal used for
ambulatory `full_rms`. Runs with absolute amplitude strictly above the threshold
are merged when their intervening gap is at most `merge_gap_s`. A merged event
must contain at least `ceil(min_duration_s * fs)` above-threshold samples.
Counts are normalized to minutes of the retained signal, whose duration is
also returned. Events are confined to an epoch and may be split at an epoch
boundary. These provisional settings measure excursions, not clinical events.
Set `DiagnosticsConfig(events=EventConfig(...))` to change them.

`calculate_channel_metrics_from_signals` in `qc.bench` preserves the existing
signature, µV inputs, permissive handling of short windows, thresholds, flags,
and contiguous-run event rate in Hz. Its 5 µV event threshold is unchanged.
Legacy imports from `analysis.qc`, `analysis.metrics_defaults`, and
`analysis.psd_peak_qc` forward to the shared implementation.

## Reference outputs are frozen before extraction

`tests/qc/synthetic.py` generates artificial recordings with DC, hum, band
signals, drift, flatlines, rail values, acceleration, and partial tails. The
fixtures capture every legacy metric, classification flag, segment, and block
output for 1, 8, and 32 channels, plus bench outputs for normal, flat, short,
and nonfinite-containing inputs. `tests/qc/fixtures/manifest.json` records the
source hashes and numerical environment used to capture them. Migration tests
require exact discrete outputs and floating agreement within `rtol=1e-10,
atol=1e-10`, including the same NaN positions. A separate same-environment
comparison checks bitwise equality against the original implementations.

Campaign recordings and their results stay in the private consumer repository.
That consumer's pre-migration summary counts are an additional release gate for
its migration. A synthetic regression pass does not establish reproduction of
the full campaign; the consumer owner performs that rerun after the release tag.
