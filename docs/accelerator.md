# NeuroTile integer matrix accelerator

`neurotile_accel` computes `C[M,N] = A[M,K] × B[K,N]`. Inputs are signed
two's-complement 8-bit integers; outputs are signed 32-bit raw sums. Bias,
activation, and requantization belong to the caller. Legal dimensions are
`1 ≤ M ≤ 16`, `1 ≤ N ≤ 64`, and `1 ≤ K ≤ 64`.

## Actual dataflow

Sixteen `mac_pe` instances form a 4×4 **output-stationary parallel MAC array**.
Each output tile retains sixteen partial sums in registers. During one reduction
step, four A elements are broadcast across rows and four B elements down columns.
All active processing elements perform one signed multiply-accumulate. This is
a broadcast array, **not** a nearest-neighbor systolic array. The distinction
matters when comparing routing and timing against a systolic design.

Each tile takes one clear cycle, K MAC cycles, and one store cycle. Partial
edge tiles gate inactive lanes and never write outside the M×N output. Operands
are reused across the sixteen PEs; this implementation reloads them for each
tile and has no overlapping DMA. The maximum raw sum magnitude is 1,048,576 at
K=64, so signed INT32 accumulation cannot overflow for legal inputs.

The memories use synthesizable Verilog arrays with asynchronous reads and
multiple result writes. This favors a simple, transparent simulation design;
mapping onto a particular FPGA's block RAM may require banked storage and a
pipelined read/write schedule. Do not interpret these arrays as a demonstrated
single-BRAM implementation. LUT/DSP/BRAM use and maximum clock must come from
the chosen target's synthesis and implementation reports.

## Bus and register map

The bus uses byte offsets and accepts one transfer on each rising edge where
`bus_valid && bus_ready`. `bus_ready` follows `bus_valid`; the design does not
insert wait states. A held valid signal therefore represents repeated transfers.
All accesses must be 32-bit aligned. Unmapped/unaligned reads return zero.

| Offset | Register | Behavior |
|---|---|---|
| 0x0000 | ID | Read-only `0x4e543031` (NT01) |
| 0x0004 | CONTROL | Write bit 0: start; bit 1: clear sticky done/error |
| 0x0008 | STATUS | Bit 0: busy; bit 1: done; bit 2: error |
| 0x000c | M | Full-width dimension configuration |
| 0x0010 | N | Full-width dimension configuration |
| 0x0014 | K | Full-width dimension configuration |
| 0x0018 | Kernel cycles | Clear, MAC, and store cycles; excludes operand loading |
| 0x001c | Useful MACs | Counts active lanes only |
| 0x0020 | Tile count | Completed 4×4/partial output tiles |
| 0x1000 + 4i | A[i] | 1024 word-addressed signed bytes |
| 0x2000 + 4i | B[i] | 4096 word-addressed signed bytes |
| 0x6000 + 4i | C[i] | 1024 read-only signed 32-bit outputs |

Operands and results are row-major. Each A/B byte occupies a separate 32-bit bus
word; reads return the raw byte zero-extended. Software must interpret its low
byte as signed when required. Operand writes use only `wstrb[0]`; other enabled
bytes have no effect. Configuration writes merge individually enabled bytes.
CONTROL acts only when its low byte is enabled. All-zero write strobes are a
no-op even on invalid addresses.

A valid start snapshots all dimensions and resets counters, done, and error.
START while busy, invalid dimensions, configuration writes while busy, effective
operand writes while busy, writes to read-only registers/C, and unmapped or
unaligned writes set sticky error without corrupting the running calculation.
An operand write with only upper-byte enables is a no-op, including while busy.
Invalid start leaves the preceding counters/results intact. Clearing status while
busy does not cancel computation. `irq` is the done level and remains asserted
until a clear, a valid start, or reset. Concurrent CONTROL clear on the final
store cycle takes precedence over the sticky done bit.

Reset is synchronous, active-low. It aborts computation and clears all control,
configuration, accumulators, and counters. It deliberately does not reset SRAM
contents. A/B must be initialized by software before use; C is valid only for the
last completed command. During a command, C may contain old or partially updated
data. After reset/abort, do not use C until another command completes.

For legal dimensions, with `T = ceil(M/4) × ceil(N/4)`:

```text
kernel_cycles = T × (K + 2)
useful_macs  = M × N × K
tile_count   = T
```

These are accelerator kernel counters. End-to-end latency additionally includes
input/weight writes, bus/CPU overhead, result reads, and activation processing.

## Verification

`sim/tb_accel.sv` computes expected results independently with integer loops. It
checks randomized matrices, negative values and signed extremes, one-element
matrices, partial tiles, maximal dimensions, byte enables, invalid dimensions,
read-only/unmapped/unaligned writes, busy protections, exact counters, sticky
status/IRQ, output bounds, reset during a command, and recovery after reset.

From the project root:

```sh
iverilog -g2012 -s tb_accel -o work/tb_accel.vvp rtl/mac_pe.v rtl/neurotile_accel.v sim/tb_accel.sv
vvp work/tb_accel.vvp
python -m unittest tests.test_accelerator -v
```

The Python wrapper supports the project tool bridge and, standalone, `IVERILOG`
and `VVP` environment variables or executables on PATH. Missing tools skip the
Python test; a passing Python run without the RTL toolchain is not RTL validation.
