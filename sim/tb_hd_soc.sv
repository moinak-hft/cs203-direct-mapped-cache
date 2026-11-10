`timescale 1ns/1ps
module tb_hd_soc;
    reg clk=0,resetn=0;
    always #5 clk=~clk;
    wire trap,console_valid,finished,rx_ready;
    wire [7:0] console_data;
    wire [31:0] exit_code,cycle_count;
    neurotile_soc #(.MEM_FILE("build/hd_firmware.hex"),.CPU_FAST_MUL(1)) dut(
        .clk(clk),.resetn(resetn),.trap(trap),.console_ready(1'b1),
        .console_valid(console_valid),.console_data(console_data),
        .rx_valid(1'b0),.rx_data(8'b0),.rx_overrun(1'b0),.rx_ready(rx_ready),
        .finished(finished),.exit_code(exit_code),.cycle_count(cycle_count)
    );
    initial begin repeat(8)@(negedge clk);resetn=1;end
    always @(posedge clk) begin
        if(console_valid)$write("%c",console_data);
        if(resetn && trap)$fatal(1,"High-resolution CPU trap at cycle%0d",cycle_count);
        if(finished)begin
            if(exit_code!=1)$fatal(1,"HD firmware failure code%0d",exit_code);
            $display("HD_SOC_PASS cycles=%0d",cycle_count);$finish;
        end
        if(cycle_count>20000000)$fatal(1,"HD CPU timeout");
    end
endmodule
