module adder(input logic a, b, output logic result);
    assign result = a ^ b;
endmodule

module tb;
    logic a, b, result;

    adder dut (
        .a(a), 
        .b(b), 
        .result(result)
    );

    initial begin
        a = 0; b = 0;
        #1 $display("0 ^ 0 = %b", result);

        a = 0; b = 1;
        #1 $display("0 ^ 1 = %b", result);

        a = 1; b = 0;
        #1 $display("1 ^ 0 = %b", result);

        a = 1; b = 1;
        #1 $display("1 ^ 1 = %b", result);
    end
endmodule