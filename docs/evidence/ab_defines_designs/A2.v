//------------------------------------------------------------------------
// i2c_master_bit_ctrl
//
// Bit-level controller for an I2C master. Receives simple bit-level
// commands (START, STOP, WRITE, READ) from a byte-level controller and
// translates them into timed, open-drain SCL/SDA control sequences.
//
// Plain Verilog-2001, self-contained (no `include).
//------------------------------------------------------------------------

module i2c_master_bit_ctrl (
    input             clk,      // system clock
    input             rst,      // synchronous active high reset
    input             nReset,   // asynchronous active low reset
    input             ena,      // core enable signal

    input      [15:0] clk_cnt,  // clock prescale value

    input      [ 3:0] cmd,      // command (from byte controller)
    output reg        cmd_ack,  // command complete acknowledge
    output reg        busy,     // i2c bus busy
    output reg        al,       // i2c bus arbitration lost

    input             din,
    output reg        dout,

    input             scl_i,    // i2c clock line input
    output            scl_o,    // i2c clock line output
    output reg        scl_oen,  // i2c clock line output enable (active low)
    input             sda_i,    // i2c data line input
    output            sda_o,    // i2c data line output
    output reg        sda_oen   // i2c data line output enable (active low)
);

    //--------------------------------------------------------------------
    // Command encodings (bit-level commands from the byte controller)
    //--------------------------------------------------------------------
    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    //--------------------------------------------------------------------
    // Bit-level command FSM states
    //--------------------------------------------------------------------
    localparam [3:0] ST_IDLE    = 4'd0;

    localparam [3:0] ST_START_A = 4'd1;
    localparam [3:0] ST_START_B = 4'd2;
    localparam [3:0] ST_START_C = 4'd3;

    localparam [3:0] ST_STOP_A  = 4'd4;
    localparam [3:0] ST_STOP_B  = 4'd5;
    localparam [3:0] ST_STOP_C  = 4'd6;

    localparam [3:0] ST_RD_A    = 4'd7;
    localparam [3:0] ST_RD_B    = 4'd8;
    localparam [3:0] ST_RD_C    = 4'd9;

    localparam [3:0] ST_WR_A    = 4'd10;
    localparam [3:0] ST_WR_B    = 4'd11;
    localparam [3:0] ST_WR_C    = 4'd12;

    reg [3:0] c_state;

    //--------------------------------------------------------------------
    // Open-drain constant-low drive outputs
    //--------------------------------------------------------------------
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //--------------------------------------------------------------------
    // Clock divider / bit-timing counter -> clk_en
    //--------------------------------------------------------------------
    reg [15:0] cnt;
    reg        clk_en;

    wire slave_wait;
    wire scl_sync;

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
        begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (rst)
        begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (!ena)
        begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (slave_wait)
        begin
            cnt    <= cnt;
            clk_en <= 1'b0;
        end
        else if (scl_sync)
        begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (cnt == 16'h0000)
        begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else
        begin
            cnt    <= cnt - 16'h0001;
            clk_en <= 1'b0;
        end
    end

    //--------------------------------------------------------------------
    // Input synchronization: two-stage capture registers
    //--------------------------------------------------------------------
    reg [1:0] cSCL;
    reg [1:0] cSDA;

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
        begin
            cSCL <= 2'b11;
            cSDA <= 2'b11;
        end
        else if (rst)
        begin
            cSCL <= 2'b11;
            cSDA <= 2'b11;
        end
        else
        begin
            cSCL <= {cSCL[0], scl_i};
            cSDA <= {cSDA[0], sda_i};
        end
    end

    //--------------------------------------------------------------------
    // Input filtering: filter_cnt derived from clk_cnt >> 2, controls
    // when new synchronized samples are shifted into the fSCL/fSDA
    // three-sample histories.
    //--------------------------------------------------------------------
    reg [13:0] filter_cnt;
    reg [2:0]  fSCL;
    reg [2:0]  fSDA;

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
            filter_cnt <= 14'h0000;
        else if (rst)
            filter_cnt <= 14'h0000;
        else if (!ena)
            filter_cnt <= 14'h0000;
        else if (filter_cnt == 14'h0000)
            filter_cnt <= clk_cnt[15:2];
        else
            filter_cnt <= filter_cnt - 14'h0001;
    end

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
        begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end
        else if (rst)
        begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end
        else if (filter_cnt == 14'h0000)
        begin
            fSCL <= {fSCL[1:0], cSCL[1]};
            fSDA <= {fSDA[1:0], cSDA[1]};
        end
    end

    // Majority function over the three-sample histories
    wire sSCL = (fSCL[0] & fSCL[1]) | (fSCL[1] & fSCL[2]) | (fSCL[2] & fSCL[0]);
    wire sSDA = (fSDA[0] & fSDA[1]) | (fSDA[1] & fSDA[2]) | (fSDA[2] & fSDA[0]);

    // Delayed versions of the filtered bus signals, for edge detection
    reg dSCL;
    reg dSDA;

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
        begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end
        else if (rst)
        begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end
        else
        begin
            dSCL <= sSCL;
            dSDA <= sSDA;
        end
    end

    //--------------------------------------------------------------------
    // START / STOP detection
    //--------------------------------------------------------------------
    wire sta_condition = ~sSDA & dSDA & sSCL;
    wire sto_condition =  sSDA & ~dSDA & sSCL;

    //--------------------------------------------------------------------
    // Slave clock stretching / multi-master clock synchronization
    //--------------------------------------------------------------------
    assign slave_wait = scl_oen & ~sSCL;
    assign scl_sync   = ~sSCL & dSCL & scl_oen;

    //--------------------------------------------------------------------
    // Bus busy tracking
    //--------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;
    end

    //--------------------------------------------------------------------
    // Read data sampling: capture filtered SDA on filtered SCL rising edge
    //--------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (sSCL & ~dSCL)
            dout <= sSDA;
    end

    //--------------------------------------------------------------------
    // Write data holding register (latched when a WRITE command starts)
    //--------------------------------------------------------------------
    reg dr;

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
            dr <= 1'b1;
        else if (rst)
            dr <= 1'b1;
        else if ((c_state == ST_IDLE) && clk_en && (cmd == I2C_CMD_WRITE))
            dr <= din;
    end

    //--------------------------------------------------------------------
    // Command FSM: combinational output decode (Moore machine)
    //--------------------------------------------------------------------
    reg sda_chk;

    always @(*)
    begin
        case (c_state)
            ST_IDLE:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end

            ST_START_A:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end
            ST_START_B:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
                sda_chk = 1'b0;
            end
            ST_START_C:
            begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
                sda_chk = 1'b0;
            end

            ST_STOP_A:
            begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
                sda_chk = 1'b0;
            end
            ST_STOP_B:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
                sda_chk = 1'b0;
            end
            ST_STOP_C:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end

            ST_RD_A:
            begin
                scl_oen = 1'b0;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end
            ST_RD_B:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end
            ST_RD_C:
            begin
                scl_oen = 1'b0;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end

            ST_WR_A:
            begin
                scl_oen = 1'b0;
                sda_oen = dr;
                sda_chk = 1'b0;
            end
            ST_WR_B:
            begin
                scl_oen = 1'b1;
                sda_oen = dr;
                sda_chk = 1'b1;
            end
            ST_WR_C:
            begin
                scl_oen = 1'b0;
                sda_oen = dr;
                sda_chk = 1'b0;
            end

            default:
            begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
                sda_chk = 1'b0;
            end
        endcase
    end

    //--------------------------------------------------------------------
    // Arbitration-lost detection
    //   - SDA expected released high (sda_oen) but observed low during
    //     write arbitration checking (sda_chk)
    //   - a STOP condition occurs while the FSM is active on a command
    //     that is not itself a requested STOP
    //--------------------------------------------------------------------
    wire arb_lost_write = sda_chk & sda_oen & ~sSDA;
    wire cmd_is_stop     = (c_state == ST_STOP_A) || (c_state == ST_STOP_B) ||
                            (c_state == ST_STOP_C);
    wire arb_lost_stop   = sto_condition & (c_state != ST_IDLE) & ~cmd_is_stop;
    wire arb_lost         = arb_lost_write | arb_lost_stop;

    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
            al <= 1'b0;
        else if (rst)
            al <= 1'b0;
        else
            al <= arb_lost;
    end

    //--------------------------------------------------------------------
    // Command FSM: state transitions and cmd_ack generation
    //--------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
    begin
        if (!nReset)
        begin
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
        end
        else if (rst)
        begin
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
        end
        else if (arb_lost)
        begin
            // Arbitration lost: return to idle, release both lines
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
        end
        else if (clk_en)
        begin
            cmd_ack <= 1'b0;

            case (c_state)
                ST_IDLE:
                begin
                    case (cmd)
                        I2C_CMD_START: c_state <= ST_START_A;
                        I2C_CMD_STOP:  c_state <= ST_STOP_A;
                        I2C_CMD_WRITE: c_state <= ST_WR_A;
                        I2C_CMD_READ:  c_state <= ST_RD_A;
                        default:       c_state <= ST_IDLE;
                    endcase
                end

                ST_START_A: c_state <= ST_START_B;
                ST_START_B: c_state <= ST_START_C;
                ST_START_C:
                begin
                    c_state <= ST_IDLE;
                    cmd_ack <= 1'b1;
                end

                ST_STOP_A: c_state <= ST_STOP_B;
                ST_STOP_B: c_state <= ST_STOP_C;
                ST_STOP_C:
                begin
                    c_state <= ST_IDLE;
                    cmd_ack <= 1'b1;
                end

                ST_RD_A: c_state <= ST_RD_B;
                ST_RD_B: c_state <= ST_RD_C;
                ST_RD_C:
                begin
                    c_state <= ST_IDLE;
                    cmd_ack <= 1'b1;
                end

                ST_WR_A: c_state <= ST_WR_B;
                ST_WR_B: c_state <= ST_WR_C;
                ST_WR_C:
                begin
                    c_state <= ST_IDLE;
                    cmd_ack <= 1'b1;
                end

                default: c_state <= ST_IDLE;
            endcase
        end
        else
        begin
            cmd_ack <= 1'b0;
        end
    end

endmodule
