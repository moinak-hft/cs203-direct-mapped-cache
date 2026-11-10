"""Self-checking UART wire-level RTL tests via the shared native/WSL bridge."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.common import run_tool, tool_available


class UARTTests(unittest.TestCase):
    @unittest.skipUnless(tool_available("iverilog") and tool_available("vvp"),
                         "Icarus Verilog (iverilog and vvp) is required")
    def test_wire_protocol_buffering_and_reset(self):
        scratch = ROOT / "work"
        scratch.mkdir(exist_ok=True)
        # Minimum, odd, and even dividers exercise sampling/count boundaries.
        for divider in (4, 7, 8, 434):
            with self.subTest(clocks_per_bit=divider):
                with tempfile.TemporaryDirectory(prefix="uart-test-", dir=scratch) as temp:
                    output = (Path(temp) / "tb_uart.vvp").relative_to(ROOT).as_posix()
                    run_tool("iverilog", ["-g2012", "-s", "tb_uart",
                                          f"-Ptb_uart.CLKS_PER_BIT={divider}",
                                          "-o", output, "rtl/uart.v", "sim/tb_uart.sv"])
                    result = run_tool("vvp", [output])
                    self.assertIn(f"UART PASS: divider={divider}", result.stdout)


if __name__ == "__main__":
    unittest.main()
