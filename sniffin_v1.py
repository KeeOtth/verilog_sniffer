import re
import subprocess
import sys
import time
from pathlib import Path


# tools
def generate_tree(file_path):
    txt_output = file_path.with_suffix(".syntax_tree.txt")
    # json_output = file_path.with_suffix(".syntax_tree.json")

    cmd_txt = ["verible-verilog-syntax", "--printtree", str(file_path)]

    # cmd_json = ["verible-verilog-syntax", "--export_json", str(file_path)]

    with open(txt_output, "w") as f:
        subprocess.run(cmd_txt, stdout=f, check=True)
    # with open(json_output, "w") as f:
    #     subprocess.run(cmd_json, stdout=f, check=True)
    return


def _offset_line(src_text: str, offset: int):
    line = src_text.count("\n", 0, offset) + 1
    return line


def debug_number_tokens(txt_tree_path):
    """
    Função para debug: mostra todos os tokens numéricos na árvore
    """
    txt_tree_path = Path(txt_tree_path)
    tree_text = txt_tree_path.read_text(encoding="utf-8")

    print("=== DEBUG: TOKENS NUMÉRICOS ENCONTRADOS ===")

    # Procura por todos os tipos de tokens numéricos
    number_patterns = [
        r"TK_DecNumber",
        r"TK_BinNumber",
        r"TK_HexNumber",
        r"TK_OctNumber",
        r"TK_UnBasedNumber",
        r"kNumber",
    ]

    for pattern in number_patterns:
        matches = re.findall(rf'#{pattern} @\d+-\d+: "[^"]*"', tree_text)
        if matches:
            print(f"\n{pattern}:")
            for match in matches:
                print(f"  {match}")


# smell finders
def find_missing_default_nettype(txt_tree_path, original_file_path):
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")

    default_nettype_none_re = re.compile(r'`default_nettype[^}]*"none"')

    has_default_nettype_none = default_nettype_none_re.search(tree_text) is not None

    if not has_default_nettype_none:
        issues.append(
            {
                "file": str(original_file_path),
                "line": 1,
                "method": "syntax_tree_missing_directive",
                "context": "top of the file",
                "message": "'default_nettype none' Ausente",
            }
        )

    return issues


def find_concatenations_in_assignments(txt_tree_path, original_file_path):
    txt_tree_path = Path(txt_tree_path)
    original_file_path = Path(original_file_path)

    tree_lines = txt_tree_path.read_text(encoding="utf-8").splitlines()
    src_text = original_file_path.read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    node_re = re.compile(r"\s*Node\s+@\d+\s+\(tag:\s*(?P<tag>[^)]+)\)\s*\{")
    leaf_re = re.compile(
        r'\s*Leaf\s+@\d+\s+\(#(?P<token>[^ ]+)\s+@(?P<start>\d+)-(?P<end>\d+):\s+"(?P<text>.*)"\)'
    )
    close_re = re.compile(r"^\s*\}\s*$")

    stack = []
    issues = []

    for idx, line in enumerate(tree_lines):
        m_node = node_re.match(line)
        if m_node:
            stack.append(m_node.group("tag"))
            continue

        if close_re.match(line):
            if stack:
                stack.pop()
            continue

        m_leaf = leaf_re.match(line)
        if not m_leaf:
            continue

        text = m_leaf.group("text")  # Tá agrupando o texto dentro do bagulho
        start_offset = int(m_leaf.group("start"))

        if (
            text == "{"
            and "kConcatenationExpression" in stack
            and "kNetVariableAssignment" in stack
        ):
            line_num = _offset_line(src_text, start_offset)
            context = (
                code_lines[line_num - 1].strip()
                if 0 <= line_num - 1 < len(code_lines)
                else ""
            )
            issues.append(
                {
                    "file": str(original_file_path),
                    "line": line_num,
                    "context": context,
                    "method": "syntax_tree_concat",
                    "message": "Concatenação encontrada em atribuição",
                }
            )

    return issues


def find_ambiguous_in_tree(txt_tree_path, original_file_path):
    issues = []

    leaf_pattern = re.compile(
        r"Leaf\s+@\d+\s+\(#TK_UnBasedNumber\s+@(?P<start>\d+)-(?P<end>\d+):\s+\"(?P<literal>.+)\"\)"
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    with open(txt_tree_path, "r", encoding="utf-8") as f:
        for line in f:
            match = leaf_pattern.search(line)
            if match:
                start_offset = int(match.group("start"))
                line_num = _offset_line(src_text, start_offset)

                literal_text = (
                    match.group("literal").encode("utf-8").decode("unicode_escape")
                )

                context_line = (
                    code_lines[line_num - 1].strip()
                    if 0 <= line_num - 1 < len(code_lines)
                    else ""
                )

                issues.append(
                    {
                        "file": str(original_file_path),
                        "line": line_num,
                        "context": context_line,
                        "method": "syntax_tree_txt",
                        "message": f"Literal ambíguo {literal_text} (via árvore sintática).",
                    }
                )
    return issues


def find_non_automatic_functions(txt_tree_path, original_file_path):
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")

    function_pattern = re.compile(
        r'Leaf @\d+ \(#"function" @\d+-\d+: "function"\)'  # tag "function"
        r'(?!\s*Leaf @\d+ \(#"automatic" @\d+-\d+: "automatic"\))'  # ver se é seguido por automatic
    )

    function_name_pattern = re.compile(
        r'Leaf @\d+ \(#SymbolIdentifier @\d+-\d+: "(?P<name>[^"]+)"\)'
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for match in function_pattern.finditer(tree_text):
        start_pos = match.start()

        remaining_text = tree_text[start_pos:]
        name_match = function_name_pattern.search(remaining_text)

        if name_match:
            function_name = name_match.group("name")

            function_real_line = 0
            for i, code_line in enumerate(code_lines, 1):
                if "function" in code_line and function_name in code_line:
                    function_real_line = i
                    break

            if function_real_line > 0:
                context = (
                    code_lines[function_real_line - 1].strip()
                    if 0 <= function_real_line - 1 < len(code_lines)
                    else ""
                )

                issues.append(
                    {
                        "file": str(original_file_path),
                        "line": function_real_line,
                        "context": context,
                        "method": "syntax_tree_non_automatic",
                        "message": f"Função '{function_name}' não usa inicialização automática de variáveis",
                    }
                )

    return issues


def find_identical_port_signal_names(txt_tree_path, original_file_path):
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")

    port_block_re = re.compile(
        r"Node @\d+ \(tag: kActualNamedPort\) \{(.*?)\}",
        re.DOTALL,
    )

    identifier_re = re.compile(r'SymbolIdentifier @\d+-\d+: "([^"]+)"')

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for block in port_block_re.finditer(tree_text):
        identifiers = identifier_re.findall(block.group(1))

        if len(identifiers) >= 2:
            port_name = identifiers[0]
            signal_name = identifiers[1]

            if port_name == signal_name:
                line_num = 0
                for i, code_line in enumerate(code_lines, 1):
                    if f".{port_name}({signal_name}" in code_line.replace(" ", ""):
                        line_num = i
                        break

                if line_num > 0:
                    context = (
                        code_lines[line_num - 1].strip()
                        if 0 <= line_num - 1 < len(code_lines)
                        else ""
                    )

                    issues.append(
                        {
                            "file": str(original_file_path),
                            "line": line_num,
                            "context": context,
                            "method": "syntax_tree_identical_names",
                            "message": f"Porta e sinal com nomes idênticos: .{port_name}({signal_name})",
                        }
                    )

    return issues

    # To-do Consertar essa função por que ela tá levando em conta os dois lados dos 2 pontos, quando era pra considerar só o lado esquerdo.
    # def find_implicit_base_numbers(txt_tree_path, original_file_path):
    """
    Detecta literais sem base explícita em estruturas de controle.
    Especificamente em:
    - Condições de loops (for, while, do-while)
    - Condições de if/else
    - Valores de case

    Retorna uma lista de issues encontrados.
    """
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")
    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    # Função auxiliar para converter offset em linha
    def _offset_to_line(offset):
        return src_text[:offset].count("\n") + 1

    # 1. DETECTAR EM LOOPS FOR (apenas na condição)
    for_loop_re = re.compile(
        r"Node @\d+ \(tag: kForLoopStatement\) \{(.*?)\n\s*?\n\}", re.DOTALL
    )

    for_condition_re = re.compile(
        r"Node @2 \(tag: kForCondition\) \{(.*?)\n\s*?\n\s*?\}", re.DOTALL
    )

    # 2. DETECTAR EM WHILE/DO-WHILE (condição completa)
    while_loop_re = re.compile(
        r"Node @\d+ \(tag: kWhileLoopStatement\) \{(.*?)\n\s*?\n\}", re.DOTALL
    )

    do_while_re = re.compile(
        r"Node @\d+ \(tag: kDoWhileStatement\) \{(.*?)\n\s*?\n\}", re.DOTALL
    )

    # 3. DETECTAR EM IF/ELSE (condição)
    if_statement_re = re.compile(
        r"Node @\d+ \(tag: kIfStatement\) \{(.*?)\n\s*?\n\}", re.DOTALL
    )

    # 4. DETECTAR EM CASE (valores dos case items)
    case_statement_re = re.compile(
        r"Node @\d+ \(tag: kCaseStatement\) \{(.*?)\n\s*?\n\}", re.DOTALL
    )

    case_item_re = re.compile(
        r"Node @\d+ \(tag: kCaseItem\) \{(.*?)\n\s*?\n\}", re.DOTALL
    )

    # Regex para encontrar números decimais sem base
    implicit_number_re = re.compile(
        r"Node @\d+ \(tag: kNumber\) \{(?!.*?kBaseDigits).*?#TK_DecNumber @(\d+)-(\d+): \"([^\"]+)\"",
        re.DOTALL,
    )

    # Função auxiliar para processar um bloco de texto
    def process_block(block_text, context_type, line_offset=0):
        found_in_block = []

        for number_match in implicit_number_re.finditer(block_text):
            start_offset = int(number_match.group(1)) + line_offset
            number_value = number_match.group(3)

            if not number_value.strip():
                continue

            line_num = _offset_to_line(start_offset)

            context = (
                code_lines[line_num - 1].strip()
                if 0 <= line_num - 1 < len(code_lines)
                else ""
            )

            found_in_block.append(
                {
                    "file": str(original_file_path),
                    "line": line_num,
                    "context": context,
                    "method": f"syntax_tree_implicit_base_{context_type}",
                    "message": f"Número sem base explícita em {context_type}: {number_value}",
                    "suggestion": f"Substitua {number_value} por constante nomeada ou especifique base (ex: 32'd{number_value})",
                }
            )

        return found_in_block

    # ========== ANALISE DE LOOPS FOR ==========
    for for_match in for_loop_re.finditer(tree_text):
        for_block = for_match.group(1)

        # Encontra apenas a condição do for (ignora inicialização e incremento)
        condition_match = for_condition_re.search(for_block)
        if condition_match:
            condition_block = condition_match.group(1)
            # Encontra offset aproximado do bloco condicional
            block_start_pos = for_match.start(1) + condition_match.start(1)
            issues.extend(
                process_block(condition_block, "for_condition", block_start_pos)
            )

    # ========== ANALISE DE WHILE LOOPS ==========
    for while_match in while_loop_re.finditer(tree_text):
        while_block = while_match.group(1)
        # Encontra a expressão dentro do while
        expr_match = re.search(
            r"Node @\d+ \(tag: kExpression\) \{(.*?)\n\s*?\}", while_block, re.DOTALL
        )
        if expr_match:
            expr_block = expr_match.group(1)
            block_start_pos = while_match.start(1) + expr_match.start(1)
            issues.extend(process_block(expr_block, "while_condition", block_start_pos))

    # ========== ANALISE DE DO-WHILE LOOPS ==========
    for do_while_match in do_while_re.finditer(tree_text):
        do_while_block = do_while_match.group(1)
        # Encontra a expressão condicional do do-while
        expr_match = re.search(
            r"Node @\d+ \(tag: kExpression\) \{(.*?)\n\s*?\}", do_while_block, re.DOTALL
        )
        if expr_match:
            expr_block = expr_match.group(1)
            block_start_pos = do_while_match.start(1) + expr_match.start(1)
            issues.extend(
                process_block(expr_block, "do_while_condition", block_start_pos)
            )

    # ========== ANALISE DE IF STATEMENTS ==========
    for if_match in if_statement_re.finditer(tree_text):
        if_block = if_match.group(1)
        # Encontra a condição do if
        cond_match = re.search(
            r"Node @\d+ \(tag: kParenGroup\) \{(?:.*?Node @\d+ \(tag: kExpression\) \{)?(.*?)\n\s*?\}",
            if_block,
            re.DOTALL,
        )
        if cond_match:
            cond_block = cond_match.group(1)
            block_start_pos = if_match.start(1) + cond_match.start(1)
            issues.extend(process_block(cond_block, "if_condition", block_start_pos))

    # ========== ANALISE DE CASE STATEMENTS ==========
    for case_match in case_statement_re.finditer(tree_text):
        case_block = case_match.group(1)

        # Procura por case items dentro do case statement
        for case_item_match in case_item_re.finditer(case_block):
            case_item_block = case_item_match.group(1)

            # Procura por expressões dentro do case item (valores do case)
            expr_match = re.search(
                r"Node @\d+ \(tag: kExpression\) \{(.*?)\n\s*?\}",
                case_item_block,
                re.DOTALL,
            )
            if expr_match:
                expr_block = expr_match.group(1)
                # Verifica se é um literal (não 'default')
                if "default" not in expr_block.lower():
                    block_start_pos = (
                        case_match.start(1)
                        + case_item_match.start(1)
                        + expr_match.start(1)
                    )
                    issues.extend(
                        process_block(expr_block, "case_value", block_start_pos)
                    )

    # Remover duplicatas baseadas em linha
    unique_issues = []
    seen_lines = set()

    for issue in issues:
        key = (issue["file"], issue["line"], issue["context"])
        if key not in seen_lines:
            seen_lines.add(key)
            unique_issues.append(issue)

    return unique_issues


# v2
def find_implicit_base_numbers(txt_tree_path, original_file_path):
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")
    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    control_blocks_re = re.compile(
        r"Node @\d+ \(tag: (kIfStatement|kForLoopStatement|kWhileLoopStatement|kDoWhileStatement|kCaseItem)\) \{"
        r"(.*?)"
        r"\n\}",
        re.DOTALL,
    )

    implicit_number_re = re.compile(
        r"Node @\d+ \(tag: kNumber\) \{"
        r"(?!.*?kBaseDigits)"
        r".*?#TK_DecNumber @(\d+)-(\d+): \"([^\"]+)\"",
        re.DOTALL,
    )

    for block in control_blocks_re.finditer(tree_text):
        block_text = block.group(2)

        for number_match in implicit_number_re.finditer(block_text):
            start_offset = int(number_match.group(1))
            number_value = number_match.group(3)

            line_num = _offset_line(src_text, start_offset)

            context = (
                code_lines[line_num - 1].strip()
                if 0 <= line_num - 1 < len(code_lines)
                else ""
            )

            issues.append(
                {
                    "file": str(original_file_path),
                    "line": line_num,
                    "context": context,
                    "method": "syntax_tree_implicit_base",
                    "message": (
                        f"Número sem base explícita em estrutura de controle: {number_value}"
                    ),
                }
            )

    return issues


# v1
# def find_implicit_base_numbers(txt_tree_path, original_file_path):
#     issues = []
#     txt_tree_path = Path(txt_tree_path)

#     tree_text = txt_tree_path.read_text(encoding="utf-8")

#     pattern = re.compile(
#         r"Node @\d+ \(tag: kNumber\) \{"
#         r"(?:(?!Node @\d+ \(tag: kBaseDigits\)).)*?"
#         r'Leaf @\d+ \(#TK_DecNumber @(\d+)-(\d+): "([^"]+)"\)'
#         r"(?:(?!Node @\d+ \(tag: kBaseDigits\)).)*?"
#         r"\}",
#         re.DOTALL,
#     )

#     src_text = Path(original_file_path).read_text(encoding="utf-8")
#     code_lines = src_text.splitlines()

#     for match in pattern.finditer(tree_text):
#         start_offset = int(match.group(1))
#         number_value = match.group(3)

#         context_before = tree_text[max(0, match.start() - 500) : match.start()]
#         if "kCaseItem" in context_before:
#             line_num = _offset_line(src_text, start_offset)
#             context = (
#                 code_lines[line_num - 1].strip()
#                 if 0 <= line_num - 1 < len(code_lines)
#                 else ""
#             )

#             issues.append(
#                 {
#                     "file": str(original_file_path),
#                     "line": line_num,
#                     "context": context,
#                     "method": "syntax_tree_implicit_base",
#                     "message": f"Número em case statement sem base explícita: {number_value}",
#                 }
#             )

#     return issues


def find_positional_port_connections(txt_tree_path, original_file_path):
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")

    positional_matches = re.finditer(
        r"Node @\d+ \(tag: kActualPositionalPort\) \{", tree_text
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for match in positional_matches:
        context_before = tree_text[max(0, match.start() - 500) : match.start()]

        instance_match = re.search(
            r'kGateInstance.*?SymbolIdentifier @(\d+)-\d+: "([^"]+)"',
            context_before,
            re.DOTALL,
        )

        if instance_match:
            start_offset = int(instance_match.group(1))
            instance_name = instance_match.group(2)

            line_num = _offset_line(src_text, start_offset)
            context = (
                code_lines[line_num - 1].strip()
                if 0 <= line_num - 1 < len(code_lines)
                else ""
            )

            issues.append(
                {
                    "file": str(original_file_path),
                    "line": line_num,
                    "context": context,
                    "method": "syntax_tree_positional_ports",
                    "message": f"Instanciação '{instance_name}' usa conexão por posição (kActualPositionalPort)",
                }
            )

    return issues


def analyze_file(file_path):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    # Gera a árvore sintática
    generate_tree(path)
    txt_tree_path = path.with_suffix(".syntax_tree.txt")

    # Executa detectores
    tree_issues = find_ambiguous_in_tree(txt_tree_path, path)
    concat_issues = find_concatenations_in_assignments(txt_tree_path, path)
    missing_nettype_issues = find_missing_default_nettype(txt_tree_path, path)
    non_automatic_issues = find_non_automatic_functions(txt_tree_path, path)
    identical_names_issues = find_identical_port_signal_names(txt_tree_path, path)
    base_pattern_issues = find_implicit_base_numbers(txt_tree_path, path)
    positional_issues = find_positional_port_connections(txt_tree_path, path)

    for entry in identical_names_issues:
        print("Tá duplicado?")
        print(f"Linha: {entry['line']}")
        print(f"Contexto: {entry['context']}")
        print("-" * 40)

    for entry in tree_issues:
        print("Ambiguidade na Linha: ", entry["line"])

    for entry in concat_issues:
        print("Concatenação na Linha: ", entry["line"])

    for entry in base_pattern_issues:
        print("Número sem base explícita na Linha: ", entry["line"])

    for entry in positional_issues:
        print("Conexão por posição na Linha: ", entry["line"])

    smell_counts = {
        "#1_Ambiguous_literals": len(tree_issues),
        "#2_Order_dependancy": len(positional_issues),
        "#3_Identical_names": len(identical_names_issues),
        "#4_Standard_base_literals": len(base_pattern_issues),
        "#5_Concat_arrayLiterals": len(concat_issues),
        "#6_Implicit_nettype": len(missing_nettype_issues),
        "#7_Non_automatic_init": len(non_automatic_issues),
    }

    return smell_counts


def main():
    for file_path in sys.argv[1:]:
        try:
            result = analyze_file(file_path)
        except FileNotFoundError as e:
            print(str(e))
            continue

        print(f"\n=== Arquivo: {file_path} ===")
        for smell, count in result.items():
            print(f"{smell}: {count} ")


if __name__ == "__main__":
    main()
