module m1;
  logic [31:0] data;
  assign data = '0;
endmodule

module riscv_core (
  input  logic        clk,
  input  logic        reset,
  input  logic [31:0] inst_data,
  output logic [31:0] inst_addr,
  input  logic [31:0] mem_data_in,
  output logic [31:0] mem_data_out,
  output logic [31:0] mem_addr,
  output logic        mem_write
);
  // Registradores
  logic [31:0] reg_file [31:0];
  logic [31:0] pc;
  logic [31:0] next_pc;
  
  // Sinais de controle
  logic [6:0] opcode;
  logic [2:0] funct3;
  logic [6:0] funct7;
  logic [4:0] rs1, rs2, rd;
  
  // Sinais ALU
  logic [31:0] alu_out;
  logic [31:0] alu_a, alu_b;
  logic [3:0]  alu_op;
  
  // Sinais imediatos
  logic [31:0] imm_i, imm_s, imm_b, imm_u, imm_j;
  
  // Inicialização
  initial begin
    for (int i = 0; i < 32; i++) begin
      reg_file[i] = 32'h0;
    end
    pc = 32'h8000_0000; // Endereço inicial típico para RISC-V
  end
  
  // Decodificação de instrução
  always_comb begin
    opcode = inst_data[6:0];
    rs1    = inst_data[19:15];
    rs2    = inst_data[24:20];
    rd     = inst_data[11:7];
    funct3 = inst_data[14:12];
    funct7 = inst_data[31:25];
    
    // Cálculo de imediatos
    imm_i = {{20{inst_data[31]}}, inst_data[31:20]};
    imm_s = {{20{inst_data[31]}}, inst_data[31:25], inst_data[11:7]};
    imm_b = {{20{inst_data[31]}}, inst_data[7], inst_data[30:25], inst_data[11:8], 1'b0};
    imm_u = {inst_data[31:12], 12'b0};
    imm_j = {{12{inst_data[31]}}, inst_data[19:12], inst_data[20], inst_data[30:21], 1'b0};
  end
  
  // Unidade de controle
  always_comb begin
    case (opcode)
      7'b0110011: alu_op = funct3; // R-type
      7'b0010011: alu_op = funct3; // I-type
      7'b1100011: alu_op = funct3; // B-type
      default:    alu_op = 4'b0;
    endcase
  end
  
  // ALU
  always_comb begin
    alu_a = reg_file[rs1];
    alu_b = (opcode == 7'b0110011) ? reg_file[rs2] : imm_i; // R-type ou I-type
    
    case (alu_op)
      4'b0000: alu_out = alu_a + alu_b;  // ADD
      4'b1000: alu_out = alu_a - alu_b;  // SUB
      4'b0001: alu_out = alu_a << alu_b; // SLL
      4'b0010: alu_out = ($signed(alu_a) < $signed(alu_b)) ? 32'h1 : 32'h0; // SLT
      4'b0011: alu_out = (alu_a < alu_b) ? 32'h1 : 32'h0; // SLTU
      4'b0100: alu_out = alu_a ^ alu_b;  // XOR
      4'b0101: alu_out = alu_a >> alu_b; // SRL
      4'b1101: alu_out = $signed(alu_a) >>> alu_b; // SRA
      4'b0110: alu_out = alu_a | alu_b;  // OR
      4'b0111: alu_out = alu_a & alu_b;  // AND
      default: alu_out = 32'h0;
    endcase
  end
  
  // Atualização de PC e registradores
  always_ff @(posedge clk or posedge reset) begin
    if (reset) begin
      pc <= 32'h8000_0000;
    end else begin
      pc <= next_pc;
      
      // Write back
      if (opcode inside {7'b0110011, 7'b0010011, 7'b1100111}) begin // R-type, I-type, JALR
        if (rd != 0) begin
          reg_file[rd] <= (opcode == 7'b1100111) ? pc + 4 : alu_out;
        end
      end else if (opcode == 7'b1101111) begin // JAL
        if (rd != 0) begin
          reg_file[rd] <= pc + 4;
        end
      end
    end
  end
  
  // Lógica de próximo PC
  always_comb begin
    case (opcode)
      7'b1101111: next_pc = pc + imm_j; // JAL
      7'b1100111: next_pc = (alu_a + imm_i) & ~1; // JALR
      7'b1100011: begin // Branch
        case (funct3)
          3'b000: next_pc = (alu_a == alu_b) ? pc + imm_b : pc + 4; // BEQ
          3'b001: next_pc = (alu_a != alu_b) ? pc + imm_b : pc + 4; // BNE
          3'b100: next_pc = ($signed(alu_a) < $signed(alu_b)) ? pc + imm_b : pc + 4; // BLT
          3'b101: next_pc = ($signed(alu_a) >= $signed(alu_b)) ? pc + imm_b : pc + 4; // BGE
          3'b110: next_pc = (alu_a < alu_b) ? pc + imm_b : pc + 4; // BLTU
          3'b111: next_pc = (alu_a >= alu_b) ? pc + imm_b : pc + 4; // BGEU
          default: next_pc = pc + 4;
        endcase
      end
      default: next_pc = pc + 4; // Próxima instrução
    endcase
  end
  
  // Interface de memória
  assign inst_addr = pc;
  assign mem_addr = alu_out;
  assign mem_data_out = reg_file[rs2];
  assign mem_write = (opcode == 7'b0100011); // Store instructions
  
endmodule

module memory_controller (
  input  logic        clk,
  input  logic        reset,
  input  logic [31:0] addr,
  input  logic [31:0] data_in,
  output logic [31:0] data_out,
  input  logic        write_en,
  
  // Interface com memória externa
  output logic [31:0] ext_addr,
  output logic [31:0] ext_data_out,
  input  logic [31:0] ext_data_in,
  output logic        ext_write_en,
  output logic        ext_read_en
);
  // Memória interna (8KB)
  logic [31:0] int_mem [2047:0];
  
  // Sinais
  logic is_internal;
  
  always_comb begin
    // Verifica se o endereço está na memória interna (0x80000000 - 0x80001FFF)
    is_internal = (addr >= 32'h8000_0000) && (addr < 32'h8000_2000);
    
    if (is_internal) begin
      data_out = int_mem[(addr - 32'h8000_0000) >> 2];
      ext_addr = 32'h0;
      ext_data_out = 32'h0;
      ext_write_en = 1'b0;
      ext_read_en = 1'b0;
    end else begin
      data_out = ext_data_in;
      ext_addr = addr;
      ext_data_out = data_in;
      ext_write_en = write_en;
      ext_read_en = ~write_en;
    end
  end
  
  always_ff @(posedge clk) begin
    if (is_internal && write_en) begin
      int_mem[(addr - 32'h8000_0000) >> 2] <= data_in;
    end
  end
  
  // Inicialização da memória
  initial begin
    for (int i = 0; i < 2048; i++) begin
      int_mem[i] = 32'h0;
    end
    // Alguns valores iniciais para teste
    int_mem[0] = 32'h00000013; // NOP
    int_mem[1] = 32'h00100093; // ADDI x1, x0, 1
    int_mem[2] = 32'h00200113; // ADDI x2, x0, 2
  end
endmodule

module top (
  input  logic        clk,
  input  logic        reset,
  output logic [31:0] debug_pc,
  output logic [31:0] debug_reg_x1,
  output logic [31:0] debug_reg_x2
);
  // Conexões entre core e controlador de memória
  logic [31:0] inst_data;
  logic [31:0] inst_addr;
  logic [31:0] mem_data_in;
  logic [31:0] mem_data_out;
  logic [31:0] mem_addr;
  logic        mem_write;
  
  // Conexões com memória externa (não utilizadas neste exemplo)
  logic [31:0] ext_addr;
  logic [31:0] ext_data_out;
  logic [31:0] ext_data_in;
  logic        ext_write_en;
  logic        ext_read_en;
  
  // Instâncias dos módulos
  riscv_core core (
    .clk(clk),
    .reset(reset),
    .inst_data(inst_data),
    .inst_addr(inst_addr),
    .mem_data_in(mem_data_in),
    .mem_data_out(mem_data_out),
    .mem_addr(mem_addr),
    .mem_write(mem_write)
  );
  
  memory_controller mem_ctrl (
    .clk(clk),
    .reset(reset),
    .addr((inst_addr == mem_addr) ? inst_addr : mem_addr),
    .data_in(mem_data_out),
    .data_out((inst_addr == mem_addr) ? inst_data : mem_data_in),
    .write_en(mem_write && (inst_addr != mem_addr)),
    
    .ext_addr(ext_addr),
    .ext_data_out(ext_data_out),
    .ext_data_in(32'h0),
    .ext_write_en(ext_write_en),
    .ext_read_en(ext_read_en)
  );
  
  // Sinais de debug
  assign debug_pc = inst_addr;
  assign debug_reg_x1 = core.reg_file[1];
  assign debug_reg_x2 = core.reg_file[2];
  
endmodule

// Testbench simples
module testbench;
  logic clk = 0;
  logic reset = 1;
  logic [31:0] debug_pc;
  logic [31:0] debug_reg_x1;
  logic [31:0] debug_reg_x2;
  
  top dut (
    .clk(clk),
    .reset(reset),
    .debug_pc(debug_pc),
    .debug_reg_x1(debug_reg_x1),
    .debug_reg_x2(debug_reg_x2)
  );
  
  // Geração de clock
  always #5 clk = ~clk;
  
  initial begin
    #20 reset = 0;
    #200 $display("PC: %h, x1: %h, x2: %h", debug_pc, debug_reg_x1, debug_reg_x2);
    $finish;
  end
endmodule