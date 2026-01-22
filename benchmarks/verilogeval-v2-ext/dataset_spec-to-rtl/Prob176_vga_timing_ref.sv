module RefModule (
    input  logic       clk,
    input  logic       reset,
    output logic [9:0] x,
    output logic [9:0] y,
    output logic       hsync,
    output logic       vsync,
    output logic       active_video
);
    localparam int H_VISIBLE = 640;
    localparam int H_FRONT   = 16;
    localparam int H_SYNC    = 96;
    localparam int H_BACK    = 48;
    localparam int H_TOTAL   = H_VISIBLE + H_FRONT + H_SYNC + H_BACK; // 800

    localparam int V_VISIBLE = 480;
    localparam int V_FRONT   = 10;
    localparam int V_SYNC    = 2;
    localparam int V_BACK    = 33;
    localparam int V_TOTAL   = V_VISIBLE + V_FRONT + V_SYNC + V_BACK; // 525

    always_ff @(posedge clk) begin
        if (reset) begin
            x <= 10'd0;
            y <= 10'd0;
        end else begin
            if (x == (H_TOTAL-1)) begin
                x <= 10'd0;
                if (y == (V_TOTAL-1)) begin
                    y <= 10'd0;
                end else begin
                    y <= y + 10'd1;
                end
            end else begin
                x <= x + 10'd1;
            end
        end
    end

    always_comb begin
        active_video = (x < H_VISIBLE) && (y < V_VISIBLE);

        hsync = ~((x >= (H_VISIBLE + H_FRONT)) && (x < (H_VISIBLE + H_FRONT + H_SYNC)));
        vsync = ~((y >= (V_VISIBLE + V_FRONT)) && (y < (V_VISIBLE + V_FRONT + V_SYNC)));
    end
endmodule

