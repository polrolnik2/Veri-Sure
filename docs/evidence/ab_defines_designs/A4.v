//------------------------------------------------------------------------
// i2c_master_bit_ctrl
//
// Bit-level controller of an I2C master core. Translates simple bit-level
// commands (START, STOP, WRITE, READ) coming from a byte-level controller
// into timed, open-drain SCL/SDA control sequences. Provides bus-busy and
// arbitration-lost detection, slave clock-stretch handling, multi-master
// clock synchronization, and digital input synchronization/filtering of
// the external SCL/SDA lines.
//
// Plain Verilog-2001, self-contained (no includes).
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

    //--------------------------------------------------------------
    // Bit-level command encoding
    //--------------------------------------------------------------
    localparam I2C_CMD_NOP   = 4'b0000;
    localparam I2C_CMD_START = 4'b0001;
    localparam I2C_CMD_STOP  = 4'b0010;
    localparam I2C_CMD_WRITE = 4'b0011;
    localparam I2C_CMD_READ  = 4'b0100;

    //--------------------------------------------------------------
    // Command FSM states
    //--------------------------------------------------------------
    localparam ST_IDLE  = 4'd0;

    localparam ST_STA_A = 4'd1;  // release SDA and SCL
    localparam ST_STA_B = 4'd2;  // pull SDA low while SCL is high
    localparam ST_STA_C = 4'd3;  // pull SCL low, cmd_ack

    localparam ST_STO_A = 4'd4;  // drive SDA low, SCL low
    localparam ST_STO_B = 4'd5;  // release SCL high, SDA still low
    localparam ST_STO_C = 4'd6;  // release SDA high while SCL high, cmd_ack

    localparam ST_RD_A  = 4'd7;  // release SDA, SCL low
    localparam ST_RD_B  = 4'd8;  // release SCL high (sample window)
    localparam ST_RD_C  = 4'd9;  // drive SCL low again, cmd_ack

    localparam ST_WR_A  = 4'd10; // drive SDA = din, SCL low
    localparam ST_WR_B  = 4'd11; // release SCL high, arbitration check
    localparam ST_WR_C  = 4'd12; // drive SCL low again, cmd_ack

    reg [3:0] state;

    //--------------------------------------------------------------
    // Open-drain output model: outputs are constant low; the line
    // level is actually controlled through the *_oen enables.
    //--------------------------------------------------------------
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //--------------------------------------------------------------
    // Input synchronization: two-stage capture of raw scl_i/sda_i
    //--------------------------------------------------------------
    reg [1:0] cSCL, cSDA;

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cSCL <= 2'b11;
            cSDA <= 2'b11;
        end else if (rst) begin
            cSCL <= 2'b11;
            cSDA <= 2'b11;
        end else begin
            cSCL <= {cSCL[0], scl_i};
            cSDA <= {cSDA[0], sda_i};
        end

    //--------------------------------------------------------------
    // Digital input filtering: filter_cnt derives its interval from
    // clk_cnt >> 2. When it expires, a new sample is shifted into the
    // three-sample histories fSCL/fSDA, and majority logic produces
    // the stable filtered signals sSCL/sSDA.
    //--------------------------------------------------------------
    reg [15:0] filter_cnt;
    reg [2:0]  fSCL, fSDA;
    wire       sSCL, sSDA;

    always @(posedge clk or negedge nReset)
        if (!nReset)
            filter_cnt <= 16'h0000;
        else if (rst)
            filter_cnt <= 16'h0000;
        else if (!ena)
            filter_cnt <= 16'h0000;
        else if (filter_cnt == 16'h0000)
            filter_cnt <= {2'b00, clk_cnt[15:2]};
        else
            filter_cnt <= filter_cnt - 16'h0001;

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (rst) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (filter_cnt == 16'h0000) begin
            fSCL <= {fSCL[1:0], cSCL[1]};
            fSDA <= {fSDA[1:0], cSDA[1]};
        end

    // Majority vote over the three-sample histories
    assign sSCL = (fSCL[0] & fSCL[1]) | (fSCL[1] & fSCL[2]) | (fSCL[2] & fSCL[0]);
    assign sSDA = (fSDA[0] & fSDA[1]) | (fSDA[1] & fSDA[2]) | (fSDA[2] & fSDA[0]);

    //--------------------------------------------------------------
    // Delayed filtered signals, used for START/STOP edge detection
    // and for rising-edge SCL sampling of dout.
    //--------------------------------------------------------------
    reg dSCL, dSDA;

    always @(posedge clk or negedge nReset)
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

    // START condition: SDA falls while SCL is high
    wire sta_condition = ~sSDA & dSDA & sSCL;
    // STOP condition: SDA rises while SCL is high
    wire sto_condition =  sSDA & ~dSDA & sSCL;

    //--------------------------------------------------------------
    // Bus busy tracking
    //--------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;

    //--------------------------------------------------------------
    // Received data bit: sampled on the rising edge of filtered SCL
    //--------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (sSCL & ~dSCL)
            dout <= sSDA;

    //--------------------------------------------------------------
    // Slave clock stretching / multi-master clock synchronization
    //--------------------------------------------------------------
    // Master has released SCL (scl_oen=1) but the filtered line is
    // still observed low: a participant is stretching the clock.
    wire slave_wait = scl_oen & ~sSCL;

    // Falling edge of filtered SCL while this master has released it:
    // another master is driving SCL low; resynchronize the counter.
    wire scl_sync = scl_oen & dSCL & ~sSCL;

    //--------------------------------------------------------------
    // Bit-timing clock divider / clk_en generation
    //--------------------------------------------------------------
    reg [15:0] cnt;
    reg        clk_en;

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cnt    <= 16'h0000;
            clk_en <= 1'b1;
        end else if (rst) begin
            cnt    <= 16'h0000;
            clk_en <= 1'b1;
        end else if (!ena) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else if (slave_wait) begin
            cnt    <= cnt;
            clk_en <= 1'b0;
        end else if ((cnt == 16'h0000) || scl_sync) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else begin
            cnt    <= cnt - 16'h0001;
            clk_en <= 1'b0;
        end

    //--------------------------------------------------------------
    // Arbitration-lost detection
    //--------------------------------------------------------------
    reg sda_chk; // asserted during the stable high phase of a WRITE bit

    // Expects SDA released high (sda_oen=1) but observes it low
    wire al_sda_lost = sda_chk & sda_oen & ~sSDA;

    // Unexpected STOP condition while a (non-STOP) command is active
    wire stop_seq   = (state == ST_STO_A) || (state == ST_STO_B) || (state == ST_STO_C);
    wire al_stop_lost = sto_condition & (state != ST_IDLE) & ~stop_seq;

    wire al_condition = al_sda_lost | al_stop_lost;

    always @(posedge clk or negedge nReset)
        if (!nReset)
            al <= 1'b0;
        else if (rst)
            al <= 1'b0;
        else
            al <= al_condition;

    //--------------------------------------------------------------
    // Command-acknowledge pulse generation
    //--------------------------------------------------------------
    wire cmd_done = clk_en & ((state == ST_STA_C) || (state == ST_STO_C) ||
                               (state == ST_RD_C)  || (state == ST_WR_C));

    always @(posedge clk or negedge nReset)
        if (!nReset)
            cmd_ack <= 1'b0;
        else if (rst)
            cmd_ack <= 1'b0;
        else
            cmd_ack <= cmd_done;

    //--------------------------------------------------------------
    // Command FSM: state register
    //--------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            state <= ST_IDLE;
        end else if (rst) begin
            state <= ST_IDLE;
        end else if (al_condition) begin
            // Arbitration lost: return to idle and release the bus
            state <= ST_IDLE;
        end else if (clk_en) begin
            case (state)
                ST_IDLE: begin
                    case (cmd)
                        I2C_CMD_START: state <= ST_STA_A;
                        I2C_CMD_STOP:  state <= ST_STO_A;
                        I2C_CMD_WRITE: state <= ST_WR_A;
                        I2C_CMD_READ:  state <= ST_RD_A;
                        default:       state <= ST_IDLE;
                    endcase
                end

                ST_STA_A: state <= ST_STA_B;
                ST_STA_B: state <= ST_STA_C;
                ST_STA_C: state <= ST_IDLE;

                ST_STO_A: state <= ST_STO_B;
                ST_STO_B: state <= ST_STO_C;
                ST_STO_C: state <= ST_IDLE;

                ST_RD_A:  state <= ST_RD_B;
                ST_RD_B:  state <= ST_RD_C;
                ST_RD_C:  state <= ST_IDLE;

                ST_WR_A:  state <= ST_WR_B;
                ST_WR_B:  state <= ST_WR_C;
                ST_WR_C:  state <= ST_IDLE;

                default:  state <= ST_IDLE;
            endcase
        end

    //--------------------------------------------------------------
    // Command FSM: output (Mealy-style) decoding of scl_oen, sda_oen
    // and sda_chk from the current phase.
    //--------------------------------------------------------------
    always @(*) begin
        // defaults: bus released
        scl_oen = 1'b1;
        sda_oen = 1'b1;
        sda_chk = 1'b0;

        case (state)
            ST_IDLE: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end

            // START: release SDA & SCL, pull SDA low while SCL high,
            // then pull SCL low.
            ST_STA_A: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end
            ST_STA_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
            end
            ST_STA_C: begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
            end

            // STOP: drive SDA low, release SCL high, then release SDA
            // high while SCL is high.
            ST_STO_A: begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
            end
            ST_STO_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
            end
            ST_STO_C: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end

            // READ: release SDA, release SCL high for the sample
            // window, then drive SCL low again.
            ST_RD_A: begin
                scl_oen = 1'b0;
                sda_oen = 1'b1;
            end
            ST_RD_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end
            ST_RD_C: begin
                scl_oen = 1'b0;
                sda_oen = 1'b1;
            end

            // WRITE: set SDA = din, release SCL high while checking
            // arbitration, then drive SCL low again.
            ST_WR_A: begin
                scl_oen = 1'b0;
                sda_oen = din;
            end
            ST_WR_B: begin
                scl_oen = 1'b1;
                sda_oen = din;
                sda_chk = 1'b1;
            end
            ST_WR_C: begin
                scl_oen = 1'b0;
                sda_oen = din;
            end

            default: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end
        endcase
    end

endmodule
