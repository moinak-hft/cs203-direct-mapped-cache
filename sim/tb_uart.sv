`timescale 1ns/1ps
module tb_uart;
    parameter integer CLKS_PER_BIT = 8;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg rx = 1;
    wire tx;
    reg tx_valid = 0;
    reg [7:0] tx_data = 0;
    wire tx_ready;
    wire rx_valid;
    wire [7:0] rx_data;
    reg rx_ready = 0;
    wire overrun;
    neurotile_uart #(.CLKS_PER_BIT(CLKS_PER_BIT)) dut (
        .clk(clk), .resetn(resetn), .rx(rx), .tx(tx), .tx_valid(tx_valid),
        .tx_data(tx_data), .tx_ready(tx_ready), .rx_valid(rx_valid),
        .rx_data(rx_data), .rx_ready(rx_ready), .overrun(overrun)
    );

    reg [7:0] tx_expected[0:3];
    integer tx_checked = 0;
    integer bit_number;
    reg [7:0] tx_observed;
    integer rx_handshakes = 0;
    integer handshakes_before;
    reg [7:0] last_consumed;
    always @(posedge clk) begin
        if (resetn && rx_valid && rx_ready) begin
            rx_handshakes = rx_handshakes + 1;
            last_consumed = rx_data;
        end
    end
    /* Decode the actual wire independently of the internal TX state. */
    always @(negedge tx) begin
        if (resetn) begin
            if (tx_checked >= 4) $fatal(1, "Unexpected TX frame");
            repeat (CLKS_PER_BIT / 2) @(posedge clk);
            #1;
            if (tx !== 0) $fatal(1, "TX start bit was not held");
            for (bit_number = 0; bit_number < 8; bit_number = bit_number + 1) begin
                repeat (CLKS_PER_BIT) @(posedge clk);
                #1;
                tx_observed[bit_number] = tx;
            end
            repeat (CLKS_PER_BIT) @(posedge clk);
            #1;
            if (tx !== 1) $fatal(1, "TX stop bit missing");
            if (tx_observed !== tx_expected[tx_checked])
                $fatal(1, "TX byte %0d got %02x expected %02x", tx_checked,
                       tx_observed, tx_expected[tx_checked]);
            tx_checked = tx_checked + 1;
        end
    end

    task automatic transmit(input reg [7:0] value);
        begin
            @(negedge clk);
            tx_data = value;
            tx_valid = 1;
            /* Hold valid/data through backpressure until an accepted edge. */
            while (!tx_ready) @(negedge clk);
            @(posedge clk);
            @(negedge clk);
            tx_valid = 0;
        end
    endtask

    task automatic receive_frame(input reg [7:0] value, input reg good_stop);
        integer i;
        begin
            @(negedge clk);
            rx = 0;
            repeat (CLKS_PER_BIT) @(negedge clk);
            for (i = 0; i < 8; i = i + 1) begin
                rx = value[i];
                repeat (CLKS_PER_BIT) @(negedge clk);
            end
            rx = good_stop;
            repeat (CLKS_PER_BIT) @(negedge clk);
            rx = 1;
            /* Let stop synchronization and false-start rejection settle. */
            repeat (2 * CLKS_PER_BIT) @(negedge clk);
        end
    endtask

    task automatic consume;
        begin
            @(negedge clk);
            rx_ready = 1;
            @(negedge clk);
            rx_ready = 0;
            if (rx_valid !== 0) $fatal(1, "RX valid did not clear on handshake");
        end
    endtask

    initial begin
        tx_expected[0] = 8'ha5;
        tx_expected[1] = 8'h3c;
        tx_expected[2] = 8'h00;
        tx_expected[3] = 8'hff;
        repeat (4) @(negedge clk);
        if (tx !== 1 || rx_valid !== 0 || overrun !== 0)
            $fatal(1, "Reset outputs invalid");
        resetn = 1;
        transmit(8'ha5);
        transmit(8'h3c);
        transmit(8'h00);
        transmit(8'hff);
        wait(tx_checked == 4);
        wait(tx_ready);

        receive_frame(8'ha6, 1);
        if (!rx_valid || rx_data !== 8'ha6 || overrun)
            $fatal(1, "RX valid frame failed");
        repeat (20) begin
            @(negedge clk);
            if (!rx_valid || rx_data !== 8'ha6)
                $fatal(1, "RX changed while backpressured");
        end
        consume();

        receive_frame(8'h55, 0);
        if (rx_valid || overrun) $fatal(1, "Bad stop bit accepted");
        /* A short low pulse must fail the half-bit start verification. */
        @(negedge clk); rx = 0;
        @(negedge clk); rx = 1;
        repeat (3 * CLKS_PER_BIT) @(negedge clk);
        if (rx_valid || overrun) $fatal(1, "False start was accepted");

        receive_frame(8'h11, 1);
        receive_frame(8'h22, 0);
        if (!rx_valid || rx_data !== 8'h11 || overrun)
            $fatal(1, "Bad frame damaged the held byte");
        receive_frame(8'h33, 1);
        if (!rx_valid || rx_data !== 8'h11 || !overrun)
            $fatal(1, "Overrun did not preserve first byte");
        consume();
        if (!overrun) $fatal(1, "Overrun is not sticky");

        /* A subsequent buffered frame still receives normally. */
        receive_frame(8'h80, 1);
        if (!rx_valid || rx_data !== 8'h80) $fatal(1, "RX did not recover after overrun");
        consume();
        handshakes_before = rx_handshakes;
        rx_ready = 1;
        receive_frame(8'hc3, 1);
        if (rx_valid || rx_handshakes != handshakes_before + 1 || last_consumed !== 8'hc3)
            $fatal(1, "Always-ready RX did not consume exactly one frame");
        rx_ready = 0;
        @(negedge clk); resetn = 0;
        repeat (3) @(negedge clk);
        if (tx !== 1 || rx_valid || overrun || rx_data !== 0)
            $fatal(1, "Reset did not clear RX and sticky overrun");
        resetn = 1;
        receive_frame(8'h7e, 1);
        if (!rx_valid || rx_data !== 8'h7e || overrun)
            $fatal(1, "UART failed after reset");
        consume();
        $display("UART PASS: divider=%0d TX bits, RX, backpressure, framing, overrun, reset", CLKS_PER_BIT);
        $finish;
    end

    initial begin
        #2000000;
        $fatal(1, "UART test timeout");
    end
endmodule
