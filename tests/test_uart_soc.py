"""Exercise the C parser, RISC-V, MMIO and accelerator over actual UART wires."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from tools.common import tool_available
from tools.build import run_uart_soc
from neurotile.model import load_model, predict

TOOLS = ("iverilog", "vvp", "riscv64-unknown-elf-gcc", "riscv64-unknown-elf-objcopy")


class UARTSoCTests(unittest.TestCase):
    @unittest.skipUnless(all(tool_available(name) for name in TOOLS),
                         "Icarus Verilog and the RISC-V bare-metal compiler are required")
    def test_checksum_rejection_and_two_wire_inferences(self):
        # One invocation compiles firmware and runs the self-checking wire peer.
        report = run_uart_soc()
        model = load_model()
        first = predict(model["sample_input"], model)
        second = predict([0] * 64, model)
        self.assertEqual(report["invalid_frames_rejected"], 1)
        self.assertEqual(report["valid_frames"], 2)
        self.assertEqual(report["prediction"], first["prediction"])
        self.assertEqual(report["logits"], first["logits"])
        self.assertEqual(report["second_result"]["prediction"], second["prediction"])
        self.assertEqual(report["second_result"]["logits"], second["logits"])
        for result in (report, report["second_result"]):
            self.assertEqual(result["kernel_cycles"], 630)
            self.assertGreater(result["firmware_cycles"], result["kernel_cycles"])


if __name__ == "__main__":
    unittest.main()
