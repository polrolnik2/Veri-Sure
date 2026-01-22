module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       car_side,
    output logic [1:0] main_light,
    output logic [1:0] side_light
);
    localparam logic [1:0] RED    = 2'b00;
    localparam logic [1:0] YELLOW = 2'b01;
    localparam logic [1:0] GREEN  = 2'b10;

    localparam int unsigned MAIN_MIN_GREEN = 10;
    localparam int unsigned YELLOW_LEN = 3;
    localparam int unsigned ALL_RED_LEN = 2;
    localparam int unsigned SIDE_GREEN_LEN = 7;

    typedef enum logic [2:0] {
        S_MAIN_G  = 3'd0,
        S_MAIN_Y  = 3'd1,
        S_ALL_R1  = 3'd2,
        S_SIDE_G  = 3'd3,
        S_SIDE_Y  = 3'd4,
        S_ALL_R2  = 3'd5
    } state_t;

    state_t state;
    logic [5:0] timer;
    logic pending_side;

    always_comb begin
        main_light = RED;
        side_light = RED;
        case (state)
            S_MAIN_G: begin
                main_light = GREEN;
                side_light = RED;
            end
            S_MAIN_Y: begin
                main_light = YELLOW;
                side_light = RED;
            end
            S_ALL_R1: begin
                main_light = RED;
                side_light = RED;
            end
            S_SIDE_G: begin
                main_light = RED;
                side_light = GREEN;
            end
            S_SIDE_Y: begin
                main_light = RED;
                side_light = YELLOW;
            end
            S_ALL_R2: begin
                main_light = RED;
                side_light = RED;
            end
            default: begin
                main_light = GREEN;
                side_light = RED;
            end
        endcase
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= S_MAIN_G;
            timer <= 6'd0;
            pending_side <= 1'b0;
        end else begin
            case (state)
                S_MAIN_G: begin
                    pending_side <= pending_side | car_side;
                    if (timer < (MAIN_MIN_GREEN-1)) timer <= timer + 6'd1;
                    else timer <= timer;

                    if (pending_side && (timer >= (MAIN_MIN_GREEN-1))) begin
                        state <= S_MAIN_Y;
                        timer <= 6'd0;
                        pending_side <= 1'b0;
                    end
                end

                S_MAIN_Y: begin
                    if (timer == (YELLOW_LEN-1)) begin
                        state <= S_ALL_R1;
                        timer <= 6'd0;
                    end else begin
                        timer <= timer + 6'd1;
                    end
                end

                S_ALL_R1: begin
                    if (timer == (ALL_RED_LEN-1)) begin
                        state <= S_SIDE_G;
                        timer <= 6'd0;
                    end else begin
                        timer <= timer + 6'd1;
                    end
                end

                S_SIDE_G: begin
                    if (timer == (SIDE_GREEN_LEN-1)) begin
                        state <= S_SIDE_Y;
                        timer <= 6'd0;
                    end else begin
                        timer <= timer + 6'd1;
                    end
                end

                S_SIDE_Y: begin
                    if (timer == (YELLOW_LEN-1)) begin
                        state <= S_ALL_R2;
                        timer <= 6'd0;
                    end else begin
                        timer <= timer + 6'd1;
                    end
                end

                S_ALL_R2: begin
                    if (timer == (ALL_RED_LEN-1)) begin
                        state <= S_MAIN_G;
                        timer <= 6'd0;
                        pending_side <= 1'b0;
                    end else begin
                        timer <= timer + 6'd1;
                    end
                end

                default: begin
                    state <= S_MAIN_G;
                    timer <= 6'd0;
                    pending_side <= 1'b0;
                end
            endcase
        end
    end
endmodule

