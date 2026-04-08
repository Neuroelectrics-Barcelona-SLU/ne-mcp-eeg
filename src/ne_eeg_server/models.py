"""
Pydantic models for ne-eeg-server — EEG analysis data types only.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    ENOBIO_8 = "Enobio 8"
    ENOBIO_20 = "Enobio 20"
    ENOBIO_32 = "Enobio 32"
    STARSTIM_8 = "Starstim 8"
    STARSTIM_20 = "Starstim 20"
    STARSTIM_32 = "Starstim 32"


class SignalQuality(str, Enum):
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class Marker(BaseModel):
    time_s: float
    label: str
    code: Optional[int] = None


class ChannelStats(BaseModel):
    """Per-channel EEG summary statistics (µV)."""
    channel: str
    mean_uv: float
    std_uv: float
    min_uv: float
    max_uv: float


class ChannelQC(BaseModel):
    """Per-channel QC result."""
    passed: bool
    rms_raw_uv: float
    rms_notch_uv: float
    rms_filtered_uv: float
    kurtosis: float
    event_rate_hz: float
    line_power_db: float
    psd_peak_snr_db: Optional[float] = None
    flags: dict[str, bool] = {}


class FileInfo(BaseModel):
    """Metadata extracted from an EEG file."""
    file_path: str
    file_name: str
    format: str
    num_channels: int
    channel_labels: list[str]
    sampling_rate_hz: int
    duration_s: float
    device: str
    file_size_bytes: int


class BandPowers(BaseModel):
    """Absolute and relative band powers for a channel."""
    absolute_uv2: dict[str, float]
    relative_pct: dict[str, float]


class ChannelAnalysis(BaseModel):
    """Full analysis result for a single channel."""
    mean_uv: float
    std_uv: float
    band_powers: BandPowers
    peak_alpha_frequency_hz: Optional[float] = None
    alpha_theta_ratio: Optional[float] = None
    qc: Optional[ChannelQC] = None
