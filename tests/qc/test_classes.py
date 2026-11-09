import unittest
from ne_eeg_server.qc import classify
from .synthetic import metric_fixture


class ClassRules(unittest.TestCase):
    def test_each_exclusive_class_has_a_reachable_case(self):
        cases = {
            "clean": {}, "hum_elevated": {"hum_rms":20}, "hum_severe":{"hum_rms":60},
            "hf_noise":{"hf_rms":9}, "motion":{"full_rms":120,"acc_1s_max":[10,10,10,100]},
            "bad_channel":{"full_rms":151},
            "common_mode":{"corr_med":1,"cm_rms":20,"corr_common":1},
            "drift":{"raw_rms":2000}, "open_input":{"full_rms":1},
            "flatline":{"const_run_s":1}, "saturated":{"sat_frac":.01},
        }
        for expected, values in cases.items():
            with self.subTest(expected=expected):
                m=metric_fixture(ne=4); m["raw_rms"][:]=200
                for key,val in values.items(): m[key][:]=val
                r=classify.classify(m)
                self.assertTrue((r["c"][-1]==classify.CODE[expected]).all())

    def test_precedence_with_cooccurring_patterns(self):
        m=metric_fixture(ne=4)
        m["acc_1s_max"][:]=[10,10,10,100]
        m["full_rms"][:]=151; m["raw_rms"][:]=200
        m["hum_rms"][:]=60; m["hf_rms"][:]=9
        steps=[("bad_channel",{}),
               ("common_mode",{"corr_med":1,"cm_rms":20,"corr_common":1}),
               ("drift",{"raw_rms":2000}), ("open_input",{"full_rms":1}),
               ("flatline",{"const_run_s":1}), ("saturated",{"sat_frac":.01})]
        for expected,values in steps:
            for key,val in values.items(): m[key][:]=val
            self.assertTrue((classify.classify(m)["c"][-1]==classify.CODE[expected]).all(),expected)

    def test_strict_and_inclusive_boundaries(self):
        m=metric_fixture()
        m["hum_rms"][:]=10; m["hf_rms"][:]=8; m["full_rms"][:]=150
        self.assertTrue(classify.classify(m)["unflagged"].all())
        m["hum_rms"][:]=50
        self.assertTrue((classify.classify(m)["c"]==classify.CODE["hum_elevated"]).all())
        m["ddc_mV"][:]=-50
        self.assertTrue((classify.classify(m)["c"]==classify.CODE["drift"]).all())
