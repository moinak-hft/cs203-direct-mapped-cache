`timescale 1ns/1ps
/* End-to-end inference: each tensor is loaded through public MMIO, not backdoor writes. */
module tb_inference;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg bus_valid=0, bus_write=0;
    reg [15:0] bus_addr=0;
    reg [31:0] bus_wdata=0;
    reg [3:0] bus_wstrb=0;
    wire bus_ready,irq;
    wire [31:0] bus_rdata;
    neurotile_accel dut(.*);
    reg [7:0] pixels[0:63],w1[0:2047],w2[0:319];
    reg signed [31:0] b1[0:31],b2[0:9];
    reg signed [31:0] hidden[0:31],logits[0:9];
    string input_path,w1_path,w2_path,b1_path,b2_path;
    integer shift,i,prediction,elapsed=0,kernel_cycles=0,macs=0,tiles=0,start_cycle;
    reg [31:0] value;
    reg signed [31:0] activation;
    always @(posedge clk) if(resetn) elapsed<=elapsed+1;
    task wr(input [15:0] address,input [31:0] data);
        begin
            @(negedge clk); bus_valid=1;bus_write=1;bus_wstrb=15;bus_addr=address;bus_wdata=data;
            @(negedge clk);bus_valid=0;bus_write=0;bus_wstrb=0;
        end
    endtask
    task rd(input [15:0] address,output [31:0] data);
        begin
            @(negedge clk);bus_valid=1;bus_write=0;bus_wstrb=0;bus_addr=address;
            #1;data=bus_rdata;
            @(negedge clk);bus_valid=0;
        end
    endtask
    task execute(input integer n,input integer k);
        begin
            wr(16'h0004,2);wr(16'h000c,1);wr(16'h0010,n);wr(16'h0014,k);wr(16'h0004,1);
            value=0;
            while(!value[1]) begin
                rd(16'h0008,value);
                if(value[2]) $fatal(1,"Accelerator status error");
            end
            rd(16'h0018,value);kernel_cycles=kernel_cycles+value;
            rd(16'h001c,value);macs=macs+value;
            rd(16'h0020,value);tiles=tiles+value;
        end
    endtask
    initial begin
        if(!$value$plusargs("INPUT=%s",input_path)) $fatal(1,"Missing INPUT");
        if(!$value$plusargs("W1=%s",w1_path)) $fatal(1,"Missing W1");
        if(!$value$plusargs("W2=%s",w2_path)) $fatal(1,"Missing W2");
        if(!$value$plusargs("B1=%s",b1_path)) $fatal(1,"Missing B1");
        if(!$value$plusargs("B2=%s",b2_path)) $fatal(1,"Missing B2");
        if(!$value$plusargs("SHIFT=%d",shift)) $fatal(1,"Missing SHIFT");
        if(shift<0 || shift>24) $fatal(1,"Invalid shift");
        $readmemh(input_path,pixels);$readmemh(w1_path,w1);$readmemh(w2_path,w2);
        $readmemh(b1_path,b1);$readmemh(b2_path,b2);
        repeat(5) @(negedge clk);resetn=1;start_cycle=elapsed;
        for(i=0;i<64;i=i+1) wr(16'h1000+4*i,{24'b0,pixels[i]});
        for(i=0;i<2048;i=i+1) wr(16'h2000+4*i,{24'b0,w1[i]});
        execute(32,64);
        for(i=0;i<32;i=i+1) begin
            rd(16'h6000+4*i,value);
            activation=($signed(value)+b1[i]) >>> shift;
            hidden[i]=activation<0 ? 0 : activation>127 ? 127 : activation;
        end
        for(i=0;i<32;i=i+1) wr(16'h1000+4*i,hidden[i]);
        for(i=0;i<320;i=i+1) wr(16'h2000+4*i,{24'b0,w2[i]});
        execute(10,32);
        prediction=0;
        for(i=0;i<10;i=i+1) begin
            rd(16'h6000+4*i,value);logits[i]=$signed(value)+b2[i];
            if(logits[i]>logits[prediction]) prediction=i;
        end
        $write("RTL_RESULT {\"prediction\":%0d,\"kernel_cycles\":%0d,\"transaction_cycles\":%0d,\"macs\":%0d,\"tiles\":%0d,\"hidden\":[",prediction,kernel_cycles,elapsed-start_cycle,macs,tiles);
        for(i=0;i<32;i=i+1) begin if(i) $write(",");$write("%0d",hidden[i]);end
        $write("],\"logits\":[");
        for(i=0;i<10;i=i+1) begin if(i) $write(",");$write("%0d",logits[i]);end
        $display("]}");$finish;
    end
    initial begin #20000000;$fatal(1,"Inference timeout");end
endmodule
