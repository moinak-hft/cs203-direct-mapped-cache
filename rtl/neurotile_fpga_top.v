`timescale 1ns/1ps
/* Board-neutral top: supply pin/clock constraints for your actual board. */
module neurotile_fpga_top #(
    parameter integer CLK_HZ=50000000,
    parameter integer BAUD=115200,
    parameter MEM_FILE="build/interactive.hex"
)(
    input wire clk,
    input wire resetn,
    input wire uart_rx,
    output wire uart_tx,
    output wire led_done,
    output wire led_error
);
    (* ASYNC_REG="TRUE" *) reg [1:0] reset_sync;
    always @(posedge clk or negedge resetn)
        if(!resetn) reset_sync<=0; else reset_sync<={reset_sync[0],1'b1};
    wire internal_resetn=reset_sync[1];
    wire tx_valid,tx_ready,rx_valid,rx_ready,overrun,trap,finished;
    wire [7:0] tx_data,rx_data;
    wire [31:0] exit_code,cycle_count;
    neurotile_uart #(.CLKS_PER_BIT(CLK_HZ/BAUD)) serial (
        .clk(clk),.resetn(internal_resetn),.rx(uart_rx),.tx(uart_tx),
        .tx_valid(tx_valid),.tx_data(tx_data),.tx_ready(tx_ready),
        .rx_valid(rx_valid),.rx_data(rx_data),.rx_ready(rx_ready),.overrun(overrun)
    );
    neurotile_soc #(.MEM_FILE(MEM_FILE)) soc (
        .clk(clk),.resetn(internal_resetn),.trap(trap),
        .console_ready(tx_ready),.console_valid(tx_valid),.console_data(tx_data),
        .rx_valid(rx_valid),.rx_data(rx_data),.rx_overrun(overrun),.rx_ready(rx_ready),
        .finished(finished),.exit_code(exit_code),.cycle_count(cycle_count)
    );
    assign led_done=finished && exit_code==1;
    assign led_error=trap || overrun || (finished && exit_code!=1);
endmodule
