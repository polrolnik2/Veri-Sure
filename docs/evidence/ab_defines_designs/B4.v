//////////////////////////////////////////////////////////////////////////
// i2c_master_bit_ctrl
//
// Bit-level controller for an I2C master. Translates simple bit-level
// commands (START, STOP, WRITE, READ) coming from a byte-level controller
// into timed, open-drain SCL/SDA control sequences. Provides bus-busy
// tracking, arbitration-lost detection, slave clock stretching support,
// multi-master clock synchronization, and glitch-filtered input sampling.
//
// Plain Verilog-2001. Relies on the `I2C_CMD_* macros defined in
// i2c_master_defines.v, which is compiled ahead of this file.
//////////////////////////////////////////////////////////////////////////

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

    //---------------------------------------------------------------------
    // Open-drain output model: both output values are constant low; the
    // corresponding *_oen signals are what actually control the lines.
    //---------------------------------------------------------------------
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //---------------------------------------------------------------------
    // Command FSM state encoding
    //---------------------------------------------------------------------
    localparam [3:0]
        ST_IDLE    = 4'd0,
        ST_START_A = 4'd1,   // release SDA and SCL
        ST_START_B = 4'd2,   // pull SDA low while SCL is high (START edge)
        ST_START_C = 4'd3,   // pull SCL low, ack
        ST_STOP_A  = 4'd4,   // drive SDA low, SCL low
        ST_STOP_B  = 4'd5,   // release SCL high, SDA still low
        ST_STOP_C  = 4'd6,   // release SDA high while SCL is high (STOP edge), ack
        ST_RD_A    = 4'd7,   // release SDA, SCL low
        ST_RD_B    = 4'd8,   // release SCL high (sample window)
        ST_RD_C    = 4'd9,   // pull SCL low again, ack
        ST_WR_A    = 4'd10,  // drive SDA per din, SCL low
        ST_WR_B    = 4'd11,  // release SCL high, arbitration check window
        ST_WR_C    = 4'd12;  // pull SCL low again, ack

    reg [3:0] c_state;

    //---------------------------------------------------------------------
    // Clock divider / bit-timing generator
    //---------------------------------------------------------------------
    reg [15:0] cnt;
    reg        clk_en;

    wire slave_wait = scl_oen & ~sSCL;              // slave is stretching SCL low
    wire scl_sync   = scl_oen & dSCL & ~sSCL;        // another master forced SCL low

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cnt    <= 16'h0;
            clk_en <= 1'b1;
        end
        else if (rst) begin
            cnt    <= 16'h0;
            clk_en <= 1'b1;
        end
        else if (!ena) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (slave_wait) begin
            clk_en <= 1'b0;
            // cnt holds its value while a slave (or another master) is
            // stretching SCL low.
        end
        else if ((cnt == 16'h0) || scl_sync) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else begin
            cnt    <= cnt - 16'h1;
            clk_en <= 1'b0;
        end

    //---------------------------------------------------------------------
    // Input synchronization (2-stage capture) and glitch filtering
    //---------------------------------------------------------------------
    reg [1:0]  cSCL, cSDA;   // 2-stage synchronizer
    reg [13:0] filter_cnt;   // filter sample interval counter (clk_cnt >> 2)
    reg [2:0]  fSCL, fSDA;   // 3-sample filter histories
    reg        sSCL, sSDA;   // filtered (majority) bus signals
    reg        dSCL, dSDA;   // delayed filtered bus signals (edge detect)

    wire filter_tick = (filter_cnt == 14'h0);

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cSCL <= 2'b11;
            cSDA <= 2'b11;
        end
        else if (rst) begin
            cSCL <= 2'b11;
            cSDA <= 2'b11;
        end
        else begin
            cSCL <= {cSCL[0], scl_i};
            cSDA <= {cSDA[0], sda_i};
        end

    always @(posedge clk or negedge nReset)
        if (!nReset)
            filter_cnt <= 14'h0;
        else if (rst)
            filter_cnt <= 14'h0;
        else if (!ena)
            filter_cnt <= clk_cnt[15:2];
        else if (filter_tick)
            filter_cnt <= clk_cnt[15:2];
        else
            filter_cnt <= filter_cnt - 14'h1;

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end
        else if (rst) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end
        else if (filter_tick) begin
            fSCL <= {fSCL[1:0], cSCL[1]};
            fSDA <= {fSDA[1:0], cSDA[1]};
        end

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            sSCL <= 1'b1;
            sSDA <= 1'b1;
        end
        else if (rst) begin
            sSCL <= 1'b1;
            sSDA <= 1'b1;
        end
        else begin
            sSCL <= (fSCL[0] & fSCL[1]) | (fSCL[1] & fSCL[2]) | (fSCL[2] & fSCL[0]);
            sSDA <= (fSDA[0] & fSDA[1]) | (fSDA[1] & fSDA[2]) | (fSDA[2] & fSDA[0]);
        end

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end
        else if (rst) begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end
        else begin
            dSCL <= sSCL;
            dSDA <= sSDA;
        end

    //---------------------------------------------------------------------
    // START / STOP condition detection and bus-busy tracking
    //---------------------------------------------------------------------
    wire sta_condition = ~sSDA & dSDA & sSCL;
    wire sto_condition =  sSDA & ~dSDA & sSCL;

    always @(posedge clk or negedge nReset)
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;

    //---------------------------------------------------------------------
    // Read data sampling: capture sSDA on the rising edge of sSCL
    //---------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (sSCL & ~dSCL)
            dout <= sSDA;

    //---------------------------------------------------------------------
    // Arbitration-lost detection
    //---------------------------------------------------------------------
    wire cmd_is_stop_state = (c_state == ST_STOP_A) | (c_state == ST_STOP_B) | (c_state == ST_STOP_C);
    wire sda_chk            = (c_state == ST_WR_B) & sda_oen;   // arbitration check window
    wire al_sda_lost        = sda_chk & ~sSDA;
    wire al_unexpected_stop = sto_condition & (c_state != ST_IDLE) & ~cmd_is_stop_state;
    wire arbitration_lost   = al_sda_lost | al_unexpected_stop;

    //---------------------------------------------------------------------
    // Command FSM
    //---------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
            al      <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end
        else if (rst) begin
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
            al      <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end
        else begin
            cmd_ack <= 1'b0;
            al      <= 1'b0;

            if (arbitration_lost) begin
                // Arbitration lost: return to idle and release both lines,
                // regardless of clk_en.
                c_state <= ST_IDLE;
                al      <= 1'b1;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
            end
            else if (clk_en) begin
                case (c_state)
                    ST_IDLE: begin
                        case (cmd)
                            `I2C_CMD_START: c_state <= ST_START_A;
                            `I2C_CMD_STOP:  c_state <= ST_STOP_A;
                            `I2C_CMD_WRITE: c_state <= ST_WR_A;
                            `I2C_CMD_READ:  c_state <= ST_RD_A;
                            default:        c_state <= ST_IDLE;
                        endcase
                    end

                    // START sequence
                    ST_START_A: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        c_state <= ST_START_B;
                    end
                    ST_START_B: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b1;
                        c_state <= ST_START_C;
                    end
                    ST_START_C: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b0;
                        c_state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    // STOP sequence
                    ST_STOP_A: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b0;
                        c_state <= ST_STOP_B;
                    end
                    ST_STOP_B: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b1;
                        c_state <= ST_STOP_C;
                    end
                    ST_STOP_C: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        c_state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    // READ sequence
                    ST_RD_A: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b0;
                        c_state <= ST_RD_B;
                    end
                    ST_RD_B: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        c_state <= ST_RD_C;
                    end
                    ST_RD_C: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b0;
                        c_state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    // WRITE sequence
                    ST_WR_A: begin
                        sda_oen <= din;
                        scl_oen <= 1'b0;
                        c_state <= ST_WR_B;
                    end
                    ST_WR_B: begin
                        sda_oen <= din;
                        scl_oen <= 1'b1;
                        c_state <= ST_WR_C;
                    end
                    ST_WR_C: begin
                        sda_oen <= din;
                        scl_oen <= 1'b0;
                        c_state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    default: c_state <= ST_IDLE;
                endcase
            end
        end

endmodule
