# QC input validation and compatibility tests, version 0.2.1

The legacy analyzer now uses the sampling rate declared in `.info`; an explicit
`fs` argument still overrides it, and files without a declared rate retain the
500 Hz legacy fallback. Invalid declared rates fail with a descriptive error.
The legacy `.easy` reader honors the declared EEG channel count, including a
single channel with no accelerometer. These changes correct non-500 Hz window
selection and filtering while preserving the established 500 Hz results.

The NEDF reader accepts XML declarations, checks required header fields and
binary payload length before decoding, preserves numbered channel positions,
and reads signed 32-bit markers. It validates optional-track declarations and
derives duration from the actual sample count and rate. Synthetic files cover
versions 1.2 and 1.4, signed 24-bit extrema, 1/8/32 EEG channels, optional
accelerometer and stimulation tracks, and a partial final five-sample block.
The 1.4 test layout and calibration were checked against the independent
[MNE NEDF reader](https://github.com/mne-tools/mne-python/blob/main/mne/io/nedf/nedf.py).
Acceleration is still discarded by this reader; pass `acc=None` when sending
its EEG arrays to the shared core. The legacy conversion helper writes zero
placeholder acceleration columns for compatibility; those are not measurements.

The additional tests exercise the complete NEDF-to-QC and `.easy`-to-QC paths
at 250 and 1000 Hz. Corrupt headers, truncated or excess payloads, invalid rates,
and inconsistent channel layouts fail explicitly. Existing core tests cover
missing `.info` fields and reference eligibility without acceleration.

`tests/qc/fixtures/signal_quality_v1.json` pins two complete tool responses
captured from the pre-extraction commit `d8861a8`: the whole public demo and a
selected four-second window with selected channels. Tests compare every returned
value exactly, including rounded metrics, flags, labels, and summary counts;
companion hashes pin the source `.easy` and `.info` files. The shared numerical
core itself is unchanged from 0.2.0.

Local validation passes 85 tests and 11 subtests. The CI workflow runs the same
suite on each push to `main` under Python 3.10, 3.11, and 3.12.

Install this patch with:

```bash
pip install "ne-mcp-eeg @ git+https://github.com/Neuroelectrics-Barcelona-SLU/ne-mcp-eeg.git@v0.2.1"
```
