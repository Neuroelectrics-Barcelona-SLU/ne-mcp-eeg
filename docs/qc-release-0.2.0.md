# QC core release 0.2.0

`ne_eeg_server.qc` provides the shared ambulatory algorithms and the existing
bench calculation through compatibility adapters. The API contract is frozen
at tag `qc-api-v1`; [qc-core.md](qc-core.md) defines the units and integration
boundary. The package version and installable Git tag are `0.2.0` and `v0.2.0`.

The extraction preserves the default version-2 metrics, eleven-class precedence,
thresholds, interval rules, interpretive labels, and disclaimer. Analysis settings
are now validated and recorded with the metrics. Opt-in diagnostics add spectral
prominence and configurable amplitude-event counts per minute. These diagnostics
do not change the artifact screen. Bench event counts retain their original
5 µV threshold and rates in Hz.

Local verification used Python 3.14.7, NumPy 2.4.4, and SciPy 1.17.1; the full
suite passed 66 tests and 11 subtests. All 108
frozen synthetic arrays and every field in the five bench reference cases
matched exactly, including NaN positions. Enabling diagnostics left all original
metric arrays and classes unchanged. The core tests cover metric units,
precedence, threshold boundaries, missing acceleration, 1/8/32-channel inputs,
reference eligibility, partial intervals, file loading, configuration persistence,
60 Hz hum, known spectral peaks, and event duration and gap boundaries.

The source distribution and wheel build successfully. All 50 core tests and
11 subtests pass when imported from the built wheel, with the editable source
checkout excluded from the import path. A subprocess check verifies that the
core imports neither MCP nor plotting/report packages. The public demo recording
also passes the strict reader-to-metrics path with diagnostics enabled.

The private consumer must retain its recording references and rerun its complete
pipeline after pinning the tag. Cached-metric classification checks supplement
that rerun but do not replace recomputing metrics from recordings. This release
contains algorithms and synthetic fixtures; it contains no campaign data or
participant results. It does not validate the provisional artifact thresholds
against physiological EEG or labeled connection states.

Install the Git release with:

```bash
pip install "ne-mcp-eeg @ git+https://github.com/Neuroelectrics-Barcelona-SLU/ne-mcp-eeg.git@v0.2.0"
```

The tag does not publish a PyPI release. Existing consumers may keep importing
`analysis.qc`, `analysis.metrics_defaults`, and `analysis.psd_peak_qc`; those
modules forward to the core.
