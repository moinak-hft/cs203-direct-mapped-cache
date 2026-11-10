"""Full RV32IM execution of the genuine high-resolution batch network."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'python'))
from tools.common import tool_available
from tools.build import run_hd_soc
from neurotile.hd_model import load_hd_model,predict_hd

TOOLS=('iverilog','vvp','riscv64-unknown-elf-gcc','riscv64-unknown-elf-objcopy')


class HighResolutionSoCTests(unittest.TestCase):
    @unittest.skipUnless(all(tool_available(name) for name in TOOLS),
                         'Icarus and bare-metal RISC-V GCC/binutils are required')
    def test_two_input_cpu_reference_and_batched_accelerator(self):
        report=run_hd_soc()
        model=load_hd_model();original=model['sample_input']
        mirror=[original[y*28+27-x] for y in range(28) for x in range(28)]
        expected=[predict_hd(pixels,model) for pixels in [original,mirror]]
        self.assertTrue(report['passed']);self.assertEqual(report['batch_size'],2)
        self.assertEqual(report['predictions'],[row['prediction'] for row in expected])
        self.assertEqual(report['logits'],[row['logits'] for row in expected])
        self.assertEqual(report['kernel_cycles'],13158)
        self.assertEqual(report['macs'],101632)
        self.assertEqual(report['tiles'],211)
        self.assertGreater(report['software_cycles'],0)
        self.assertGreater(report['accelerated_cycles'],report['kernel_cycles'])
        self.assertAlmostEqual(report['speedup_including_transfers'],
                               report['software_cycles']/report['accelerated_cycles'])


if __name__=='__main__':unittest.main()
