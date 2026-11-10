`timescale 1ns/1ps
/* Board-neutral UART: 8 data bits, no parity, one stop bit, LSB first.
 * CLKS_PER_BIT >= 4. A held RX byte is preserved on overrun.
 */
module neurotile_uart #(
    parameter integer CLKS_PER_BIT = 434
) (
    input wire clk,
    input wire resetn,
    input wire rx,
    output reg tx,
    input wire tx_valid,
    input wire [7:0] tx_data,
    output wire tx_ready,
    output reg rx_valid,
    output reg [7:0] rx_data,
    input wire rx_ready,
    output reg overrun
);
    localparam integer COUNTER_BITS = $clog2(CLKS_PER_BIT);
    localparam [1:0] IDLE = 2'd0, START = 2'd1, DATA = 2'd2, STOP = 2'd3;
    reg [1:0] tx_state;
    reg [COUNTER_BITS-1:0] tx_count;
    reg [2:0] tx_bit;
    reg [7:0] tx_shift;

    /* Only the synchronized signal is consumed by the receiver FSM. */
    (* ASYNC_REG = "TRUE" *) reg rx_meta;
    (* ASYNC_REG = "TRUE" *) reg rx_sync;
    reg [1:0] rx_state;
    reg [COUNTER_BITS-1:0] rx_count;
    reg [2:0] rx_bit;
    reg [7:0] rx_shift;

    assign tx_ready = resetn && tx_state == IDLE;

`ifndef SYNTHESIS
    initial begin
        if (CLKS_PER_BIT < 4)
            $fatal(1, "neurotile_uart requires CLKS_PER_BIT >= 4");
    end
`endif

    always @(posedge clk) begin
        if (!resetn) begin
            tx <= 1'b1;
            tx_state <= IDLE;
            tx_count <= 0;
            tx_bit <= 0;
            tx_shift <= 0;
        end else begin
            case (tx_state)
                IDLE: begin
                    tx <= 1'b1;
                    if (tx_valid) begin
                        tx_shift <= tx_data;
                        tx <= 1'b0;
                        tx_count <= CLKS_PER_BIT - 1;
                        tx_bit <= 0;
                        tx_state <= START;
                    end
                end
                START: begin
                    if (tx_count != 0) tx_count <= tx_count - 1'b1;
                    else begin
                        tx <= tx_shift[0];
                        tx_count <= CLKS_PER_BIT - 1;
                        tx_state <= DATA;
                    end
                end
                DATA: begin
                    if (tx_count != 0) tx_count <= tx_count - 1'b1;
                    else begin
                        tx_count <= CLKS_PER_BIT - 1;
                        if (tx_bit == 7) begin
                            tx <= 1'b1;
                            tx_state <= STOP;
                        end else begin
                            tx_bit <= tx_bit + 1'b1;
                            tx <= tx_shift[tx_bit + 1'b1];
                        end
                    end
                end
                STOP: begin
                    if (tx_count != 0) tx_count <= tx_count - 1'b1;
                    else tx_state <= IDLE;
                end
                default: begin tx <= 1'b1; tx_state <= IDLE; end
            endcase
        end
    end

    always @(posedge clk) begin
        if (!resetn) begin
            rx_meta <= 1'b1;
            rx_sync <= 1'b1;
            rx_state <= IDLE;
            rx_count <= 0;
            rx_bit <= 0;
            rx_shift <= 0;
            rx_valid <= 1'b0;
            rx_data <= 0;
            overrun <= 1'b0;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;
            if (rx_valid && rx_ready) rx_valid <= 1'b0;
            case (rx_state)
                IDLE: begin
                    if (!rx_sync) begin
                        rx_count <= (CLKS_PER_BIT / 2) - 1;
                        rx_state <= START;
                    end
                end
                START: begin
                    if (rx_count != 0) rx_count <= rx_count - 1'b1;
                    else if (!rx_sync) begin
                        rx_count <= CLKS_PER_BIT - 1;
                        rx_bit <= 0;
                        rx_state <= DATA;
                    end else rx_state <= IDLE;
                end
                DATA: begin
                    if (rx_count != 0) rx_count <= rx_count - 1'b1;
                    else begin
                        rx_shift[rx_bit] <= rx_sync;
                        rx_count <= CLKS_PER_BIT - 1;
                        if (rx_bit == 7) rx_state <= STOP;
                        else rx_bit <= rx_bit + 1'b1;
                    end
                end
                STOP: begin
                    if (rx_count != 0) rx_count <= rx_count - 1'b1;
                    else begin
                        /* Low stop bit: discard frame, retain buffered byte. */
                        if (rx_sync) begin
                            if (!rx_valid || rx_ready) begin
                                rx_data <= rx_shift;
                                rx_valid <= 1'b1;
                            end else overrun <= 1'b1;
                        end
                        rx_state <= IDLE;
                    end
                end
                default: rx_state <= IDLE;
            endcase
        end
    end
endmodule
