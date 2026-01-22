module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic [1:0] coin,
    output logic       dispense,
    output logic [5:0] change
);
    localparam logic [6:0] PRICE = 7'd30;

    logic [5:0] credit;

    function automatic logic [5:0] coin_value(input logic [1:0] c);
        case (c)
            2'b01: coin_value = 6'd5;
            2'b10: coin_value = 6'd10;
            2'b11: coin_value = 6'd25;
            default: coin_value = 6'd0;
        endcase
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            credit <= 6'd0;
            dispense <= 1'b0;
            change <= 6'd0;
        end else begin
            logic [6:0] new_credit;
            logic [6:0] change_full;
            new_credit = {1'b0, credit} + {1'b0, coin_value(coin)};

            dispense <= 1'b0;
            change <= 6'd0;

            if (new_credit >= PRICE) begin
                dispense <= 1'b1;
                change_full = new_credit - PRICE;
                change <= change_full[5:0];
                credit <= 6'd0;
            end else begin
                credit <= new_credit[5:0];
            end
        end
    end
endmodule
