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

    pattern = re.compile(
        r"kActualNamedPort.*?"
        r'SymbolIdentifier @\d+-\d+: "(?P<port_name>[^"]+)".*?'
        r'SymbolIdentifier @\d+-\d+: "(?P<signal_name>[^"]+)"',
        re.DOTALL,
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for match in pattern.finditer(tree_text):
        port_name = match.group("port_name")
        signal_name = match.group("signal_name")

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


def find_implicit_base_numbers(txt_tree_path, original_file_path):
    issues = []
    txt_tree_path = Path(txt_tree_path)

    tree_text = txt_tree_path.read_text(encoding="utf-8")

    pattern = re.compile(
        r"Node @\d+ \(tag: kNumber\) \{"
        r"(?:(?!Node @\d+ \(tag: kBaseDigits\)).)*?"
        r'Leaf @\d+ \(#TK_DecNumber @(\d+)-(\d+): "([^"]+)"\)'
        r"(?:(?!Node @\d+ \(tag: kBaseDigits\)).)*?"
        r"\}",
        re.DOTALL,
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for match in pattern.finditer(tree_text):
        start_offset = int(match.group(1))
        number_value = match.group(3)

        context_before = tree_text[max(0, match.start() - 500) : match.start()]
        if "kCaseItem" in context_before:
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
                    "message": f"Número em case statement sem base explícita: {number_value}",
                }
            )

    return issues


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


def main():
    all_issues = []

    inicio = time.perf_counter()

    for file_path in sys.argv[1:]:
        path = Path(file_path)
        if not path.exists():
            print(f"Arquivo não encontrado: {file_path}", file=sys.stderr)
            continue

        generate_tree(path)
        txt_tree_path = path.with_suffix(".syntax_tree.txt")

        tree_issues = find_ambiguous_in_tree(txt_tree_path, path)
        concat_issues = find_concatenations_in_assignments(txt_tree_path, path)
        missing_nettype_issues = find_missing_default_nettype(txt_tree_path, path)
        non_automatic_issues = find_non_automatic_functions(txt_tree_path, path)
        identical_names_issues = find_identical_port_signal_names(txt_tree_path, path)
        base_pattern_issues = find_implicit_base_numbers(txt_tree_path, path)
        positional_issues = find_positional_port_connections(txt_tree_path, path)
        # debug_number_tokens(txt_tree_path)

        combined_issues = {f"{i['line']}:": i for i in tree_issues}

        for issue in (
            tree_issues
            + concat_issues
            + missing_nettype_issues
            + non_automatic_issues
            + identical_names_issues
            + base_pattern_issues
            + positional_issues
        ):
            key = f"{issue['line']}"
            if key not in combined_issues:
                combined_issues[key] = issue

        issues = list(combined_issues.values())

        if issues:
            all_issues.extend(issues)
            for issue in issues:
                print(f"  Linha {issue['line']}: {issue['message']}")
                print(f"     Contexto: {issue['context']}")
        else:
            print("  Achei nada boy.")

    fim = time.perf_counter()

    tempo_decorrido = fim - inicio

    print(f"tempo de execução: {tempo_decorrido}\n")


if __name__ == "__main__":
    main()
