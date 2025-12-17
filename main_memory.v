module main_memory #(
    parameter ADDRESS_WIDTH = 16,
    parameter DATA_WIDTH = 8
) (
    input wire clk,
    input wire [ADDRESS_WIDTH-1:0] addr,
    input wire [DATA_WIDTH-1:0] data_in,
    input wire write_en,
    input wire read_en,
    output reg [DATA_WIDTH-1:0] data_out,
    output reg ready
);

    localparam MEM_DEPTH = 1 << ADDRESS_WIDTH;
    reg [DATA_WIDTH-1:0] mem [0:MEM_DEPTH-1];

    always @(posedge clk) begin
        ready <= 0;
        if (write_en) begin
            mem[addr] <= data_in;
        end else if (read_en) begin
            data_out <= mem[addr];
            ready <= 1;
        end
    end

endmodule