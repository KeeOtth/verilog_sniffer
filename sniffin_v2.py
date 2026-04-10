import re
import subprocess
from pathlib import Path


# -------------- Tools --------------
def generate_tree(file_path):
    txt_output = file_path.with_suffix(".syntax_tree.txt")
    cmd_txt = ["verible-verilog-syntax", "--printtree", str(file_path)]
    with open(txt_output, "w") as f:
        subprocess.run(cmd_txt, stdout=f, check=True)


def _offset_line(src_text: str, offset: int):
    return src_text.count("\n", 0, offset) + 1


# -------------- Smell Finders --------------
def find_missing_default_nettype(txt_tree_path, original_file_path):
    issues = []
    tree_text = Path(txt_tree_path).read_text(encoding="utf-8")
    default_nettype_none_re = re.compile(r'`default_nettype[^}]*"none"')
    if not default_nettype_none_re.search(tree_text):
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

    for line in tree_lines:
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

        text = m_leaf.group("text")
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

    for line in Path(txt_tree_path).read_text().splitlines():
        m = leaf_pattern.search(line)
        if m:
            start_offset = int(m.group("start"))
            line_num = _offset_line(src_text, start_offset)
            literal_text = m.group("literal").encode("utf-8").decode("unicode_escape")

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
    tree_text = Path(txt_tree_path).read_text(encoding="utf-8")

    function_pattern = re.compile(
        r'Leaf @\d+ \(#"function" @\d+-\d+: "function"\)'
        r'(?!\s*Leaf @\d+ \(#"automatic" @\d+-\d+: "automatic"\))'
    )

    function_name_pattern = re.compile(
        r'Leaf @\d+ \(#SymbolIdentifier @\d+-\d+: "(?P<name>[^"]+)"\)'
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for match in function_pattern.finditer(tree_text):
        remaining = tree_text[match.start() :]
        name_match = function_name_pattern.search(remaining)

        if name_match:
            function_name = name_match.group("name")

            for i, code_line in enumerate(code_lines, 1):
                if "function" in code_line and function_name in code_line:
                    context = code_lines[i - 1].strip()
                    issues.append(
                        {
                            "file": str(original_file_path),
                            "line": i,
                            "context": context,
                            "method": "syntax_tree_non_automatic",
                            "message": f"Função '{function_name}' não usa automatic",
                        }
                    )
                    break

    return issues


def find_identical_port_signal_names(txt_tree_path, original_file_path):
    issues = []
    tree_text = Path(txt_tree_path).read_text(encoding="utf-8")

    pattern = re.compile(
        r"kActualNamedPort.*?"
        r'SymbolIdentifier @\d+-\d+: "(?P<port>[^"]+)".*?'
        r'SymbolIdentifier @\d+-\d+: "(?P<signal>[^"]+)"',
        re.DOTALL,
    )

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for m in pattern.finditer(tree_text):
        port = m.group("port")
        sig = m.group("signal")

        if port == sig:
            for i, l in enumerate(code_lines, 1):
                if f".{port}({sig}" in l.replace(" ", ""):
                    issues.append(
                        {
                            "file": str(original_file_path),
                            "line": i,
                            "context": l.strip(),
                            "method": "syntax_tree_identical_names",
                            "message": f"Porta e sinal com nomes idênticos: .{port}({sig})",
                        }
                    )
                    break

    return issues

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

# def find_implicit_base_numbers(txt_tree_path, original_file_path):
#     issues = []
#     tree_text = Path(txt_tree_path).read_text(encoding="utf-8")

#     pattern = re.compile(
#         r"Node @\d+ \(tag: kNumber\) \{"
#         r"(?:(?!Node @\d+ \(tag: kBaseDigits\)).)*?"
#         r'Leaf @\d+ \(#TK_DecNumber @(\d+)-\d+: "([^"]+)"\)'
#         r"(?:(?!Node @\d+ \(tag: kBaseDigits\)).)*?"
#         r"\}",
#         re.DOTALL,
#     )

#     src_text = Path(original_file_path).read_text(encoding="utf-8")
#     code_lines = src_text.splitlines()

#     for m in pattern.finditer(tree_text):
#         start_offset = int(m.group(1))
#         number = m.group(2)

#         ctx = tree_text[max(0, m.start() - 500) : m.start()]
#         if "kCaseItem" in ctx:
#             line_num = _offset_line(src_text, start_offset)
#             issues.append(
#                 {
#                     "file": str(original_file_path),
#                     "line": line_num,
#                     "context": code_lines[line_num - 1].strip(),
#                     "method": "syntax_tree_implicit_base",
#                     "message": f"Número no case sem base explícita: {number}",
#                 }
#             )
#     return issues


def find_positional_port_connections(txt_tree_path, original_file_path):
    issues = []
    tree_text = Path(txt_tree_path).read_text(encoding="utf-8")

    src_text = Path(original_file_path).read_text(encoding="utf-8")
    code_lines = src_text.splitlines()

    for m in re.finditer(r"Node @\d+ \(tag: kActualPositionalPort\) \{", tree_text):
        context_before = tree_text[max(0, m.start() - 500) : m.start()]

        inst = re.search(
            r'kGateInstance.*?SymbolIdentifier @(\d+)-\d+: "([^"]+)"',
            context_before,
            re.DOTALL,
        )

        if inst:
            start = int(inst.group(1))
            name = inst.group(2)
            line = _offset_line(src_text, start)

            issues.append(
                {
                    "file": str(original_file_path),
                    "line": line,
                    "context": code_lines[line - 1].strip(),
                    "method": "syntax_tree_positional_ports",
                    "message": f"Instanciação '{name}' usa positional ports",
                }
            )

    return issues


# -------------- MAIN ANALYSIS FUNCTION --------------
def analyze_file(file_path):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(file_path)

    generate_tree(path)
    txt_tree = path.with_suffix(".syntax_tree.txt")

    smells = {
        "#1_Ambiguous_literals": len(find_ambiguous_in_tree(txt_tree, path)),
        "#2_Order_dependancy": len(find_positional_port_connections(txt_tree, path)),
        "#3_Identical_names": len(find_identical_port_signal_names(txt_tree, path)),
        "#4_Standard_base_literals": len(find_implicit_base_numbers(txt_tree, path)),
        "#5_Concat_arrayLiterals": len(
            find_concatenations_in_assignments(txt_tree, path)
        ),
        "#6_Implicit_nettype": len(find_missing_default_nettype(txt_tree, path)),
        "#7_Non_automatic_init": len(find_non_automatic_functions(txt_tree, path)),
    }

    return smells
