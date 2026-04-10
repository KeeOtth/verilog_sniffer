import re


class VeribleASTParser:
    NODE_REGEX = re.compile(r"Node .* \(tag: (\w+)\)")
    LEAF_REGEX = re.compile(r'Leaf .* \(#(\w+).*: "([^"]+)"\)')

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
                token_type = leaf_match.group(1)
                token_value = leaf_match.group(2)

                leaf = {"type": token_type, "token": token_value, "meta": line}

                if stack:
                    stack[-1]["children"].append(leaf)

                continue

            # --- CLOSE NODE ---
            if line == "}":
                if stack:
                    stack.pop()

        return root


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


class UnsizedBaselessLiteralDetector(SmellDetector):
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


class Analyzer:
    def __init__(self, detectors):
        self.detectors = detectors

    def run(self, tree):
        all_results = []

        for detector in self.detectors:
            results = detector.detect(tree)
            all_results.extend(results)

        return all_results


if __name__ == "__main__":
    # Caminho do arquivo gerado pelo Verible
    input_file = "ast.txt"

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Parse
    parser = VeribleASTParser()
    tree = parser.parse(lines)

    # Detectores
    detectors = [UnsizedBaselessLiteralDetector()]

    # Analyzer
    analyzer = Analyzer(detectors)
    results = analyzer.run(tree)

    # Output
    print("\n=== RESULTADOS ===\n")
    if not results:
        print("Nenhum smell detectado.\n")
    else:
        for r in results:
            print(r)
