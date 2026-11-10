`timescale 1ns/1ps
module tb_fpga_uart;
    localparam DIVISOR=32;
    reg clk=0,resetn=0,uart_rx=1;
    always #5 clk=~clk;
    wire uart_tx,led_done,led_error;
    neurotile_fpga_top #(.CLK_HZ(3686400),.BAUD(115200)) dut(.*);
    wire monitor_valid,monitor_ready,monitor_tx,monitor_overrun;
    wire [7:0] monitor_data;
    neurotile_uart #(.CLKS_PER_BIT(DIVISOR)) monitor (
        .clk(clk),.resetn(resetn),.rx(uart_tx),.tx(monitor_tx),
        .tx_valid(1'b0),.tx_data(8'b0),.tx_ready(monitor_ready),
        .rx_valid(monitor_valid),.rx_data(monitor_data),.rx_ready(1'b1),.overrun(monitor_overrun)
    );
    reg [7:0] pixels[0:63];
    string input_path;
    integer lines=0;
    integer parsed_prediction;
    string current_line="";
    always @(posedge clk) begin
        if(monitor_valid)begin
            $write("%c",monitor_data);
            if(monitor_data==10)begin
                case(lines)
                    0: if(current_line!="NEUROTILE READY")
                        $fatal(1,"Unexpected UART boot message: %s",current_line);
                    1: if(current_line!="UART_RESULT {\"error\":\"invalid frame\"}")
                        $fatal(1,"Invalid checksum was not rejected: %s",current_line);
                    2,3: begin
                        if($sscanf(current_line,"UART_RESULT {\"prediction\":%d",parsed_prediction)!=1)
                            $fatal(1,"Valid frame failed: %s",current_line);
                        if(parsed_prediction<0 || parsed_prediction>9)
                            $fatal(1,"Invalid prediction: %0d",parsed_prediction);
                    end
                    default: $fatal(1,"Unexpected extra UART line: %s",current_line);
                endcase
                lines<=lines+1;
                current_line="";
            end else current_line={current_line,monitor_data};
        end
        if(resetn && led_error)$fatal(1,"FPGA top error LED");
        if(monitor_overrun)$fatal(1,"Monitor overrun");
    end
    task automatic send_byte(input [7:0] value);
        integer bit_index;
        begin
            @(negedge clk);uart_rx=0;repeat(DIVISOR)@(negedge clk);
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)begin
                uart_rx=value[bit_index];repeat(DIVISOR)@(negedge clk);
            end
            uart_rx=1;repeat(DIVISOR)@(negedge clk);
        end
    endtask
    task automatic send_frame(input integer zero_payload,input integer bad_checksum);
        integer pixel_index;
        reg [7:0] checksum,value;
        begin
            checksum=0;
            send_byte("N");send_byte("T");
            for(pixel_index=0;pixel_index<64;pixel_index=pixel_index+1)begin
                value=zero_payload ? 8'b0 : pixels[pixel_index];
                checksum=checksum^value;
                send_byte(value);
            end
            send_byte(bad_checksum ? checksum^8'h01 : checksum);
        end
    endtask
    initial begin
        if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"Missing INPUT");
        $readmemh(input_path,pixels);
        repeat(8)@(negedge clk);resetn=1;
        wait(lines==1);
        /* Ignore unrelated bytes and recover the overlapping N,N,T prefix,
         * then reject an otherwise valid bad checksum.
         */
        send_byte(8'h55);send_byte(8'h00);send_byte(8'h7e);
        send_byte("N");
        send_frame(0,1);
        wait(lines==2);
        if(led_done)$fatal(1,"Rejected request lit the completion LED");
        /* Recovery must process two requests without dropping or mixing bytes.
         * The host parser checks both complete logits against integer Python.
         */
        send_frame(0,0);
        wait(lines==3);
        if(!led_done)$fatal(1,"First successful inference did not light completion LED");
        send_frame(1,0);
        repeat(100)@(negedge clk);
        if(led_done)$fatal(1,"New valid request did not clear completion LED");
        wait(lines==4);repeat(2*DIVISOR)@(negedge clk);
        if(!led_done)$fatal(1,"Second successful inference did not light completion LED");
        $display("FPGA_UART_PASS invalid_checksum=1 valid_frames=2 noise_bytes=4 overlap_resync=1");$finish;
    end
    initial begin #30000000;$fatal(1,"UART SoC timeout");end
endmodule
