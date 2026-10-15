module or1200_dc_fsm(
    input clk,
    input rst,
    input dc_en,
    input dcqmem_cycstb_i,
    input dcqmem_ci_i,
    input dcqmem_we_i,
    input [3:0] dcqmem_sel_i,
    input tagcomp_miss,
    input biudata_valid,
    input biudata_error,
    input [31:0] start_addr,
    output [31:0] saved_addr,
    output [3:0] dcram_we,
    output biu_read,
    output biu_write,
    output first_hit_ack,
    output first_miss_ack,
    output first_miss_err,
    output burst,
    output tag_we,
    output [31:0] dc_addr,
    output idle,
    output cload,
    output cstore,
    output lrefill3,
    output srefill4,
    output hitmiss_eval,
    output store,
    output load,
    output cache_inhibit,
    output cnt_nonzero,
    output first_store_hit_ack
);

    localparam [2:0] IDLE     = 3'd0;
    localparam [2:0] CLOAD    = 3'd1;
    localparam [2:0] CSTORE   = 3'd2;
    localparam [2:0] LREFILL3 = 3'd3;
    localparam [2:0] SREFILL4 = 3'd4;

    reg [2:0] state;
    reg [31:0] saved_addr_r;
    reg [1:0] cnt;
    reg hitmiss_eval_r;
    reg store_r;
    reg load_r;
    reg cache_inhibit_r;

    wire ci_access;
    wire store_hit_ack_int;
    wire load_hit_ack_int;

    assign ci_access = dcqmem_cycstb_i & dcqmem_ci_i;
    assign saved_addr = saved_addr_r;

    assign idle = (state == IDLE);
    assign cload = (state == CLOAD);
    assign cstore = (state == CSTORE);
    assign lrefill3 = (state == LREFILL3);
    assign srefill4 = (state == SREFILL4);
    assign hitmiss_eval = hitmiss_eval_r;
    assign store = store_r;
    assign load = load_r;
    assign cache_inhibit = cache_inhibit_r;
    assign cnt_nonzero = (cnt != 2'b00);

    assign biu_read = (hitmiss_eval_r & tagcomp_miss) |
                      ((!hitmiss_eval_r) & load_r);
    assign biu_write = store_r;

    assign load_hit_ack_int = (state == CLOAD) & hitmiss_eval_r &
                              !tagcomp_miss & !cache_inhibit_r & !ci_access;
    assign store_hit_ack_int = (state == CSTORE) & biudata_valid &
                               !tagcomp_miss & !cache_inhibit_r & !ci_access;
    assign first_store_hit_ack = store_hit_ack_int;
    assign first_hit_ack = load_hit_ack_int | store_hit_ack_int;

    assign first_miss_ack = ((state == CLOAD) | (state == CSTORE)) &
                            biudata_valid;
    assign first_miss_err = ((state == CLOAD) | (state == CSTORE)) &
                            biudata_error;

    assign burst = ((state == CLOAD) & load_r & tagcomp_miss &
                    !cache_inhibit_r & !ci_access) |
                   (state == LREFILL3) |
                   (state == SREFILL4);

    assign dcram_we = (load_r & biudata_valid &
                       !cache_inhibit_r & !ci_access) ? 4'b1111 :
                      (store_hit_ack_int ? dcqmem_sel_i : 4'b0000);

    assign tag_we = biu_read & biudata_valid & !cache_inhibit_r & !ci_access;

    assign dc_addr = (!hitmiss_eval_r & (biu_read | biu_write)) ?
                     saved_addr_r : start_addr;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state          <= IDLE;
            saved_addr_r   <= 32'b0;
            cnt            <= 2'b00;
            hitmiss_eval_r <= 1'b0;
            store_r        <= 1'b0;
            load_r         <= 1'b0;
            cache_inhibit_r <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    state           <= IDLE;
                    cnt             <= 2'b00;
                    hitmiss_eval_r  <= 1'b0;
                    store_r         <= 1'b0;
                    load_r          <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                    if (dc_en && dcqmem_cycstb_i) begin
                        saved_addr_r   <= start_addr;
                        hitmiss_eval_r <= 1'b1;
                        cache_inhibit_r <= 1'b0;
                        if (dcqmem_we_i) begin
                            state    <= CSTORE;
                            store_r  <= 1'b1;
                        end else begin
                            state   <= CLOAD;
                            load_r  <= 1'b1;
                        end
                    end
                end

                CLOAD: begin
                    if (biudata_error ||
                        (hitmiss_eval_r && !dcqmem_cycstb_i)) begin
                        state           <= IDLE;
                        hitmiss_eval_r  <= 1'b0;
                        load_r          <= 1'b0;
                        store_r         <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt             <= 2'b00;
                    end else begin
                        if (ci_access) begin
                            cache_inhibit_r <= 1'b1;
                            hitmiss_eval_r  <= 1'b0;
                        end else if (hitmiss_eval_r) begin
                            hitmiss_eval_r <= 1'b0;
                            if (!tagcomp_miss) begin
                                state           <= IDLE;
                                load_r          <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                                cnt             <= 2'b00;
                            end
                        end

                        if (biudata_valid) begin
                            if (cache_inhibit_r || ci_access) begin
                                state           <= IDLE;
                                hitmiss_eval_r  <= 1'b0;
                                load_r          <= 1'b0;
                                store_r         <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                                cnt             <= 2'b00;
                            end else if (tagcomp_miss) begin
                                state <= LREFILL3;
                                hitmiss_eval_r <= 1'b0;
                                cnt <= 2'd2;
                                saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                            end
                        end
                    end
                end

                CSTORE: begin
                    if (biudata_error ||
                        (hitmiss_eval_r && !dcqmem_cycstb_i)) begin
                        state           <= IDLE;
                        hitmiss_eval_r  <= 1'b0;
                        store_r         <= 1'b0;
                        load_r          <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt             <= 2'b00;
                    end else begin
                        if (ci_access) begin
                            cache_inhibit_r <= 1'b1;
                            hitmiss_eval_r  <= 1'b0;
                        end else if (hitmiss_eval_r) begin
                            hitmiss_eval_r <= 1'b0;
                        end

                        if (biudata_valid) begin
                            if (cache_inhibit_r || ci_access) begin
                                state           <= IDLE;
                                hitmiss_eval_r  <= 1'b0;
                                store_r         <= 1'b0;
                                load_r          <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                                cnt             <= 2'b00;
                            end else if (tagcomp_miss) begin
`ifdef OR1200_DC_STORE_REFILL
                                state           <= SREFILL4;
                                hitmiss_eval_r  <= 1'b0;
                                store_r         <= 1'b0;
                                load_r          <= 1'b1;
                                cache_inhibit_r <= 1'b0;
                                cnt             <= 2'd3;
`else
                                state           <= IDLE;
                                hitmiss_eval_r  <= 1'b0;
                                store_r         <= 1'b0;
                                load_r          <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                                cnt             <= 2'b00;
`endif
                            end else begin
                                state           <= IDLE;
                                hitmiss_eval_r  <= 1'b0;
                                store_r         <= 1'b0;
                                load_r          <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                                cnt             <= 2'b00;
                            end
                        end
                    end
                end

                LREFILL3: begin
                    if (biudata_valid) begin
                        if (cnt != 2'b00) begin
                            cnt <= cnt - 2'd1;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                        end else begin
                            state           <= IDLE;
                            load_r          <= 1'b0;
                            store_r         <= 1'b0;
                            hitmiss_eval_r  <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                            cnt             <= 2'b00;
                        end
                    end
                end

                SREFILL4: begin
`ifdef OR1200_DC_STORE_REFILL
                    if (biudata_valid) begin
                        if (cnt != 2'b00) begin
                            cnt <= cnt - 2'd1;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                        end else begin
                            state           <= IDLE;
                            load_r          <= 1'b0;
                            store_r         <= 1'b0;
                            hitmiss_eval_r  <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                            cnt             <= 2'b00;
                        end
                    end
`else
                    state <= IDLE;
                    load_r <= 1'b0;
                    store_r <= 1'b0;
                    hitmiss_eval_r <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                    cnt <= 2'b00;
`endif
                end

                default: begin
                    state           <= IDLE;
                    cnt             <= 2'b00;
                    hitmiss_eval_r  <= 1'b0;
                    store_r         <= 1'b0;
                    load_r          <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                end
            endcase
        end
    end

endmodule