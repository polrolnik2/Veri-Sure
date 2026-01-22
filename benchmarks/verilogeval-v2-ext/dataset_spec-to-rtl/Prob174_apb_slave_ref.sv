module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic        psel,
    input  logic        penable,
    input  logic        pwrite,
    input  logic [7:0]  paddr,
    input  logic [31:0] pwdata,
    output logic [31:0] prdata,
    output logic        pready,
    output logic        pslverr
);
    logic [31:0] reg0, reg1, reg2, reg3;

    wire access = psel && penable;

    always_ff @(posedge clk) begin
        if (reset) begin
            reg0 <= 32'd0;
            reg1 <= 32'd0;
            reg2 <= 32'd0;
            reg3 <= 32'd0;
            prdata <= 32'd0;
        end else begin
            if (access) begin
                if (pwrite) begin
                    unique case (paddr)
                        8'h00: reg0 <= pwdata;
                        8'h04: reg1 <= pwdata;
                        8'h08: reg2 <= pwdata;
                        8'h0C: reg3 <= pwdata;
                        default: begin end
                    endcase
                end else begin
                    unique case (paddr)
                        8'h00: prdata <= reg0;
                        8'h04: prdata <= reg1;
                        8'h08: prdata <= reg2;
                        8'h0C: prdata <= reg3;
                        default: prdata <= 32'd0;
                    endcase
                end
            end
        end
    end

    assign pready = 1'b1;
    assign pslverr = 1'b0;
endmodule

