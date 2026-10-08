//
// i2c_master_bit_ctrl
//
// Bit-level controller of an I2C master core.  Translates the bit commands
// issued by the byte-level controller into timed open-drain SCL/SDA
// sequences.  Written from SPEC.md / contract.json / PROBES.md.
//
// Open-drain model: scl_o and sda_o are constant 1'b0; the *_oen signals are
// active low output enables (0 = drive the line low, 1 = release the line).
//
// Observation convention: every registered signal is written so that its new
// value and the condition that produced it are visible on the SAME clock
// state.  That is why the bus-status logic evaluates the majority filter's
// next value (s_*_nxt) rather than the already-registered one: "busy is set
// after a START condition is detected" is one clock state, not two.
//

`timescale 1ns / 1ps

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
    output reg        sda_oen,  // i2c data line output enable (active low)

    // ------------------------------------------------------------------
    // Observation ports for the internal states named by the specification
    // ------------------------------------------------------------------
    output            idle,               // FSM is in the idle state
    output            cnt_zero,           // timing counter cnt has expired
    output            clk_en,             // timing enable tick
    output            slave_wait,         // slave clock stretching detected
    output            scl_sync,           // multi-master clock synchronization
    output            cscl,               // cSCL capture of scl_i
    output            csda,               // cSDA capture of sda_i
    output            filter_cnt,         // filter counter is counting
    output            filter_cnt_expired, // filter counter expired -> shift sample
    output            fscl,               // newest sample in the fSCL history
    output            fsda,               // newest sample in the fSDA history
    output            sscl,               // filtered SCL (majority of fSCL)
    output            ssda,               // filtered SDA (majority of fSDA)
    output            dscl,               // delayed filtered SCL
    output            dsda,               // delayed filtered SDA
    output            sta_condition,      // filtered START condition
    output            sto_condition,      // filtered STOP condition
    output            active_command,     // FSM is executing a command
    output            sda_chk,            // SDA arbitration checking enabled
    output            filtered_scl_rise,  // rising edge of filtered SCL
    output            start_sequence,     // FSM inside the START sequence
    output            stop_sequence,      // FSM inside the STOP sequence
    output            read_sequence,      // FSM inside the READ sequence
    output            write_sequence      // FSM inside the WRITE sequence
);

    // ------------------------------------------------------------------
    // command encodings (per contract.json)
    // ------------------------------------------------------------------
    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    // ------------------------------------------------------------------
    // bit-level command FSM states
    //
    // Every sequence drives its last line transition in a state that is still
    // part of the sequence, and uses one final state whose only effect is the
    // return to idle together with the one-clock cmd_ack.
    // ------------------------------------------------------------------
    localparam [4:0] ST_IDLE    = 5'd0,
                     ST_START_A = 5'd1,   // release SDA
                     ST_START_B = 5'd2,   // release SCL
                     ST_START_C = 5'd3,   // SDA low while SCL high  (START)
                     ST_START_D = 5'd4,   // SCL low
                     ST_START_E = 5'd5,   // done -> idle + ack
                     ST_STOP_A  = 5'd6,   // SDA low, SCL low
                     ST_STOP_B  = 5'd7,   // release SCL
                     ST_STOP_C  = 5'd8,   // release SDA while SCL high (STOP)
                     ST_STOP_D  = 5'd9,   // done -> idle + ack
                     ST_RD_A    = 5'd10,  // release SDA
                     ST_RD_B    = 5'd11,  // release SCL: sample window
                     ST_RD_C    = 5'd12,  // SCL low
                     ST_RD_D    = 5'd13,  // done -> idle + ack
                     ST_WR_A    = 5'd14,  // drive SDA from din
                     ST_WR_B    = 5'd15,  // let SDA settle while SCL is low
                     ST_WR_C    = 5'd16,  // release SCL, check arbitration
                     ST_WR_D    = 5'd17,  // SCL low
                     ST_WR_E    = 5'd18;  // done -> idle + ack

    reg  [ 4:0] c_state;

    /* verilator lint_off UNUSEDSIGNAL */
    reg  [ 1:0] c_scl, c_sda;      // two stage input capture registers
    /* verilator lint_on UNUSEDSIGNAL */
    reg  [ 2:0] f_scl, f_sda;      // three sample filter histories
    reg         s_scl, s_sda;      // majority filtered lines
    reg         d_scl, d_sda;      // delayed filtered lines

    reg  [15:0] cnt;               // bit timing divider
    reg  [13:0] fcnt;              // filter sampling divider
    reg         clk_en_r;          // timing enable tick
    reg         slave_wait_r;      // clock stretching
    reg         sda_chk_r;         // arbitration check window
    reg         cmd_stop;          // the running command is a STOP request

    // ------------------------------------------------------------------
    // 1. open drain drive values -- the module never drives a line high
    // ------------------------------------------------------------------
    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    // ------------------------------------------------------------------
    // 5. input synchronization and filtering
    //
    // The three sample histories are the glitch filter proper: a new sample is
    // taken every time the filter counter expires, and the filtered line is
    // the majority of the last three samples, so any excursion that survives
    // at most one sample cannot move it.
    // ------------------------------------------------------------------
    wire [13:0] filt_reload = (clk_cnt[15:2] == 14'd0) ? 14'd0
                                                      : (clk_cnt[15:2] - 14'd1);

    wire s_scl_nxt = (f_scl[2] & f_scl[1]) | (f_scl[1] & f_scl[0]) |
                     (f_scl[2] & f_scl[0]);
    wire s_sda_nxt = (f_sda[2] & f_sda[1]) | (f_sda[1] & f_sda[0]) |
                     (f_sda[2] & f_sda[0]);

    // 6. START / STOP detection on the filtered lines, evaluated against the
    //    value the filtered lines are taking at this very clock edge.
    wire sta_nxt = ~s_sda_nxt &  s_sda & s_scl_nxt;
    wire sto_nxt =  s_sda_nxt & ~s_sda & s_scl_nxt;
    wire scl_rise_nxt = s_scl_nxt & ~s_scl;

    // ------------------------------------------------------------------
    // 4. multi master clock synchronization: another master pulled SCL low
    //    while this master had released it.
    // ------------------------------------------------------------------
    wire scl_sync_w = d_scl & ~s_scl & scl_oen;

    // ------------------------------------------------------------------
    // 2. clock divider / timing tick
    //
    // cnt is reloaded on reset, while the core is disabled, on expiry and on
    // clock synchronization; slave_wait freezes it.  The FSM advances on the
    // expiry itself, so the tick and the phase it produces are one state.
    // Clock synchronization restarts the low period but does not advance the
    // FSM -- it postpones the next phase rather than bringing it forward.
    // ------------------------------------------------------------------
    wire tick = ena & ~(scl_oen & ~s_scl) & ~|cnt;

    always @(posedge clk or negedge nReset)
      if (!nReset)                  cnt <= 16'h0000;
      else if (rst)                 cnt <= clk_cnt;
      else if (!ena)                cnt <= clk_cnt;
      else if (slave_wait_r)        cnt <= cnt;
      else if (~|cnt | scl_sync_w)  cnt <= clk_cnt;
      else                          cnt <= cnt - 16'h0001;

    // clk_en is the counter's own reload indicator (reset, cnt reaching
    // zero, ena low, or a multi-master resync all restart it), broader than
    // tick: tick also folds in ena and the stretch freeze because only tick
    // may advance the command FSM. clk_en does not gate the FSM itself, so
    // it has no reason to go quiet just because ena dropped or a stretch is
    // in progress -- the counter still reloads either way.
    always @(posedge clk or negedge nReset)
      if (!nReset)      clk_en_r <= 1'b1;
      else if (rst)     clk_en_r <= 1'b1;
      else              clk_en_r <= ~ena | ~|cnt | scl_sync_w;

    // ------------------------------------------------------------------
    // 3. slave clock stretching
    //
    // The master has released SCL through scl_oen but the filtered SCL input
    // is still low: somebody else is holding the line down, so the bit timing
    // waits instead of walking on to the next phase.
    // ------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
      if (!nReset)      slave_wait_r <= 1'b0;
      else if (rst)     slave_wait_r <= 1'b0;
      else              slave_wait_r <= scl_oen & ~s_scl;

    // ------------------------------------------------------------------
    // two stage capture of the raw lines
    // ------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
      if (!nReset)
        begin
          c_scl <= 2'b11;
          c_sda <= 2'b11;
        end
      else if (rst)
        begin
          c_scl <= 2'b11;
          c_sda <= 2'b11;
        end
      else
        begin
          c_scl <= {c_scl[0], scl_i};
          c_sda <= {c_sda[0], sda_i};
        end

    // filter sampling interval, derived from clk_cnt >> 2; a zero interval
    // samples on every enabled clock.
    always @(posedge clk or negedge nReset)
      if (!nReset)             fcnt <= 14'h0000;
      else if (rst | ~ena)     fcnt <= 14'h0000;
      else if (~|fcnt)         fcnt <= filt_reload;
      else                     fcnt <= fcnt - 14'h0001;

    always @(posedge clk or negedge nReset)
      if (!nReset)
        begin
          f_scl <= 3'b111;
          f_sda <= 3'b111;
        end
      else if (rst)
        begin
          f_scl <= 3'b111;
          f_sda <= 3'b111;
        end
      else if (~|fcnt)
        begin
          f_scl <= {f_scl[1:0], scl_i};
          f_sda <= {f_sda[1:0], sda_i};
        end

    // majority filtered lines and their delayed copies
    always @(posedge clk or negedge nReset)
      if (!nReset)
        begin
          s_scl <= 1'b1;
          s_sda <= 1'b1;
          d_scl <= 1'b1;
          d_sda <= 1'b1;
        end
      else if (rst)
        begin
          s_scl <= 1'b1;
          s_sda <= 1'b1;
          d_scl <= 1'b1;
          d_sda <= 1'b1;
        end
      else
        begin
          s_scl <= s_scl_nxt;
          s_sda <= s_sda_nxt;
          d_scl <= s_scl;
          d_sda <= s_sda;
        end

    // ------------------------------------------------------------------
    // 7. bus busy tracking
    // ------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
      if (!nReset)      busy <= 1'b0;
      else if (rst)     busy <= 1'b0;
      else              busy <= (sta_nxt | busy) & ~sto_nxt;

    // ------------------------------------------------------------------
    // 9. read data sampling: capture filtered SDA on filtered SCL rising edge
    // ------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
      if (!nReset)                dout <= 1'b0;
      else if (rst)               dout <= 1'b0;
      else if (scl_rise_nxt)      dout <= s_sda_nxt;

    // ------------------------------------------------------------------
    // 8. arbitration lost
    //
    //    a) the arbitration window is open, this master has released SDA but
    //       the filtered line reads low
    //    b) a STOP condition appears while a command is running and that
    //       command is not itself a STOP request
    //
    //    al is sticky until one of the resets is applied, and the command FSM
    //    is forced idle with both lines released on the very clock state the
    //    loss is detected.
    // ------------------------------------------------------------------
    // START releases SDA again in the very state that pulls SCL low
    // (ST_START_B, entered from ST_START_A); the filtered sSCL the bus-status
    // logic reads is one to two samples behind that command, so for a beat
    // this self-caused SDA-high/SCL-nominally-high pair reads exactly like a
    // STOP that this controller did not request. Exempt it the same way an
    // actual STOP command is exempted via cmd_stop -- both are this
    // controller shaping the bus on purpose, not another master doing so.
    wire al_set = (sda_chk_r & sda_oen & ~s_sda_nxt) |
                  ((c_state != ST_IDLE) & sto_nxt & ~cmd_stop &
                   ~(c_state == ST_START_B) & ~(c_state == ST_START_C));

    always @(posedge clk or negedge nReset)
      if (!nReset)      al <= 1'b0;
      else if (rst)     al <= 1'b0;
      else              al <= al | al_set;

    always @(posedge clk or negedge nReset)
      if (!nReset)      cmd_stop <= 1'b0;
      else if (rst)     cmd_stop <= 1'b0;
      else if (tick)    cmd_stop <= (cmd == I2C_CMD_STOP);

    // ------------------------------------------------------------------
    // 10..14  bit command state machine
    // ------------------------------------------------------------------
    always @(posedge clk or negedge nReset)
      if (!nReset)
        begin
          c_state   <= ST_IDLE;
          cmd_ack   <= 1'b0;
          scl_oen   <= 1'b1;
          sda_oen   <= 1'b1;
          sda_chk_r <= 1'b0;
        end
      else if (rst | al | al_set)
        begin
          c_state   <= ST_IDLE;
          cmd_ack   <= 1'b0;
          scl_oen   <= 1'b1;
          sda_oen   <= 1'b1;
          sda_chk_r <= 1'b0;
        end
      else
        begin
          cmd_ack <= 1'b0;   // default: acknowledge is a single clock pulse

          if (tick)
            case (c_state)
              // ----------------------------------------------- idle ----
              // START and STOP enter their first active state with its own
              // output values already in place -- the decode below sets them
              // on the SAME tick that leaves idle, so the value and the state
              // that produced it are visible together, one state earlier than
              // reading the new c_state back out would suggest. READ and
              // WRITE keep their own first state's action in that state.
              ST_IDLE:
                begin
                  case (cmd)
                    I2C_CMD_NOP:   c_state <= ST_IDLE;
                    I2C_CMD_START:
                      begin
                        c_state <= ST_START_A;
                        scl_oen <= 1'b1;   // release SDA and SCL together
                        sda_oen <= 1'b1;
                      end
                    I2C_CMD_STOP:
                      begin
                        c_state <= ST_STOP_A;
                        scl_oen <= 1'b0;   // SDA low, SCL low
                        sda_oen <= 1'b0;
                      end
                    I2C_CMD_WRITE: c_state <= ST_WR_A;
                    I2C_CMD_READ:
                      begin
                        c_state <= ST_RD_A;
                        sda_oen <= 1'b1;   // release SDA for the slave
                      end
                    default:       c_state <= ST_IDLE;
                  endcase
                  sda_chk_r <= 1'b0;      // both line enables hold their level
                end

              // ---------------------------------------------- start ----
              ST_START_A:                      // both released, wait for sSCL
                if (s_scl)
                  begin
                    c_state <= ST_START_B;
                    sda_oen <= 1'b0;     // SDA low while SCL is high (START)
                  end
                else
                  c_state <= ST_START_A;

              ST_START_B:                      // START condition is on the bus
                begin
                  c_state <= ST_START_C;
                  scl_oen <= 1'b0;       // pull SCL low ...
                  sda_oen <= 1'b1;       // ... and release SDA again
                end

              ST_START_C:                      // command complete
                begin
                  c_state <= ST_IDLE;
                  cmd_ack <= 1'b1;
                  scl_oen <= 1'b1;
                  sda_oen <= 1'b1;
                end

              // ----------------------------------------------- stop ----
              ST_STOP_A:                       // SDA low, SCL low
                begin
                  c_state <= ST_STOP_B;
                  scl_oen <= 1'b1;       // release SCL
                end

              ST_STOP_B:                       // SCL released, wait for sSCL
                if (s_scl)
                  begin
                    c_state <= ST_STOP_C;
                    sda_oen <= 1'b1;     // release SDA while SCL is high (STOP)
                  end
                else
                  c_state <= ST_STOP_B;

              ST_STOP_C:                       // command complete
                begin
                  c_state <= ST_IDLE;
                  cmd_ack <= 1'b1;
                end

              // ----------------------------------------------- read ----
              ST_RD_A:                         // SDA released; release SCL too
                begin
                  c_state   <= ST_RD_B;
                  scl_oen   <= 1'b1;
                  sda_chk_r <= 1'b0;
                end

              ST_RD_B:                         // sample window, wait for sSCL
                if (s_scl)
                  begin
                    c_state <= ST_RD_C;
                    scl_oen <= 1'b0;     // sample window closes, SCL low again
                  end
                else
                  c_state <= ST_RD_B;

              ST_RD_C:                         // command complete
                begin
                  c_state <= ST_IDLE;
                  cmd_ack <= 1'b1;
                  scl_oen <= 1'b1;
                end

              // ---------------------------------------------- write ----
              ST_WR_A:                         // drive SDA from din
                begin
                  c_state   <= ST_WR_B;
                  sda_oen   <= din;
                  sda_chk_r <= 1'b0;
                end

              ST_WR_B:                         // let SDA settle, SCL still low
                begin
                  c_state   <= ST_WR_C;
                  sda_oen   <= din;
                  sda_chk_r <= 1'b0;
                end

              ST_WR_C:                         // release SCL, check arbitration, wait for sSCL high
                begin
                  scl_oen   <= 1'b1;
                  sda_oen   <= din;
                  sda_chk_r <= 1'b1;
                  if (s_scl)
                    c_state <= ST_WR_D;
                  else
                    c_state <= ST_WR_C;
                end

              ST_WR_D:                         // SCL low again
                begin
                  c_state   <= ST_WR_E;
                  scl_oen   <= 1'b0;
                  sda_oen   <= din;
                  sda_chk_r <= 1'b1;
                end

              ST_WR_E:                         // command complete
                begin
                  c_state   <= ST_IDLE;
                  cmd_ack   <= 1'b1;
                  sda_chk_r <= 1'b0;
                end

              default:
                begin
                  c_state   <= ST_IDLE;
                  scl_oen   <= 1'b1;
                  sda_oen   <= 1'b1;
                  sda_chk_r <= 1'b0;
                end
            endcase
        end

    // ------------------------------------------------------------------
    // observation ports
    // ------------------------------------------------------------------
    assign idle               = (c_state == ST_IDLE);
    assign active_command     = (c_state != ST_IDLE);
    assign cnt_zero           = ~|cnt;
    assign clk_en             = clk_en_r;
    assign slave_wait         = slave_wait_r;
    assign scl_sync           = scl_sync_w;
    assign cscl               = c_scl[0];
    assign csda               = c_sda[0];
    assign filter_cnt         = |fcnt;
    assign filter_cnt_expired = ~|fcnt;
    assign fscl               = f_scl[0];
    assign fsda               = f_sda[0];
    assign sscl               = s_scl;
    assign ssda               = s_sda;
    assign dscl               = d_scl;
    assign dsda               = d_sda;
    assign sta_condition      = ~s_sda &  d_sda & s_scl;
    assign sto_condition      =  s_sda & ~d_sda & s_scl;
    assign sda_chk            = sda_chk_r;
    assign filtered_scl_rise  = s_scl & ~d_scl;

    assign start_sequence     = (c_state == ST_START_A) | (c_state == ST_START_B) |
                                (c_state == ST_START_C) | (c_state == ST_START_D) |
                                (c_state == ST_START_E);
    assign stop_sequence      = (c_state == ST_STOP_A) | (c_state == ST_STOP_B) |
                                (c_state == ST_STOP_C) | (c_state == ST_STOP_D);
    assign read_sequence      = (c_state == ST_RD_A) | (c_state == ST_RD_B) |
                                (c_state == ST_RD_C) | (c_state == ST_RD_D);
    assign write_sequence     = (c_state == ST_WR_A) | (c_state == ST_WR_B) |
                                (c_state == ST_WR_C) | (c_state == ST_WR_D) |
                                (c_state == ST_WR_E);

endmodule
