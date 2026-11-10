`timescale 1ns/1ps
// One output-stationary signed INT8 MAC with a signed INT32 accumulator.
module mac_pe (
    input wire clk,
    input wire resetn,
    input wire clear,
    input wire enable,
    input wire signed [7:0] lhs,
    input wire signed [7:0] rhs,
    output reg signed [31:0] acc
);
    wire signed [15:0] product = lhs * rhs;
    wire signed [31:0] extended_product = {{16{product[15]}}, product};
    always @(posedge clk) begin
        if (!resetn || clear)
            acc <= 32'sd0;
        else if (enable)
            acc <= acc + extended_product;
    end
endmodule
