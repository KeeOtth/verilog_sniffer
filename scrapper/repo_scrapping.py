import csv
import time

import requests

GITHUB_TOKEN = "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"
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}


def buscar_repositorios(paginas=5):
    repositorios = {}
    url = "https://api.github.com/search/code"

    query = "extension:sv OR extension:svh OR extension:vh"

    for page in range(1, paginas + 1):
        params = {"q": query, "per_page": 100, "page": page}
        print(f"Buscando página {page} com query: {params['q']}")
        response = requests.get(url, headers=HEADERS, params=params)
        print(f"Status code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if "items" not in data or len(data["items"]) == 0:
                print(f"Nenhum resultado encontrado na página {page}")
                break
            for item in data["items"]:
                repo_name = item["repository"]["full_name"]
                repo_url = item["repository"]["html_url"]
                file_path = item["path"]
                if repo_name not in repositorios:
                    repositorios[repo_name] = {"url": repo_url, "arquivos": []}
                repositorios[repo_name]["arquivos"].append(file_path)
        elif response.status_code == 403:
            print("Limite de taxa atingido. Aguardando 60 segundos.")
            time.sleep(60)
            continue
        else:
            print(f"Erro na requisição na página {page}: {response.status_code}")
            break

    return repositorios


# Função para salvar CSV permanece igual
def salvar_csv(repositorios, arquivo_saida="repositorios_sv.csv"):
    with open(arquivo_saida, mode="w", newline="", encoding="utf-8") as csv_file:
        fieldnames = ["repositório", "url", "arquivos"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for repo_name, info in repositorios.items():
            writer.writerow(
                {
                    "repositório": repo_name,
                    "url": info["url"],
                    "arquivos": "; ".join(info["arquivos"]),
                }
            )
    print(f"Resultados salvos em {arquivo_saida}")


# Principal
def main():
    repositorios = buscar_repositorios(paginas=5)
    print(f"Total de repositórios encontrados: {len(repositorios)}")
    salvar_csv(repositorios)


if __name__ == "__main__":
    main()
