`timescale 1ns/1ps
// Small scratchpad-backed 4x4 output-stationary parallel MAC accelerator.
// This is a broadcast array, not a nearest-neighbor systolic implementation.
module neurotile_accel (
    input wire clk,
    input wire resetn,
    input wire bus_valid,
    input wire bus_write,
    input wire [15:0] bus_addr,
    input wire [31:0] bus_wdata,
    input wire [3:0] bus_wstrb,
    output wire bus_ready,
    output reg [31:0] bus_rdata,
    output wire irq
);
    localparam IDLE = 2'd0, CLEAR = 2'd1, MAC = 2'd2, STORE = 2'd3;
    reg [1:0] state;
    reg done, error;
    reg [31:0] dim_m, dim_n, dim_k;
    reg [6:0] run_m, run_n, run_k;
    reg [6:0] tile_row, tile_col, k_pos;
    reg [31:0] kernel_cycles, useful_macs, tile_count;
    reg [7:0] a_mem [0:1023];
    reg [7:0] b_mem [0:4095];
    reg signed [31:0] c_mem [0:1023];

    wire busy = state != IDLE;
    wire aligned = bus_addr[1:0] == 2'b00;
    wire is_a = bus_addr >= 16'h1000 && bus_addr < 16'h2000;
    wire is_b = bus_addr >= 16'h2000 && bus_addr < 16'h6000;
    wire is_c = bus_addr >= 16'h6000 && bus_addr < 16'h7000;
    wire [9:0] a_word = (bus_addr - 16'h1000) >> 2;
    wire [11:0] b_word = (bus_addr - 16'h2000) >> 2;
    wire [9:0] c_word = (bus_addr - 16'h6000) >> 2;
    wire dimensions_valid = dim_m >= 1 && dim_m <= 16 &&
                            dim_n >= 1 && dim_n <= 64 &&
                            dim_k >= 1 && dim_k <= 64;
    wire [6:0] rows_left = run_m - tile_row;
    wire [6:0] cols_left = run_n - tile_col;
    wire [2:0] live_rows = rows_left >= 4 ? 3'd4 : rows_left[2:0];
    wire [2:0] live_cols = cols_left >= 4 ? 3'd4 : cols_left[2:0];
    wire [5:0] macs_this_cycle = live_rows * live_cols;
    wire signed [7:0] a_lane [0:3];
    wire signed [7:0] b_lane [0:3];
    wire signed [31:0] pe_result [0:15];

    assign bus_ready = bus_valid;
    assign irq = done;

    function [31:0] merge_bytes;
        input [31:0] old_value, new_value;
        input [3:0] strobes;
        integer byte_index;
        begin
            merge_bytes = old_value;
            for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
                if (strobes[byte_index])
                    merge_bytes[byte_index*8 +: 8] = new_value[byte_index*8 +: 8];
        end
    endfunction

    genvar row, col;
    generate
        for (row = 0; row < 4; row = row + 1) begin: operand_rows
            assign a_lane[row] = (tile_row + row < run_m && k_pos < run_k)
                ? a_mem[(tile_row + row) * run_k + k_pos] : 8'd0;
            assign b_lane[row] = (tile_col + row < run_n && k_pos < run_k)
                ? b_mem[k_pos * run_n + tile_col + row] : 8'd0;
            for (col = 0; col < 4; col = col + 1) begin: pe_cols
                mac_pe pe (
                    .clk(clk), .resetn(resetn), .clear(state == CLEAR),
                    .enable(state == MAC && tile_row + row < run_m &&
                            tile_col + col < run_n),
                    .lhs(a_lane[row]), .rhs(b_lane[col]),
                    .acc(pe_result[row*4+col])
                );
            end
        end
    endgenerate

    always @* begin
        bus_rdata = 32'd0;
        if (aligned) begin
            case (bus_addr)
                16'h0000: bus_rdata = 32'h4e543031;
                16'h0008: bus_rdata = {29'd0, error, done, busy};
                16'h000c: bus_rdata = dim_m;
                16'h0010: bus_rdata = dim_n;
                16'h0014: bus_rdata = dim_k;
                16'h0018: bus_rdata = kernel_cycles;
                16'h001c: bus_rdata = useful_macs;
                16'h0020: bus_rdata = tile_count;
                default: begin
                    if (is_a) bus_rdata = {24'd0, a_mem[a_word]};
                    else if (is_b) bus_rdata = {24'd0, b_mem[b_word]};
                    else if (is_c) bus_rdata = c_mem[c_word];
                end
            endcase
        end
    end

    integer store_row, store_col;
    always @(posedge clk) begin
        if (!resetn) begin
            state <= IDLE;
            done <= 1'b0;
            error <= 1'b0;
            dim_m <= 32'd0;
            dim_n <= 32'd0;
            dim_k <= 32'd0;
            run_m <= 7'd0;
            run_n <= 7'd0;
            run_k <= 7'd0;
            tile_row <= 7'd0;
            tile_col <= 7'd0;
            k_pos <= 7'd0;
            kernel_cycles <= 32'd0;
            useful_macs <= 32'd0;
            tile_count <= 32'd0;
        end else begin
            if (busy) kernel_cycles <= kernel_cycles + 1'b1;
            case (state)
                CLEAR: begin
                    k_pos <= 7'd0;
                    state <= MAC;
                end
                MAC: begin
                    useful_macs <= useful_macs + macs_this_cycle;
                    if (k_pos + 1 >= run_k) state <= STORE;
                    else k_pos <= k_pos + 1'b1;
                end
                STORE: begin
                    for (store_row = 0; store_row < 4; store_row = store_row + 1)
                        for (store_col = 0; store_col < 4; store_col = store_col + 1)
                            if (tile_row + store_row < run_m && tile_col + store_col < run_n)
                                c_mem[(tile_row + store_row)*run_n + tile_col + store_col]
                                    <= pe_result[store_row*4+store_col];
                    tile_count <= tile_count + 1'b1;
                    if (tile_col + 4 < run_n) begin
                        tile_col <= tile_col + 4;
                        state <= CLEAR;
                    end else if (tile_row + 4 < run_m) begin
                        tile_col <= 7'd0;
                        tile_row <= tile_row + 4;
                        state <= CLEAR;
                    end else begin
                        state <= IDLE;
                        done <= 1'b1;
                    end
                end
                default: ;
            endcase

            // All-zero byte enables are a no-op, including on unmapped addresses.
            if (bus_valid && bus_write && |bus_wstrb) begin
                if (!aligned) error <= 1'b1;
                else if (is_a || is_b) begin
                    if (bus_wstrb[0]) begin
                        if (busy) error <= 1'b1;
                        else if (is_a) a_mem[a_word] <= bus_wdata[7:0];
                        else b_mem[b_word] <= bus_wdata[7:0];
                    end
                end else begin
                    case (bus_addr)
                        16'h0004: if (bus_wstrb[0]) begin
                            if (bus_wdata[1]) begin
                                done <= 1'b0;
                                error <= 1'b0;
                            end
                            if (bus_wdata[0]) begin
                                if (busy || !dimensions_valid) error <= 1'b1;
                                else begin
                                    run_m <= dim_m[6:0];
                                    run_n <= dim_n[6:0];
                                    run_k <= dim_k[6:0];
                                    tile_row <= 7'd0;
                                    tile_col <= 7'd0;
                                    k_pos <= 7'd0;
                                    kernel_cycles <= 32'd0;
                                    useful_macs <= 32'd0;
                                    tile_count <= 32'd0;
                                    done <= 1'b0;
                                    error <= 1'b0;
                                    state <= CLEAR;
                                end
                            end
                        end
                        16'h000c: if (busy) error <= 1'b1;
                                      else dim_m <= merge_bytes(dim_m,bus_wdata,bus_wstrb);
                        16'h0010: if (busy) error <= 1'b1;
                                      else dim_n <= merge_bytes(dim_n,bus_wdata,bus_wstrb);
                        16'h0014: if (busy) error <= 1'b1;
                                      else dim_k <= merge_bytes(dim_k,bus_wdata,bus_wstrb);
                        default: error <= 1'b1;
                    endcase
                end
            end
        end
    end
endmodule
