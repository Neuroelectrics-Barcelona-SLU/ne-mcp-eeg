import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
from ne_eeg_server.qc import load


class LoaderChecks(unittest.TestCase):
    def test_sparse_montage_preserves_channel_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"recording.info"
            p.write_text("EEG sampling rate: 500 Samples/second\nNumber of EEG channels: 4\nChannel 3: Cz\n")
            info = load.parse_info(str(p))
            self.assertEqual(info["electrodes"], ["CH1", "CH2", "Cz", "CH4"])
            data = load.split_columns(np.zeros((100, 6), dtype=int), info)
            self.assertIsNone(data["acc"])
            self.assertTrue(info["metadata_warnings"])

    def test_missing_required_metadata_and_inconsistent_columns_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"x.info"
            for body in ["Number of EEG channels: 4\n", "EEG sampling rate: 500\n", "EEG sampling rate: 500\nNumber of EEG channels: 4\nEEG units: uV\n"]:
                p.write_text(body)
                with self.assertRaises(ValueError): load.parse_info(str(p))
        for count, acc in [(6,True),(9,False),(7,None)]:
            with self.assertRaises(ValueError): load.split_columns(np.zeros((100,count)), {"n_eeg":4,"acc":acc})

    def test_cache_separates_same_name_size_and_mtime_in_different_directories(self):
        with tempfile.TemporaryDirectory() as d:
            paths=[]
            for name,text in [("a","1\t2\n"),("b","3\t4\n")]:
                p=Path(d)/name/"same.easy"; p.parent.mkdir(); p.write_text(text)
                os.utime(p, ns=(1_700_000_000_000_000_000,)*2); paths.append(str(p))
            self.assertNotEqual(load.cache_path_for(paths[0],d), load.cache_path_for(paths[1],d))
            self.assertEqual(load.load_easy(paths[0],d)[0,0],1)
            self.assertEqual(load.load_easy(paths[1],d)[0,0],3)
