`timescale 1ns/1ps
/* Board-neutral simulation SoC. Console is a parallel byte strobe, not a UART. */
module neurotile_soc #(
    parameter MEM_WORDS = 32768,
    parameter MEM_FILE = "build/firmware.hex",
    parameter CPU_FAST_MUL = 0
)(
    input wire clk,
    input wire resetn,
    output wire trap,
    input wire console_ready,
    output wire console_valid,
    output wire [7:0] console_data,
    input wire rx_valid,
    input wire [7:0] rx_data,
    input wire rx_overrun,
    output wire rx_ready,
    output reg finished,
    output reg [31:0] exit_code,
    output reg [31:0] cycle_count
);
    wire mem_valid, mem_instr, mem_ready;
    wire [31:0] mem_addr, mem_wdata, mem_rdata;
    wire [3:0] mem_wstrb;
    reg [31:0] memory [0:MEM_WORDS-1];
    initial $readmemh(MEM_FILE, memory);
    wire ram_selected = mem_addr < MEM_WORDS*4;
    wire accel_selected = mem_addr[31:16] == 16'h1000;
    wire console_selected = mem_addr[31:5] == 27'h1000000;
    wire accel_ready, accel_irq;
    wire [31:0] accel_rdata;
    localparam RAM_ADDRESS_BITS = $clog2(MEM_WORDS);
    wire [31:0] ram_rdata = ram_selected ? memory[mem_addr[RAM_ADDRESS_BITS+1:2]] : 32'b0;
    wire [31:0] io_rdata = mem_addr[4:0] == 8 ? cycle_count :
                          mem_addr[4:0] == 12 ? {rx_valid,23'b0,rx_data} :
                          mem_addr[4:0] == 16 ? {29'b0,rx_overrun,rx_valid,console_ready} : 32'b0;
    wire console_write = mem_addr == 32'h20000000 && mem_wstrb[0];
    assign mem_ready = mem_valid && (accel_selected ? accel_ready : console_write ? console_ready : 1'b1);
    assign console_valid = resetn && mem_valid && mem_ready && console_write;
    assign console_data = mem_wdata[7:0];
    assign rx_ready = resetn && mem_valid && mem_ready && mem_addr == 32'h2000000c && !(|mem_wstrb);
    assign mem_rdata = ram_selected ? ram_rdata : accel_selected ? accel_rdata :
                       console_selected ? io_rdata : 32'b0;
    picorv32 #(
        .ENABLE_MUL(1), .ENABLE_FAST_MUL(CPU_FAST_MUL), .ENABLE_DIV(1), .ENABLE_IRQ(0),
        .ENABLE_COUNTERS(1), .PROGADDR_RESET(0), .STACKADDR(MEM_WORDS*4)
    ) cpu (
        .clk(clk), .resetn(resetn), .trap(trap), .mem_valid(mem_valid),
        .mem_instr(mem_instr), .mem_ready(mem_ready), .mem_addr(mem_addr),
        .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb), .mem_rdata(mem_rdata),
        .irq(32'b0), .pcpi_wr(1'b0), .pcpi_rd(32'b0),
        .pcpi_wait(1'b0), .pcpi_ready(1'b0)
    );
    neurotile_accel accelerator (
        .clk(clk), .resetn(resetn), .bus_valid(mem_valid && accel_selected),
        .bus_write(|mem_wstrb), .bus_addr(mem_addr[15:0]),
        .bus_wdata(mem_wdata), .bus_wstrb(mem_wstrb),
        .bus_ready(accel_ready), .bus_rdata(accel_rdata), .irq(accel_irq)
    );
    integer lane;
    always @(posedge clk) begin
        if (!resetn) begin
            finished <= 0;
            exit_code <= 0;
            cycle_count <= 0;
        end else begin
            cycle_count <= cycle_count + 1;
            if (mem_valid && mem_ready && |mem_wstrb) begin
                if (ram_selected) begin
                    for (lane=0; lane<4; lane=lane+1)
                        if (mem_wstrb[lane]) memory[mem_addr[RAM_ADDRESS_BITS+1:2]][8*lane+:8] <= mem_wdata[8*lane+:8];
                end else if (mem_addr == 32'h20000004) begin
                    finished <= mem_wdata != 0;
                    exit_code <= mem_wdata;
                end
            end
        end
    end
endmodule
