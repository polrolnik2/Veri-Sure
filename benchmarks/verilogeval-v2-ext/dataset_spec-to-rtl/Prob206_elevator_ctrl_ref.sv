module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       req0,
    input  logic       req1,
    input  logic       req2,
    output logic [1:0] floor,
    output logic [1:0] dir,
    output logic       door_open
);
    localparam logic [1:0] DIR_IDLE = 2'd0;
    localparam logic [1:0] DIR_UP   = 2'd1;
    localparam logic [1:0] DIR_DOWN = 2'd2;

    logic [2:0] pending;

    function automatic logic has_above(input logic [2:0] pend, input logic [1:0] fl);
        case (fl)
            2'd0: has_above = pend[2] | pend[1];
            2'd1: has_above = pend[2];
            default: has_above = 1'b0;
        endcase
    endfunction

    function automatic logic has_below(input logic [2:0] pend, input logic [1:0] fl);
        case (fl)
            2'd2: has_below = pend[1] | pend[0];
            2'd1: has_below = pend[0];
            default: has_below = 1'b0;
        endcase
    endfunction

    function automatic logic pend_here(input logic [2:0] pend, input logic [1:0] fl);
        case (fl)
            2'd0: pend_here = pend[0];
            2'd1: pend_here = pend[1];
            2'd2: pend_here = pend[2];
            default: pend_here = 1'b0;
        endcase
    endfunction

    function automatic logic [2:0] clear_here(input logic [2:0] pend, input logic [1:0] fl);
        logic [2:0] tmp;
        begin
            tmp = pend;
            case (fl)
                2'd0: tmp[0] = 1'b0;
                2'd1: tmp[1] = 1'b0;
                2'd2: tmp[2] = 1'b0;
                default: tmp = pend;
            endcase
            clear_here = tmp;
        end
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            floor <= 2'd0;
            dir <= DIR_IDLE;
            door_open <= 1'b0;
            pending <= 3'd0;
        end else begin
            logic [2:0] pend_next;
            logic above;
            logic below;

            pend_next = pending | {req2, req1, req0};
            door_open <= 1'b0;

            if (pend_here(pend_next, floor)) begin
                // Serve current floor.
                pending <= clear_here(pend_next, floor);
                dir <= DIR_IDLE;
                door_open <= 1'b1;
            end else if (pend_next == 3'd0) begin
                pending <= pend_next;
                dir <= DIR_IDLE;
            end else begin
                above = has_above(pend_next, floor);
                below = has_below(pend_next, floor);

                pending <= pend_next;

                case (dir)
                    DIR_UP: begin
                        if (above) begin
                            floor <= floor + 2'd1;
                            dir <= DIR_UP;
                        end else if (below) begin
                            floor <= floor - 2'd1;
                            dir <= DIR_DOWN;
                        end else begin
                            dir <= DIR_IDLE;
                        end
                    end
                    DIR_DOWN: begin
                        if (below) begin
                            floor <= floor - 2'd1;
                            dir <= DIR_DOWN;
                        end else if (above) begin
                            floor <= floor + 2'd1;
                            dir <= DIR_UP;
                        end else begin
                            dir <= DIR_IDLE;
                        end
                    end
                    default: begin  // IDLE
                        if (above) begin
                            floor <= floor + 2'd1;
                            dir <= DIR_UP;
                        end else if (below) begin
                            floor <= floor - 2'd1;
                            dir <= DIR_DOWN;
                        end else begin
                            dir <= DIR_IDLE;
                        end
                    end
                endcase
            end
        end
    end
endmodule

