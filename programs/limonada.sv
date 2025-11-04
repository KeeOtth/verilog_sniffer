 `default_nettype none
module adder(input logic a, b, ci, output logic sum);
    assign sum = a ^ b ^ ci;
endmodule

module top(output logic sum1, sum2);
    logic a, b, c1;

    assign a = 1'b1;
    assign b = 1'b0;
    assign c1 = 1'b1;

    // certo
    adder u1 (.a(a), .b(b), .ci(c1), .sum(sum1));
    // errado
    adder u2 (.a(a), .b(b), .ci(cl), .sum(sum2));
endmodule


module tb;
    logic sum1, sum2;
    top uut (.sum1(sum1), .sum2(sum2));

    initial begin
        #1;
        $display("sum1 (correto) = %b", sum1);
        $display("sum2 (erro)   = %b", sum2);
    end
endmodule
