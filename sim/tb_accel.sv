`timescale 1ns/1ps
module tb_accel;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg bus_valid = 0, bus_write = 0;
    reg [15:0] bus_addr = 0;
    reg [31:0] bus_wdata = 0;
    reg [3:0] bus_wstrb = 0;
    wire bus_ready, irq;
    wire [31:0] bus_rdata;
    neurotile_accel dut (.*);
    integer a_reference [0:1023];
    integer b_reference [0:4095];
    reg [31:0] random_state = 32'h6e743031;
    integer checks = 0, cases_run = 0;

    function integer random_byte;
        begin
            random_state = random_state * 32'd1664525 + 32'd1013904223;
            random_byte = $signed(random_state[31:24]);
        end
    endfunction

    task automatic write_word(input [15:0] address, input [31:0] value,
                              input [3:0] strobes = 4'b1111);
        begin
            @(negedge clk);
            bus_addr = address; bus_wdata = value; bus_wstrb = strobes;
            bus_valid = 1; bus_write = 1;
            #1;
            if (bus_ready !== 1'b1) $fatal(1,"write not accepted at %h", address);
            @(posedge clk); #1;
            @(negedge clk);
            bus_valid = 0; bus_write = 0; bus_wstrb = 0;
        end
    endtask

    task automatic read_word(input [15:0] address, output [31:0] value);
        begin
            @(negedge clk);
            bus_addr = address; bus_valid = 1; bus_write = 0; bus_wstrb = 0;
            #1;
            if (bus_ready !== 1'b1) $fatal(1,"read not accepted at %h", address);
            value = bus_rdata;
            @(posedge clk); #1;
            @(negedge clk); bus_valid = 0;
        end
    endtask

    task automatic expect_word(input [15:0] address, input [31:0] expected);
        reg [31:0] actual;
        begin
            read_word(address, actual);
            if (actual !== expected)
                $fatal(1,"address %h expected %h got %h",address,expected,actual);
            checks = checks + 1;
        end
    endtask

    task automatic wait_done;
        reg [31:0] status;
        integer polls;
        begin: polling
            for (polls = 0; polls < 10000; polls = polls + 1) begin
                read_word(16'h0008,status);
                if (!status[0]) begin
                    if (!status[1] || irq !== 1'b1)
                        $fatal(1,"completion missing: status=%h irq=%b",status,irq);
                    disable polling;
                end
            end
            $fatal(1,"accelerator timeout");
        end
    endtask

    task automatic run_case(input integer m, n, k, pattern,
                            input bit busy_checks);
        integer i,j,p,value,expected,tiles;
        reg [31:0] actual;
        begin
            write_word(16'h0004,2);
            expect_word(16'h0008,0);
            for (i=0;i<m*k;i=i+1) begin
                if (pattern==1) value=-128;
                else if (pattern==2) value=127;
                else if (pattern==3) value=(i%2==0)?-128:127;
                else value=random_byte();
                a_reference[i]=value;
                write_word(16'h1000+i*4,value);
            end
            for (i=0;i<k*n;i=i+1) begin
                if (pattern==1 || pattern==2) value=-128;
                else if (pattern==3) value=(i%3==0)?127:-128;
                else value=random_byte();
                b_reference[i]=value;
                write_word(16'h2000+i*4,value);
            end
            write_word(16'h000c,m);
            write_word(16'h0010,n);
            write_word(16'h0014,k);
            write_word(16'h0004,1);
            expect_word(16'h0008,1);
            if (irq !== 1'b0) $fatal(1,"irq did not clear at start");
            if (busy_checks) begin
                write_word(16'h1000,8'h55);
                write_word(16'h2000,8'h66);
                write_word(16'h000c,1);
                write_word(16'h0010,1);
                write_word(16'h0014,1);
                write_word(16'h0004,1);
                expect_word(16'h0008,5);
                expect_word(16'h000c,m);
                expect_word(16'h0010,n);
                expect_word(16'h0014,k);
                expect_word(16'h1000,a_reference[0]&255);
                expect_word(16'h2000,b_reference[0]&255);
            end
            wait_done();
            expect_word(16'h0008,busy_checks?6:2);
            for (i=0;i<m;i=i+1)
                for (j=0;j<n;j=j+1) begin
                    expected=0;
                    for (p=0;p<k;p=p+1)
                        expected=expected+a_reference[i*k+p]*b_reference[p*n+j];
                    read_word(16'h6000+(i*n+j)*4,actual);
                    if ($signed(actual) !== expected)
                        $fatal(1,"case %0d M%0d N%0d K%0d C[%0d,%0d] expected %0d got %0d",
                            cases_run,m,n,k,i,j,expected,$signed(actual));
                    checks=checks+1;
                end
            tiles=((m+3)/4)*((n+3)/4);
            expect_word(16'h0018,tiles*(k+2));
            expect_word(16'h001c,m*n*k);
            expect_word(16'h0020,tiles);
            cases_run=cases_run+1;
            $display("case %0d passed: M=%0d N=%0d K=%0d cycles=%0d macs=%0d tiles=%0d",
                cases_run,m,n,k,tiles*(k+2),m*n*k,tiles);
        end
    endtask

    task automatic invalid_dimensions(input [31:0] m,n,k);
        begin
            write_word(16'h0004,2);
            write_word(16'h000c,m);
            write_word(16'h0010,n);
            write_word(16'h0014,k);
            write_word(16'h0004,1);
            expect_word(16'h0008,4);
            if (irq !== 0) $fatal(1,"invalid command asserted irq");
        end
    endtask

    integer random_case,m_value,n_value,k_value;
    reg [31:0] stable_cycles, saved_result;
    initial begin
        repeat(3) @(negedge clk);
        resetn=1;
        expect_word(0,32'h4e543031);
        expect_word(8,0);
        expect_word(16'h0018,0);
        expect_word(16'h001c,0);
        expect_word(16'h0020,0);
        expect_word(16'h8000,0);
        expect_word(16'h0001,0);
        if (bus_ready !== 0) $fatal(1,"ready must follow valid");

        // Effective byte enables on operands and on full-width configuration.
        write_word(16'h1000,32'h000000ff,4'b0001);
        write_word(16'h1000,32'h12345678,4'b1110);
        expect_word(16'h1000,255);
        write_word(16'h1000,0,4'b0000);
        expect_word(16'h1000,255);
        write_word(16'h2000,32'h00000080,4'b0001);
        write_word(16'h2000,32'h12345678,4'b1110);
        expect_word(16'h2000,128);
        write_word(16'h000c,32'h11223344);
        write_word(16'h000c,32'haabbccdd,4'b0101);
        expect_word(16'h000c,32'h11bb33dd);
        write_word(16'h0004,2,4'b0010);
        expect_word(8,0);
        write_word(16'h8000,1,0);
        expect_word(8,0);
        write_word(16'h0001,1);
        expect_word(8,4);
        write_word(4,2);
        write_word(16'h6000,123);
        expect_word(8,4);
        write_word(4,2);
        write_word(16'h8000,1);
        expect_word(8,4);

        invalid_dimensions(0,1,1);
        invalid_dimensions(1,0,1);
        invalid_dimensions(1,1,0);
        invalid_dimensions(17,1,1);
        invalid_dimensions(1,65,1);
        invalid_dimensions(1,1,65);
        invalid_dimensions(32'hffffffff,1,1);

        run_case(1,1,1,1,0);
        run_case(4,4,64,2,0);
        run_case(5,7,64,3,1);
        run_case(16,64,64,0,0);
        // A smaller result must not write the preceding run's unused output words.
        read_word(16'h6ffc,saved_result);
        run_case(3,5,7,0,0);
        expect_word(16'h6ffc,saved_result);
        run_case(16,1,1,3,0);
        run_case(1,64,1,0,0);
        for (random_case=0;random_case<12;random_case=random_case+1) begin
            m_value=(random_byte()&15)+1;
            n_value=(random_byte()&63)+1;
            k_value=(random_byte()&63)+1;
            run_case(m_value,n_value,k_value,0,0);
        end
        read_word(16'h0018,stable_cycles);
        repeat(8) @(negedge clk);
        expect_word(16'h0018,stable_cycles);
        invalid_dimensions(0,1,1);
        expect_word(16'h0018,stable_cycles);

        // Abort an in-flight command, then establish clean control state.
        write_word(16'h000c,1);
        write_word(16'h0010,1);
        write_word(16'h0014,64);
        write_word(4,1);
        repeat(5) @(negedge clk);
        resetn=0;
        repeat(3) @(negedge clk);
        resetn=1;
        expect_word(8,0);
        expect_word(16'h000c,0);
        expect_word(16'h0010,0);
        expect_word(16'h0014,0);
        expect_word(16'h0018,0);
        expect_word(16'h001c,0);
        expect_word(16'h0020,0);
        if (irq !== 0) $fatal(1,"reset did not clear irq");
        expect_word(16'h1000,a_reference[0]&255);
        run_case(2,3,4,0,0);
        write_word(4,2);
        expect_word(8,0);
        if (irq !== 0) $fatal(1,"clear did not deassert irq");
        $display("ACCELERATOR PASS: %0d matrix cases, %0d checked values",cases_run,checks);
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1,"global watchdog expired");
    end
endmodule
