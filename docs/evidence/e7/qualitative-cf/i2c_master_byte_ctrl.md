# i2c_master_byte_ctrl: what repair did from the real-child start

**Method.**
- **Edits:** for each arm I diffed the start against the final and read the latched commits in its logs, including all 6 luna13 checks launches.
- **Re-simulation:** I ran each edit alone on the start, using iverilog and the run's own stimulus (scratch scripts, not committed; `../../e7_behaviour/byte_ctrl_codes.py` reproduces the command-code results).
- **Figures:** points of edges equal to golden. **gc** is the same design with golden's command codes.
- **Common to all 9 designs:** they keep the real child `bit_controller` and the swapped codes READ=0100, WRITE=1000 (mode B). No arm touched the codes, and no check or ref can see them. They are now the largest defect: luna12's start goes from 43.2% to **97.6%** under gc. The earlier study listed these codes as mode B, latent behind the stand-in child. The session re-ran the swap (`../BYTE-CTRL-CODES.json`): luna12 43.2 → 97.6%, luna13 34.4 → 74.1%, luna14 15.5 → 13.9%. luna14 also needs its command held (36.0%; 64.5% with both).

### luna12 (start 43.2% golden / 0.9% ref)
| arm | main edits | reqs | effect vs golden / ref | class |
|---|---|---|---|---|
| checks 52→56 | (1) core_txd=ack_in only in `ST_ACK&&cmd==WRITE`; (2) `core_ack_r && ena`; (3) NOP cycle before read-ACK; (4) dead ld&&shift branch | (1) +0026,0119 −0048; (2) +0076,0045; (3) +0067,0050 | 7,564 edges changed: golden 1,825 after vs 1,118 before; ref 3 vs 27. (1) +0.7 (−0.7 gc); (2) −0.02; (3) −0.3 (−2.0 gc) | (1) c; (2) b (REQ-0076's check stalls on ena=0; spec: "does not directly use ena"); (3) e; (4) d |
| model 52→70 | (1) `assign core_ack_r=(core_cmd_r!=NOP); assign core_rxd_r=sda_i;` on child-driven nets (rtl.sv:261-262); (2) sr on `ld=IDLE&&go`, `shift=(READ\|WRITE)&&core_ack` (ref_model.py:52-55); (3) al ignored at ACK/STOP completion; (4) ≈ checks (1) | (1) +6 −2; (2) +7 −1; (3) +8 −0070,0100 (the al-abort rule); (4) +0026 | 73,050 changed: golden 1,741 vs 17,857; ref 17 vs 933; 73,554 x cells. (1) −2.2 (−21.0 gc); (2) −8.2 (−24.5 gc); (3) −1.1 (−18.0 gc) | (1) c, re-imports mode A; (2) b, modes D+E from the ref; (3) e |

**Why the luna12 model arm gained 18 requirements but lost golden agreement.**
- `find_signal` reports a net driven by a child instance's output as "READ but nothing drives it". The session reproduced this on a toy module. In all 6 logs it ignores instance outputs.
- So the editor added drivers carrying the reference model's instant-child values onto nets the child already drives.
- In the editor's simulator (Verilator, two-state) the FSM still follows the child, but the probes show the added values, and the checks read probes. This was checked by hand on a directed stimulus, not inside the cocotb suite.
- In the grading simulation (iverilog, four-state) the conflicting drivers resolve to x. The session measured 4.8% unknown output cells in this final, mostly `dout` and `ack_out`, against 0% for golden, the start and the checks final.
- The ChipVerilog pass is bounded at k=16 and never reaches this behaviour.

### luna13 (start 34.4% / 5.6%)
| arm | main edits | reqs | effect | class |
|---|---|---|---|---|
| checks 49→55→67→75 (across launches) | (1) ack_out on every ACK; (2) core_txd_r=ack_in in read-ACK; (3) `rst \|\| (al_r && !core_ack_r)`; (4) sr on same-edge ld/shift | (3) +13 (0007…0124) −0032, −0066 ("rst or i2c_al…returns to ST_IDLE"); (4) +0034,0043,0119,0049,0053 | 106,919 changed: golden 8,457 vs 18,624. (1) +5.2 (+15.1 gc); (2) 0 (+1.0 gc); (3) −6.4 (−22.0 gc); (4) −1.8 (−8.4 gc) | (1,2) a; (3) e, which the checks reward; (4) b, mode D from the checks (this run's ref registers ld/shift) |
| model 49→58 | (1) core_txd probe only; (2) = checks (1); (3) sr kept on al; (4) `ld=ld_r\|(idle&go)` | (1) +0028,0059,0113; (2) +0014,0051,0099; (3) gradient; (4) +3 −0066 | 48,647 changed: golden 21,205 vs 1,220; ref 630 vs 704. (1) 0; (3) +4.4 (+8.1 gc); (4) −0.3 | (1) c; (2,3) a; (4) c/d |

**Why the luna13 checks arm passed 17 more yet moved away from golden.**
- 13 of its 19 checks-only passes come from edit (3).
- In its reasoning the editor noted that the spec states the abort unconditionally and that this edit felt like a deviation. It committed anyway, and the commit latched +12.
- The abort is not a symptom of the swapped codes. The session measured `i2c_al` high on 0.8–1.0% of golden's own edges, in about two thirds of testpoints: the stimulus provokes arbitration loss. With the codes fixed, the designs reproduce golden's activity (`../BYTE-CTRL-CODES.json`). The checks reward ignoring an event the spec says must abort. Of the two checks the edit broke, only REQ-0066 restates the abort rule; REQ-0032 is about the bit counter.
- The discarded out-of-memory launch latched the same edit.
- Reverting (3) in the final gives 37.0%, above the start.
- The model arm never touched al. Its gains, ack_out and keeping sr on al, are in both the ref and golden.

### luna14 (start 15.5% / 7.4%; pulsed core_cmd, mode C)
| arm | main edits | reqs | effect | class |
|---|---|---|---|---|
| checks 72→80 | (1) al aborts only in READ/WRITE; (2) `stop_pending`; (3) rst nesting | +8 (0012,0013,0062,0063,0069,0070,0121,0122) | 46,992 changed: golden 1,572 vs 1,936; ref 7,000 vs 56 (the ref never raises al). (1) alone gives the final trace; (2) 0 edges; once the command is held, (1) costs 12.1 under gc | (1) e; (2,3) d |
| model 72 (0/15 latched) | rebuilt the ref's stand-in child; re-wired the instance; its last staged edit, holding core_cmd, was never judged | commits fell to 65–70; REQ-0057/0099 went dark | identical | — (the hold: 36.0%, with gc 64.5%) |

**Arms compared.** From the same start the arms moved differently, and neither dominated.
- **Model arm:** it reproduced the ref's abstraction, copying its expressions in luna12 and rebuilding its stand-in child in luna14. In luna13 it twice tried a pulsed command; the checks rejected both (52→39, 58→40).
- **Checks arm:** it never copied code. Instead it found deviations from the spec that the checks reward:
  - narrowing the al abort, a new mode in 3 of 6 arms that costs 12–22 points under gc;
  - same-edge ld/shift;
  - gating on ena.
- **Both arms:** made probe-only edits, and neither fixed mode B. The one fix for mode C was staged by the model arm and never judged.

On luna13, the edits each arm happened to find decide the outcome, more than the feedback channel does.

**Not established:**
- exact credit within batched commits;
- which checks reward ignoring `i2c_al`, and what scenario they expect to continue through it;
- how yosys treats the multi-driven nets.
