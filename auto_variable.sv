module tb;
    function automatic int maxx (int a, int b);
        int max = a;
        if (b > max)
            max = b;
        return max;
    endfunction

    initial begin
        int r1, r2, r3;
        r1 = maxx(3, 7);
        $display("maxx(3, 7) = %0d", r1);

        r2 = maxx(1, 2);
        $display("maxx(1, 2) = %0d", r2);
        
        r3 = maxx(0, 0);
        $display("maxx(0, 0) = %0d", r3);
    end
endmodule