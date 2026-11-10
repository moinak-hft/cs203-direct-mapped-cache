"""Check actual high-resolution C/RTL outputs and K-tail/batch scheduling."""
from __future__ import annotations
import copy
from pathlib import Path
import random
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'python'))
from tools.common import tool_available
from tools.hd_infer import rtl_infer_hd_batch,c_infer_hd_batch
from neurotile.hd_model import load_hd_model,predict_hd


class HighResolutionBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.model=load_hd_model()

    def test_invalid_batches_and_pixels_are_rejected_before_execution(self):
        for batch in [[],[[0]*784]*3,[[0]*783],[[17]*784],[[True]*784]]:
            with self.subTest(size=len(batch)):
                with self.assertRaises(ValueError):rtl_infer_hd_batch(batch,self.model)

    @unittest.skipUnless(tool_available('gcc'),'Native C compiler required')
    def test_actual_native_c_hidden_logits_and_batch_rows(self):
        rng=random.Random(2026)
        cases=[self.model['sample_input'],[0]*784,[16]*784,
               [rng.randrange(17) for _ in range(784)]]
        for first in range(0,len(cases),2):
            batch=cases[first:first+2];result=c_infer_hd_batch(batch,self.model)
            self.assertEqual(result['batch_size'],2)
            self.assertEqual(result['hidden'],[predict_hd(x,self.model)['hidden'] for x in batch])
            self.assertEqual(result['logits'],[predict_hd(x,self.model)['logits'] for x in batch])

    @unittest.skipUnless(tool_available('iverilog') and tool_available('vvp'),'Icarus Verilog required')
    def test_two_digits_reuse_weights_and_hardware_launches(self):
        first=self.model['sample_input'];second=[0]*784
        single=rtl_infer_hd_batch([first],self.model)
        batch=rtl_infer_hd_batch([first,second],self.model)
        self.assertEqual(batch['predictions'],[predict_hd(x,self.model)['prediction'] for x in [first,second]])
        self.assertEqual(batch['logits'][0],single['logits'][0])
        self.assertEqual(batch['kernel_cycles'],13158)
        self.assertEqual(batch['kernel_cycles'],single['kernel_cycles'])
        self.assertEqual(batch['macs'],2*50816)
        self.assertEqual(batch['tiles'],211)
        self.assertEqual(batch['launches'],14)
        self.assertLess(batch['transaction_cycles'],2*single['transaction_cycles'])
        self.assertGreater(batch['transaction_cycles'],single['transaction_cycles'])

    @unittest.skipUnless(tool_available('iverilog') and tool_available('vvp'),'Icarus Verilog required')
    def test_signed_partial_sums_and_final_sixteen_pixel_k_tail(self):
        fixture=copy.deepcopy(self.model)
        fixture['w1']=[0]*(784*64);fixture['b1']=[0]*64
        fixture['w2']=[0]*(64*10);fixture['b2']=[0]*10
        fixture['hidden_shift']=1
        # Negative first-block sum must be combined with the second block
        # before ReLU/shift. The last16-pixel K block must not be dropped.
        fixture['w1'][0*64+0]=-8;fixture['w1'][64*64+0]=9
        fixture['w1'][768*64+1]=4;fixture['w1'][783*64+2]=7
        fixture['w2'][0*10+0]=3;fixture['w2'][1*10+1]=-5
        fixture['w2'][2*10+2]=11;fixture['b2'][4]=-9
        image=[0]*784;image[0]=16;image[64]=16;image[768]=5;image[783]=3
        expected=predict_hd(image,fixture)
        self.assertEqual(expected['hidden'][:3],[8,10,10])
        result=rtl_infer_hd_batch([image,[0]*784],fixture)
        self.assertEqual(result['hidden'][0][:3],[8,10,10])
        self.assertEqual(result['logits'][0],expected['logits'])
        self.assertEqual(result['logits'][0][:3],[24,-50,110])
        self.assertEqual(result['kernel_cycles'],13158)


if __name__=='__main__':unittest.main()
