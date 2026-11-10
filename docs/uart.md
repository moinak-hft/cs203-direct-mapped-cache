# Board-neutral UART

`rtl/uart.v` implements `neurotile_uart`: a synthesizable full-duplex UART
with 8 data bits, no parity, one stop bit and least-significant bit first.
It needs a clock and reset, and connects to the board's logic-level serial
RX/TX pins. Board clocking, pins, voltage standards and constraints belong
in the board integration.

`CLKS_PER_BIT` is an integer clock divider, with supported values **>= 4**.
Baud rate is `clock_hz / CLKS_PER_BIT`. The default 434 gives approximately
115207 baud at 50 MHz, suitable for a nominal 115200-baud host. Choose a
divider with low baud error for the actual board clock. Reset is synchronous
and active low; the idle TX level is high.

TX accepts a byte on a rising edge when `tx_valid && tx_ready`. Hold
`tx_valid` and `tx_data` stable until that edge. `tx_ready` is low while
serializing the start, data and stop bits, so backpressure is explicit.
The caller can hold a pending next byte throughout the current frame.

RX passes through two synchronization flip-flops marked `ASYNC_REG`. The
receiver confirms the start bit halfway through its duration, samples each
data bit at its center, and requires a high stop sample. A low stop sample
discards the frame; a short false start returns to idle. This is a single
center-sample receiver rather than an oversampling/majority-vote design.

`rx_valid` and `rx_data` hold one received byte until a rising edge with
`rx_ready`. If a new valid frame completes while that byte remains held,
the old byte is preserved and `overrun` becomes sticky until reset. A ready
handshake on the same edge as a new valid frame frees the slot and accepts
the new byte. Framing errors do not overwrite buffered data or assert
overrun. There is no RTS/CTS flow control; firmware or a host protocol must
pace traffic if the receiver cannot keep up.

Run `python -m unittest discover -s tests -p test_uart.py -v` to compile and
simulate the self-checking bench through the shared native/WSL tool helper.
It checks decoded TX bits and the ready/valid protocol, RX data holding,
false starts, invalid stops, sticky overrun, recovery and reset at minimum,
odd, even and default dividers. These simulations verify digital behavior; board
baud tolerance and signal integrity require hardware testing.
