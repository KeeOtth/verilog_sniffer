module mux (
    input logic [1:0] seletor,
    output logic [7:0] saida
);
    always_comb begin
        case (seletor)
            0: saida = 8'd10;
            01: saida = 8'd20;
            10: saida = 8'd30;
            2: saida = 8'd40;
        endcase
    end
endmodule