import unittest
import numpy as np
from ne_eeg_server.qc import classify
from .synthetic import metric_fixture


class Intervals(unittest.TestCase):
    def test_channel_majorities(self):
        self.assertEqual(classify.segments(np.zeros((10, 1), int)), [(0, 10, "SIGNAL")])
        self.assertEqual(classify.segments(np.array([[10, 0, 0]] * 10)), [(0, 10, "SIGNAL")])

    def test_short_failure_is_not_absorbed_into_signal(self):
        c = np.zeros((21, 4), int)
        c[10] = classify.CODE["saturated"]
        self.assertEqual(classify.segments(c), [(0, 10, "SIGNAL"), (10, 11, "DRIFT/SAT"), (11, 21, "SIGNAL")])

    def test_blocks_use_real_bounds(self):
        m = metric_fixture(ne=21)
        r = classify.classify(m)
        b = classify.blocks(r["c"], r, m)
        np.testing.assert_array_equal(b["start_s"], [0, 600])
        np.testing.assert_array_equal(b["end_s"], [600, 630])
        for bad in [0, -1, 15, 610, float("nan")]:
            with self.assertRaises(ValueError):
                classify.blocks(r["c"], r, m, bad)
