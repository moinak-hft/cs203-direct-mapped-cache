import copy
import sys
import unittest
from tools.common import ROOT
sys.path.insert(0,str(ROOT/'python'))
from neurotile.model import load_model,validate_model
from tools.serial_client import encode_frame


class ContractTests(unittest.TestCase):
    def test_models_that_cannot_match_int32_hardware_are_rejected(self):
        model=load_model()
        for field,value in [('hidden_shift',25),('hidden_shift',True)]:
            fixture=copy.deepcopy(model);fixture[field]=value
            with self.assertRaises(ValueError):validate_model(fixture)
        for field in ['b1','b2']:
            fixture=copy.deepcopy(model);fixture[field][0]=2**31-1
            with self.assertRaises(ValueError):validate_model(fixture)
    def test_serial_request_has_exact_size_and_checksum(self):
        pixels=load_model()['sample_input'];frame=encode_frame(pixels)
        self.assertEqual(len(frame),67);self.assertEqual(frame[:2],b'NT')
        checksum=0
        for value in pixels:checksum^=value
        self.assertEqual(frame[2:66],bytes(pixels));self.assertEqual(frame[66],checksum)
        with self.assertRaises(ValueError):encode_frame([17]*64)


if __name__=='__main__':unittest.main()
