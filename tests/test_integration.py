from __future__ import annotations
import json
import random
import sys
import unittest
from tools.common import ROOT,tool_available
sys.path.insert(0,str(ROOT/'python'))
from neurotile.model import load_model,predict
from neurotile.dataset import load_dataset


class NativeCIntegration(unittest.TestCase):
    @unittest.skipUnless(tool_available('gcc'),'Native C compiler required')
    def test_c_matches_python_on_unseen_and_extreme_inputs(self):
        from tools.native_ref import c_infer
        model=load_model();rows,_=load_dataset('test');rng=random.Random(81)
        cases=[model['sample_input'],[0]*64,[16]*64,*rng.sample(rows,20),
               *[[rng.randrange(17) for _ in range(64)] for _ in range(10)]]
        for pixels in cases:
            result=c_infer(pixels,model)
            self.assertEqual(result['logits'],predict(pixels,model)['logits'])
            self.assertEqual(result['hidden'],predict(pixels,model)['hidden'])


class RTLInferenceIntegration(unittest.TestCase):
    @unittest.skipUnless(tool_available('iverilog') and tool_available('vvp'),'Icarus required')
    def test_complete_network_matches_python_for_all_classes_and_extremes(self):
        from tools.infer import rtl_infer
        model=load_model();rows,labels=load_dataset('test')
        cases=[rows[labels.index(i)] for i in range(10)]+[[0]*64,[16]*64]
        for pixels in cases:
            with self.subTest(pixels=pixels[:8]):
                result=rtl_infer(pixels,model)
                expected=predict(pixels,model)
                self.assertEqual(result['hidden'],expected['hidden'])
                self.assertEqual(result['logits'],expected['logits'])
                self.assertEqual(result['kernel_cycles'],630)
                self.assertEqual(result['macs'],2368)
                self.assertEqual(result['tiles'],11)
                self.assertGreater(result['transaction_cycles'],result['kernel_cycles'])

    @unittest.skipUnless(all(tool_available(t) for t in ['iverilog','vvp','riscv64-unknown-elf-gcc',
                          'riscv64-unknown-elf-objcopy']),'RISC-V GCC/binutils and Icarus required')
    def test_real_riscv_firmware_boots_and_compares_inference_paths(self):
        from tools.build import run_soc
        result=run_soc()
        expected=predict(load_model()['sample_input'],load_model())
        self.assertTrue(result['passed'])
        self.assertEqual(result['logits'],expected['logits'])
        self.assertEqual(result['kernel_cycles'],630)
        self.assertGreater(result['software_cycles'],0)
        self.assertGreater(result['accelerated_cycles'],result['kernel_cycles'])


if __name__=='__main__':unittest.main()
