import subprocess
import time

tempos = []
for i in range(100):

    inicio = time.perf_counter()
    cmd_txt =  ["python3", "sniffin.py", "limonada.sv"]
    subprocess.run(cmd_txt)
    fim = time.perf_counter()

    resultado = fim - inicio
    tempos.append(resultado)

total_time = 0
for entry in tempos:
    total_time = total_time = entry

media = total_time/len(tempos)
print(f"total time: {total_time}\n tamanho do vetor: {len(tempos)}\n Média dos tempos de execução de cada instância: {media}\n")
