"""
NE-specific constants: electrode positions, frequency bands, device specs, file formats.
"""

# ---------------------------------------------------------------------------
# International 10-20 system positions (standard 21 electrodes)
# ---------------------------------------------------------------------------
ELECTRODES_10_20: list[str] = [
    "Fp1", "Fp2",
    "F7", "F3", "Fz", "F4", "F8",
    "T3", "C3", "Cz", "C4", "T4",
    "T5", "P3", "Pz", "P4", "T6",
    "O1", "Oz", "O2",
    "A1", "A2",
]

# ---------------------------------------------------------------------------
# Extended 10-10 system positions (used by Enobio 32 / Starstim 32)
# ---------------------------------------------------------------------------
ELECTRODES_10_10: list[str] = [
    "Fp1", "Fpz", "Fp2",
    "AF7", "AF3", "AFz", "AF4", "AF8",
    "F9", "F7", "F5", "F3", "F1", "Fz", "F2", "F4", "F6", "F8", "F10",
    "FT9", "FT7", "FC5", "FC3", "FC1", "FCz", "FC2", "FC4", "FC6", "FT8", "FT10",
    "T9", "T7", "C5", "C3", "C1", "Cz", "C2", "C4", "C6", "T8", "T10",
    "TP9", "TP7", "CP5", "CP3", "CP1", "CPz", "CP2", "CP4", "CP6", "TP8", "TP10",
    "P9", "P7", "P5", "P3", "P1", "Pz", "P2", "P4", "P6", "P8", "P10",
    "PO9", "PO7", "PO3", "POz", "PO4", "PO8", "PO10",
    "O1", "Oz", "O2",
    "Iz",
    "A1", "A2", "M1", "M2",
]

ALL_VALID_POSITIONS: set[str] = set(ELECTRODES_10_20) | set(ELECTRODES_10_10)

# ---------------------------------------------------------------------------
# EEG frequency bands (Hz) — standard clinical definitions
# ---------------------------------------------------------------------------
FREQ_BANDS: dict[str, tuple[float, float]] = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta":  (13.0, 30.0),
    "gamma": (30.0, 125.0),
}

# ---------------------------------------------------------------------------
# Device specifications
# ---------------------------------------------------------------------------
SAMPLING_RATE_HZ: int = 500
RESOLUTION_BITS: int = 24
BANDWIDTH_HZ: tuple[float, float] = (0.0, 125.0)
PRECISION_UV: float = 0.05  # 24-bit resolution → ~0.05 µV LSB

# Number of EEG channels per device variant
DEVICE_CHANNELS: dict[str, int] = {
    "Enobio 8": 8,
    "Enobio 20": 20,
    "Enobio 32": 32,
    "Starstim 8": 8,
    "Starstim 20": 20,
    "Starstim 32": 32,
}

# Data units as stored in .easy files (nanovolts)
EASY_FILE_UNITS: str = "nV"
NV_TO_UV: float = 1e-3

# Accelerometer specs
ACCELEROMETER_CHANNELS: int = 3
ACCELEROMETER_SAMPLING_RATE_HZ: int = 100
ACCELEROMETER_UNITS: str = "mm/s^2"

# LSL outlet names (Lab Streaming Layer integration)
LSL_OUTLETS: list[str] = ["EEG", "Accelerometer", "Quality", "Markers"]

# Supported NE file formats
FILE_FORMATS: list[str] = ["easy", "easy.gz", "nedf", "edf"]
FILE_FORMAT_DESCRIPTIONS: dict[str, str] = {
    "easy":    "Native NE ASCII format — raw EEG + markers, nV, tab-separated",
    "easy.gz": "Gzip-compressed .easy file",
    "nedf":    "NE extension of EDF — ASCII header + binary data, 24-bit",
    "edf":     "European Data Format — 16-bit, DC-filtered, widely compatible",
}
