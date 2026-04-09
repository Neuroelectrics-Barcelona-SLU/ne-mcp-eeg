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

    content = header_bytes.decode("utf-8", errors="replace")
    nedftitle = content[1:content.find(">")]
    if " " in nedftitle:
        nedftitle = nedftitle.split(" ")[0]
    closing_tag = "</" + nedftitle + ">"
    lastindex = content.find(closing_tag)
    if lastindex < 0:
        raise ValueError("Could not find closing tag in NEDF header")
    lastindex += len(closing_tag)
    xml_str = content[:lastindex]

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

    if version == "1.4":
        num_channels = int(xmldict["EEGSettings"]["TotalNumberOfChannels"])
        fs = int(xmldict["EEGSettings"]["EEGSamplingRate"])
        n_samples = int(xmldict["EEGSettings"]["NumberOfRecordsOfEEG"])
        duration_s = float(xmldict["EEGSettings"]["EEGRecordingDuration"])

        electrodes_dict = dict(xmldict["EEGSettings"]["EEGMontage"])
        electrodes_num = {int(k[7:]): v for k, v in electrodes_dict.items()}
        electrodes = [electrodes_num[k] for k in sorted(electrodes_num)]

        device = xmldict.get("StepDetails", {}).get("DeviceClass", "Unknown")
        start_ts = int(xmldict["StepDetails"]["StartDate_firstEEGTimestamp"])

        has_acc = xmldict.get("AccelerometerData", "OFF") == "ON"
        has_extra_tracks = "STIMSettings" in xmldict
    elif version == "1.2":
        num_channels = int(xmldict["TotalNumberOfChannels"])
        fs = int(xmldict["EEGSamplingRate"])
        n_samples = int(xmldict["NumberOfRecordsOfEEG"])
        duration_s = n_samples / fs

        electrodes_dict = dict(xmldict["EEGMontage"])
        electrodes_num = {int(k[7:]): v for k, v in electrodes_dict.items()}
        electrodes = [electrodes_num[k] for k in sorted(electrodes_num)]

        device = "Unknown"
        start_ts = int(xmldict.get("StartDateEEG", 0))
        has_acc = False
        has_extra_tracks = False
    else:
        raise ValueError(f"Unsupported NEDF version: {version}")

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
        marker = b1 * 16777216 + b2 * 65536 + b3 * 256 + b4
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
