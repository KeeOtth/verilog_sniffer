import concurrent.futures
import csv
import logging
import os
import shutil
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import requests

try:
    from ..sniffin_variation import SMELL_NAMES, analyze_file
except Exception:
    # Quando executado como script dentro de scrapper (cd scrapper && python -m ...)
    # adiciona o diretório pai ao sys.path para permitir import absoluto.
    # Gambiarra
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sniffin_variation import SMELL_NAMES, analyze_file

BASE_RAW_URL = "https://raw.githubusercontent.com/"
TEMP_ROOT = Path("temp_repos")

# Diretórios e arquivos CSV (usa a pasta `csv/` no root do projeto)
REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = REPO_ROOT / "csv"

# CORRIGIDO: Todas as extensões com ponto
HDL_EXT = (".sv", ".svh", ".vh", ".v", ".vhd", ".vhdl")

CSV_INPUT = CSV_DIR / "repositorios_sv.csv"
CSV_OUT_DETALHADO = CSV_DIR / "resultados_detalhados3.csv"
CSV_OUT_REPO = CSV_DIR / "tabela_agregada3.csv"

# Configuração de paralelismo
DEFAULT_MAX_WORKERS = max(4, (os.cpu_count() or 2) * 2)

# Logging básico
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# Cache de branch bem-sucedido por repositório para evitar tentativas repetidas
_branch_cache = {}


def contar_smells(resultado):

    contador = Counter()

    for smell in resultado:
        contador[smell["smell"]] += 1

    return contador


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


def build_github_url(repo_name, branch, file_path):
    repo_name = repo_name.strip("/")
    if not branch or branch == "(no-branch)":
        branch = "master"
    return f"https://github.com/{repo_name}/blob/{branch}/{file_path}"


def baixar_arquivo_raw(repo, file_path, dest_file, session: requests.Session):
    """Baixa um arquivo usando a sessão fornecida. Usa cache de branch por repo."""
    # Se já tivermos encontrado um branch que funciona para esse repo, tente primeiro
    cached = _branch_cache.get(repo)

    branches = []
    if cached:
        branches.append(cached)

    # limitar tentativa a branches comuns para reduzir latência
    for b in ("master", "main"):
        if b not in branches:
            branches.append(b)

    # tenta cada branch
    for br in branches:
        url = f"{BASE_RAW_URL}{repo}/{br}/{file_path}"
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_file, "wb") as f:
                    f.write(resp.content)
                logging.info(f"Baixado: {repo}/{file_path} ({br})")
                _branch_cache[repo] = br
                return True, br
        except Exception:
            continue

    # fallback: tentar sem branch
    url = f"{BASE_RAW_URL}{repo}/{file_path}"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_file, "wb") as f:
                f.write(resp.content)
            logging.info(f"Baixado (sem branch): {repo}/{file_path}")
            _branch_cache[repo] = "(no-branch)"
            return True, "(no-branch)"
    except Exception:
        pass

    logging.warning(f"Arquivo não encontrado em {repo}: {file_path}")
    return False, None


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

    # Usa uma sessão compartilhada por repositório (keep-alive)
    session = requests.Session()

    def worker(relative_path):
        nonlocal arquivos_processados
        relative_path = relative_path.strip()

        if not verificar_extensao_hdl(relative_path):
            logging.info(f"PULAR (não HDL): {relative_path}")
            return None

        dest_file = temp_repo_dir / relative_path

        ok, branch = baixar_arquivo_raw(repo_name, relative_path, dest_file, session)
        if not ok:
            return None

        try:
            resultado = analyze_file(dest_file)
            smells = contar_smells(resultado)
            arquivos_processados += 1
        except Exception as e:
            logging.warning(f"Analisando {dest_file}: {e}")
            return None

        num_linhas = contar_linhas(dest_file)

        github_url = build_github_url(repo_name, branch, relative_path)
        rows = []
        for smell in SMELL_NAMES:
            quantidade = smells.get(smell, 0)
            rows.append(
                {
                    "repo": repo_name,
                    "arquivo": github_url,
                    "linhas": num_linhas,
                    "smell": smell,
                    "quantidade": quantidade,
                }
            )
        return (rows, smells)

    # paraleliza por arquivo (I/O bound + subprocess calls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as exc:
        futures = {exc.submit(worker, p): p for p in files}
        for fut in concurrent.futures.as_completed(futures):
            res = None
            try:
                res = fut.result()
            except Exception as e:
                logging.warning(f"Erro no worker: {e}")
                res = None

            if not res:
                continue

            rows, smells = res
            resultados_detalhados.extend(rows)

            for smell, qty in smells.items():
                soma_smells_repo[smell] = soma_smells_repo.get(smell, 0) + qty

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
    todos_smells = SMELL_NAMES

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
