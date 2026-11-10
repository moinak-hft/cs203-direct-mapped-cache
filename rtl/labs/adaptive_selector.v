// Seed-7 CART tree from python/neurotile/labs.py:train_prefetch_tree.
// Inputs are features from the PREVIOUS 32-demand window, scaled 0..255.
// Policy IDs: 0=off, 1=next line, 2=stride. Predictor generation is separate.
// Unused feature ports preserve the documented four-feature training interface.
module adaptive_selector (
    input  wire [7:0] unit_delta,
    input  wire [7:0] dominant_delta,
    input  wire [7:0] reuse_fraction,
    input  wire [7:0] stride_abs,
    output reg  [1:0] policy
);
    always @* begin
        if (unit_delta > 8'd0)
            policy = 2'd1;
        else if (dominant_delta <= 8'd16)
            policy = 2'd0;
        else if (dominant_delta <= 8'd49)
            policy = 2'd1;
        else
            policy = 2'd2;
    end
endmodule
