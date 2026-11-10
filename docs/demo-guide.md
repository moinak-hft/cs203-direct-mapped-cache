# Running and presenting NeuroTile

For the upgraded v2 interface, start `python tools/serve.py` and open
http://127.0.0.1:8000. The main editor is now a 128×64 canvas. Load the first
two-digit example (72), try reference/C/RTL, inspect both detected boxes and
28×28 crops, upload a PNG/JPEG, then try brush/eraser/undo and a manual split.
Leading zeros are preserved. An empty canvas returns no forced digit.
`python tools/benchmark_hd.py` regenerates the measured batching and synthetic
pair evaluation. See [highres-vision.md](highres-vision.md) and
[highres-hardware.md](highres-hardware.md) for v2 details. The original 8×8
commands below remain available through their legacy CLI/API routes.

Run these commands from the repository root, the directory containing `tools/`,
`rtl/`, and `web/`. Commands use Python rather than shell-specific build syntax.
Use the Python 3 executable available on your system; on systems where its name
is `python3`, replace the initial `python` in each command with `python3`.

The committed model, examples, Python reference, architecture models, and HTTP
server need only Python's standard library. A native C compiler enables the C
backend; Icarus enables RTL inference. RISC-V GCC/binutils enable the firmware
and CPU experiments. NumPy is required only for retraining, and pyserial only
for the optional physical UART client.

## Check the environment

```text
python tools/build.py doctor
```

The JSON output shows the command used for each tool, or `null` when missing.
The portable helper prefers native tools. On Windows it can also use an
installed WSL Ubuntu toolchain; `NEUROTILE_WSL_DISTRO` selects another distro.
Individual tool executables can be selected with environment variables such
as `IVERILOG`, `VVP`, `GCC`, and `RISCV64_UNKNOWN_ELF_GCC`.

The required hardware verification commands are `iverilog`, `vvp`,
`riscv64-unknown-elf-gcc`, and `riscv64-unknown-elf-objcopy`; the native backend
uses `gcc`. Generic structural synthesis additionally uses `yosys`. Missing
tools are reported rather than replaced by fabricated results.

## Start the local interface

```text
python tools/serve.py --host 127.0.0.1 --port 8000
```

Open [NeuroTile locally](http://127.0.0.1:8000/). Keep this terminal running;
Ctrl+C stops the server. The backend selector marks unavailable backends. The
server stays on loopback with this command and does not publish the project.

The three tabs have different scopes:

| Tab | What actually executes |
|---|---|
| Inference: Python | Exact integer reference, without hardware simulation |
| Inference: C | Native C executable, checked against the reference |
| Inference: RTL | Icarus simulates the real Verilog accelerator and inference bench |
| Memory lab | Python timing model plus the separately tested trained RTL selector |
| Security lab | Python cache event experiment plus a separately tested RTL event cache |

The saved SoC benchmark shown below inference comes from its generated report;
it is not a live CPU run triggered by every browser click.

## A meaningful live demo

1. Start with the provided dataset example and select **Verilog / Icarus
   simulation**. Run inference. Show the predicted digit, the reference check,
   actual signed logits, and hidden activations. Raw logits are not
   probabilities. The committed example's expected label and prediction are 0.
2. Load the next example and run again. Paint or erase some pixels to show that
   the input changes the real calculation. Editing invalidates the preceding
   output. Explain that the training data consists of normalized 8×8 digits;
   arbitrary sketches are not guaranteed to classify correctly.
3. Run the same unchanged input through **C** and **Python**. Class scores and
   hidden activations should agree exactly. Host milliseconds depend on machine
   load, simulator startup, and process overhead; they are not FPGA latency.
4. Show the saved SoC experiment. It compares two implementations running on the
   same PicoRV32 CPU: C arithmetic versus C controlling the original accelerator.
   Explain the difference between total CPU cycles and accelerator kernel cycles
   using the section below.
5. Open **Memory lab** and compare fixed stride, fixed rule, and the learned
   selector. The default learned selector ties the rule and loses to stride in
   aggregate. This makes a useful discussion about baselines, workload choice,
   and how training-label accuracy differs from application speed.
6. Open **Security lab**. Explain the controlled observer experiment, its chance
   baseline, and the separate benign trace showing the loss of associativity.
   State the fixed-schedule threat model; the result is not a general security
   proof or a cryptographic key recovery experiment.

For a hardware-focused demonstration, follow the browser view with the SoC and
UART commands below. The interactive FPGA wrapper is implemented and verified
in simulation; physical FPGA deployment requires the board work described in
[architecture.md](architecture.md).

## Run the actual experiments from the terminal

| Command | Result and scope |
|---|---|
| `python tools/build.py accel` | Self-checking randomized matrix/MMIO RTL bench |
| `python tools/build.py infer` | Complete standalone RTL network inference and exact Python comparison |
| `python tools/infer.py` | The same RTL inference using the committed example |
| `python tools/build.py native` | Build the host C reference executable |
| `python tools/build.py firmware` | Build benchmark firmware, ELF, binary, and RAM hex |
| `python tools/build.py soc` | Boot real RISC-V firmware in simulation; regenerate `reports/soc.json` |
| `python tools/build.py soc --vcd` | Run the SoC and additionally write `build/soc.vcd` |
| `python tools/labs.py` | Regenerate modeled experiments in `reports/labs.json` |
| `python tools/build.py labs` | Run the independent cache/selector RTL component bench |
| `python tools/build.py interactive` | Build interactive UART firmware and `build/interactive.hex` |
| `python tools/build.py uart-soc` | Run wire-level UART, CPU, and accelerator regression; regenerate `reports/uart_soc.json` |
| `python tools/build.py synth` | Regenerate generic Yosys RTL structure/statistics reports |

`tools/infer.py --input` additionally accepts a JSON file containing an array
of exactly 64 integers in 0–16. The default invocation needs no custom file.
The HTTP API validates the same range and length.

The SoC benchmark prints a JSON report with a passing flag, prediction, label,
software/accelerated cycle counts, kernel cycles, and logits. The UART regression
checks boot output, header noise and resynchronization, invalid-checksum
rejection, and two valid requests with exact reference logits. Its baud divider
is shortened for simulation. It does not require a board or USB adapter.

## Explain the performance figures correctly

The saved bundled-example SoC report records **162,378 CPU cycles** for C
arithmetic and **78,422 CPU cycles** with accelerator calls, approximately
**2.07× speedup**. These intervals include CPU operand copies, accelerator
polling, result reads, bias addition, and activation processing. They exclude
boot and the subsequent report transmission. Rerunning after firmware changes
regenerates the report; use the new report's numbers when presenting changes.

The **630 kernel cycles** measure only the arithmetic engine's clear, MAC, and
store phases across both layers. They exclude operand loading, result traffic,
and CPU instructions. Do not divide the C cycle count by 630 and call that the
application speedup.

The standalone RTL browser backend additionally reports **5,678 transaction
cycles** for its direct testbench bus driver. This includes that driver's data
movement and sequencing, but no CPU execution. It is a different experiment
from the approximately 78,000-cycle RISC-V interval. The interactive UART
firmware's `firmware_cycles` uses its own timed C path and excludes receiving
the request and printing the response.

The network performs **2,368 useful MACs** in **11 output tiles**. A single digit
uses M=1, so one row of the 4×4 array is active. The engine also supports and
tests larger matrices; the current UI does not expose batch inference. None of
these simulation counts imply an achieved FPGA clock, power, or energy result.

## Run the checks and preserve evidence

For the complete regression, with missing tools treated as a failure:

```text
python tools/check.py --require-tools --synth
```

This runs model/data/quantization checks, randomized accelerator verification,
native C and complete RTL inference comparisons, RISC-V firmware, UART/protocol
checks, and the independent architecture labs. It regenerates reviewable JSON
and logs under `reports/`; `--synth` adds generic Yosys checks. Read the reported
skipped-test list: a successful software-only test run does not establish RTL
verification. For an environment without the hardware tools, use
`python tools/check.py` and report its skipped checks explicitly.

The main evidence files are:

| File | What it establishes |
|---|---|
| `reports/verification.json` and `reports/tests.log` | Tests executed, failures/errors/skips, and tool versions |
| `reports/inference.json` | Exact standalone RTL inference result and cycle scope |
| `reports/soc.json` | Compiled C running on PicoRV32, including accelerator transfer overhead |
| `reports/uart_soc.json` | Full UART wire/firmware/accelerator simulation |
| `reports/labs.json` | Actual modeled policy and isolation experiments |
| `reports/synthesis.json` and `reports/synthesis.log` | Generic structural synthesis; no FPGA utilization or timing result |
| `models/metrics.json` and `data/provenance.json` | Model evaluation and official writer-disjoint dataset provenance |

## Retrain and rebuild

The bundled pretrained model makes retraining optional. To reproduce the fixed
training schedule:

```text
python -m pip install -r requirements-training.txt
python tools/train_model.py --seed 2026 --epochs 180
python tools/check.py --require-tools --synth
```

The trainer reads the bundled official UCI training/test files, fits with NumPy,
calibrates quantization on training activations, and exports model JSON,
metrics, SHA-256, and `firmware/generated/model.h`. The schedule does not use
test-based early stopping. Floating-point training can vary across NumPy/BLAS
environments; the committed integer model is the exact inference contract.

Stop and restart the local server after retraining so its loaded data and
examples are consistent. Rebuild firmware and regenerate saved experiments:

```text
python tools/build.py soc
python tools/build.py uart-soc
```

To try a different training run without replacing the committed model/header:

```text
python tools/train_model.py --seed 2027 --epochs 180 --output-root work/training-2027
```

The alternate output is an offline experiment; the running server and compiled
C backend continue to use the repository's committed model/header until those
artifacts are deliberately replaced and rebuilt.

## Optional physical UART client

The FPGA wrapper accepts a binary 67-byte request: ASCII `NT`, 64 pixels, then
the XOR of pixel bytes. It replies with `UART_RESULT ` followed by JSON and a
newline. The detailed protocol and MMIO map are in
[architecture.md](architecture.md).

Install the optional host dependency only when connecting hardware:

```text
python -m pip install -r requirements-hardware.txt
python tools/serial_client.py --help
```

Select the connected device's actual serial port when invoking the client;
it loads the bundled example by default and checks returned logits against the
integer reference. The browser's RTL option remains a simulator backend and
does not silently switch to a physical board.
