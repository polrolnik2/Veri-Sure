module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       start,
    input  logic [7:0] dividend,
    input  logic [7:0] divisor,
    output logic [7:0] quotient,
    output logic [7:0] remainder,
    output logic       done
);
    logic       busy;
    logic [3:0] count;

    logic [7:0] dividend_shift;
    logic [7:0] divisor_latched;
    logic [7:0] quotient_shift;
    logic [8:0] rem;

    always_ff @(posedge clk) begin
        if (reset) begin
            busy <= 1'b0;
            count <= 4'd0;
            dividend_shift <= 8'd0;
            divisor_latched <= 8'd0;
            quotient_shift <= 8'd0;
            rem <= 9'd0;
            quotient <= 8'd0;
            remainder <= 8'd0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            if (!busy) begin
                if (start) begin
                    if (divisor == 8'd0) begin
                        quotient <= 8'hFF;
                        remainder <= dividend;
                        done <= 1'b1;
                    end else begin
                        busy <= 1'b1;
                        count <= 4'd0;
                        dividend_shift <= dividend;
                        divisor_latched <= divisor;
                        quotient_shift <= 8'd0;
                        rem <= 9'd0;
                    end
                end
            end else begin
                logic [8:0] rem_shift;
                logic [8:0] divisor_ext;
                logic [8:0] rem_next;
                logic q_bit;

                rem_shift = {rem[7:0], dividend_shift[7]};
                divisor_ext = {1'b0, divisor_latched};

                if (rem_shift >= divisor_ext) begin
                    rem_next = rem_shift - divisor_ext;
                    q_bit = 1'b1;
                end else begin
                    rem_next = rem_shift;
                    q_bit = 1'b0;
                end

                rem <= rem_next;
                dividend_shift <= {dividend_shift[6:0], 1'b0};
                quotient_shift <= {quotient_shift[6:0], q_bit};
                count <= count + 4'd1;

                if (count == 4'd7) begin
                    busy <= 1'b0;
                    quotient <= {quotient_shift[6:0], q_bit};
                    remainder <= rem_next[7:0];
                    done <= 1'b1;
                end
            end
        end
    end
endmodule

