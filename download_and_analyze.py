import csv
import os
import requests
import shutil
from pathlib import Path
from sniffin2 import analyze_file

BASE_RAW_URL = "https://raw.githubusercontent.com/"
TEMP_ROOT = Path("temp_repos")

HDL_EXT = (".sv")

CSV_INPUT = "repositorios_sv.csv"
CSV_OUT_DETALHADO = "resultados_detalhados2.csv"
CSV_OUT_REPO = "tabela_agregada2.csv"


# ================================================================
# 1) Leitura do CSV de repositórios do GitHub
# ================================================================
def ler_csv_repos():
    repos = []
    with open(CSV_INPUT, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repos.append({
                "name": row["repositório"],
                "url": row["url"],
                "files": row["arquivos"].split("; ")
            })
    return repos


# ================================================================
# 2) Download OTIMIZADO — baixar só os arquivos específicos
# ================================================================
def baixar_arquivo_raw(repo, file_path, dest_file):
    """
    repo:     'user/repo'
    file_path: caminho dentro do repositório
    """

    possible_branches = ["main", "master", "dev", "development"]

    for br in possible_branches:
        url = f"{BASE_RAW_URL}{repo}/{br}/{file_path}"

        resp = requests.get(url)
        if resp.status_code == 200:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_file, "wb") as f:
                f.write(resp.content)
            return True

    print(f"[ERRO] Arquivo não encontrado em {repo}: {file_path}")
    return False


# ================================================================
# 3) Processamento do repositório
# ================================================================
def processar_repositorio(repo, writer_detalhado, agregador):
    repo_name = repo["name"]
    files = repo["files"]

    print(f"\n=== PROCESSANDO {repo_name} ===")

    temp_repo_dir = TEMP_ROOT / repo_name.replace("/", "__")

    # Contador agregado por smell
    soma_smells_repo = {}

    for relative_path in files:
        relative_path = relative_path.strip()
        if not relative_path.lower().endswith(HDL_EXT):
            continue

        dest_file = temp_repo_dir / relative_path

        ok = baixar_arquivo_raw(repo_name, relative_path, dest_file)
        if not ok:
            continue

        # Analisar
        try:
            smells = analyze_file(dest_file)
        except Exception as e:
            print(f"[ERRO] Analisando {dest_file}: {e}")
            continue

        # Registrar linha a linha no CSV detalhado
        for smell, quantidade in smells.items():
            writer_detalhado.writerow({
                "repo": repo_name,
                "arquivo": str(dest_file),
                "smell": smell,
                "quantidade": quantidade
            })

            soma_smells_repo[smell] = soma_smells_repo.get(smell, 0) + quantidade

    # Remover arquivos temporários imediatamente
    if temp_repo_dir.exists():
        shutil.rmtree(temp_repo_dir)

    # Salvar agregados finais
    agregador[repo_name] = soma_smells_repo


# ================================================================
# 4) Escrita da tabela agregada por repositório
# ================================================================
def salvar_tabela_agregada(agregador):
    todos_smells = set()
    for repo, smells in agregador.items():
        todos_smells.update(smells.keys())
    todos_smells = sorted(todos_smells)

    with open(CSV_OUT_REPO, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["repo"] + todos_smells
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for repo, smells in agregador.items():
            row = {"repo": repo}
            for smell in todos_smells:
                row[smell] = smells.get(smell, 0)
            writer.writerow(row)

    print(f"[OK] Tabela agregada salva em {CSV_OUT_REPO}")


# ================================================================
# 5) MAIN
# ================================================================
def main():
    TEMP_ROOT.mkdir(exist_ok=True)

    repos = ler_csv_repos()
    agregador = {}

    # CSV detalhado por arquivo
    with open(CSV_OUT_DETALHADO, "w", newline="", encoding="utf-8") as f_det:
        writer_detalhado = csv.DictWriter(
            f_det,
            fieldnames=["repo", "arquivo", "smell", "quantidade"]
        )
        writer_detalhado.writeheader()

        for repo in repos:
            processar_repositorio(repo, writer_detalhado, agregador)

    salvar_tabela_agregada(agregador)

    print("\n[OK] Processo finalizado!")


if __name__ == "__main__":
    main()
