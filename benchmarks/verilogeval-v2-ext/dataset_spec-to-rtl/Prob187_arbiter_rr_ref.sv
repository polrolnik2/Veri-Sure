module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic [3:0] req,
    output logic [3:0] grant
);
    logic [1:0] ptr;
    logic [3:0] grant_next;
    logic [1:0] ptr_next;

    always_comb begin
        grant_next = 4'b0000;
        unique case (ptr)
            2'd0: begin
                if (req[0]) grant_next = 4'b0001;
                else if (req[1]) grant_next = 4'b0010;
                else if (req[2]) grant_next = 4'b0100;
                else if (req[3]) grant_next = 4'b1000;
            end
            2'd1: begin
                if (req[1]) grant_next = 4'b0010;
                else if (req[2]) grant_next = 4'b0100;
                else if (req[3]) grant_next = 4'b1000;
                else if (req[0]) grant_next = 4'b0001;
            end
            2'd2: begin
                if (req[2]) grant_next = 4'b0100;
                else if (req[3]) grant_next = 4'b1000;
                else if (req[0]) grant_next = 4'b0001;
                else if (req[1]) grant_next = 4'b0010;
            end
            default: begin // 2'd3
                if (req[3]) grant_next = 4'b1000;
                else if (req[0]) grant_next = 4'b0001;
                else if (req[1]) grant_next = 4'b0010;
                else if (req[2]) grant_next = 4'b0100;
            end
        endcase

        ptr_next = ptr;
        if (grant_next != 4'b0000) begin
            unique case (1'b1)
                grant_next[0]: ptr_next = 2'd1;
                grant_next[1]: ptr_next = 2'd2;
                grant_next[2]: ptr_next = 2'd3;
                default:      ptr_next = 2'd0;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            ptr <= 2'd0;
            grant <= 4'b0000;
        end else begin
            grant <= grant_next;
            ptr <= ptr_next;
        end
    end
endmodule

