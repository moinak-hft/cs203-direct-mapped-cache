`timescale 1ns/1ps
module tb_labs;
    reg clk = 0;
    always #5 clk = !clk;
    reg resetn = 0;
    reg shared_valid = 0, isolated_valid = 0;
    reg request_domain = 0;
    reg [15:0] request_line = 0;
    wire [31:0] fill_data = 32'hc0000000 | {16'd0, request_line};
    wire shared_response, shared_hit, isolated_response, isolated_hit;
    wire [7:0] shared_cost, isolated_cost;
    wire [31:0] shared_data, isolated_data;
    reg [7:0] unit_delta = 0, dominant_delta = 0, reuse_fraction = 0, stride_abs = 0;
    wire [1:0] policy;
    integer accesses = 0, selector_checks = 0, index;
    reg [33:0] vectors [0:65535];
    string vector_path;

    adaptive_selector selector(unit_delta, dominant_delta, reuse_fraction, stride_abs, policy);
    domain_cache #(.ISOLATE(0)) shared_cache(
        clk, resetn, shared_valid, request_domain, request_line, fill_data,
        shared_response, shared_hit, shared_cost, shared_data);
    domain_cache #(.ISOLATE(1)) isolated_cache(
        clk, resetn, isolated_valid, request_domain, request_line, fill_data,
        isolated_response, isolated_hit, isolated_cost, isolated_data);

    task request;
        input isolated;
        input [15:0] line;
        input domain;
        input expected_hit;
        begin
            @(negedge clk);
            request_line = line;
            request_domain = domain;
            shared_valid = !isolated;
            isolated_valid = isolated;
            @(posedge clk); #1;
            if (isolated) begin
                if (isolated_response !== 1 || isolated_hit !== expected_hit
                    || isolated_cost !== (expected_hit ? 8'd1 : 8'd13)
                    || isolated_data !== (32'hc0000000 | {16'd0,line}))
                    $fatal(1, "isolated mismatch line=%0d domain=%0d hit=%0b expected=%0b",line,domain,isolated_hit,expected_hit);
            end else begin
                if (shared_response !== 1 || shared_hit !== expected_hit
                    || shared_cost !== (expected_hit ? 8'd1 : 8'd13)
                    || shared_data !== (32'hc0000000 | {16'd0,line}))
                    $fatal(1, "shared mismatch line=%0d domain=%0d hit=%0b expected=%0b",line,domain,shared_hit,expected_hit);
            end
            accesses = accesses + 1;
            @(negedge clk);
            shared_valid = 0;
            isolated_valid = 0;
        end
    endtask

    task selection;
        input [7:0] unit_value, dominant_value, reuse_value, stride_value;
        input [1:0] expected;
        begin
            unit_delta = unit_value;
            dominant_delta = dominant_value;
            reuse_fraction = reuse_value;
            stride_abs = stride_value;
            #1;
            if (policy !== expected)
                $fatal(1,"selector mismatch unit=%0d dominant=%0d got=%0d expected=%0d",unit_value,dominant_value,policy,expected);
            selector_checks = selector_checks + 1;
        end
    endtask

    initial begin
        repeat(2) @(posedge clk);
        @(negedge clk); resetn = 1;
        // Shared attacker primes both ways of both sets. Victim changes set 0.
        request(0,0,0,0); request(0,2,0,0);
        request(0,1,0,0); request(0,3,0,0);
        request(0,8,1,0);
        request(0,0,0,0); request(0,1,0,1);
        // Isolated observer retains a line while the other domain churns.
        request(1,0,0,0); request(1,1,0,0);
        request(1,8,1,0); request(1,0,0,1); request(1,1,0,1);
        for(index=0;index<8;index=index+1) begin
            request(1,16+index*2,1,0);
            request(1,0,0,1);
        end
        // A domain cannot hit the other domain's copy, even at the same line.
        request(1,30,0,0); request(1,30,1,1); request(1,30,0,1);
        // Shared tags are accessible to either requester.
        request(0,1,1,1);
        // Learned classes and their threshold boundaries.
        selection(255,255,0,1,1);
        selection(0,255,0,3,2);
        selection(0,8,100,114,0);
        selection(0,16,0,0,0);
        selection(0,17,0,0,1);
        selection(0,49,255,255,1);
        selection(0,50,255,255,2);
        if ($value$plusargs("vectors=%s",vector_path)) begin
            $readmemh(vector_path,vectors);
            for(index=0;index<65536;index=index+1)
                selection(vectors[index][33:26],vectors[index][25:18],
                          vectors[index][17:10],vectors[index][9:2],vectors[index][1:0]);
        end
        @(negedge clk); resetn = 0;
        @(posedge clk); #1;
        if(shared_response !== 0 || isolated_response !== 0)
            $fatal(1,"response valid survived reset");
        @(negedge clk); resetn = 1;
        request(0,1,0,0); request(1,30,0,0);
        $display("LABS_RTL_PASS accesses=%0d selector_checks=%0d",accesses,selector_checks);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1,"lab testbench timeout");
    end
endmodule
