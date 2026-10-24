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

    reg [2:0] state_r;
    reg [31:0] saved_addr_r;
    reg [1:0] cnt_r;
    reg hitmiss_eval_r;
    reg store_r;
    reg load_r;
    reg cache_inhibit_r;

    wire cache_inhibit_now;
    wire store_hit_ack_int;

    assign cache_inhibit_now = cache_inhibit_r |
                               (dcqmem_cycstb_i & dcqmem_ci_i);

    assign idle = (state_r == IDLE);
    assign cload = (state_r == CLOAD);
    assign cstore = (state_r == CSTORE);
    assign lrefill3 = (state_r == LREFILL3);
    assign srefill4 = (state_r == SREFILL4);
    assign hitmiss_eval = hitmiss_eval_r;
    assign store = store_r;
    assign load = load_r;
    assign cache_inhibit = cache_inhibit_r;
    assign cnt_nonzero = (cnt_r != 2'b00);

    assign saved_addr = saved_addr_r;

    assign biu_read = load_r &&
                      (cache_inhibit_now || !hitmiss_eval_r || tagcomp_miss);
    assign biu_write = store_r;

    assign store_hit_ack_int = (state_r == CSTORE) && store_r &&
                               biudata_valid && !tagcomp_miss &&
                               !cache_inhibit_now;
    assign first_store_hit_ack = store_hit_ack_int;

    assign first_hit_ack =
        ((state_r == CLOAD) && load_r && hitmiss_eval_r &&
         !cache_inhibit_now && !tagcomp_miss) || store_hit_ack_int;

    assign first_miss_ack = ((state_r == CLOAD) || (state_r == CSTORE)) &&
                            biudata_valid;
    assign first_miss_err = ((state_r == CLOAD) || (state_r == CSTORE)) &&
                            biudata_error;

    assign burst = (state_r == LREFILL3) ||
                   ((state_r == CLOAD) && load_r &&
                    !cache_inhibit_now && tagcomp_miss);

    assign dcram_we =
        (load_r && biudata_valid && biu_read && !cache_inhibit_now)
            ? 4'b1111
            : (store_hit_ack_int ? dcqmem_sel_i : 4'b0000);

    assign tag_we = biu_read && biudata_valid && !cache_inhibit_now;

    assign dc_addr = (hitmiss_eval_r || !(biu_read || biu_write))
                   ? start_addr : saved_addr_r;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_r         <= IDLE;
            saved_addr_r    <= 32'b0;
            cnt_r           <= 2'b0;
            hitmiss_eval_r  <= 1'b0;
            store_r         <= 1'b0;
            load_r          <= 1'b0;
            cache_inhibit_r <= 1'b0;
        end else begin
            case (state_r)
                IDLE: begin
                    hitmiss_eval_r  <= 1'b0;
                    store_r         <= 1'b0;
                    load_r          <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                    cnt_r           <= 2'b0;

                    if (dc_en && dcqmem_cycstb_i) begin
                        saved_addr_r    <= start_addr;
                        hitmiss_eval_r  <= 1'b1;
                        cache_inhibit_r <= 1'b0;
                        if (dcqmem_we_i) begin
                            store_r <= 1'b1;
                            load_r  <= 1'b0;
                            state_r <= CSTORE;
                        end else begin
                            store_r <= 1'b0;
                            load_r  <= 1'b1;
                            state_r <= CLOAD;
                        end
                    end
                end

                CLOAD: begin
                    if (dcqmem_cycstb_i && dcqmem_ci_i)
                        cache_inhibit_r <= 1'b1;

                    if ((hitmiss_eval_r && !dcqmem_cycstb_i) ||
                        biudata_error ||
                        (cache_inhibit_now && biudata_valid)) begin
                        state_r         <= IDLE;
                        hitmiss_eval_r  <= 1'b0;
                        load_r          <= 1'b0;
                        store_r         <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt_r           <= 2'b0;
                    end else if (hitmiss_eval_r) begin
                        hitmiss_eval_r <= 1'b0;
                        if (!cache_inhibit_now && !tagcomp_miss) begin
                            state_r         <= IDLE;
                            load_r          <= 1'b0;
                            store_r         <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                            cnt_r           <= 2'b0;
                        end else if (!cache_inhibit_now && biudata_valid) begin
                            state_r           <= LREFILL3;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                            cnt_r             <= 2'd2;
                        end
                    end else if (biudata_valid) begin
                        state_r           <= LREFILL3;
                        saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                        cnt_r             <= 2'd2;
                    end
                end

                CSTORE: begin
                    if (dcqmem_cycstb_i && dcqmem_ci_i)
                        cache_inhibit_r <= 1'b1;

                    if ((hitmiss_eval_r && !dcqmem_cycstb_i) ||
                        biudata_error || biudata_valid) begin
                        state_r         <= IDLE;
                        hitmiss_eval_r  <= 1'b0;
                        store_r         <= 1'b0;
                        load_r          <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt_r           <= 2'b0;
                    end else if (hitmiss_eval_r) begin
                        hitmiss_eval_r <= 1'b0;
                    end
                end

                LREFILL3: begin
                    if (biudata_valid) begin
                        if (cnt_r != 2'b00) begin
                            cnt_r             <= cnt_r - 2'b01;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                        end else begin
                            state_r         <= IDLE;
                            cnt_r           <= 2'b0;
                            hitmiss_eval_r  <= 1'b0;
                            load_r          <= 1'b0;
                            store_r         <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                        end
                    end
                end

                SREFILL4: begin
                    if (biudata_valid) begin
                        if (cnt_r != 2'b00) begin
                            cnt_r             <= cnt_r - 2'b01;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                        end else begin
                            state_r         <= IDLE;
                            cnt_r           <= 2'b0;
                            hitmiss_eval_r  <= 1'b0;
                            load_r          <= 1'b0;
                            store_r         <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                        end
                    end
                end

                default: begin
                    state_r         <= IDLE;
                    cnt_r           <= 2'b0;
                    hitmiss_eval_r  <= 1'b0;
                    store_r         <= 1'b0;
                    load_r          <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                end
            endcase
        end
    end

endmodule