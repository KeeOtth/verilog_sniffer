import re
import subprocess
import sys
from pathlib import Path

PATH-HERE = "" #Input the path here to the file you want to analyze. It can be a .sv file or a .syntax_tree.txt file.

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


class AtomDetector:
    def detect(self, tree):
        raise NotImplementedError


class UnsizedBaselessDetector(AtomDetector):
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

    # -------- DETECTION --------

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


class NonAutoFunctionDetector(AtomDetector):
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


class PackedMultidimConcatDetector(AtomDetector):

    def collect_multidimensional_packed_vars(self, tree):

        variables = set()

        for node in traverse(tree):
            if node["type"] != "kPortDeclaration":
                continue

            packed_dims = find_descendants(node, "kDataType")

            if not packed_dims:
                continue

            data_type = packed_dims[0]

            packed_nodes = find_descendants(data_type, "kPackedDimensions")

            if not packed_nodes:
                continue

            dimension_ranges = find_descendants(packed_nodes[0], "kDimensionRange")

            # Mais de uma dimensão packed
            if len(dimension_ranges) < 2:
                continue

            symbol_ids = []
            for child in node.get("children", []):
                if child is data_type or child.get("type") == "kDataType":
                    continue
                if child.get("type") == "SymbolIdentifier":
                    symbol_ids.append(child)
                symbol_ids.extend(find_descendants(child, "SymbolIdentifier"))

            if symbol_ids:
                variables.add(symbol_ids[-1]["token"])

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


    def rhs_is_assignment_pattern(self, assignment):
  
        expressions = get_children_by_type(assignment, "kExpression")

        if not expressions:
            return False

        rhs = expressions[0]
        return bool(find_descendants(rhs, "kAssignmentPattern"))


    def build_result(self, assignment, variable):

        return {
            "smell": "packed_multidimensional_concat_assignment",
            "variable": variable,
            "raw": assignment.get("meta", ""),
        }

    # --------------------------------------------------
    # DETECTION
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

            if not self.rhs_is_assignment_pattern(node):
                continue

            results.append(self.build_result(node, variable))

        return results


class CaseXDetector(AtomDetector):


    def is_case_statement(self, node):
        return node["type"] == "kCaseStatement"

    def get_case_keyword(self, node):
        for child in node.get("children", []):
            if child.get("type") == "casex":
                return "casex"
            if child.get("type") == "casez":
                return "casez"
            if child.get("type") == "case":
                return "case"
        return None

    def has_casex_keyword(self, node):
        return self.get_case_keyword(node) == "casex"

    def extract_case_expression(self, node):
        paren_groups = get_children_by_type(node, "kParenGroup")

        if not paren_groups:
            return None

        expressions = get_children_by_type(paren_groups[0], "kExpression")

        if expressions:
            return expressions[0]

        return None

    def extract_case_expression_token(self, case_expr):
        if not case_expr:
            return None

        symbol_ids = find_descendants(case_expr, "SymbolIdentifier")

        if symbol_ids:
            return symbol_ids[0]["token"]

        return None

    def count_case_items(self, node):
        case_item_lists = get_children_by_type(node, "kCaseItemList")

        count = 0
        for item_list in case_item_lists:
            count += len(get_children_by_type(item_list, "kCaseItem"))
            count += len(get_children_by_type(item_list, "kDefaultItem"))

        return count

    def build_result(self, case_statement):
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
        results = []

        for node in traverse(tree):
            if not self.is_case_statement(node):
                continue

            if not self.has_casex_keyword(node):
                continue

            results.append(self.build_result(node))

        return results


class ChainedComparisonDetector(AtomDetector):

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

            for i in range(len(tokens) - 4):
                a, op1, b, op2, c = tokens[i : i + 5]

                if op1 in self.CMP_OPS and op2 in self.CMP_OPS:
                    if self.is_operand(a) and self.is_operand(b) and self.is_operand(c):
                        results.append(self.build_result(a, op1, b, op2, c, node))

        return results


class MixedSignedUnsignedBinaryDetector(AtomDetector):
    ARITHMETIC_OPERATORS = {"+", "-", "*", "/", "%"}
    DEFAULT_SIGNED_TYPES = {"byte", "shortint", "int", "longint", "integer"}
    DECLARATION_TYPES = {"kDataDeclaration", "kPortDeclaration"}

    def is_binary_expression(self, node):
        return node["type"] == "kBinaryExpression"

    def declared_signedness(self, data_type):
        tokens = [
            node.get("token")
            for node in traverse(data_type)
            if node.get("token") is not None
        ]

        if "unsigned" in tokens:
            return False
        if "signed" in tokens:
            return True

        return any(token in self.DEFAULT_SIGNED_TYPES for token in tokens)

    def declared_identifiers(self, declaration, data_type):
        identifiers = []

        def walk(node):
            if node is data_type or node.get("type") in {
                "kExpression",
                "kNetVariableAssignment",
            }:
                return

            if node.get("type") == "SymbolIdentifier":
                identifiers.append(node["token"])

            for child in node.get("children", []):
                walk(child)

        walk(declaration)
        return identifiers

    def collect_variable_signedness(self, tree):
        signedness = {}

        for node in traverse(tree):
            if node.get("type") not in self.DECLARATION_TYPES:
                continue

            data_types = find_descendants(node, "kDataType")
            if not data_types:
                continue

            data_type = data_types[0]
            is_signed = self.declared_signedness(data_type)

            for identifier in self.declared_identifiers(node, data_type):
                signedness[identifier] = is_signed

        return signedness


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

    def number_signedness(self, number):
        base_digits = find_descendants(number, "kBaseDigits")

        if not base_digits:
            if find_descendants(number, "TK_DecNumber"):
                return True
            return None

        base_tokens = [
            node.get("token", "")
            for base in base_digits
            for node in traverse(base)
            if node.get("token")
        ]
        return any(re.match(r"^'[sS]", token) for token in base_tokens)

    def reference_name(self, node):
        identifiers = find_descendants(node, "SymbolIdentifier")
        if identifiers:
            return identifiers[0]["token"]
        return None

    def infer_signedness(self, node, variables):
        if node is None:
            return None

        if node.get("type") == "kNumber":
            return self.number_signedness(node)

        if node.get("type") == "kBinaryExpression":
            lhs, rhs = self.extract_operands(node)
            lhs_signed = self.infer_signedness(lhs, variables)
            rhs_signed = self.infer_signedness(rhs, variables)
            if lhs_signed is None or rhs_signed is None:
                return None
            return lhs_signed and rhs_signed

        name = self.reference_name(node)
        if name in variables:
            return variables[name]

        children = node.get("children", [])
        structural_children = [c for c in children if "token" not in c]

        if len(structural_children) == 1:
            return self.infer_signedness(structural_children[0], variables)

        return None


    def operand_description(self, operand):
        name = self.reference_name(operand)
        if name:
            return name

        tokens = [
            node.get("token")
            for node in traverse(operand)
            if node.get("token") is not None
        ]
        return "".join(tokens) or None

    def build_result(self, lhs, rhs, lhs_signed, rhs_signed, binary_expr):

        return {
            "smell": "mixed_signed_unsigned_binary_expression",
            "operator": self.extract_operator(binary_expr),
            "left": self.operand_description(lhs),
            "left_signedness": "signed" if lhs_signed else "unsigned",
            "right": self.operand_description(rhs),
            "right_signedness": "signed" if rhs_signed else "unsigned",
            "raw": binary_expr.get("meta", ""),
        }

    # --------------------------------------------------
    # DETECTION
    # --------------------------------------------------

    def detect(self, tree):

        results = []
        variables = self.collect_variable_signedness(tree)

        for node in traverse(tree):
            if not self.is_binary_expression(node):
                continue

            if not self.is_arithmetic_expression(node):
                continue

            lhs, rhs = self.extract_operands(node)
            lhs_signed = self.infer_signedness(lhs, variables)
            rhs_signed = self.infer_signedness(rhs, variables)

            if lhs_signed is None or rhs_signed is None:
                continue

            if lhs_signed == rhs_signed:
                continue

            results.append(
                self.build_result(lhs, rhs, lhs_signed, rhs_signed, node)
            )

        return results

ImplicitDecimalBinaryDetector = MixedSignedUnsignedBinaryDetector

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
    return "PATH-HERE"


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
    return Path("PATH-HERE")


DETECTORS = [
    UnsizedBaselessDetector(),
    NonAutoFunctionDetector(),
    PackedMultidimConcatDetector(),
    CaseXDetector(),
    ChainedComparisonDetector(),
    MixedSignedUnsignedBinaryDetector(),
]

ATOM_NAMES = [
    "unsized_baseless_literal_in_control",
    "non_automatic_function",
    "packed_multidimensional_concat_assignment",
    "casex_statement",
    "chained_comparison",
    "mixed_signed_unsigned_binary_expression",
]


def analyze_file(file_path):

    file_path = Path(file_path)

    if file_path.suffix == ".sv":
        syntax_tree_path = generate_syntax_tree(file_path)
        lines = read_syntax_tree(syntax_tree_path)
    else:
        lines = read_syntax_tree(file_path)

    parser = VeribleASTParser()
    tree = parser.parse(lines)

    analyzer = Analyzer(DETECTORS)

    return analyzer.run(tree)


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
        MixedSignedUnsignedBinaryDetector(),
    ]

    # Analyzer
    analyzer = Analyzer(detectors)
    results = analyzer.run(tree)

    print("\n=== RESULTS ===\n")
    if not results:
        print("NO ATOMS DETECTED.\n")
    else:
        for r in results:
            print(r)
