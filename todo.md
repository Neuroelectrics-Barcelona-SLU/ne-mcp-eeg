# TODO — ne-eeg-server

- [ ] adopt the core C-engine loader in the legacy reader while preserving its input compatibility
- [ ] let generate_qc_report accept a preloaded analyzer so several windows do not reload the file
- [x] extract the shared QC core with bench compatibility and synthetic reference tests
- [x] add the provisional ambulatory preset, including the minimum 1–40 Hz band-amplitude criterion
- [x] add configurable spectral prominence and amplitude-event diagnostics without changing classes
- [x] cover NEDF and non-500 Hz inputs and pin complete NIC signal_quality results
- [x] add long_recording_qc and reconcile the consumer migration to v0.2.1
