module adder(input logic value_1, value_2, output logic result);
    assign result = value_1 ^ value_2;
endmodule

module tb;
    logic value_1, value_2, result;

    adder dut (
        .value_1(value_1),
        .value_2(value_2),
        .result(result)
    );

    initial begin
        value_1 = 0; value_2 = 0;
        #1 $display("0 ^ 0 = %b", result);

        value_1 = 0; value_2 = 1;
        #1 $display("0 ^ 1 = %b", result);

        value_1 = 1; value_2 = 0;
        #1 $display("1 ^ 0 = %b", result);

        value_1 = 1; value_2 = 1;
        #1 $display("1 ^ 1 = %b", result);
    end
endmodule
