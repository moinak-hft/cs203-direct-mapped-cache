module direct_mapped_cache #(
    parameter ADDRESS_WIDTH = 16,
    parameter DATA_WIDTH = 8,
    parameter INDEX_WIDTH = 8
) (
    input wire clk,
    input wire reset,
    
    input wire [ADDRESS_WIDTH-1:0] addr,
    input wire [DATA_WIDTH-1:0] data_in,
    input wire read,
    input wire write,
    
    output reg [DATA_WIDTH-1:0] data_out,
    output reg hit,
    output reg miss
);

    localparam TAG_WIDTH = ADDRESS_WIDTH - INDEX_WIDTH;
    localparam CACHE_DEPTH = 1 << INDEX_WIDTH;

    localparam S_IDLE = 0, S_COMPARE = 1, S_READ_FETCH = 2, S_READ_WAIT = 3, S_READ_UPDATE = 4, S_WRITE_THRU = 5;

    reg [2:0] state, next_state;
    
    reg [ADDRESS_WIDTH-1:0] addr_reg;
    reg [DATA_WIDTH-1:0] data_in_reg;

    wire [INDEX_WIDTH-1:0] index;
    wire [TAG_WIDTH-1:0] tag;
    wire is_hit;

    wire [TAG_WIDTH-1:0] cache_tag_out;
    wire [DATA_WIDTH-1:0] cache_data_out;
    wire cache_valid_out;
    reg cache_write_en;
    reg [TAG_WIDTH-1:0] cache_tag_in;
    reg [DATA_WIDTH-1:0] cache_data_in;

    wire [DATA_WIDTH-1:0] mem_data_out;
    wire mem_ready;
    reg mem_write_en;
    reg mem_read_en;
    reg [ADDRESS_WIDTH-1:0] mem_addr;
    reg [DATA_WIDTH-1:0] mem_data_in;

    assign index = (state == S_IDLE) ? addr[INDEX_WIDTH-1:0] : addr_reg[INDEX_WIDTH-1:0];
    assign tag = (state == S_IDLE) ? addr[ADDRESS_WIDTH-1:INDEX_WIDTH] : addr_reg[ADDRESS_WIDTH-1:INDEX_WIDTH];
    assign is_hit = (cache_tag_out == tag) && cache_valid_out;

    cache_memory_array #(
        .CACHE_DEPTH(CACHE_DEPTH),
        .DATA_WIDTH(DATA_WIDTH),
        .TAG_WIDTH(TAG_WIDTH)
    ) cache_mem (
        .clk(clk),
        .reset(reset),
        .index(index),
        .tag_in(cache_tag_in),
        .data_in(cache_data_in),
        .write_en(cache_write_en),
        .tag_out(cache_tag_out),
        .data_out(cache_data_out),
        .valid_out(cache_valid_out)
    );

    main_memory #(
        .ADDRESS_WIDTH(ADDRESS_WIDTH),
        .DATA_WIDTH(DATA_WIDTH)
    ) main_mem (
        .clk(clk),
        .addr(mem_addr),
        .data_in(mem_data_in),
        .write_en(mem_write_en),
        .read_en(mem_read_en),
        .data_out(mem_data_out),
        .ready(mem_ready)
    );

    always @(posedge clk or posedge reset) begin
        if (reset) begin
            state <= S_IDLE;
        end else begin
            state <= next_state;
            if (state == S_IDLE && (read || write)) begin
                addr_reg <= addr;
                data_in_reg <= data_in;
            end
        end
    end

    always @(*) begin
        next_state = state;
        hit = 0;
        miss = 0;
        data_out = 8'bx;
        
        cache_write_en = 0;
        cache_tag_in = tag;
        cache_data_in = 8'bx;
        
        mem_write_en = 0;
        mem_read_en = 0;
        mem_addr = addr_reg;
        mem_data_in = data_in_reg;

        case (state)
            S_IDLE: begin
                if (read) begin
                    next_state = S_COMPARE;
                end else if (write) begin
                    next_state = S_COMPARE;
                end
            end
            
            S_COMPARE: begin
                if (read) begin
                    if (is_hit) begin
                        hit = 1;
                        data_out = cache_data_out;
                        next_state = S_IDLE;
                    end else begin
                        miss = 1;
                        next_state = S_READ_FETCH;
                    end
                end else begin
                    next_state = S_WRITE_THRU;
                end
            end

            S_READ_FETCH: begin
                mem_read_en = 1;
                mem_addr = addr_reg;
                next_state = S_READ_WAIT;
            end

            S_READ_WAIT: begin
                mem_read_en = 1;
                mem_addr = addr_reg;
                if (mem_ready) begin
                    next_state = S_READ_UPDATE;
                end else begin
                    next_state = S_READ_WAIT;
                end
            end

            S_READ_UPDATE: begin
                cache_write_en = 1;
                cache_tag_in = tag;
                cache_data_in = mem_data_out;
                data_out = mem_data_out;
                next_state = S_IDLE;
            end

            S_WRITE_THRU: begin
                mem_write_en = 1;
                if (is_hit) begin
                    hit = 1;
                    cache_write_en = 1;
                    cache_data_in = data_in_reg;
                end else begin
                    miss = 1;
                end
                next_state = S_IDLE;
            end
        endcase
    end

endmodule