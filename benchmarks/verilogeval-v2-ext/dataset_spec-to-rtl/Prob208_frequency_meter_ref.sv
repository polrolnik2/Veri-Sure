module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic        sig_in,
    output logic [15:0] freq_count,
    output logic        done
);
    localparam int unsigned WINDOW = 64;

    logic [5:0] win_cnt;
    logic [15:0] edge_cnt;
    logic sig_prev;

    always_ff @(posedge clk) begin
        if (reset) begin
            win_cnt <= 6'd0;
            edge_cnt <= 16'd0;
            sig_prev <= 1'b0;
            freq_count <= 16'd0;
            done <= 1'b0;
        end else begin
            logic edge_inc;
            logic [15:0] edge_cnt_next;
            done <= 1'b0;

            edge_inc = sig_in & ~sig_prev;
            edge_cnt_next = edge_cnt + {15'd0, edge_inc};
            sig_prev <= sig_in;

            if (win_cnt == (WINDOW-1)) begin
                freq_count <= edge_cnt_next;
                done <= 1'b1;
                win_cnt <= 6'd0;
                edge_cnt <= 16'd0;
            end else begin
                win_cnt <= win_cnt + 6'd1;
                edge_cnt <= edge_cnt_next;
            end
        end
    end
endmodule

