# Internal states the checks observe

The specification names internal states of this module, and 106 of the
122 checks read them by name. A design that does not expose a signal of
that name makes every check reading it ABSTAIN -- so those checks say
nothing about your design at all.

Declare each of these as an **additional output port** of
`i2c_master_bit_ctrl`, driven with the value its note describes. Extra
outputs beyond the contract are fine: the harness drives only the
contract's inputs and samples signals by name.

Each note is quoted from the specification; the spans beneath it are the
sentences of the specification that name the state.

## `idle` (width 1)

the command FSM is in the specification's idle state

  > Any unsupported or idle command leaves the FSM in the idle state.
  > In the idle state, it decodes `cmd` and enters the corresponding START, STOP, READ, or WRITE sequence.
  > When arbitration is lost, the main FSM returns to idle and releases both SCL and SDA.
  > At the end of a command sequence, the FSM returns to idle and pulses `cmd_ack` for one clock cycle.

## `cnt_zero` (width 1)

the internal timing counter cnt has reached zero or expired

  > when the counter reaches zero
  > When the counter expires, the module asserts `clk_en`
  > When the counter expires

## `clk_en` (width 1)

the internal timing-enable tick is asserted

  > generate the `clk_en` tick used to advance the bit-level FSM
  > The FSM advances only when `clk_en` is asserted.
  > acts as the timing enable for the command FSM
  > The FSM only advances to the next bit-timing phase when `clk_en` is asserted.

## `slave_wait` (width 1)

the slave clock-stretching wait condition is asserted

  > If `slave_wait` is asserted
  > `slave_wait` is asserted when the master has just released SCL high through `scl_oen`, but the filtered SCL input `sSCL` remains low.
  > While `slave_wait` remains active
  > the module asserts `slave_wait`

## `scl_sync` (width 1)

multi-master clock synchronization has detected an external SCL falling edge while SCL is released

  > `scl_sync` detects a falling edge on the filtered SCL input while this master has released SCL high.
  > The module reloads its counter and restarts its low-period timing to synchronize with the shared bus clock.
  > the module asserts `scl_sync`, reloads the timing counter, and synchronizes its local low-period timing to the shared bus clock.

## `cscl` (width 1)

the cSCL synchronization register has captured the raw SCL input

  > Raw `scl_i` and `sda_i` are first captured into two-stage registers `cSCL` and `cSDA`.
  > The raw `scl_i` and `sda_i` signals are first captured into two-stage registers `cSCL` and `cSDA` on the rising edge of `clk`.

## `csda` (width 1)

the cSDA synchronization register has captured the raw SDA input

  > Raw `scl_i` and `sda_i` are first captured into two-stage registers `cSCL` and `cSDA`.
  > The raw `scl_i` and `sda_i` signals are first captured into two-stage registers `cSCL` and `cSDA` on the rising edge of `clk`.

## `filter_cnt` (width 1)

the internal filter counter used to derive the input-filter sampling interval

  > through `filter_cnt`
  > A filter counter then controls when samples are shifted into `fSCL` and `fSDA`.
  > A filter counter, `filter_cnt`, derives its sampling interval from `clk_cnt >> 2`.

## `filter_cnt_expired` (width 1)

the filter counter has expired and a new synchronized sample is shifted into the filter histories

  > A filter counter then controls when samples are shifted into `fSCL` and `fSDA`.
  > Whenever this counter expires, new synchronized samples are shifted into the three-sample histories `fSCL` and `fSDA`.

## `fscl` (width 1)

the fSCL filtered-history sample situation

  > samples are shifted into `fSCL` and `fSDA`
  > the three-sample histories `fSCL` and `fSDA`

## `fsda` (width 1)

the fSDA filtered-history sample situation

  > samples are shifted into `fSCL` and `fSDA`
  > the three-sample histories `fSCL` and `fSDA`

## `sscl` (width 1)

the filtered SCL signal sSCL

  > The filtered outputs `sSCL` and `sSDA` are generated using a majority function over the three-sample histories.
  > the filtered bus signals `sSCL` and `sSDA`
  > These filtered signals are treated as the stable internal versions of the I2C SCL and SDA lines.

## `ssda` (width 1)

the filtered SDA signal sSDA

  > The filtered outputs `sSCL` and `sSDA` are generated using a majority function over the three-sample histories.
  > the filtered bus signals `sSCL` and `sSDA`
  > These filtered signals are treated as the stable internal versions of the I2C SCL and SDA lines.

## `dscl` (width 1)

the delayed filtered SCL value dSCL

  > The module also maintains delayed versions of the filtered bus signals in `dSCL` and `dSDA`.
  > By comparing the current filtered values against the delayed values

## `dsda` (width 1)

the delayed filtered SDA value dSDA

  > The module also maintains delayed versions of the filtered bus signals in `dSCL` and `dSDA`.
  > By comparing the current filtered values against the delayed values

## `sta_condition` (width 1)

the filtered START condition is detected

  > A START condition is detected when filtered SDA falls while filtered SCL is high: `sta_condition = ~sSDA & dSDA & sSCL`.
  > A START condition is detected when SDA transitions from high to low while SCL is high.

## `sto_condition` (width 1)

the filtered STOP condition is detected

  > A STOP condition is detected when filtered SDA rises while filtered SCL is high: `sto_condition = sSDA & ~dSDA & sSCL`
  > A STOP condition is detected when SDA transitions from low to high while SCL is high.

## `active_command` (width 1)

the bit-level FSM is active rather than idle

  > A STOP condition is detected while the FSM is active
  > during an active command
  > When arbitration is lost, the FSM returns to `idle` and releases both SCL and SDA.

## `sda_chk` (width 1)

SDA arbitration checking is enabled

  > Each sequence drives `scl_oen`, `sda_oen`, and `sda_chk` according to the required I2C timing phase.
  > When the FSM reaches the stable high phase of a WRITE bit, it asserts `sda_chk`.
  > enables SDA arbitration checking during the stable high phase

## `filtered_scl_rise` (width 1)

the filtered SCL signal has a rising edge

  > on the rising edge of the filtered SCL signal
  > Whenever the filtered SCL signal has a rising edge

## `start_sequence` (width 1)

the FSM is executing the START command sequence

  > enters the corresponding START, STOP, READ, or WRITE sequence
  > The START sequence releases SDA and SCL, then pulls SDA low while SCL is high to create a valid I2C START condition. It then pulls SCL low and asserts `cmd_ack`.
  > For a START command, the FSM releases SDA and SCL as needed, then pulls SDA low while SCL is high to generate a valid I2C START condition.

## `stop_sequence` (width 1)

the FSM is executing the STOP command sequence

  > enters the corresponding START, STOP, READ, or WRITE sequence
  > The STOP sequence drives SDA low, releases SCL high, then releases SDA high while SCL is high to create a valid I2C STOP condition.
  > For a STOP command, the FSM first ensures SDA is low, then releases SCL high.

## `read_sequence` (width 1)

the FSM is executing the READ command sequence

  > enters the corresponding START, STOP, READ, or WRITE sequence
  > The READ sequence releases SDA so the slave can drive the data bit. SCL is released high for the sample window, then driven low again.
  > For a READ command, the FSM releases SDA so the external slave can drive the data bit.

## `write_sequence` (width 1)

the FSM is executing the WRITE command sequence

  > enters the corresponding START, STOP, READ, or WRITE sequence
  > The WRITE sequence sets SDA according to `din`, releases SCL high, enables SDA arbitration checking during the high phase, then pulls SCL low again.
  > For a WRITE command, the FSM drives or releases SDA according to the value of `din`.

