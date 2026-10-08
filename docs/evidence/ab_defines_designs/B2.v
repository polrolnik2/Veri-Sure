//////////////////////////////////////////////////////////////////////////
//
// i2c_master_bit_ctrl
//
// Bit-level controller for an I2C master. Receives simple bit-level
// commands (START/STOP/READ/WRITE) from a byte-level controller and
// translates them into timed, open-drain SCL/SDA control sequences.
// Handles bus-busy tracking, arbitration-lost detection, slave clock
// stretching, multi-master clock synchronization, and input
// synchronization/glitch filtering of the SCL/SDA lines.
//
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

    //////////////////////////////////////////////////////////////////
    // Bit-level command FSM state encoding
    //////////////////////////////////////////////////////////////////
    localparam [3:0]
        ST_IDLE    = 4'd0,
        ST_START_A = 4'd1,
        ST_START_B = 4'd2,
        ST_START_C = 4'd3,
        ST_STOP_A  = 4'd4,
        ST_STOP_B  = 4'd5,
        ST_STOP_C  = 4'd6,
        ST_RD_A    = 4'd7,
        ST_RD_B    = 4'd8,
        ST_RD_C    = 4'd9,
        ST_WR_A    = 4'd10,
        ST_WR_B    = 4'd11,
        ST_WR_C    = 4'd12,
        ST_WR_D    = 4'd13;

    reg  [3:0]  state;

    //////////////////////////////////////////////////////////////////
    // Bit-timing clock divider
    //////////////////////////////////////////////////////////////////
    reg  [15:0] cnt;
    reg         clk_en;

    //////////////////////////////////////////////////////////////////
    // Input synchronization / glitch filtering
    //////////////////////////////////////////////////////////////////
    reg  [1:0]  cSCL, cSDA;         // two-stage input synchronizer
    reg  [15:0] filter_cnt;         // filter sample interval counter
    reg  [2:0]  fSCL, fSDA;         // 3-sample histories for majority filter
    wire        sSCL, sSDA;         // filtered (majority-voted) bus signals
    reg         dSCL, dSDA;         // delayed filtered signals (edge detect)

    //////////////////////////////////////////////////////////////////
    // Bus condition detection
    //////////////////////////////////////////////////////////////////
    wire        sta_condition;
    wire        sto_condition;

    //////////////////////////////////////////////////////////////////
    // Clock stretching / multi-master synchronization
    //////////////////////////////////////////////////////////////////
    wire        slave_wait;
    wire        scl_sync;

    //////////////////////////////////////////////////////////////////
    // Arbitration checking
    //////////////////////////////////////////////////////////////////
    reg         sda_chk;
    wire        sda_arb_lost;
    wire        unexpected_stop;
    wire        arb_lost;

    //////////////////////////////////////////////////////////////////
    // Open-drain output drive values (constant low; enables do the work)
    //////////////////////////////////////////////////////////////////
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //////////////////////////////////////////////////////////////////
    // Input synchronizer + digital glitch filter
    //////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cSCL       <= 2'b11;
            cSDA       <= 2'b11;
            fSCL       <= 3'b111;
            fSDA       <= 3'b111;
            filter_cnt <= 16'h0;
        end
        else if (rst) begin
            cSCL       <= 2'b11;
            cSDA       <= 2'b11;
            fSCL       <= 3'b111;
            fSDA       <= 3'b111;
            filter_cnt <= 16'h0;
        end
        else begin
            // two-stage synchronizer, always running
            cSCL <= {cSCL[0], scl_i};
            cSDA <= {cSDA[0], sda_i};

            if (!ena) begin
                filter_cnt <= 16'h0;
            end
            else if (filter_cnt == 16'h0) begin
                filter_cnt <= {2'b00, clk_cnt[15:2]}; // clk_cnt >> 2
                fSCL       <= {fSCL[1:0], cSCL[1]};
                fSDA       <= {fSDA[1:0], cSDA[1]};
            end
            else begin
                filter_cnt <= filter_cnt - 16'h1;
            end
        end

    // majority-vote filter over the 3-sample history
    assign sSCL = (fSCL[2] & fSCL[1]) | (fSCL[2] & fSCL[0]) | (fSCL[1] & fSCL[0]);
    assign sSDA = (fSDA[2] & fSDA[1]) | (fSDA[2] & fSDA[0]) | (fSDA[1] & fSDA[0]);

    // delayed filtered signals, used for edge detection
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

    //////////////////////////////////////////////////////////////////
    // START / STOP detection
    //////////////////////////////////////////////////////////////////
    assign sta_condition = ~sSDA & dSDA & sSCL;
    assign sto_condition =  sSDA & ~dSDA & sSCL;

    // bus-busy tracking
    always @(posedge clk or negedge nReset)
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;

    //////////////////////////////////////////////////////////////////
    // Read data sampling: capture SDA on the rising edge of filtered SCL
    //////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (sSCL & ~dSCL)
            dout <= sSDA;

    //////////////////////////////////////////////////////////////////
    // Slave clock stretching / multi-master clock synchronization
    //////////////////////////////////////////////////////////////////
    // master released SCL, but the bus still reads low: a slave is stretching
    assign slave_wait = scl_oen & ~sSCL;

    // master released SCL, but SCL just fell externally: another master
    // is driving the bus; resynchronize to it
    assign scl_sync = scl_oen & dSCL & ~sSCL;

    //////////////////////////////////////////////////////////////////
    // Bit-timing clock divider / clk_en generation
    //////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cnt    <= 16'h0;
            clk_en <= 1'b1;
        end
        else if (rst) begin
            cnt    <= 16'h0;
            clk_en <= 1'b1;
        end
        else if ((cnt == 16'h0) || !ena || scl_sync) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (slave_wait) begin
            cnt    <= cnt;
            clk_en <= 1'b0;
        end
        else begin
            cnt    <= cnt - 16'h1;
            clk_en <= 1'b0;
        end

    //////////////////////////////////////////////////////////////////
    // Arbitration-lost detection
    //////////////////////////////////////////////////////////////////
    // expected SDA released high (sda_oen=1) during a write's stable-high
    // check phase, but the bus reads low
    assign sda_arb_lost = sda_chk & sda_oen & ~sSDA;

    // a STOP condition appeared while a command other than STOP is active
    assign unexpected_stop = sto_condition & (state != ST_IDLE)  &
                                              (state != ST_STOP_A) &
                                              (state != ST_STOP_B) &
                                              (state != ST_STOP_C);

    assign arb_lost = sda_arb_lost | unexpected_stop;

    always @(posedge clk or negedge nReset)
        if (!nReset)
            al <= 1'b0;
        else if (rst)
            al <= 1'b0;
        else
            al <= arb_lost;

    //////////////////////////////////////////////////////////////////
    // Bit-level command FSM: next-state logic
    //////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            state <= ST_IDLE;
        end
        else if (rst) begin
            state <= ST_IDLE;
        end
        else if (arb_lost) begin
            // lost arbitration (or an unrequested STOP): abort to idle
            state <= ST_IDLE;
        end
        else if (clk_en) begin
            case (state)
                ST_IDLE:
                    case (cmd)
                        `I2C_CMD_START: state <= ST_START_A;
                        `I2C_CMD_STOP : state <= ST_STOP_A;
                        `I2C_CMD_WRITE: state <= ST_WR_A;
                        `I2C_CMD_READ : state <= ST_RD_A;
                        default       : state <= ST_IDLE;
                    endcase

                ST_START_A: state <= ST_START_B;
                ST_START_B: state <= ST_START_C;
                ST_START_C: state <= ST_IDLE;

                ST_STOP_A:  state <= ST_STOP_B;
                ST_STOP_B:  state <= ST_STOP_C;
                ST_STOP_C:  state <= ST_IDLE;

                ST_RD_A:    state <= ST_RD_B;
                ST_RD_B:    state <= ST_RD_C;
                ST_RD_C:    state <= ST_IDLE;

                ST_WR_A:    state <= ST_WR_B;
                ST_WR_B:    state <= ST_WR_C;
                ST_WR_C:    state <= ST_WR_D;
                ST_WR_D:    state <= ST_IDLE;

                default:    state <= ST_IDLE;
            endcase
        end

    //////////////////////////////////////////////////////////////////
    // Bit-level command FSM: output decode (scl_oen / sda_oen / sda_chk)
    //////////////////////////////////////////////////////////////////
    always @* begin
        // defaults: release both lines, no arbitration check
        scl_oen = 1'b1;
        sda_oen = 1'b1;
        sda_chk = 1'b0;

        case (state)
            ST_IDLE: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end

            // START: release SDA & SCL, then pull SDA low while SCL is
            // high, then pull SCL low
            ST_START_A: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end
            ST_START_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
            end
            ST_START_C: begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
            end

            // STOP: ensure SDA & SCL low, release SCL high, then release
            // SDA high while SCL is high
            ST_STOP_A: begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
            end
            ST_STOP_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
            end
            ST_STOP_C: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end

            // READ: release SDA, release SCL for the sample window, then
            // pull SCL low again. dout is captured by the SCL rising-edge
            // sampling logic above.
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

            // WRITE: drive SDA per din, release SCL high, check
            // arbitration during the stable-high phase, then pull SCL
            // low again
            ST_WR_A: begin
                scl_oen = 1'b0;
                sda_oen = din;
            end
            ST_WR_B: begin
                scl_oen = 1'b1;
                sda_oen = din;
            end
            ST_WR_C: begin
                scl_oen = 1'b1;
                sda_oen = din;
                sda_chk = 1'b1;
            end
            ST_WR_D: begin
                scl_oen = 1'b0;
                sda_oen = din;
            end

            default: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end
        endcase
    end

    //////////////////////////////////////////////////////////////////
    // cmd_ack: one-clk-cycle pulse when a command sequence completes
    //////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cmd_ack <= 1'b0;
        end
        else if (rst) begin
            cmd_ack <= 1'b0;
        end
        else if (arb_lost) begin
            cmd_ack <= 1'b0;
        end
        else if (clk_en) begin
            cmd_ack <= (state == ST_START_C) || (state == ST_STOP_C) ||
                       (state == ST_RD_C)    || (state == ST_WR_D);
        end
        else begin
            cmd_ack <= 1'b0;
        end

endmodule
