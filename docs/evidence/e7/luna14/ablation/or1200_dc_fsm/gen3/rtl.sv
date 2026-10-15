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
    output reg [3:0] dcram_we,
    output reg biu_read,
    output reg biu_write,
    output reg first_hit_ack,
    output reg first_miss_ack,
    output reg first_miss_err,
    output reg burst,
    output reg tag_we,
    output reg [31:0] dc_addr,
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

    wire cache_inhibit_eff;
    assign cache_inhibit_eff = cache_inhibit_r |
        (((state == CLOAD) || (state == CSTORE)) &&
         dcqmem_cycstb_i && dcqmem_ci_i);

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
    assign first_store_hit_ack = (state == CSTORE) && biudata_valid &&
                                 !tagcomp_miss && !cache_inhibit_eff;

    always @(*) begin
        biu_read = 1'b0;
        if (load_r) begin
            if ((state == CLOAD) &&
                (cache_inhibit_eff || !hitmiss_eval_r || tagcomp_miss))
                biu_read = 1'b1;
            else if ((state == LREFILL3) || (state == SREFILL4))
                biu_read = 1'b1;
        end

        biu_write = store_r;

        first_hit_ack =
            ((state == CLOAD) && hitmiss_eval_r && dcqmem_cycstb_i &&
             !tagcomp_miss && !cache_inhibit_eff) ||
            ((state == CSTORE) && biudata_valid && !tagcomp_miss &&
             !cache_inhibit_eff);
        first_miss_ack = ((state == CLOAD) || (state == CSTORE)) &&
                         biudata_valid;
        first_miss_err = ((state == CLOAD) || (state == CSTORE)) &&
                         biudata_error;

        dcram_we = 4'b0000;
        if (load_r && biudata_valid && !cache_inhibit_eff)
            dcram_we = 4'b1111;
        else if ((state == CSTORE) && biudata_valid && !tagcomp_miss &&
                 !cache_inhibit_eff)
            dcram_we = dcqmem_sel_i;

        tag_we = biu_read && biudata_valid && !cache_inhibit_eff;

        burst = ((state == CLOAD) && load_r && tagcomp_miss &&
                 !cache_inhibit_eff) || (state == LREFILL3) ||
                (state == SREFILL4);

        if (hitmiss_eval_r || !(biu_read || biu_write))
            dc_addr = start_addr;
        else
            dc_addr = saved_addr_r;
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= IDLE;
            saved_addr_r <= 32'b0;
            cnt <= 2'b00;
            hitmiss_eval_r <= 1'b0;
            store_r <= 1'b0;
            load_r <= 1'b0;
            cache_inhibit_r <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    hitmiss_eval_r <= 1'b0;
                    store_r <= 1'b0;
                    load_r <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                    cnt <= 2'b00;
                    if (dc_en && dcqmem_cycstb_i) begin
                        saved_addr_r <= start_addr;
                        hitmiss_eval_r <= 1'b1;
                        cache_inhibit_r <= 1'b0;
                        if (dcqmem_we_i) begin
                            store_r <= 1'b1;
                            load_r <= 1'b0;
                            state <= CSTORE;
                        end else begin
                            store_r <= 1'b0;
                            load_r <= 1'b1;
                            state <= CLOAD;
                        end
                    end
                end

                CLOAD: begin
                    if (dcqmem_cycstb_i && dcqmem_ci_i)
                        cache_inhibit_r <= 1'b1;

                    if (biudata_error ||
                        (hitmiss_eval_r && !dcqmem_cycstb_i)) begin
                        state <= IDLE;
                        hitmiss_eval_r <= 1'b0;
                        store_r <= 1'b0;
                        load_r <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt <= 2'b00;
                    end else if (hitmiss_eval_r && dcqmem_cycstb_i &&
                                 !cache_inhibit_eff && !tagcomp_miss) begin
                        state <= IDLE;
                        hitmiss_eval_r <= 1'b0;
                        store_r <= 1'b0;
                        load_r <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt <= 2'b00;
                    end else begin
                        if (hitmiss_eval_r)
                            hitmiss_eval_r <= 1'b0;

                        if (biudata_valid) begin
                            if (cache_inhibit_eff || !tagcomp_miss) begin
                                state <= IDLE;
                                hitmiss_eval_r <= 1'b0;
                                store_r <= 1'b0;
                                load_r <= 1'b0;
                                cache_inhibit_r <= 1'b0;
                                cnt <= 2'b00;
                            end else begin
                                state <= LREFILL3;
                                saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                                cnt <= 2'd2;
                            end
                        end
                    end
                end

                CSTORE: begin
                    if (dcqmem_cycstb_i && dcqmem_ci_i)
                        cache_inhibit_r <= 1'b1;

                    if (biudata_error ||
                        (hitmiss_eval_r && !dcqmem_cycstb_i)) begin
                        state <= IDLE;
                        hitmiss_eval_r <= 1'b0;
                        store_r <= 1'b0;
                        load_r <= 1'b0;
                        cache_inhibit_r <= 1'b0;
                        cnt <= 2'b00;
                    end else begin
                        if (hitmiss_eval_r)
                            hitmiss_eval_r <= 1'b0;

                        if (biudata_valid) begin
                            state <= IDLE;
                            hitmiss_eval_r <= 1'b0;
                            store_r <= 1'b0;
                            load_r <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                            cnt <= 2'b00;
                        end
                    end
                end

                LREFILL3: begin
                    if (biudata_valid) begin
                        if (cnt != 2'b00) begin
                            cnt <= cnt - 2'b01;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                        end else begin
                            state <= IDLE;
                            hitmiss_eval_r <= 1'b0;
                            store_r <= 1'b0;
                            load_r <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                            cnt <= 2'b00;
                        end
                    end
                end

                SREFILL4: begin
                    if (biudata_valid) begin
                        if (cnt != 2'b00) begin
                            cnt <= cnt - 2'b01;
                            saved_addr_r[3:2] <= saved_addr_r[3:2] + 2'b01;
                        end else begin
                            state <= IDLE;
                            hitmiss_eval_r <= 1'b0;
                            store_r <= 1'b0;
                            load_r <= 1'b0;
                            cache_inhibit_r <= 1'b0;
                            cnt <= 2'b00;
                        end
                    end
                end

                default: begin
                    state <= IDLE;
                    cnt <= 2'b00;
                    hitmiss_eval_r <= 1'b0;
                    store_r <= 1'b0;
                    load_r <= 1'b0;
                    cache_inhibit_r <= 1'b0;
                end
            endcase
        end
    end

endmodule