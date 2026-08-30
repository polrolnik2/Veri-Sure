//
// i2c_master_bit_ctrl
//
// Bit-level controller for an I2C master. Receives simple bit commands
// (START / STOP / WRITE / READ) from a byte-level controller and turns
// them into timed, open-drain SCL/SDA control sequences. Handles bus-busy
// tracking, arbitration-lost detection, slave clock stretching,
// multi-master clock synchronization, and input synchronization/filtering
// of the SCL and SDA lines.
//
// Plain Verilog-2001. Requires i2c_master_defines.v to be compiled first
// for the `I2C_CMD_* command macros.
//

module i2c_master_bit_ctrl (
    clk,
    rst,
    nReset,
    ena,

    clk_cnt,

    cmd,
    cmd_ack,
    busy,
    al,

    din,
    dout,

    scl_i,
    scl_o,
    scl_oen,
    sda_i,
    sda_o,
    sda_oen
);

    //
    // inputs & outputs
    //
    input             clk;      // system clock
    input             rst;      // synchronous active high reset
    input             nReset;   // asynchronous active low reset
    input             ena;      // core enable signal

    input      [15:0] clk_cnt;  // clock prescale value

    input      [ 3:0] cmd;      // command (from byte controller)
    output            cmd_ack;  // command complete acknowledge
    output            busy;     // i2c bus busy
    output            al;       // i2c bus arbitration lost

    input             din;
    output            dout;

    input             scl_i;    // i2c clock line input
    output            scl_o;    // i2c clock line output
    output            scl_oen;  // i2c clock line output enable (active low)
    input             sda_i;    // i2c data line input
    output            sda_o;    // i2c data line output
    output            sda_oen;  // i2c data line output enable (active low)

    //
    // registered outputs
    //
    reg  cmd_ack;
    reg  busy;
    reg  al;
    reg  dout;
    reg  scl_oen;
    reg  sda_oen;

    // open-drain: lines are never driven high directly
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //
    // internal state
    //

    // clock divider / bit-timing generator
    reg  [15:0] cnt;
    reg         clk_en;

    // input synchronizer + digital glitch filter
    reg  [15:0] filter_cnt;
    reg  [ 1:0] cSCL, cSDA;      // 2-stage synchronizer capture
    reg  [ 2:0] fSCL, fSDA;      // 3-sample filter history
    wire        sSCL, sSDA;      // filtered (majority-voted) bus levels
    reg         dSCL, dSDA;      // delayed filtered bus levels (1 clk)

    // bus condition detection
    wire        sta_condition;
    wire        sto_condition;

    // clock stretch / multi-master sync helpers
    wire        slave_wait;
    wire        scl_sync;

    // arbitration checking
    wire        sda_chk;
    wire        arb_lost;

    // command FSM state
    reg  [ 4:0] c_state;

    localparam [4:0]
        ST_IDLE    = 5'd0,

        ST_START_A = 5'd1,
        ST_START_B = 5'd2,
        ST_START_C = 5'd3,
        ST_START_D = 5'd4,

        ST_STOP_A  = 5'd5,
        ST_STOP_B  = 5'd6,
        ST_STOP_C  = 5'd7,
        ST_STOP_D  = 5'd8,

        ST_RD_A    = 5'd9,
        ST_RD_B    = 5'd10,
        ST_RD_C    = 5'd11,
        ST_RD_D    = 5'd12,

        ST_WR_A    = 5'd13,
        ST_WR_B    = 5'd14,
        ST_WR_C    = 5'd15,
        ST_WR_D    = 5'd16;

    //
    // input synchronization & majority-vote filtering
    //
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL       <= 2'b11;
            cSDA       <= 2'b11;
            filter_cnt <= 16'h0;
            fSCL       <= 3'b111;
            fSDA       <= 3'b111;
        end else if (rst) begin
            cSCL       <= 2'b11;
            cSDA       <= 2'b11;
            filter_cnt <= 16'h0;
            fSCL       <= 3'b111;
            fSDA       <= 3'b111;
        end else begin
            // 2-stage capture of the raw pad inputs
            cSCL <= {cSCL[0], scl_i};
            cSDA <= {cSDA[0], sda_i};

            if (!ena) begin
                // core disabled: hold the filter counter reset
                filter_cnt <= 16'h0;
            end else if (filter_cnt == 16'h0) begin
                // filter sample interval derived from clk_cnt / 4
                filter_cnt <= {2'b00, clk_cnt[15:2]};
                fSCL       <= {fSCL[1:0], cSCL[1]};
                fSDA       <= {fSDA[1:0], cSDA[1]};
            end else begin
                filter_cnt <= filter_cnt - 16'h1;
            end
        end
    end

    // majority function over the 3-sample history
    assign sSCL = (fSCL[0] & fSCL[1]) | (fSCL[1] & fSCL[2]) | (fSCL[2] & fSCL[0]);
    assign sSDA = (fSDA[0] & fSDA[1]) | (fSDA[1] & fSDA[2]) | (fSDA[2] & fSDA[0]);

    // delayed copies of the filtered bus signals, used for edge detection
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end else if (rst) begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end else begin
            dSCL <= sSCL;
            dSDA <= sSDA;
        end
    end

    // START: SDA falls while SCL is high
    // STOP : SDA rises while SCL is high
    assign sta_condition = ~sSDA & dSDA & sSCL;
    assign sto_condition =  sSDA & ~dSDA & sSCL;

    //
    // bus busy tracking
    //
    always @(posedge clk or negedge nReset) begin
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;
    end

    //
    // read data sampling: capture SDA on the rising edge of filtered SCL
    //
    always @(posedge clk or negedge nReset) begin
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (sSCL & ~dSCL)
            dout <= sSDA;
    end

    //
    // slave clock stretching / multi-master clock synchronization
    //
    // slave_wait: we have released SCL, but the filtered line is still low
    // scl_sync  : SCL fell externally while we had it released
    assign slave_wait = scl_oen & ~sSCL;
    assign scl_sync   = scl_oen & dSCL & ~sSCL;

    //
    // clock divider: generates clk_en, the bit-FSM timing tick
    //
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else if (rst) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else if (!ena) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else if (slave_wait) begin
            // SCL is being held low by another bus participant: pause
            cnt    <= cnt;
            clk_en <= 1'b0;
        end else if ((cnt == 16'h0) || scl_sync) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else begin
            cnt    <= cnt - 16'h1;
            clk_en <= 1'b0;
        end
    end

    //
    // arbitration checking
    //
    // asserted during the stable high phase of a WRITE bit
    assign sda_chk = (c_state == ST_WR_C);

    // lost arbitration when:
    //  - we expected SDA released high (sda_oen=1) but see it filtered low
    //  - an unrequested STOP condition appears while a command is active
    assign arb_lost = (sda_chk & sda_oen & ~sSDA) |
                       ((c_state != ST_IDLE) & sto_condition & (cmd != `I2C_CMD_STOP));

    always @(posedge clk or negedge nReset) begin
        if (!nReset)
            al <= 1'b0;
        else if (rst)
            al <= 1'b0;
        else
            al <= arb_lost;
    end

    //
    // command FSM
    //
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else if (rst) begin
            c_state <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else begin
            cmd_ack <= 1'b0;

            if (arb_lost) begin
                // arbitration lost: return to idle, release both lines
                c_state <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
            end else if (clk_en) begin
                case (c_state)
                    ST_IDLE: begin
                        case (cmd)
                            `I2C_CMD_START : c_state <= ST_START_A;
                            `I2C_CMD_STOP  : c_state <= ST_STOP_A;
                            `I2C_CMD_WRITE : c_state <= ST_WR_A;
                            `I2C_CMD_READ  : c_state <= ST_RD_A;
                            default        : c_state <= ST_IDLE;
                        endcase
                    end

                    // START: release SDA & SCL, pull SDA low while SCL high,
                    // then pull SCL low and acknowledge
                    ST_START_A: begin scl_oen <= 1'b1; sda_oen <= 1'b1; c_state <= ST_START_B; end
                    ST_START_B: begin scl_oen <= 1'b1; sda_oen <= 1'b1; c_state <= ST_START_C; end
                    ST_START_C: begin scl_oen <= 1'b1; sda_oen <= 1'b0; c_state <= ST_START_D; end
                    ST_START_D: begin scl_oen <= 1'b0; sda_oen <= 1'b0; c_state <= ST_IDLE; cmd_ack <= 1'b1; end

                    // STOP: drive SDA low, release SCL high, then release
                    // SDA high while SCL high, and acknowledge
                    ST_STOP_A: begin scl_oen <= 1'b0; sda_oen <= 1'b0; c_state <= ST_STOP_B; end
                    ST_STOP_B: begin scl_oen <= 1'b1; sda_oen <= 1'b0; c_state <= ST_STOP_C; end
                    ST_STOP_C: begin scl_oen <= 1'b1; sda_oen <= 1'b0; c_state <= ST_STOP_D; end
                    ST_STOP_D: begin scl_oen <= 1'b1; sda_oen <= 1'b1; c_state <= ST_IDLE; cmd_ack <= 1'b1; end

                    // READ: release SDA, release SCL for the sample window,
                    // drive SCL low again, and acknowledge. dout is captured
                    // separately by the sSCL rising-edge sampling logic.
                    ST_RD_A: begin scl_oen <= 1'b0; sda_oen <= 1'b1; c_state <= ST_RD_B; end
                    ST_RD_B: begin scl_oen <= 1'b1; sda_oen <= 1'b1; c_state <= ST_RD_C; end
                    ST_RD_C: begin scl_oen <= 1'b1; sda_oen <= 1'b1; c_state <= ST_RD_D; end
                    ST_RD_D: begin scl_oen <= 1'b0; sda_oen <= 1'b1; c_state <= ST_IDLE; cmd_ack <= 1'b1; end

                    // WRITE: drive/release SDA per din, release SCL high
                    // (arbitration checked via sda_chk during ST_WR_C),
                    // drive SCL low again, and acknowledge
                    ST_WR_A: begin scl_oen <= 1'b0; sda_oen <= din; c_state <= ST_WR_B; end
                    ST_WR_B: begin scl_oen <= 1'b1; sda_oen <= din; c_state <= ST_WR_C; end
                    ST_WR_C: begin scl_oen <= 1'b1; sda_oen <= din; c_state <= ST_WR_D; end
                    ST_WR_D: begin scl_oen <= 1'b0; sda_oen <= din; c_state <= ST_IDLE; cmd_ack <= 1'b1; end

                    default: c_state <= ST_IDLE;
                endcase
            end
        end
    end

endmodule
