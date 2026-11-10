# High-resolution and batched hardware inference

The MNIST model uses 784 real 28×28 input pixels and 64 hidden units. It is not an
upsampled 8×8 classifier. The original 8×8 pipeline remains available separately.

The high-resolution path reuses the existing synthesizable
`neurotile_accel` without enlarging its local memories or its16-bit MMIO map.
The accelerator supports K≤64 per launch; the 784-input layer is scheduled as
twelve 64-input blocks followed by one 16-input block. Each block returns raw
INT32 partial sums. The host or C firmware adds all thirteen sums before adding
bias and applying the hidden shift/ReLU/saturation. Activating each block
separately would compute a different network and is tested against explicitly.

## Real batch reuse

One or two digit crops can be rows of matrix A. Matrix B is the same network
weight block for both. A two-digit batch therefore shares the weight transfers
and accelerator launches instead of invoking two independent networks.

The 4×4 broadcast tile can service both rows concurrently. Kernel counters are
read from the real RTL after every launch:

| Quantity | Single digit | Two-digit batch |
|---|---:|---:|
|Useful MACs|50,816|101,632|
|Launches|14|14|
|4×4 output tiles|211|211|
|Kernel cycles|13,158|13,158|

The first layer costs `(784 + 2×13) × ceil(64/4) = 12,960` cycles. The final
64→10 layer costs `(64+2) × ceil(10/4) = 198` cycles. Each tile has a clear phase,
its K multiply phases and a store phase. These counts are implementation
properties verified by the bench, not estimates based on peak throughput.

The standalone single-digit MMIO driver takes 118,422 cycles including writes,
polling, intermediate readback and final result reads. A two-row batch takes
121,802 cycles. It adds operand/result traffic but reuses all weight transfers,
so it uses fewer cycles than two separate 118,422-cycle invocations. CPU-driven
cycles additionally include RISC-V instruction execution and are reported by
the separate full-SoC benchmark. Image preprocessing is outside both kernel
and standalone MMIO cycle scopes.

## Run the actual implementations

```sh
python tools/hd_infer.py
python tools/hd_infer.py --backend c
python tools/hd_infer.py --input crops.json
```

`crops.json` contains one or two arrays of 784 integer pixel values in 0..16.
Both backends return their own intermediate hidden values and logits, and
compare every value with the Python integer reference. The RTL backend actually
compiles and executes `sim/tb_hd_inference.sv`; no Python-computed outputs are
substituted for RTL outputs. The native C backend compiles
`firmware/hd_reference.c` against the generated MNIST header.

Public Python helpers are:

```python
from tools.hd_infer import rtl_infer_hd_batch, c_infer_hd_batch
report = rtl_infer_hd_batch([first_crop, second_crop])
```

The result has `batch_size`, `predictions`, `hidden`, `logits`, `backend`,
`verified`, `host_elapsed_ms` and a `cycle_scope` description. Actual RTL results
also include `kernel_cycles`, `transaction_cycles`, `macs`, `tiles`, `launches`.
Host elapsed time includes simulator/process overhead and is not hardware
latency.

## Firmware

`firmware/hd_driver.h` implements the same K-blocked scheduling with
`hd_dense_hw_batch(input,weights,out,m,k,n,&cycles,&macs,&tiles)`. It accepts one
or two rows, K≤784 and N≤64. The hardware itself still accepts K≤64; firmware
performs the decomposition and sums the results in software.

`firmware/hd_main.c` benchmarks two inputs on the RISC-V CPU: the official
sample and its horizontal mirror. The mirror is a synthetic correctness
workload, not a labeled accuracy example. It computes a software reference,
executes the batched accelerator driver, checks first-layer sums, hidden values
and logits, and emits a `HD_SOC_RESULT` JSON line before writing the standard
completion register. The root build tool supplies the matching firmware image
and full-system bench target.

Run `python tools/build.py hd-soc` for this full processor simulation. Its
`tb_hd_soc` enables the PicoRV32 fast multiplier (`CPU_FAST_MUL=1`) and builds
firmware with `-O2`. The original legacy SoC benches keep their default slow
multiplier configuration. Both the C and accelerated paths within each
benchmark use the same CPU configuration.

The executed HD run measured3,061,160 software cycles and1,204,060 accelerated
cycles, or2.5424×. Data copies, partial-sum accumulation, activation and control
code are included. The image-segmentation and host-transport stages are not.
The exact report is `reports/hd_soc.json`; this simulation takes several minutes
on a typical development machine. These figures are distinct from standalone
MMIO bench cycles and from the original8×8 benchmark.

These additions do not claim a DMA engine, physical FPGA timing, convolutional
hardware or a sequence-trained recognizer. Canvas segmentation and normalization
produce individual 28×28 crops; classification runs through the selected actual
backend. The larger drawing canvas and the 28×28 model input are distinct
resolutions.
