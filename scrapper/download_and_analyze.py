import csv
import os
import shutil
from pathlib import Path

import requests

from sniffin2 import analyze_file

BASE_RAW_URL = "https://raw.githubusercontent.com/"
TEMP_ROOT = Path("temp_repos")

# CORRIGIDO: Todas as extensões com ponto
HDL_EXT = (".sv", ".svh", ".vh", ".v", ".vhd", ".vhdl")

CSV_INPUT = "repositorios_sv.csv"
CSV_OUT_DETALHADO = "resultados_detalhados2.csv"
CSV_OUT_REPO = "tabela_agregada2.csv"


def contar_linhas(arquivo_path):
    """Conta o número de linhas de um arquivo"""
    try:
        with open(arquivo_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def ler_csv_repos():
    repos = []
    with open(CSV_INPUT, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Verifica se há arquivos listados
            arquivos_str = row.get("arquivos", "").strip()
            if not arquivos_str:
                print(f"[AVISO] Repositório sem arquivos: {row['repositório']}")
                continue

            repos.append(
                {
                    "name": row["repositório"],
                    "url": row["url"],
                    "files": [f.strip() for f in arquivos_str.split(";") if f.strip()],
                }
            )
    print(f"[INFO] Total de repositórios com arquivos: {len(repos)}")
    return repos


def baixar_arquivo_raw(repo, file_path, dest_file):
    possible_branches = ["main", "master", "dev", "development", "trunk"]

    for br in possible_branches:
        url = f"{BASE_RAW_URL}{repo}/{br}/{file_path}"

        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_file, "wb") as f:
                    f.write(resp.content)
                print(f"[OK] Baixado: {repo}/{file_path}")
                return True
        except Exception as e:
            continue

    # Tentar sem branch (alguns usam caminho direto)
    url = f"{BASE_RAW_URL}{repo}/{file_path}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_file, "wb") as f:
                f.write(resp.content)
            print(f"[OK] Baixado (sem branch): {repo}/{file_path}")
            return True
    except Exception:
        pass

    print(f"[ERRO] Arquivo não encontrado em {repo}: {file_path}")
    return False


def verificar_extensao_hdl(arquivo_path):
    """Verifica se o arquivo tem extensão HDL"""
    return any(arquivo_path.lower().endswith(ext) for ext in HDL_EXT)


def processar_repositorio(repo, resultados_detalhados, agregador):
    repo_name = repo["name"]
    files = repo["files"]

    print(f"\n=== PROCESSANDO {repo_name} ({len(files)} arquivos) ===")

    temp_repo_dir = TEMP_ROOT / repo_name.replace("/", "__")

    # Contador agregado por smell
    soma_smells_repo = {}
    arquivos_processados = 0

    for relative_path in files:
        relative_path = relative_path.strip()

        # Verificação CORRETA de extensão
        if not verificar_extensao_hdl(relative_path):
            print(f"[PULAR] Extensão não HDL: {relative_path}")
            continue

        dest_file = temp_repo_dir / relative_path

        ok = baixar_arquivo_raw(repo_name, relative_path, dest_file)
        if not ok:
            continue

        # Analisar
        try:
            smells = analyze_file(dest_file)
            arquivos_processados += 1
        except Exception as e:
            print(f"[ERRO] Analisando {dest_file}: {e}")
            continue

        num_linhas = contar_linhas(dest_file)

        # Registrar linha a linha no CSV detalhado
        for smell, quantidade in smells.items():
            resultados_detalhados.append(
                {
                    "repo": repo_name,
                    "arquivo": str(dest_file),
                    "linhas": num_linhas,
                    "smell": smell,
                    "quantidade": quantidade,
                }
            )
            soma_smells_repo[smell] = soma_smells_repo.get(smell, 0) + quantidade

    print(
        f"[INFO] {repo_name}: {arquivos_processados}/{len(files)} arquivos processados"
    )

    # Remover arquivos temporários
    if temp_repo_dir.exists():
        shutil.rmtree(temp_repo_dir)

    if soma_smells_repo:  # Só adiciona se processou algum arquivo
        agregador[repo_name] = soma_smells_repo
    else:
        print(f"[AVISO] Nenhum arquivo HDL processado para {repo_name}")


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


def main():
    TEMP_ROOT.mkdir(exist_ok=True)

    repos = ler_csv_repos()
    print(f"\n[INFO] Total de repositórios para processar: {len(repos)}")

    agregador = {}
    resultados_detalhados = []  # <- onde vamos guardar tudo antes de ordenar

    contador = 0
    for repo in repos:
        contador += 1
        print(f"\n[{contador}/{len(repos)}] ", end="")
        processar_repositorio(repo, resultados_detalhados, agregador)

    # =========================
    # PASSO 5 — ORDENAR RESULTADOS
    # =========================
    resultados_detalhados.sort(key=lambda x: x["linhas"])

    # salvar CSV detalhado ordenado
    with open(CSV_OUT_DETALHADO, "w", newline="", encoding="utf-8") as f_det:
        writer = csv.DictWriter(
            f_det,
            fieldnames=["repo", "arquivo", "linhas", "smell", "quantidade"],
        )
        writer.writeheader()
        writer.writerows(resultados_detalhados)

    salvar_tabela_agregada(agregador)

    print(f"\n[OK] Processo finalizado!")
    print(f"[RESUMO] Total repositórios processados: {len(agregador)}")
    print(
        f"[RESUMO] Total arquivos processados: {sum(len(v) for v in agregador.values())}"
    )


if __name__ == "__main__":
    main()
