`timescale 1ns / 1ps

module tb_cache;

    localparam ADDRESS_WIDTH = 16;
    localparam DATA_WIDTH = 8;
    localparam INDEX_WIDTH = 8;
    
    reg clk;
    reg reset;
    
    reg [ADDRESS_WIDTH-1:0] addr;
    reg [DATA_WIDTH-1:0] data_in;
    reg read;
    reg write;
    
    wire [DATA_WIDTH-1:0] data_out;
    wire hit;
    wire miss;

    direct_mapped_cache #(
        .ADDRESS_WIDTH(ADDRESS_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .INDEX_WIDTH(INDEX_WIDTH)
    ) uut (
        .clk(clk),
        .reset(reset),
        .addr(addr),
        .data_in(data_in),
        .read(read),
        .write(write),
        .data_out(data_out),
        .hit(hit),
        .miss(miss)
    );

    always begin
        #5 clk = ~clk;
    end

    task wait_cycles;
        input integer cycles;
        begin
            repeat (cycles) @(posedge clk);
        end
    endtask

    task cpu_read;
        input [ADDRESS_WIDTH-1:0] r_addr;
        begin
            @(posedge clk);
            addr <= r_addr;
            read <= 1;
            write <= 0;
            @(posedge clk);
            read <= 0;
            while (hit == 0 && miss == 0) begin
                @(posedge clk);
            end
        end
    endtask

    task cpu_write;
        input [ADDRESS_WIDTH-1:0] w_addr;
        input [DATA_WIDTH-1:0] w_data;
        begin
            @(posedge clk);
            addr <= w_addr;
            data_in <= w_data;
            read <= 0;
            write <= 1;
            @(posedge clk);
            write <= 0;
            while (hit == 0 && miss == 0) begin
                @(posedge clk);
            end
        end
    endtask

    initial begin
        clk = 0;
        reset = 1;
        addr = 0;
        data_in = 0;
        read = 0;
        write = 0;
        
        $display("Time\tAddr\tDataIn\tRead\tWrite\tDataOut\tHit\tMiss");
        $monitor("%0t\t%h\t%h\t%b\t%b\t%h\t%b\t%b", $time, addr, data_in, read, write, data_out, hit, miss);

        @(posedge clk);
        reset = 0;
        
        $display("\n--- Test 1: Write, then Read (Hit) ---");
        cpu_write(16'h1234, 8'hAA);
        wait_cycles(2);
        cpu_read(16'h1234);
        wait_cycles(2);
        
        $display("\n--- Test 2: Read Miss ---");
        cpu_read(16'h5678);
        wait_cycles(5);
        
        $display("\n--- Test 3: Read Hit (Consecutive) ---");
        cpu_read(16'h5678);
        wait_cycles(2);

        $display("\n--- Test 4: Conflict Miss (Eviction) ---");
        cpu_read(16'h4434);
        wait_cycles(5);
        
        $display("\n--- Test 5: Original Read (Now Miss) ---");
        cpu_read(16'h1234);
        wait_cycles(5);

        $display("\n--- Test 6: Write-through (No-allocate) ---");
        cpu_write(16'hABCD, 8'hC3);
        wait_cycles(2);
        
        $display("\n--- Test 7: Read after Write (Miss, then Hit) ---");
        cpu_read(16'hABCD);
        wait_cycles(5);
        cpu_read(16'hABCD);
        wait_cycles(2);

        $display("\n--- Simulation Complete ---");
        $stop;
    end

endmodule