module cache_memory_array #(
    parameter CACHE_DEPTH = 256,
    parameter DATA_WIDTH = 8,
    parameter TAG_WIDTH = 8
) (
    input wire clk,
    input wire reset,
    input wire [($clog2(CACHE_DEPTH))-1:0] index,
    input wire [TAG_WIDTH-1:0] tag_in,
    input wire [DATA_WIDTH-1:0] data_in,
    input wire write_en,
    
    output reg [TAG_WIDTH-1:0] tag_out,
    output reg [DATA_WIDTH-1:0] data_out,
    output reg valid_out
);

    reg [TAG_WIDTH-1:0] tag_array [0:CACHE_DEPTH-1];
    reg [DATA_WIDTH-1:0] data_array [0:CACHE_DEPTH-1];
    reg valid_array [0:CACHE_DEPTH-1];

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            for (integer i = 0; i < CACHE_DEPTH; i = i + 1) begin
                valid_array[i] <= 0;
                tag_array[i] <= 0;
                data_array[i] <= 0;
            end
        end else if (write_en) begin
            tag_array[index] <= tag_in;
            data_array[index] <= data_in;
            valid_array[index] <= 1;
        end
    end

    always @(*) begin
        tag_out = tag_array[index];
        data_out = data_array[index];
        valid_out = valid_array[index];
    end

endmodule