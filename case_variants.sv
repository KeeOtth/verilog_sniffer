module test_case_variants;
    logic [3:0] instruction;
    logic [2:0] opcode;

    always_comb begin
        case (instruction)
            4'b0000: opcode = 3'b000;
            default: opcode = 3'b001;
        endcase

    end
endmodule
