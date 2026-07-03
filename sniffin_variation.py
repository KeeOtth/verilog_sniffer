import re
import subprocess
import sys
from pathlib import Path


class VeribleASTParser:
    NODE_REGEX = re.compile(r"Node .* \(tag: (\w+)\)")
    LEAF_REGEX = re.compile(
        r'Leaf .* \(#(?P<type>[^ ]+) @(?P<start>\d+-\d+): "(?P<text>[^"]*)"\)'
    )

    def parse(self, lines):
        stack = []
        root = None

        for line in lines:
            line = line.strip()

            # --- NODE ---
            node_match = self.NODE_REGEX.search(line)
            if node_match:
                node_type = node_match.group(1)

                node = {"type": node_type, "children": [], "meta": line}

                if stack:
                    stack[-1]["children"].append(node)
                else:
                    root = node

                stack.append(node)
                continue

            # --- LEAF ---
            leaf_match = self.LEAF_REGEX.search(line)
            if leaf_match:
                token_type = leaf_match.group("type").strip('"')
                token_value = leaf_match.group("text")

                leaf = {"type": token_type, "token": token_value, "meta": line}

                if stack:
                    stack[-1]["children"].append(leaf)

                continue

            # --- CLOSE NODE ---
            if line == "}":
                if stack:
                    stack.pop()

        return root


def find_descendants_by_token(node, token):

    results = []

    def walk(n):

        if n.get("token") == token:
            results.append(n)

        for c in n.get("children", []):
            walk(c)

    walk(node)

    return results


def get_children_by_type(node, type_name):
    return [c for c in node.get("children", []) if c["type"] == type_name]


def has_child(node, type_name):
    return any(c["type"] == type_name for c in node.get("children", []))


def find_descendants(node, type_name):
    results = []

    def _walk(n):
        for c in n.get("children", []):
            if c["type"] == type_name:
                results.append(c)
            _walk(c)

    _walk(node)
    return results


def traverse(node):
    yield node
    for c in node.get("children", []):
        yield from traverse(c)


class SmellDetector:
    def detect(self, tree):
        raise NotImplementedError


class UnsizedBaselessDetector(SmellDetector):
    def is_control_structure(self, node):
        return node["type"] in [
            "kIfStatement",
            "kWhileStatement",
            "kForStatement",
            "kCaseStatement",
        ]

    def is_unsized_baseless_number(self, node):
        return node["type"] == "kNumber" and not has_child(node, "kBaseDigits")

    def extract_from_case(self, node):
        expressions = []

        case_item_lists = get_children_by_type(node, "kCaseItemList")

        for item_list in case_item_lists:
            case_items = get_children_by_type(item_list, "kCaseItem")

            for item in case_items:
                expr_lists = get_children_by_type(item, "kExpressionList")

                for expr_list in expr_lists:
                    expressions.extend(get_children_by_type(expr_list, "kExpression"))

        return expressions

    def extract_from_if(self, node):
        return get_children_by_type(node, "kExpression")

    def extract_from_for(self, node):
        return get_children_by_type(node, "kExpression")

    def extract_control_expressions(self, node):
        if node["type"] == "kCaseStatement":
            return self.extract_from_case(node)

        if node["type"] == "kIfStatement":
            return self.extract_from_if(node)

        if node["type"] == "kWhileStatement":
            return self.extract_from_if(node)

        if node["type"] == "kForStatement":
            return self.extract_from_for(node)

        return []

    # -------- RESULTADO --------

    def extract_token(self, number_node):
        leaves = find_descendants(number_node, "TK_DecNumber")
        if leaves:
            return leaves[0]["token"]
        return None

    def build_result(self, number_node, context_node):
        return {
            "smell": "unsized_baseless_literal_in_control",
            "literal": self.extract_token(number_node),
            "context": context_node["type"],
            "raw": number_node.get("meta", ""),
        }

    # -------- DETECÇÃO --------

    def detect(self, tree):
        results = []

        for node in traverse(tree):
            if self.is_control_structure(node):
                expressions = self.extract_control_expressions(node)

                for expr in expressions:
                    numbers = find_descendants(expr, "kNumber")

                    for num in numbers:
                        if self.is_unsized_baseless_number(num):
                            results.append(self.build_result(num, node))

        return results


class NonAutoFunctionDetector(SmellDetector):
    def is_function(self, node):
        return node["type"] == "kFunctionDeclaration"

    def has_automatic(self, function_node):

        headers = get_children_by_type(function_node, "kFunctionHeader")

        if not headers:
            return False

        return len(find_descendants(headers[0], "automatic")) > 0

    def extract_name(self, function_node):

        headers = get_children_by_type(function_node, "kFunctionHeader")

        if not headers:
            return None

        ids = find_descendants(headers[0], "SymbolIdentifier")

        if ids:
            return ids[0]["token"]

        return None

    def build_result(self, function_node):

        return {
            "smell": "non_automatic_function",
            "function": self.extract_name(function_node),
            "raw": function_node.get("meta", ""),
        }

    def detect(self, tree):

        results = []

        for node in traverse(tree):
            if not self.is_function(node):
                continue

            if self.has_automatic(node):
                continue

            results.append(self.build_result(node))

        return results


class PackedMultidimConcatDetector(SmellDetector):
    # --------------------------------------------------
    # CATÁLOGO DE VARIÁVEIS MULTIDIMENSIONAIS PACKED
    # --------------------------------------------------

    def collect_multidimensional_packed_vars(self, tree):

        variables = set()

        for node in traverse(tree):
            if node["type"] != "kPortDeclaration":
                continue

            packed_dims = get_children_by_type(node, "kDataType")

            if not packed_dims:
                continue

            data_type = packed_dims[0]

            packed_nodes = get_children_by_type(data_type, "kPackedDimensions")

            if not packed_nodes:
                continue

            dimension_ranges = find_descendants(packed_nodes[0], "kDimensionRange")

            # Mais de uma dimensão packed
            if len(dimension_ranges) < 2:
                continue

            ids = get_children_by_type(node, "kUnqualifiedId")

            if not ids:
                continue

            symbol_ids = find_descendants(ids[0], "SymbolIdentifier")

            if symbol_ids:
                variables.add(symbol_ids[0]["token"])

        return variables

    # --------------------------------------------------
    # ASSIGNMENTS
    # --------------------------------------------------

    def is_assignment(self, node):
        return node["type"] == "kNetVariableAssignment"

    def extract_lhs_reference(self, assignment):

        lpvalues = get_children_by_type(assignment, "kLPValue")

        if not lpvalues:
            return None

        refs = get_children_by_type(lpvalues[0], "kReference")

        if not refs:
            return None

        return refs[0]

    def lhs_has_index(self, assignment):

        ref = self.extract_lhs_reference(assignment)

        if not ref:
            return False

        return len(get_children_by_type(ref, "kDimensionScalar")) > 0

    def extract_lhs_name(self, assignment):

        ref = self.extract_lhs_reference(assignment)

        if not ref:
            return None

        ids = find_descendants(ref, "SymbolIdentifier")

        if ids:
            return ids[0]["token"]

        return None

    # --------------------------------------------------
    # RHS
    # --------------------------------------------------

    def rhs_is_concatenation(self, assignment):

        expressions = get_children_by_type(assignment, "kExpression")

        if not expressions:
            return False

        return len(find_descendants(expressions[0], "kConcatenationExpression")) > 0

    # --------------------------------------------------
    # RESULTADO
    # --------------------------------------------------

    def build_result(self, assignment, variable):

        return {
            "smell": "packed_multidimensional_concat_assignment",
            "variable": variable,
            "raw": assignment.get("meta", ""),
        }

    # --------------------------------------------------
    # DETECÇÃO
    # --------------------------------------------------

    def detect(self, tree):

        results = []

        multidim_vars = self.collect_multidimensional_packed_vars(tree)

        if not multidim_vars:
            return results

        for node in traverse(tree):
            if not self.is_assignment(node):
                continue

            variable = self.extract_lhs_name(node)

            if variable not in multidim_vars:
                continue

            if self.lhs_has_index(node):
                continue

            if not self.rhs_is_concatenation(node):
                continue

            results.append(self.build_result(node, variable))

        return results


class CaseXDetector(SmellDetector):
    """
    Detector for casex statements in the AST.
    Identifies all casex constructs and reports their locations.
    """

    def is_case_statement(self, node):
        """Check if node is a kCaseStatement"""
        return node["type"] == "kCaseStatement"

    def get_case_keyword(self, node):
        """Return the case keyword used on the direct children of a kCaseStatement."""
        for child in node.get("children", []):
            if child.get("type") == "casex":
                return "casex"
            if child.get("type") == "casez":
                return "casez"
            if child.get("type") == "case":
                return "case"
        return None

    def has_casex_keyword(self, node):
        """
        Check if a kCaseStatement contains the 'casex' keyword.
        Returns True only when the case statement uses 'casex'.
        """
        return self.get_case_keyword(node) == "casex"

    def extract_case_expression(self, node):
        """
        Extract the expression being tested in the case statement.
        Returns the expression node or None.
        """
        # Find the ParenGroup that contains the expression
        paren_groups = get_children_by_type(node, "kParenGroup")

        if not paren_groups:
            return None

        expressions = get_children_by_type(paren_groups[0], "kExpression")

        if expressions:
            return expressions[0]

        return None

    def extract_case_expression_token(self, case_expr):
        """
        Extract the token/name of the case expression.
        For example: "instruction" from casex (instruction)
        """
        if not case_expr:
            return None

        # Try to get symbol identifier
        symbol_ids = find_descendants(case_expr, "SymbolIdentifier")

        if symbol_ids:
            return symbol_ids[0]["token"]

        return None

    def count_case_items(self, node):
        """Count the number of case items"""
        case_item_lists = get_children_by_type(node, "kCaseItemList")

        count = 0
        for item_list in case_item_lists:
            count += len(get_children_by_type(item_list, "kCaseItem"))
            count += len(get_children_by_type(item_list, "kDefaultItem"))

        return count

    def build_result(self, case_statement):
        """Build the result dictionary for a casex statement"""
        case_expr = self.extract_case_expression(case_statement)
        expr_token = self.extract_case_expression_token(case_expr)
        item_count = self.count_case_items(case_statement)

        return {
            "smell": "casex_statement",
            "case_expression": expr_token,
            "num_items": item_count,
            "raw": case_statement.get("meta", ""),
        }

    def detect(self, tree):
        """
        Detect all casex statements in the tree.
        Returns a list of dictionaries containing casex statement information.
        """
        results = []

        for node in traverse(tree):
            if not self.is_case_statement(node):
                continue

            if not self.has_casex_keyword(node):
                continue

            results.append(self.build_result(node))

        return results


class ChainedComparisonDetector(SmellDetector):
    """Detecta correntes de comparação (ex: a < b < c) para operadores de comparação.

    A detecção é feita varrendo folhas de cada `kExpression` e procurando a
    subsequência: operando, operador_comparação, operando, operador_comparação, operando.
    Operadores considerados: <, >, <=, >=, ==, !=, ===, !==.
    """

    CMP_OPS = {"<", ">", "<=", ">=", "==", "!=", "===", "!=="}

    def is_expression(self, node):
        return node.get("type") == "kExpression"

    def leaf_tokens(self, node):
        tokens = []

        def _walk(n):
            if isinstance(n, dict) and "token" in n:
                tokens.append(n["token"])
            for c in n.get("children", []):
                _walk(c)

        _walk(node)
        return tokens

    def is_operand(self, tok):
        # Identificador (ex: foo, obj.field) ou número literal
        if not isinstance(tok, str) or not tok:
            return False
        if re.match(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$", tok):
            return True
        if re.match(r"^\d+$", tok):
            return True
        return False

    def build_result(self, left, op1, middle, op2, right, expr_node):
        return {
            "smell": "chained_comparison",
            "left": left,
            "op1": op1,
            "middle": middle,
            "op2": op2,
            "right": right,
            "raw": expr_node.get("meta", ""),
        }

    def detect(self, tree):
        results = []

        for node in traverse(tree):
            if not self.is_expression(node):
                continue

            tokens = self.leaf_tokens(node)
            if not tokens:
                continue

            # Varre sequência procurando operand op operand op operand
            for i in range(len(tokens) - 4):
                a, op1, b, op2, c = tokens[i : i + 5]

                if op1 in self.CMP_OPS and op2 in self.CMP_OPS:
                    if self.is_operand(a) and self.is_operand(b) and self.is_operand(c):
                        results.append(self.build_result(a, op1, b, op2, c, node))

        return results


class ImplicitDecimalBinaryDetector(SmellDetector):
    ARITHMETIC_OPERATORS = {"+", "-", "*", "/", "%"}

    # --------------------------------------------------
    # IDENTIFICAÇÃO
    # --------------------------------------------------

    def is_binary_expression(self, node):
        return node["type"] == "kBinaryExpression"

    def is_unsized_decimal(self, node):
        return node["type"] == "kNumber" and not has_child(node, "kBaseDigits")

    # --------------------------------------------------
    # EXPRESSÃO
    # --------------------------------------------------

    def extract_operator(self, binary_expr):

        for child in binary_expr.get("children", []):
            token = child.get("token")

            if token in self.ARITHMETIC_OPERATORS:
                return token

        return None

    def is_arithmetic_expression(self, binary_expr):
        return self.extract_operator(binary_expr) is not None

    def extract_operands(self, binary_expr):

        children = binary_expr.get("children", [])

        if len(children) != 3:
            return None, None

        return children[0], children[2]

    def extract_unsized_decimal_operand(self, binary_expr):

        lhs, rhs = self.extract_operands(binary_expr)

        for operand in (lhs, rhs):
            if operand is None:
                continue

            if self.is_unsized_decimal(operand):
                return operand

        return None

    # --------------------------------------------------
    # RESULTADO
    # --------------------------------------------------

    def extract_literal(self, number_node):

        leaves = find_descendants(number_node, "TK_DecNumber")

        if leaves:
            return leaves[0]["token"]

        return None

    def build_result(self, number_node, binary_expr):

        return {
            "smell": "implicit_decimal_literal_in_binary_expression",
            "literal": self.extract_literal(number_node),
            "operator": self.extract_operator(binary_expr),
            "raw": number_node.get("meta", ""),
        }

    # --------------------------------------------------
    # DETECÇÃO
    # --------------------------------------------------

    def detect(self, tree):

        results = []

        for node in traverse(tree):
            if not self.is_binary_expression(node):
                continue

            if not self.is_arithmetic_expression(node):
                continue

            number = self.extract_unsized_decimal_operand(node)

            if number is None:
                continue

            results.append(self.build_result(number, node))

        return results


class Analyzer:
    def __init__(self, detectors):
        self.detectors = detectors

    def run(self, tree):
        all_results = []

        for detector in self.detectors:
            results = detector.detect(tree)
            all_results.extend(results)

        return all_results


def get_input_file():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return "/home/gabriel/ast-comparator/atom.syntax_tree.txt"


def generate_syntax_tree(file_path: Path):
    txt_output = file_path.with_suffix(".syntax_tree.txt")
    cmd_txt = ["verible-verilog-syntax", "--printtree", str(file_path)]

    subprocess.run(cmd_txt, stdout=txt_output.open("w", encoding="utf-8"), check=True)
    return txt_output


def read_syntax_tree(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return f.readlines()


def get_input_file():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    return Path("/home/gabriel/ast-comparator/atom.syntax_tree.txt")


if __name__ == "__main__":
    input_path = get_input_file()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if input_path.suffix == ".sv":
        syntax_tree_path = generate_syntax_tree(input_path)
        lines = read_syntax_tree(syntax_tree_path)
    else:
        lines = read_syntax_tree(input_path)

    # Parse
    parser = VeribleASTParser()
    tree = parser.parse(lines)

    # Detectores
    detectors = [
        UnsizedBaselessDetector(),
        NonAutoFunctionDetector(),
        PackedMultidimConcatDetector(),
        CaseXDetector(),
        ChainedComparisonDetector(),
        ImplicitDecimalBinaryDetector(),
    ]

    # Analyzer
    analyzer = Analyzer(detectors)
    results = analyzer.run(tree)

    print("\n=== RESULTADOS ===\n")
    if not results:
        print("Nenhum smell detectado.\n")
    else:
        for r in results:
            print(r)
