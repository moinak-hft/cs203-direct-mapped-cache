`timescale 1ns/1ps
/* Genuine 28x28 inference through the public unchanged accelerator interface.
 * K=784 is split into 12x64 + 16. Two input rows reuse each weight block.
 * This host bench sums raw partial results and applies the model activation.
 */
module tb_hd_inference;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg bus_valid=0, bus_write=0;
    reg [15:0] bus_addr=0;
    reg [31:0] bus_wdata=0;
    reg [3:0] bus_wstrb=0;
    wire bus_ready,irq;
    wire [31:0] bus_rdata;
    neurotile_accel dut(.*);
    reg [7:0] pixels[0:1567],w1[0:50175],w2[0:639];
    reg signed [31:0] b1[0:63],b2[0:9];
    reg signed [31:0] partial[0:127],hidden[0:127],logits[0:19];
    integer predictions[0:1];
    string input_path,w1_path,w2_path,b1_path,b2_path;
    integer shift,batch_size,row,j,q,base,k_size,elapsed=0,kernel_cycles=0;
    integer macs=0,tiles=0,launches=0,start_cycle;
    reg [31:0] value;
    reg signed [31:0] activation;
    always @(posedge clk) if(resetn) elapsed<=elapsed+1;
    task wr(input [15:0] address,input [31:0] data);
        begin
            @(negedge clk);bus_valid=1;bus_write=1;bus_wstrb=15;bus_addr=address;bus_wdata=data;
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
            wr(16'h0004,2);wr(16'h000c,batch_size);wr(16'h0010,n);wr(16'h0014,k);wr(16'h0004,1);
            value=0;
            while(!value[1]) begin
                rd(16'h0008,value);
                if(value[2])$fatal(1,"HD accelerator status error");
            end
            rd(16'h0018,value);kernel_cycles=kernel_cycles+value;
            rd(16'h001c,value);macs=macs+value;
            rd(16'h0020,value);tiles=tiles+value;
            launches=launches+1;
        end
    endtask
    initial begin
        if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"Missing INPUT");
        if(!$value$plusargs("W1=%s",w1_path))$fatal(1,"Missing W1");
        if(!$value$plusargs("W2=%s",w2_path))$fatal(1,"Missing W2");
        if(!$value$plusargs("B1=%s",b1_path))$fatal(1,"Missing B1");
        if(!$value$plusargs("B2=%s",b2_path))$fatal(1,"Missing B2");
        if(!$value$plusargs("SHIFT=%d",shift))$fatal(1,"Missing SHIFT");
        if(!$value$plusargs("BATCH=%d",batch_size))$fatal(1,"Missing BATCH");
        if(shift<0 || shift>24 || batch_size<1 || batch_size>2)$fatal(1,"Invalid HD configuration");
        $readmemh(input_path,pixels);$readmemh(w1_path,w1);$readmemh(w2_path,w2);
        $readmemh(b1_path,b1);$readmemh(b2_path,b2);
        for(row=0;row<128;row=row+1)partial[row]=0;
        repeat(5)@(negedge clk);resetn=1;start_cycle=elapsed;
        for(base=0;base<784;base=base+64)begin
            k_size=784-base<64 ? 784-base : 64;
            for(row=0;row<batch_size;row=row+1)
                for(q=0;q<k_size;q=q+1)
                    wr(16'h1000+4*(row*k_size+q),{24'b0,pixels[row*784+base+q]});
            for(q=0;q<k_size;q=q+1)
                for(j=0;j<64;j=j+1)
                    wr(16'h2000+4*(q*64+j),{24'b0,w1[(base+q)*64+j]});
            execute(64,k_size);
            for(row=0;row<batch_size;row=row+1)
                for(j=0;j<64;j=j+1)begin
                    rd(16'h6000+4*(row*64+j),value);
                    partial[row*64+j]=partial[row*64+j]+$signed(value);
                end
        end
        for(row=0;row<batch_size;row=row+1)
            for(j=0;j<64;j=j+1)begin
                activation=(partial[row*64+j]+b1[j]) >>> shift;
                hidden[row*64+j]=activation<0 ? 0 : activation>127 ? 127 : activation;
                wr(16'h1000+4*(row*64+j),hidden[row*64+j]);
            end
        for(q=0;q<640;q=q+1)wr(16'h2000+4*q,{24'b0,w2[q]});
        execute(10,64);
        for(row=0;row<batch_size;row=row+1)begin
            predictions[row]=0;
            for(j=0;j<10;j=j+1)begin
                rd(16'h6000+4*(row*10+j),value);
                logits[row*10+j]=$signed(value)+b2[j];
                if(logits[row*10+j]>logits[row*10+predictions[row]])predictions[row]=j;
            end
        end
        $write("HD_RTL_RESULT {\"batch_size\":%0d,\"kernel_cycles\":%0d,\"transaction_cycles\":%0d,\"macs\":%0d,\"tiles\":%0d,\"launches\":%0d,\"predictions\":[",batch_size,kernel_cycles,elapsed-start_cycle,macs,tiles,launches);
        for(row=0;row<batch_size;row=row+1)begin if(row)$write(",");$write("%0d",predictions[row]);end
        $write("],\"hidden\":[");
        for(row=0;row<batch_size;row=row+1)begin
            if(row)$write(",");$write("[");
            for(j=0;j<64;j=j+1)begin if(j)$write(",");$write("%0d",hidden[row*64+j]);end
            $write("]");
        end
        $write("],\"logits\":[");
        for(row=0;row<batch_size;row=row+1)begin
            if(row)$write(",");$write("[");
            for(j=0;j<10;j=j+1)begin if(j)$write(",");$write("%0d",logits[row*10+j]);end
            $write("]");
        end
        $display("]}");$finish;
    end
    initial begin #100000000;$fatal(1,"HD inference timeout");end
endmodule
