//------------------------------------------------------------------------
// i2c_master_bit_ctrl
//
// Bit-level controller of the OpenCores-style I2C master core. Receives
// simple bit commands (START, STOP, WRITE, READ) from the byte-level
// controller and translates them into timed, open-drain SCL/SDA control
// sequences. Provides bus-busy tracking, arbitration-lost detection,
// slave clock stretching, multi-master clock synchronization, input
// synchronization, and glitch filtering.
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

    //---------------------------------------------------------------
    // internal bit-level command encoding
    //---------------------------------------------------------------
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    //---------------------------------------------------------------
    // bit-level FSM state encoding
    //---------------------------------------------------------------
    localparam [4:0]
        ST_IDLE  = 5'd0,
        ST_STA_A = 5'd1,
        ST_STA_B = 5'd2,
        ST_STA_C = 5'd3,
        ST_STA_D = 5'd4,
        ST_STO_A = 5'd5,
        ST_STO_B = 5'd6,
        ST_STO_C = 5'd7,
        ST_STO_D = 5'd8,
        ST_RD_A  = 5'd9,
        ST_RD_B  = 5'd10,
        ST_RD_C  = 5'd11,
        ST_RD_D  = 5'd12,
        ST_WR_A  = 5'd13,
        ST_WR_B  = 5'd14,
        ST_WR_C  = 5'd15,
        ST_WR_D  = 5'd16;

    reg  [4:0]  state;

    //---------------------------------------------------------------
    // internal registers / wires
    //---------------------------------------------------------------
    reg  [15:0] cnt;          // bit-timing counter
    reg         clk_en;       // bit-timing tick

    reg  [15:0] filter_cnt;   // input filter sample-interval counter
    wire [15:0] filter_load;  // clk_cnt >> 2

    reg  [1:0]  cSCL, cSDA;   // input synchronizer stages
    reg  [2:0]  fSCL, fSDA;   // filter sample history
    wire        sSCL, sSDA;   // filtered (majority-voted) bus signals
    reg         dSCL, dSDA;   // delayed filtered bus signals (for edges)

    wire        sta_condition;
    wire        sto_condition;

    wire        slave_wait;
    wire        scl_sync;

    reg         sda_chk;      // arbitration-check enable (asserted during
                               // the stable-high phase of a WRITE bit)
    wire        al_arbitration;
    wire        al_stop;

    //---------------------------------------------------------------
    // open-drain outputs: constant low drive value, control via *_oen
    //---------------------------------------------------------------
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //---------------------------------------------------------------
    // input synchronization (2-stage) into cSCL / cSDA
    //---------------------------------------------------------------
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

    //---------------------------------------------------------------
    // input filter sample-interval counter, derived from clk_cnt >> 2
    //---------------------------------------------------------------
    assign filter_load = {2'b00, clk_cnt[15:2]};

    always @(posedge clk or negedge nReset)
        if (!nReset)
            filter_cnt <= 16'h0000;
        else if (rst)
            filter_cnt <= 16'h0000;
        else if (!ena)
            filter_cnt <= filter_load;
        else if (filter_cnt == 16'h0000)
            filter_cnt <= filter_load;
        else
            filter_cnt <= filter_cnt - 16'h0001;

    //---------------------------------------------------------------
    // filter sample history (fSCL / fSDA) and majority-filtered bus
    // signals (sSCL / sSDA)
    //---------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (rst) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (ena && (filter_cnt == 16'h0000)) begin
            fSCL <= {fSCL[1:0], cSCL[1]};
            fSDA <= {fSDA[1:0], cSDA[1]};
        end

    assign sSCL = (fSCL[0] & fSCL[1]) | (fSCL[1] & fSCL[2]) | (fSCL[2] & fSCL[0]);
    assign sSDA = (fSDA[0] & fSDA[1]) | (fSDA[1] & fSDA[2]) | (fSDA[2] & fSDA[0]);

    //---------------------------------------------------------------
    // delayed filtered bus signals, used for edge detection
    //---------------------------------------------------------------
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

    //---------------------------------------------------------------
    // START / STOP condition detection
    //---------------------------------------------------------------
    assign sta_condition = ~sSDA &  dSDA & sSCL;
    assign sto_condition =  sSDA & ~dSDA & sSCL;

    //---------------------------------------------------------------
    // bus busy tracking: set after START, cleared after STOP
    //---------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;

    //---------------------------------------------------------------
    // read data sampling on the rising edge of filtered SCL
    //---------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (~dSCL & sSCL)
            dout <= sSDA;

    //---------------------------------------------------------------
    // slave clock stretching / multi-master clock synchronization
    //---------------------------------------------------------------
    assign slave_wait = scl_oen & ~sSCL;             // master released, line still low
    assign scl_sync   = scl_oen & dSCL & ~sSCL;       // falling edge while released

    //---------------------------------------------------------------
    // bit-timing counter / clk_en generation
    //---------------------------------------------------------------
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
        end else if (scl_sync) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else if (slave_wait) begin
            clk_en <= 1'b0;                            // hold cnt, pause timing
        end else if (cnt == 16'h0000) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end else begin
            cnt    <= cnt - 16'h0001;
            clk_en <= 1'b0;
        end

    //---------------------------------------------------------------
    // arbitration-lost detection
    //---------------------------------------------------------------
    assign al_arbitration = sda_chk & sda_oen & ~sSDA;
    assign al_stop        = sto_condition & (state != ST_IDLE) & (cmd != I2C_CMD_STOP);

    always @(posedge clk or negedge nReset)
        if (!nReset)
            al <= 1'b0;
        else if (rst)
            al <= 1'b0;
        else if (al_arbitration | al_stop)
            al <= 1'b1;
        else if (state == ST_IDLE)
            al <= 1'b0;

    //---------------------------------------------------------------
    // bit-level command FSM
    //---------------------------------------------------------------
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            state   <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk <= 1'b0;
        end else if (rst) begin
            state   <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;   // default: one-cycle pulse only

            if (al_arbitration | al_stop) begin
                if (clk_en) begin
                    state   <= ST_IDLE;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                    sda_chk <= 1'b0;
                end
            end else if (clk_en) begin
                case (state)
                    ST_IDLE: begin
                        sda_chk <= 1'b0;
                        case (cmd)
                            I2C_CMD_START: state <= ST_STA_A;
                            I2C_CMD_STOP:  state <= ST_STO_A;
                            I2C_CMD_WRITE: state <= ST_WR_A;
                            I2C_CMD_READ:  state <= ST_RD_A;
                            default:       state <= ST_IDLE;
                        endcase
                    end

                    //---------------------------------------------
                    // START: release SDA & SCL, then pull SDA low
                    // while SCL is high, then pull SCL low and ack.
                    //---------------------------------------------
                    ST_STA_A: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        state   <= ST_STA_B;
                    end
                    ST_STA_B: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        state   <= ST_STA_C;
                    end
                    ST_STA_C: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b1;
                        state   <= ST_STA_D;
                    end
                    ST_STA_D: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    //---------------------------------------------
                    // STOP: drive SDA low, release SCL high, then
                    // release SDA high while SCL is high, then ack.
                    //---------------------------------------------
                    ST_STO_A: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b0;
                        state   <= ST_STO_B;
                    end
                    ST_STO_B: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b1;
                        state   <= ST_STO_C;
                    end
                    ST_STO_C: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        state   <= ST_STO_D;
                    end
                    ST_STO_D: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    //---------------------------------------------
                    // READ: release SDA, release SCL high for the
                    // sample window, pull SCL low again, then ack.
                    //---------------------------------------------
                    ST_RD_A: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b0;
                        state   <= ST_RD_B;
                    end
                    ST_RD_B: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        state   <= ST_RD_C;
                    end
                    ST_RD_C: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b0;
                        state   <= ST_RD_D;
                    end
                    ST_RD_D: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    //---------------------------------------------
                    // WRITE: set SDA per din, release SCL high,
                    // enable arbitration checking, pull SCL low,
                    // then ack.
                    //---------------------------------------------
                    ST_WR_A: begin
                        sda_oen <= din;
                        scl_oen <= 1'b0;
                        state   <= ST_WR_B;
                    end
                    ST_WR_B: begin
                        scl_oen <= 1'b1;
                        state   <= ST_WR_C;
                    end
                    ST_WR_C: begin
                        scl_oen <= 1'b1;
                        sda_chk <= 1'b1;
                        state   <= ST_WR_D;
                    end
                    ST_WR_D: begin
                        scl_oen <= 1'b0;
                        sda_chk <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    default: state <= ST_IDLE;
                endcase
            end
        end

endmodule
