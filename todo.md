# TODO — ne-eeg-server

- [ ] extract and tag the shared QC core with bench compatibility and additive diagnostics
- [ ] hand the release tag to Klaus for the long-recording MCP tool and private consumer migration
- [ ] switch readers/easy.py to pandas engine="c" with sep="\t" (python engine took 590 s vs 22 s on a 3.7 GB .easy; fall back to sniffing only on failure)
- [ ] add a human-EEG threshold preset (defaults are shorted-input bench values and fail every physiological channel; see Test003 overnight report, Section 1)
- [ ] add a minimum 1–40 Hz RMS threshold so open inputs with 50 Hz pickup fail on flatness, not only on line power
- [ ] add a long-recording mode: per-epoch metrics, status heatmap, DC/saturation/accelerometer timeline (prototype scripts from the 2026-11-09 overnight-file analysis, kept with that report)
- [ ] let generate_qc_report accept a preloaded analyzer so several windows do not reload the file
