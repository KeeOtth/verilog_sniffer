module mux (
    input logic [1:0] seletor,
    output logic [7:0] saida
);
    always_comb begin
        case (seletor)
            2'b00: saida = 8'd10;
            2'b01: saida = 8'd20;
            2'b10: saida = 8'd30;
            2'b11: saida = 8'd40;
        endcase
    end
endmodule