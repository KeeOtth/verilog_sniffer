import subprocess
import sys
import re
from pathlib import Path

def find_ambiguous_literals(file_path):
    issues = []
    pattern = re.compile(r"=\s*'([01xXzZ])[\s;]")
    
    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if match := pattern.search(line):
                literal = f"'{match.group(1)}"
                issues.append({
                    'file': str(file_path),
                    'line': line_num,
                    'column': match.start() + 1,
                    'literal': literal,
                    'context': line.strip(),
                    'message': f"Literal numérico ambíguo '{literal}' encontrado."
                })
    
    return issues

def main():
    if len(sys.argv) < 2:
        print("Uso: python3 find_ambiguous_literals.py <arquivo1.sv> [arquivo2.v ...]")
        sys.exit(1)
    
    all_issues = []
    
    for file_path in sys.argv[1:]:
        path = Path(file_path)
        if not path.exists():
            print(f"Arquivo não encontrado: {file_path}", file=sys.stderr)
            continue
        
        print(f"Analisando {file_path}...")
        issues = find_ambiguous_literals(path)
        
        if issues:
            all_issues.extend(issues)
            print(f"  Encontrados {len(issues)} problemas:")
            for issue in issues:
                print(f"  Linha {issue['line']}:{issue['column']}: {issue['message']}")
                print(f"     Contexto: {issue['context']}")
        else:
            print("  Nenhum literal ambíguo encontrado.")
    
    if all_issues:
        print("\nResumo de problemas encontrados:")
        for issue in all_issues:
            print(f"{issue['file']}:{issue['line']}:{issue['column']} - {issue['message']}")
        
        with open('ambiguous_literals_report.txt', 'w') as f:
            for issue in all_issues:
                f.write(f"{issue['file']}:{issue['line']}:{issue['column']}: warning: {issue['message']}\n")
        
        print("\nRelatório salvo em 'ambiguous_literals_report.txt'")
        sys.exit(1)
    else:
        print("\nNenhum literal ambíguo encontrado nos arquivos analisados.")
        sys.exit(0)

if __name__ == '__main__':
    main()