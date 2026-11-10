`timescale 1ns/1ps
module tb_soc;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    wire trap, console_valid, finished;
    wire [7:0] console_data;
    wire [31:0] exit_code, cycle_count;
    wire console_ready=1'b1,rx_valid=1'b0,rx_overrun=1'b0;
    wire [7:0] rx_data=0;
    wire rx_ready;
    neurotile_soc dut(.*);
    initial begin
        if ($test$plusargs("VCD")) begin
            $dumpfile("build/soc.vcd"); $dumpvars(0,tb_soc);
        end
        repeat(8) @(negedge clk);
        resetn=1;
    end
    always @(posedge clk) begin
        if (console_valid) $write("%c",console_data);
        if (resetn && trap) $fatal(1,"CPU trapped at cycle %0d",cycle_count);
        if (finished) begin
            if(exit_code != 1) $fatal(1,"Firmware failed code=%0d",exit_code);
            $display("SOC_PASS cycles=%0d",cycle_count);
            $finish;
        end
        if(cycle_count>5000000) $fatal(1,"SoC timeout");
    end
endmodule
