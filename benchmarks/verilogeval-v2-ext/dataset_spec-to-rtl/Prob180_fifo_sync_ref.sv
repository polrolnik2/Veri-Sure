module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       wr_en,
    input  logic       rd_en,
    input  logic [7:0] din,
    output logic [7:0] dout,
    output logic       full,
    output logic       empty
);
    localparam int unsigned DEPTH = 16;
    localparam int unsigned ADDR_BITS = 4;

    logic [7:0] mem [0:DEPTH-1];
    logic [ADDR_BITS-1:0] wr_ptr;
    logic [ADDR_BITS-1:0] rd_ptr;
    logic [ADDR_BITS:0]   count; // 0..DEPTH

    assign empty = (count == 0);
    assign full  = (count == DEPTH);

    always_ff @(posedge clk) begin
        if (reset) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count <= '0;
            dout <= 8'd0;
        end else begin
            logic wr_fire;
            logic rd_fire;
            wr_fire = wr_en && !full;
            rd_fire = rd_en && !empty;

            if (wr_fire) begin
                mem[wr_ptr] <= din;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (rd_fire) begin
                dout <= mem[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
            end

            unique case ({wr_fire, rd_fire})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule

