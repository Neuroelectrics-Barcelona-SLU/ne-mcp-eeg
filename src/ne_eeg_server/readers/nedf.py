"""
Minimal .nedf reader extracted from NEPy (Neuroelectrics, 2018).

Reads a .nedf file (ASCII XML header + binary EEG data, 24-bit resolution)
and returns arrays compatible with the .easy analysis pipeline.
"""

from __future__ import annotations

import os
import datetime
import xml.etree.ElementTree as ET

import numpy as np


class XmlDictConfig(dict):
    """Convert an ElementTree node into a nested dict."""
    def __init__(self, parent_element):
        if list(parent_element.items()):
            self.update(dict(list(parent_element.items())))
        for element in parent_element:
            if len(element):
                if len(element) == 1 or element[0].tag != element[1].tag:
                    aDict = XmlDictConfig(element)
                else:
                    aDict = {element[0].tag: XmlListConfig(element)}
                if list(element.items()):
                    aDict.update(dict(list(element.items())))
                self.update({element.tag: aDict})
            elif list(element.items()):
                self.update({element.tag: dict(list(element.items()))})
            else:
                self.update({element.tag: element.text})


class XmlListConfig(list):
    def __init__(self, aList):
        for element in aList:
            if len(element):
                if len(element) == 1 or element[0].tag != element[1].tag:
                    self.append(XmlDictConfig(element))
                else:
                    self.append(XmlListConfig(element))
            elif element.text:
                text = element.text.strip()
                if text:
                    self.append(text)


def read_nedf(filepath: str) -> dict:
    """Read a .nedf file and return a dict with EEG data and metadata.

    Returns:
        dict with keys:
            eeg_uV: ndarray [n_samples, n_channels] in µV
            markers: ndarray [n_samples] (int)
            electrodes: list[str] — channel labels
            fs: int — sampling rate
            num_channels: int
            device: str
            start_date: str — ISO format
            start_date_unix_ms: int
            duration_s: float
    """
    if not os.path.isfile(filepath):
        raise ValueError(f"File not found: {filepath}")

    with open(filepath, "rb") as f:
        header_bytes = f.read(10240)
        binary_data = f.read()

    if len(header_bytes) != 10240:
        raise ValueError("truncated NEDF header; expected 10240 bytes")
    xml_str = header_bytes.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        inner_start = xml_str.find(">") + 1
        inner_end = xml_str.rfind("</")
        inner = xml_str[inner_start:inner_end]
        xml_str = "<NEDFRoot>" + inner + "</NEDFRoot>"
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse NEDF header: {e}")
    xmldict = XmlDictConfig(root)

    version = xmldict.get("NEDFversion", "1.4")

    def required_int(mapping, key):
        try:
            return int(mapping[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"missing or invalid NEDF field: {key}") from None

    if xmldict.get("AdditionalChannelStatus", "OFF") != "OFF":
        raise ValueError("NEDF additional-channel tracks are not supported")

    if version == "1.4":
        settings = xmldict.get("EEGSettings")
        if not isinstance(settings, dict):
            raise ValueError("missing NEDF EEGSettings")
        num_channels = required_int(settings, "TotalNumberOfChannels")
        fs = required_int(settings, "EEGSamplingRate")
        n_samples = required_int(settings, "NumberOfRecordsOfEEG")
        steps = xmldict.get("StepDetails") or {}
        device = steps.get("DeviceClass", "Unknown")
        start_ts = required_int(steps, "StartDate_firstEEGTimestamp")
        acc_state = xmldict.get("AccelerometerData")
        if acc_state not in (None, "ON", "OFF"):
            raise ValueError("invalid NEDF AccelerometerData declaration")
        acc_count = required_int(xmldict, "NumberOfChannelsOfAccelerometer") if "NumberOfChannelsOfAccelerometer" in xmldict else (3 if acc_state == "ON" else 0)
        if acc_count not in (0, 3) or (acc_state is not None and (acc_state == "ON") != bool(acc_count)):
            raise ValueError("inconsistent or unsupported NEDF accelerometer layout")
        has_acc = bool(acc_count)
        has_extra_tracks = "STIMSettings" in xmldict
    elif version == "1.2":
        settings = xmldict
        num_channels = required_int(settings, "TotalNumberOfChannels")
        fs = required_int(settings, "EEGSamplingRate")
        n_samples = required_int(settings, "NumberOfRecordsOfEEG")
        device = "Unknown"
        start_ts = int(xmldict.get("StartDateEEG", 0))
        has_acc = False
        has_extra_tracks = False
    else:
        raise ValueError(f"Unsupported NEDF version: {version}")

    if num_channels < 1 or fs <= 0 or n_samples < 1:
        raise ValueError("NEDF channel count, sampling rate, and sample count must be positive")
    try:
        electrodes_num = {int(k[7:]): v for k, v in settings["EEGMontage"].items()}
    except (KeyError, AttributeError, TypeError, ValueError):
        raise ValueError("missing or invalid NEDF EEGMontage") from None
    if set(electrodes_num) != set(range(1, num_channels + 1)):
        raise ValueError("NEDF montage and channel count disagree")
    electrodes = [electrodes_num[k] or f"CH{k}" for k in range(1, num_channels + 1)]
    duration_s = n_samples / fs
    expected_bytes = n_samples * (3 * num_channels * (3 if has_extra_tracks else 1) + 4)
    if has_acc:
        expected_bytes += ((n_samples + 4) // 5) * 6
    if len(binary_data) != expected_bytes:
        raise ValueError(f"NEDF payload length mismatch: expected {expected_bytes} bytes, found {len(binary_data)}")

    # Parse binary data
    nedf_bytes = bytearray(binary_data)
    pos = -1

    def get_byte():
        nonlocal pos
        pos += 1
        return nedf_bytes[pos]

    eeg_data = []
    markers = []
    acc_counter = 5

    for _ in range(n_samples):
        if has_acc:
            if acc_counter == 5:
                acc_counter = 1
                for _ in range(3):
                    b1, b2 = get_byte(), get_byte()
            else:
                acc_counter += 1

        sample = []
        for _ in range(num_channels):
            b1, b2, b3 = get_byte(), get_byte(), get_byte()
            val = b1 * 65536 + b2 * 256 + b3
            if b1 >= 128:
                val = (16777216 * 255) + val - (16777216 * 256)
            val_nv = (val * 2.4 * 1e9) / 6.0 / 8388607.0
            sample.append(val_nv / 1000.0)  # µV
        eeg_data.append(sample)

        # Skip interleaved data tracks if present in the binary stream
        # Skip interleaved extra data tracks if present in the binary stream
        if has_extra_tracks:
            for _ in range(2):
                for _ in range(num_channels):
                    get_byte(); get_byte(); get_byte()

        b1, b2, b3, b4 = get_byte(), get_byte(), get_byte(), get_byte()
        marker = int.from_bytes(bytes((b1, b2, b3, b4)), "big", signed=True)
        markers.append(marker)

    start_date = datetime.datetime.fromtimestamp(start_ts / 1000.0).strftime("%Y-%m-%d %H:%M:%S")

    # Extract extended metadata from header
    step_details = xmldict.get("StepDetails", {}) if version == "1.4" else {}
    eeg_settings = xmldict.get("EEGSettings", xmldict) if version == "1.4" else xmldict

    # Trigger label mapping (e.g., Trigger1=EO, Trigger2=EC)
    trigger_labels = {}
    trig_info = xmldict.get("TriggerInformation", {})
    if isinstance(trig_info, dict):
        for k, v in trig_info.items():
            if k.startswith("Trigger") and v:
                try:
                    trigger_labels[int(k[7:])] = str(v)
                except (ValueError, TypeError):
                    pass

    return {
        "eeg_uV": np.array(eeg_data, dtype="float32"),
        "markers": np.array(markers, dtype="int64"),
        "electrodes": electrodes,
        "fs": fs,
        "num_channels": num_channels,
        "device": device,
        "start_date": start_date,
        "start_date_unix_ms": start_ts,
        "duration_s": duration_s,
        # Extended metadata
        "step_name": step_details.get("StepName", ""),
        "device_id": step_details.get("DeviceID", ""),
        "software_version": step_details.get("SoftwareVersion", ""),
        "firmware_version": step_details.get("FirmwareVersion", ""),
        "communication_type": step_details.get("CommunicationType", ""),
        "line_filter": eeg_settings.get("LineFilterStatus", ""),
        "packets_lost": int(eeg_settings.get("NumberOfPacketsLost", 0) or 0),
        "eeg_units": eeg_settings.get("EEGUnits", "nV"),
        "trigger_labels": trigger_labels,
        "format": "nedf",
        "nedf_version": version,
    }
