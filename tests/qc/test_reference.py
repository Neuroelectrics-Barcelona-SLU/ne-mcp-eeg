import unittest
import numpy as np
from ne_eeg_server.qc import classify, metrics
from .synthetic import metric_fixture


class ReferenceChecks(unittest.TestCase):
    def test_unused_inputs_do_not_create_hum_outliers(self):
        m = metric_fixture(nch=20)
        m["full_rms"][:, 4:] = .5
        m["hum_rms"][:, :4] = 30.
        r = classify.classify(m)
        np.testing.assert_array_equal(r["c"][:, :4], classify.CODE["hum_elevated"])

    def test_unused_inputs_do_not_hide_residual_outlier(self):
        m = metric_fixture(nch=20)
        m["full_rms"][:, 4:] = .5
        m["resid_rms"][:] = 1000.
        m["resid_rms"][:, :4] = [10, 10, 10, 100]
        r = classify.classify(m)
        np.testing.assert_array_equal(r["c"][:, 3], classify.CODE["bad_channel"])
        np.testing.assert_array_equal(r["c"][:, :3], classify.CODE["clean"])

    def test_insufficient_reference_and_zero_acc_baseline_are_unassessed(self):
        m = metric_fixture(nch=3)
        m["hum_rms"][:, 0] = 30.
        m["corr_med"][:] = 1.; m["cm_rms"][:] = 100.; m["corr_common"][:] = 1.
        r = classify.classify(m)
        self.assertFalse(r["relative_available"].any())
        self.assertFalse(r["cm_ep"].any())
        self.assertFalse(r["motion_available"])
        self.assertEqual(r["c"][0, 0], classify.CODE["hum_elevated"])

    def test_low_amplitude_and_long_constant_runs_are_excluded(self):
        m = metric_fixture()
        m["full_rms"][0, 0] = 1.5
        m["const_run_s"][0, 1] = 1.
        np.testing.assert_array_equal(metrics.reference_candidates(m)[0], [False, False, True, True])
