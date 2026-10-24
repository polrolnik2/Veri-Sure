// PLUMBING FIXTURE ONLY -- ports from the contract, no behaviour. Exists to
// prove the harness elaborates, records traces and decides the frozen set;
// it is not a candidate and is not meant to pass anything.
module i2c_master_bit_ctrl (
    input        clk,
    input        rst,
    input        nReset,
    input        ena,
    input [15:0] clk_cnt,
    input  [3:0] cmd,
    output       cmd_ack,
    output       busy,
    output       al,
    input        din,
    output       dout,
    input        scl_i,
    output       scl_o,
    output       scl_oen,
    input        sda_i,
    output       sda_o,
    output       sda_oen
);
    assign cmd_ack = 1'b0;
    assign busy    = 1'b0;
    assign al      = 1'b0;
    assign dout    = 1'b0;
    assign scl_o   = 1'b0;
    assign scl_oen = 1'b1;
    assign sda_o   = 1'b0;
    assign sda_oen = 1'b1;
endmodule
