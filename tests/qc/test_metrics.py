import unittest
import numpy as np
from ne_eeg_server.qc import classify, metrics
from .synthetic import metric_fixture


class MetricChecks(unittest.TestCase):
    def test_units_against_known_sinusoids(self):
        fs = 500
        t = np.arange(15000) / fs
        # 20 µV RMS at 10 Hz; 100 µV RMS at 50 Hz; 100 mV DC.
        v = 1e8 + 1000 * np.sqrt(2) * (20*np.sin(2*np.pi*10*t) + 100*np.sin(2*np.pi*50*t))
        m = metrics.compute(v[:, None], None, fs, log=None)
        self.assertAlmostEqual(m["dc_mV"][0, 0], 100., places=8)
        self.assertAlmostEqual(m["raw_rms"][0, 0], np.hypot(20, 100), places=6)
        self.assertAlmostEqual(m["hum_rms"][0, 0], 100., places=5)
        self.assertAlmostEqual(m["full_rms"][0, 0], 20., delta=.1)
        self.assertAlmostEqual(m["ddc_mV"][0, 0], 0., places=8)
        self.assertTrue(np.isnan(m["acc_1s_max"][0]))

    def test_accelerometer_units_no_mutation_and_tail(self):
        n = 15017
        t = np.arange(n)/500
        a = np.column_stack([np.ones(n)*100, np.sin(2*np.pi*t)*np.sqrt(2)*250, np.ones(n)*9800])
        before = a.copy()
        m = metrics.compute((10000*np.sin(2*np.pi*10*t))[:, None], a, 500, log=None)
        np.testing.assert_array_equal(a, before)
        self.assertAlmostEqual(m["acc_rms"][0], 250., places=8)
        self.assertAlmostEqual(m["acc_1s_max"][0], 250., places=8)
        self.assertEqual(m["excluded_tail_samples"], 17)

    def test_invalid_input_is_rejected(self):
        x = np.zeros((15000, 1))
        for fs, ep in [(0,30),(100,30),(500,0),(500,5),(500,float("nan"))]:
            with self.assertRaises(ValueError): metrics.compute(x,None,fs,ep,log=None)
        with self.assertRaises(ValueError): metrics.compute(x[:100],None,500,log=None)
        with self.assertRaises(ValueError): metrics.compute(x,np.zeros((15000,2)),500,log=None)
        x[0] = np.nan
        with self.assertRaises(ValueError): metrics.compute(x,None,500,log=None)
        m = metric_fixture(); m["full_rms"][0,0] = np.nan
        with self.assertRaises(ValueError): classify.classify(m)

    def test_rail_and_constant_duration(self):
        v = np.full((15000, 1), 400_000_047, dtype=np.int64)
        m = metrics.compute(v, None, 500, log=None)
        self.assertEqual(m["sat_frac"][0,0], 1.)
        self.assertEqual(m["flat_frac"][0,0], 1.)
        self.assertEqual(m["const_run_s"][0,0], 14999/500)
        self.assertEqual(classify.classify(m)["c"][0,0], classify.CODE["saturated"])
