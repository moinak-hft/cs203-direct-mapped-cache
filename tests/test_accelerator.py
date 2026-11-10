"""Compile and run the RTL's independently calculated matrix scoreboard."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
try:
    from tools.common import run_tool, tool_available
except ImportError:
    def tool_available(name):
        return bool(os.environ.get(name.upper()) or shutil.which(name))

    def run_tool(name, args, cwd=ROOT):
        executable = os.environ.get(name.upper()) or shutil.which(name)
        return subprocess.run([executable, *map(str, args)], cwd=cwd,
                              capture_output=True, text=True, check=True)


class AcceleratorRTLTests(unittest.TestCase):
    @unittest.skipUnless(tool_available("iverilog") and tool_available("vvp"),
                         "Icarus Verilog (iverilog and vvp) is required")
    def test_randomized_integer_matrix_engine_and_mmio(self):
        scratch = ROOT / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="accel-test-", dir=scratch) as temp:
            executable = Path(temp) / "tb_accel.vvp"
            # Relative paths work for both native tools and tools.common's WSL bridge.
            output = executable.relative_to(ROOT).as_posix()
            run_tool("iverilog", ["-g2012", "-s", "tb_accel", "-o", output,
                                  "rtl/mac_pe.v", "rtl/neurotile_accel.v",
                                  "sim/tb_accel.sv"], cwd=ROOT)
            result = run_tool("vvp", [output], cwd=ROOT)
            stdout = result.stdout if hasattr(result, "stdout") else str(result)
            self.assertIn("ACCELERATOR PASS:", stdout)


if __name__ == "__main__":
    unittest.main()
