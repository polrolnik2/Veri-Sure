module or1200_dc_fsm__probed(
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

    localparam [2:0] ST_IDLE     = 3'd0;
    localparam [2:0] ST_CLOAD    = 3'd1;
    localparam [2:0] ST_CSTORE   = 3'd2;
    localparam [2:0] ST_LREFILL3 = 3'd3;
    localparam [2:0] ST_SREFILL4 = 3'd4;

    reg [2:0] state_r;
    reg [31:0] saved_addr_r;
    reg [1:0] cnt_r;
    reg hitmiss_eval_r;
    reg store_r;
    reg load_r;
    reg cache_inhibit_r;

    wire ci_now;
    wire first_store_hit_ack_int;
    wire load_hit_ack_int;
    wire load_refill_write;

    assign ci_now = dcqmem_cycstb_i && dcqmem_ci_i;

    assign idle = (state_r == ST_IDLE);
    assign cload = (state_r == ST_CLOAD);
    assign cstore = (state_r == ST_CSTORE);
    assign lrefill3 = (state_r == ST_LREFILL3);
    assign srefill4 = (state_r == ST_SREFILL4);

    assign hitmiss_eval = hitmiss_eval_r;
    assign store = store_r;
    assign load = load_r;
    assign cache_inhibit = cache_inhibit_r;
    assign cnt_nonzero = (cnt_r != 2'd0);
    assign saved_addr = saved_addr_r;

    assign biu_read =
        load_r &&
        (((state_r == ST_CLOAD) &&
          (cache_inhibit_r || ci_now || !hitmiss_eval_r || tagcomp_miss)) ||
         (state_r == ST_LREFILL3) ||
         (state_r == ST_SREFILL4));

    assign biu_write = store_r;

    assign load_hit_ack_int =
        (state_r == ST_CLOAD) && load_r && hitmiss_eval_r &&
        !tagcomp_miss && !cache_inhibit_r && !ci_now &&
        dcqmem_cycstb_i;

    assign first_store_hit_ack_int =
        (state_r == ST_CSTORE) && store_r && biudata_valid &&
        !tagcomp_miss && !cache_inhibit_r && !ci_now;

    assign first_store_hit_ack = first_store_hit_ack_int;
    assign first_hit_ack = load_hit_ack_int || first_store_hit_ack_int;

    assign first_miss_ack =
        ((state_r == ST_CLOAD) || (state_r == ST_CSTORE)) &&
        biudata_valid;

    assign first_miss_err =
        ((state_r == ST_CLOAD) || (state_r == ST_CSTORE)) &&
        biudata_error;

    assign burst =
        (((state_r == ST_CLOAD) && load_r && tagcomp_miss &&
          !cache_inhibit_r && !ci_now) ||
         (state_r == ST_LREFILL3) ||
         (state_r == ST_SREFILL4));

    assign load_refill_write =
        load_r && biudata_valid && biu_read &&
        !cache_inhibit_r && !ci_now;

    assign dcram_we =
        {4{load_refill_write}} |
        ({4{first_store_hit_ack_int}} & dcqmem_sel_i);

    assign tag_we =
        biu_read && biudata_valid && !cache_inhibit_r && !ci_now;

    assign dc_addr =
        (!hitmiss_eval_r && (biu_read || biu_write)) ?
        saved_addr_r : start_addr;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state_r        <= ST_IDLE;
            saved_addr_r   <= 32'd0;
            cnt_r          <= 2'd0;
            hitmiss_eval_r <= 1'b0;
            store_r        <= 1'b0;
            load_r         <= 1'b0;
            cache_inhibit_r <= 1'b0;
        end else begin
            case (state_r)
                ST_IDLE: begin
                    hitmiss_eval_r <= 1'b0;
                    store_r        <= 1'b0;
                    load_r         <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                    cnt_r          <= 2'd0;

                    if (dc_en && dcqmem_cycstb_i) begin
                        saved_addr_r   <= start_addr;
                        hitmiss_eval_r <= 1'b1;
                        cache_inhibit_r <= 1'b0;
                        if (dcqmem_we_i) begin
                            state_r <= ST_CSTORE;
                            store_r <= 1'b1;
                            load_r  <= 1'b0;
                        end else begin
                            state_r <= ST_CLOAD;
                            store_r <= 1'b0;
                            load_r  <= 1'b1;
                        end
                    end
                end

                ST_CLOAD: begin
                    if (ci_now)
                        cache_inhibit_r <= 1'b1;

                    if (biudata_error) begin
                        state_r         <= ST_IDLE;
                        hitmiss_eval_r  <= 1'b0;
                        load_r          <= 1'b0;
                        store_r         <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                    end else if (hitmiss_eval_r) begin
                        if (!dcqmem_cycstb_i) begin
                            state_r         <= ST_IDLE;
                            hitmiss_eval_r  <= 1'b0;
                            load_r          <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                        end else if (dcqmem_ci_i) begin
                            hitmiss_eval_r <= 1'b0;
                            cache_inhibit_r <= 1'b1;
                            if (biudata_valid) begin
                                state_r         <= ST_IDLE;
                                load_r          <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                            end
                        end else if (!tagcomp_miss) begin
                            state_r         <= ST_IDLE;
                            hitmiss_eval_r  <= 1'b0;
                            load_r          <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                        end else begin
                            hitmiss_eval_r <= 1'b0;
                            if (biudata_valid) begin
                                state_r <= ST_LREFILL3;
                                saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                                cnt_r <= 2'd2;
                            end
                        end
                    end else if (biudata_valid) begin
                        if (cache_inhibit_r || ci_now) begin
                            state_r         <= ST_IDLE;
                            load_r          <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                        end else begin
                            state_r <= ST_LREFILL3;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                            cnt_r <= 2'd2;
                        end
                    end
                end

                ST_LREFILL3: begin
                    if (biudata_error) begin
                        state_r         <= ST_IDLE;
                        load_r          <= 1'b0;
                        hitmiss_eval_r  <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                    end else if (biudata_valid) begin
                        if (cnt_r != 2'd0) begin
                            cnt_r <= cnt_r - 2'd1;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                        end else begin
                            state_r         <= ST_IDLE;
                            load_r          <= 1'b0;
                            cnt_r           <= 2'd0;
                            cache_inhibit_r <= 1'b0;
                        end
                    end
                end

                ST_CSTORE: begin
                    if (ci_now)
                        cache_inhibit_r <= 1'b1;

                    if (biudata_error) begin
                        state_r         <= ST_IDLE;
                        hitmiss_eval_r  <= 1'b0;
                        store_r         <= 1'b0;
                        load_r          <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                    end else if (hitmiss_eval_r) begin
                        if (!dcqmem_cycstb_i) begin
                            state_r         <= ST_IDLE;
                            hitmiss_eval_r  <= 1'b0;
                            store_r         <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                        end else begin
                            hitmiss_eval_r <= 1'b0;
                            if (dcqmem_ci_i)
                                cache_inhibit_r <= 1'b1;
                            if (biudata_valid) begin
                                state_r         <= ST_IDLE;
                                store_r         <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                            end
                        end
                    end else if (biudata_valid) begin
                        state_r         <= ST_IDLE;
                        store_r         <= 1'b0;
                        load_r          <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                    end
                end

                ST_SREFILL4: begin
                    if (biudata_error) begin
                        state_r         <= ST_IDLE;
                        load_r          <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                    end else if (biudata_valid) begin
                        if (cnt_r != 2'd0) begin
                            cnt_r <= cnt_r - 2'd1;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'd1;
                        end else begin
                            state_r         <= ST_IDLE;
                            load_r          <= 1'b0;
                            cnt_r           <= 2'd0;
                            cache_inhibit_r <= 1'b0;
                        end
                    end
                end

                default: begin
                    state_r         <= ST_IDLE;
                    cnt_r           <= 2'd0;
                    hitmiss_eval_r  <= 1'b0;
                    store_r         <= 1'b0;
                    load_r          <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                end
            endcase
        end
    end

endmodule

// Shipped interface: the contract's ports, probes left unconnected.
module or1200_dc_fsm (
    input wire clk,
    input wire rst,
    input wire dc_en,
    input wire dcqmem_cycstb_i,
    input wire dcqmem_ci_i,
    input wire dcqmem_we_i,
    input wire [3:0] dcqmem_sel_i,
    input wire tagcomp_miss,
    input wire biudata_valid,
    input wire biudata_error,
    input wire [31:0] start_addr,
    output wire [31:0] saved_addr,
    output wire [3:0] dcram_we,
    output wire biu_read,
    output wire biu_write,
    output wire first_hit_ack,
    output wire first_miss_ack,
    output wire first_miss_err,
    output wire burst,
    output wire tag_we,
    output wire [31:0] dc_addr
);
    or1200_dc_fsm__probed u_probed (
        .clk(clk),
        .rst(rst),
        .dc_en(dc_en),
        .dcqmem_cycstb_i(dcqmem_cycstb_i),
        .dcqmem_ci_i(dcqmem_ci_i),
        .dcqmem_we_i(dcqmem_we_i),
        .dcqmem_sel_i(dcqmem_sel_i),
        .tagcomp_miss(tagcomp_miss),
        .biudata_valid(biudata_valid),
        .biudata_error(biudata_error),
        .start_addr(start_addr),
        .saved_addr(saved_addr),
        .dcram_we(dcram_we),
        .biu_read(biu_read),
        .biu_write(biu_write),
        .first_hit_ack(first_hit_ack),
        .first_miss_ack(first_miss_ack),
        .first_miss_err(first_miss_err),
        .burst(burst),
        .tag_we(tag_we),
        .dc_addr(dc_addr)
    );
endmodule
