// Standalone tiny cache event prototype: 2 sets x 2 ways, one word per line.
// request_line is a line address, not a byte address. A miss atomically fills
// request_fill_data supplied by the test harness. There is no memory bus here.
// Every request completes after one clock; response_cost is a MODEL annotation
// (hit 1 / miss 13), not an implemented thirteen-clock memory controller.
// ISOLATE gives each domain its own way. Cross-domain hits/fills are excluded;
// its only way requires no replacement state. Shared mode uses per-set RR.
module domain_cache #(
    parameter ISOLATE = 0
) (
    input wire clk,
    input wire resetn,
    input wire request_valid,
    input wire request_domain,
    input wire [15:0] request_line,
    input wire [31:0] request_fill_data,
    output reg response_valid,
    output reg response_hit,
    output reg [7:0] response_cost,
    output reg [31:0] response_data
);
    reg [14:0] tags [0:1][0:1];
    reg [31:0] words [0:1][0:1];
    reg valid [0:1][0:1];
    reg owner [0:1][0:1];
    reg next_way [0:1];
    integer set_i, way_i;
    reg selected_way;
    reg found;

    always @(posedge clk) begin
        if (!resetn) begin
            response_valid <= 0;
            response_hit <= 0;
            response_cost <= 0;
            response_data <= 0;
            for (set_i=0; set_i<2; set_i=set_i+1) begin
                next_way[set_i] <= 0;
                for (way_i=0; way_i<2; way_i=way_i+1) begin
                    valid[set_i][way_i] <= 0;
                    tags[set_i][way_i] <= 0;
                    words[set_i][way_i] <= 0;
                    owner[set_i][way_i] <= 0;
                end
            end
        end else begin
            response_valid <= request_valid;
            if (request_valid) begin
                found = 0;
                selected_way = 0;
                for (way_i=0; way_i<2; way_i=way_i+1) begin
                    if (valid[request_line[0]][way_i]
                        && tags[request_line[0]][way_i] == request_line[15:1]
                        && (!ISOLATE || (way_i == request_domain && owner[request_line[0]][way_i] == request_domain))) begin
                        found = 1;
                        selected_way = way_i;
                    end
                end
                response_hit <= found;
                response_cost <= found ? 8'd1 : 8'd13;
                if (found) begin
                    response_data <= words[request_line[0]][selected_way];
                end else begin
                    if (ISOLATE)
                        selected_way = request_domain;
                    else if (!valid[request_line[0]][0])
                        selected_way = 0;
                    else if (!valid[request_line[0]][1])
                        selected_way = 1;
                    else
                        selected_way = next_way[request_line[0]];
                    valid[request_line[0]][selected_way] <= 1;
                    tags[request_line[0]][selected_way] <= request_line[15:1];
                    words[request_line[0]][selected_way] <= request_fill_data;
                    owner[request_line[0]][selected_way] <= request_domain;
                    response_data <= request_fill_data;
                    if (!ISOLATE)
                        next_way[request_line[0]] <= !selected_way;
                end
            end
        end
    end
endmodule
