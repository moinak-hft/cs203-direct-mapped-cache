# Board bring-up and physical validation

The interactive UART commands in this guide use the legacy 8×8 UCI model.
The v2 browser and HD inference bench use the separate 28×28 MNIST model.
To build its CPU-driven benchmark image, run `python tools/build.py hd-firmware`
and select `build/hd_firmware.hex` as the top's `MEM_FILE`. That image runs a
two-input correctness/performance benchmark and reports `HD_SOC_RESULT`; it is
not an interactive high-resolution UART service. The physical board path is
still unverified. The simulated HD benchmark enables the CPU's fast multiplier
and compiles C with `-O2`; see `reports/hd_soc.json` for its exact configuration.

The board-neutral top is `neurotile_fpga_top`. CPU, UART protocol and inference
have been tested together in RTL simulation. A board has not been selected or
programmed; no pin file, clock frequency achievement or resource fit is claimed.

## Prepare the source and firmware

```sh
python tools/build.py interactive
python tools/build.py uart-soc
```

Add these sources to the vendor project:

```text
third_party/picorv32/picorv32.v
rtl/mac_pe.v
rtl/neurotile_accel.v
rtl/neurotile_soc.v
rtl/uart.v
rtl/neurotile_fpga_top.v
```

Set the top's `CLK_HZ` parameter to the actual input clock and `BAUD` to the host
baud, default115200. Integer `CLK_HZ/BAUD` must be at least4. The default50MHz
uses divider434, about115207baud. Add `build/interactive.hex` as a memory
initialization file, preserving or adjusting the top's `MEM_FILE` path according
to the vendor tool's working directory.

Provide board-specific constraints for `clk`, active-low `resetn`, `uart_rx`,
`uart_tx`, `led_done` and `led_error`. Use the board's schematic and vendor pin
definitions. The top synchronizes reset release; UART RX has two synchronizer
stages. Use an appropriate logic-level USB/UART interface and the actual board
I/O voltage. These details cannot be inferred without a board model.

## Implementation considerations

The SoC has128KiB initialized RAM. Operand/result memories have asynchronous
reads and multiple ports serving the4×4 tile. Generic RTL synthesis passes,
but this interface does not imply a single FPGA BRAM instance. Bank the
memories, add pipeline stages or accept register/LUT implementation according
to the target. Re-run the integer/counter tests if latency or scheduling changes.

Review synthesis warnings, inferred memory types, DSP mapping, utilization and
post-route timing. Constrain the input clock explicitly. Physical Fmax and power
require the selected device, implementation flow and measurements. Keep those
results separate from the included generic Yosys statistics.

## Physical protocol

Firmware prints `NEUROTILE READY` followed by a newline. Send one request at a
time:

| Bytes | Meaning |
|---|---|
|0..1|ASCII `NT`|
|2..65|64 pixel values, each0..16, row-major8×8|
|66|XOR of the64 pixel bytes|

The reply is one line beginning `UART_RESULT ` followed by JSON with prediction,
signed logits, kernel cycles and firmware cycles. Bad values/checksum return an
error line and leave the receiver available for the next framed request.
An incomplete request has no timeout in firmware; reset the board to abandon a
truncated frame. The host client's deadline prevents an indefinite host wait.

`led_done` is cleared at the start of a valid inference and set after its reply.
`led_error` indicates a CPU trap, UART overrun or non-success completion code.
The UART has one held receive byte; requests are stop-and-wait, not pipelined.

```sh
python -m pip install -r requirements-hardware.txt
python tools/serial_client.py --port COM3
# Linux example:
python tools/serial_client.py --port /dev/ttyUSB0
```

The client verifies the returned prediction and all logits against the bundled
Python integer reference. It is included for bring-up; physical execution is
unverified until a real board is connected and tested. The browser's RTL backend
uses simulation and does not silently connect to a serial port.
