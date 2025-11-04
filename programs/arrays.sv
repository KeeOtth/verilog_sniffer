module top_ok(output logic [1:0][31:0] A, output logic [1:0][31:0] B);
    initial begin
        A = {1'b1, 1'b1};
        B = {1'b1, 1'b1};
    end
endmodule

module tb;
    logic [1:0][31:0] A;
    logic [1:0][31:0] B;
    logic [31:0] x;
    assign x = '0;
    //assign x = '0;
    top_ok uut(.A(A), .B(B));

    initial begin
        #1;
        $display("A[0] = %h", A[0]);
        $display("A[1] = %h", A[1]);
    end
endmodule