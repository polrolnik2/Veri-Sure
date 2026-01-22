module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       push,
    input  logic       pop,
    input  logic [7:0] din,
    output logic [7:0] dout,
    output logic       full,
    output logic       empty
);
    localparam int unsigned DEPTH = 16;

    logic [7:0] mem [0:DEPTH-1];
    logic [4:0] sp; // 0..DEPTH (occupancy)

    assign empty = (sp == 0);
    assign full  = (sp == DEPTH);

    always_ff @(posedge clk) begin
        int i;
        if (reset) begin
            sp <= 5'd0;
            dout <= 8'd0;
            for (i = 0; i < DEPTH; i = i + 1) begin
                mem[i] <= 8'd0;
            end
        end else begin
            logic pop_ok;
            logic push_ok;
            pop_ok = pop && !empty;
            push_ok = push && (!full || pop_ok);

            if (pop_ok) begin
                dout <= mem[sp - 1'b1];
            end

            if (pop_ok && push_ok) begin
                // Replace-top: pop then push at same index.
                mem[sp - 1'b1] <= din;
                sp <= sp;
            end else if (pop_ok) begin
                sp <= sp - 1'b1;
            end else if (push_ok) begin
                mem[sp[3:0]] <= din;
                sp <= sp + 1'b1;
            end
        end
    end
endmodule

