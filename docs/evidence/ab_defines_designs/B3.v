//////////////////////////////////////////////////////////////////////////
//
// i2c_master_bit_ctrl
//
// Bit-level controller for an I2C master. Receives simple bit commands
// (START, STOP, WRITE, READ) from a byte-level controller and translates
// them into timed, open-drain SCL/SDA control sequences. Implements
// input synchronization/filtering, bus-busy tracking, START/STOP
// detection, slave clock stretching, multi-master clock synchronization
// and arbitration-lost detection.
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

    //////////////////////////////////////////////////////////////////////
    // Open-drain output model: lines are always driven to constant 0;
    // actual line control is via the (active-low) output enables.
    //////////////////////////////////////////////////////////////////////
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    //////////////////////////////////////////////////////////////////////
    // Input synchronization: two-stage capture of the raw pad inputs.
    //////////////////////////////////////////////////////////////////////
    reg [1:0] cSCL, cSDA;

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

    //////////////////////////////////////////////////////////////////////
    // Input filtering: sampling-interval counter derived from clk_cnt>>2.
    //////////////////////////////////////////////////////////////////////
    reg [15:0] filter_cnt;

    always @(posedge clk or negedge nReset)
        if (!nReset)
            filter_cnt <= 16'h0000;
        else if (rst)
            filter_cnt <= 16'h0000;
        else if (!ena)
            filter_cnt <= 16'h0000;
        else if (filter_cnt == 16'h0000)
            filter_cnt <= (clk_cnt >> 2);
        else
            filter_cnt <= filter_cnt - 16'h0001;

    // three-sample histories, shifted in whenever filter_cnt expires
    reg [2:0] fSCL, fSDA;

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end
        else if (rst) begin
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end
        else if (filter_cnt == 16'h0000) begin
            fSCL <= {fSCL[1:0], cSCL[1]};
            fSDA <= {fSDA[1:0], cSDA[1]};
        end

    // filtered (majority-voted) bus signals
    reg sSCL, sSDA;

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
            sSCL <= (fSCL[2] & fSCL[1]) | (fSCL[2] & fSCL[0]) | (fSCL[1] & fSCL[0]);
            sSDA <= (fSDA[2] & fSDA[1]) | (fSDA[2] & fSDA[0]) | (fSDA[1] & fSDA[0]);
        end

    // delayed versions of the filtered signals, for edge detection
    reg dSCL, dSDA;

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

    //////////////////////////////////////////////////////////////////////
    // START / STOP condition detection
    //////////////////////////////////////////////////////////////////////
    wire sta_condition = ~sSDA & dSDA & sSCL;
    wire sto_condition =  sSDA & ~dSDA & sSCL;

    //////////////////////////////////////////////////////////////////////
    // Bus-busy tracking
    //////////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (sta_condition)
            busy <= 1'b1;
        else if (sto_condition)
            busy <= 1'b0;

    //////////////////////////////////////////////////////////////////////
    // Read data sampling: dout captures sSDA on the rising edge of sSCL
    //////////////////////////////////////////////////////////////////////
    always @(posedge clk or negedge nReset)
        if (!nReset)
            dout <= 1'b0;
        else if (rst)
            dout <= 1'b0;
        else if (sSCL & ~dSCL)
            dout <= sSDA;

    //////////////////////////////////////////////////////////////////////
    // Slave clock stretching / multi-master clock synchronization
    //////////////////////////////////////////////////////////////////////
    wire slave_wait = scl_oen & ~sSCL;              // released SCL still reads low
    wire scl_sync   = scl_oen & dSCL & ~sSCL;        // falling edge while released

    //////////////////////////////////////////////////////////////////////
    // Bit-timing clock divider
    //////////////////////////////////////////////////////////////////////
    reg [15:0] cnt;
    reg        clk_en;

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            cnt    <= 16'h0000;
            clk_en <= 1'b1;
        end
        else if (rst) begin
            cnt    <= 16'h0000;
            clk_en <= 1'b1;
        end
        else if (!ena) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else if (slave_wait) begin
            cnt    <= cnt;
            clk_en <= 1'b0;
        end
        else if ((cnt == 16'h0000) || scl_sync) begin
            cnt    <= clk_cnt;
            clk_en <= 1'b1;
        end
        else begin
            cnt    <= cnt - 16'h0001;
            clk_en <= 1'b0;
        end

    //////////////////////////////////////////////////////////////////////
    // Command FSM
    //////////////////////////////////////////////////////////////////////
    localparam [3:0]
        idle    = 4'd0,
        start_a = 4'd1,
        start_b = 4'd2,
        stop_a  = 4'd3,
        stop_b  = 4'd4,
        rd_a    = 4'd5,
        rd_b    = 4'd6,
        wr_a    = 4'd7,
        wr_b    = 4'd8,
        wr_c    = 4'd9;

    reg [3:0] state;
    reg [3:0] cmd_r;   // latched command for the operation in progress
    reg       sda_chk; // SDA arbitration-check enable (asserted during WRITE high phase)

    // Arbitration lost:
    //  - during arbitration checking, SDA expected released high but reads low
    //  - an unrequested STOP condition is seen while a command is in progress
    wire arb_lost = (sda_chk & ~sSDA) |
                    (sto_condition & (state != idle) & (cmd_r != `I2C_CMD_STOP));

    always @(posedge clk or negedge nReset)
        if (!nReset) begin
            state   <= idle;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk <= 1'b0;
            cmd_r   <= `I2C_CMD_NOP;
            al      <= 1'b0;
        end
        else if (rst) begin
            state   <= idle;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk <= 1'b0;
            cmd_r   <= `I2C_CMD_NOP;
            al      <= 1'b0;
        end
        else begin
            al <= arb_lost;

            if (arb_lost) begin
                // arbitration lost: return to idle, release both lines
                state   <= idle;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
                sda_chk <= 1'b0;
                cmd_ack <= 1'b0;
            end
            else if (clk_en) begin
                case (state)
                    idle: begin
                        cmd_ack <= 1'b0;
                        sda_chk <= 1'b0;
                        case (cmd)
                            `I2C_CMD_START: begin
                                scl_oen <= 1'b1;
                                sda_oen <= 1'b1;
                                cmd_r   <= cmd;
                                state   <= start_a;
                            end
                            `I2C_CMD_STOP: begin
                                sda_oen <= 1'b0;
                                cmd_r   <= cmd;
                                state   <= stop_a;
                            end
                            `I2C_CMD_WRITE: begin
                                sda_oen <= din ? 1'b1 : 1'b0;
                                cmd_r   <= cmd;
                                state   <= wr_a;
                            end
                            `I2C_CMD_READ: begin
                                sda_oen <= 1'b1;
                                cmd_r   <= cmd;
                                state   <= rd_a;
                            end
                            default: begin
                                state <= idle;
                            end
                        endcase
                    end

                    // START: release SDA & SCL, then pull SDA low while SCL
                    // is high (start condition), then pull SCL low.
                    start_a: begin
                        sda_oen <= 1'b0;
                        state   <= start_b;
                    end
                    start_b: begin
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= idle;
                    end

                    // STOP: drive SDA low, release SCL high, then release
                    // SDA high while SCL is high (stop condition).
                    stop_a: begin
                        scl_oen <= 1'b1;
                        state   <= stop_b;
                    end
                    stop_b: begin
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                        state   <= idle;
                    end

                    // READ: release SDA, release SCL high for the sample
                    // window, then pull SCL low again. Sampling itself is
                    // done independently by the dout-capture logic.
                    rd_a: begin
                        scl_oen <= 1'b1;
                        state   <= rd_b;
                    end
                    rd_b: begin
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= idle;
                    end

                    // WRITE: SDA already set from din, release SCL high,
                    // check arbitration during the stable high phase, then
                    // pull SCL low again.
                    wr_a: begin
                        scl_oen <= 1'b1;
                        state   <= wr_b;
                    end
                    wr_b: begin
                        sda_chk <= 1'b1;
                        state   <= wr_c;
                    end
                    wr_c: begin
                        sda_chk <= 1'b0;
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= idle;
                    end

                    default: state <= idle;
                endcase
            end
        end

endmodule
