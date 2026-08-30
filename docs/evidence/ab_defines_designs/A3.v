//-----------------------------------------------------------------------------
// i2c_master_bit_ctrl
//
// Bit-level controller for an I2C master. Receives simple bit commands
// (START, STOP, WRITE, READ) from a byte-level controller and translates
// them into timed, open-drain SCL/SDA control sequences. Provides bus-busy
// and arbitration-lost detection, slave clock stretching, multi-master
// clock synchronization, and digitally filtered/synchronized bus inputs.
//-----------------------------------------------------------------------------

module i2c_master_bit_ctrl (
    input             clk,      // system clock
    input             rst,      // synchronous active high reset
    input             nReset,   // asynchronous active low reset
    input             ena,      // core enable signal

    input      [15:0] clk_cnt,  // clock prescale value

    input      [ 3:0] cmd,      // command (from byte controller)
    output reg        cmd_ack,  // command complete acknowledge
    output reg        busy,     // i2c bus busy
    output            al,       // i2c bus arbitration lost

    input             din,
    output reg        dout,

    input             scl_i,    // i2c clock line input
    output            scl_o,    // i2c clock line output
    output reg        scl_oen,  // i2c clock line output enable (active low)
    input             sda_i,    // i2c data line input
    output            sda_o,    // i2c data line output
    output reg        sda_oen   // i2c data line output enable (active low)
);

    //-------------------------------------------------------------------
    // Command encoding (decoded from byte controller while FSM is idle)
    //-------------------------------------------------------------------
    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    //-------------------------------------------------------------------
    // Bit-level command FSM states
    //-------------------------------------------------------------------
    localparam [3:0]
        idle    = 4'd0,
        start_a = 4'd1,
        start_b = 4'd2,
        start_c = 4'd3,
        stop_a  = 4'd4,
        stop_b  = 4'd5,
        stop_c  = 4'd6,
        rd_a    = 4'd7,
        rd_b    = 4'd8,
        rd_c    = 4'd9,
        wr_a    = 4'd10,
        wr_b    = 4'd11,
        wr_c    = 4'd12,
        wr_d    = 4'd13;

    reg [3:0] c_state;

    //-------------------------------------------------------------------
    // Open-drain output model: outputs are constant low; oen controls
    // whether the line is actively driven low or released high.
    //-------------------------------------------------------------------
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //-------------------------------------------------------------------
    // Bit-timing clock divider: generates clk_en from clk_cnt
    //-------------------------------------------------------------------
    reg  [15:0] cnt;
    reg         clk_en;
    wire        slave_wait;
    wire        scl_sync;

    // Slave clock stretching: SCL just released by this master but the
    // filtered SCL input is still low -> hold the timing counter.
    assign slave_wait = scl_oen & ~sSCL;

    // Multi-master clock synchronization: falling edge on filtered SCL
    // while this master has released SCL high -> reload/resync counter.
    assign scl_sync = scl_oen & dSCL & ~sSCL;

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

    //-------------------------------------------------------------------
    // Input synchronization: two-stage capture of raw scl_i / sda_i
    //-------------------------------------------------------------------
    reg [1:0] cSCL, cSDA;

    always @(posedge clk or negedge nReset) begin
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
    end

    //-------------------------------------------------------------------
    // Digital glitch filter: filter_cnt derived from clk_cnt >> 2;
    // when it expires, the synchronized sample is shifted into a
    // 3-sample history, and the filtered line is the majority of that
    // history.
    //-------------------------------------------------------------------
    reg  [15:0] filter_cnt;
    reg  [2:0]  fSCL, fSDA;
    wire        sSCL, sSDA;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt <= 16'h0;
        end else if (rst) begin
            filter_cnt <= 16'h0;
        end else if (!ena) begin
            filter_cnt <= 16'h0;
        end else if (filter_cnt == 16'h0) begin
            filter_cnt <= {2'b00, clk_cnt[15:2]};
        end else begin
            filter_cnt <= filter_cnt - 16'h1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (rst) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (ena && (filter_cnt == 16'h0)) begin
            fSCL <= {fSCL[1:0], cSCL[1]};
            fSDA <= {fSDA[1:0], cSDA[1]};
        end
    end

    // Majority-of-3 filtering
    assign sSCL = (fSCL[0] & fSCL[1]) | (fSCL[1] & fSCL[2]) | (fSCL[2] & fSCL[0]);
    assign sSDA = (fSDA[0] & fSDA[1]) | (fSDA[1] & fSDA[2]) | (fSDA[2] & fSDA[0]);

    //-------------------------------------------------------------------
    // Delayed filtered lines (used for edge / condition detection)
    //-------------------------------------------------------------------
    reg dSCL, dSDA;

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

    //-------------------------------------------------------------------
    // START / STOP condition detection
    //-------------------------------------------------------------------
    wire sta_condition = ~sSDA & dSDA & sSCL;
    wire sto_condition =  sSDA & ~dSDA & sSCL;

    //-------------------------------------------------------------------
    // Bus busy tracking
    //-------------------------------------------------------------------
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition) begin
            busy <= 1'b1;
        end else if (sto_condition) begin
            busy <= 1'b0;
        end
    end

    //-------------------------------------------------------------------
    // Read data sampling: capture filtered SDA on rising edge of
    // filtered SCL.
    //-------------------------------------------------------------------
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (~dSCL & sSCL) begin
            dout <= sSDA;
        end
    end

    //-------------------------------------------------------------------
    // Arbitration checking / arbitration-lost detection
    //-------------------------------------------------------------------
    // sda_chk is asserted during the stable high phase of a WRITE bit
    wire sda_chk = (c_state == wr_c);

    // Arbitration lost when we expect SDA released high (din=1) but the
    // filtered line is observed low, or when an unrequested STOP is
    // detected while a command is active.
    assign al = (sda_chk & din & ~sSDA) |
                (sto_condition & (c_state != idle) & (cmd != I2C_CMD_STOP));

    //-------------------------------------------------------------------
    // Bit-level command FSM
    //-------------------------------------------------------------------
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            c_state <= idle;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else if (rst) begin
            c_state <= idle;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else begin
            cmd_ack <= 1'b0;

            if (al) begin
                // Arbitration lost: return to idle, release both lines
                c_state <= idle;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
            end else if (clk_en) begin
                case (c_state)
                    idle: begin
                        case (cmd)
                            I2C_CMD_START: c_state <= start_a;
                            I2C_CMD_STOP : c_state <= stop_a;
                            I2C_CMD_WRITE: c_state <= wr_a;
                            I2C_CMD_READ : c_state <= rd_a;
                            default      : c_state <= idle;
                        endcase
                    end

                    // START: release SDA & SCL, pull SDA low while SCL
                    // is high, then pull SCL low and acknowledge.
                    start_a: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        c_state <= start_b;
                    end
                    start_b: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        c_state <= start_c;
                    end
                    start_c: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        c_state <= idle;
                        cmd_ack <= 1'b1;
                    end

                    // STOP: drive SDA low, release SCL high, then
                    // release SDA high while SCL is high; acknowledge.
                    stop_a: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        c_state <= stop_b;
                    end
                    stop_b: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        c_state <= stop_c;
                    end
                    stop_c: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        c_state <= idle;
                        cmd_ack <= 1'b1;
                    end

                    // READ: release SDA, release SCL high for the
                    // sample window, drive SCL low again; acknowledge.
                    // (Actual sampling into dout happens on the sSCL
                    // rising-edge logic above, independent of state.)
                    rd_a: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        c_state <= rd_b;
                    end
                    rd_b: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        c_state <= rd_c;
                    end
                    rd_c: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        c_state <= idle;
                        cmd_ack <= 1'b1;
                    end

                    // WRITE: set SDA per din, release SCL high, hold
                    // stable high phase (arbitration checked via
                    // sda_chk), drive SCL low again; acknowledge.
                    wr_a: begin
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        c_state <= wr_b;
                    end
                    wr_b: begin
                        scl_oen <= 1'b1;
                        sda_oen <= din;
                        c_state <= wr_c;
                    end
                    wr_c: begin
                        scl_oen <= 1'b1;
                        sda_oen <= din;
                        c_state <= wr_d;
                    end
                    wr_d: begin
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        c_state <= idle;
                        cmd_ack <= 1'b1;
                    end

                    default: c_state <= idle;
                endcase
            end
        end
    end

endmodule
