"""
Gera duas planilhas de amostra para testar a aplicacao:

  - amostra_aprovado.xlsx: valores inspirados no caso real documentado no
    Tema 01 (instrumento 703.1208), todas as caracteristicas dentro da
    tolerancia -> parecer esperado: APROVADO.
  - amostra_reprovado.xlsx: mesma base, com uma medida alterada de
    proposito para cair fora da tolerancia -> parecer esperado: REPROVADO.

Os valores numericos foram levemente ajustados em relacao ao documento
original (nao sao os dados reais da Schulz), servindo apenas como massa
de teste para demonstrar o funcionamento do MVP.
"""
import os

import openpyxl

CABECALHO = ["DIMENSION", "NOMINAL", "+TOL", "-TOL", "MEAS 1", "MEAS 2"]

CARACTERISTICAS_BASE = [
    ("62P_DIAMETRO 1", 6.075, 0.01, -0.01, 6.0787295, 6.0780314),
    ("62P_DIAMETRO 2", 6.075, 0.01, -0.01, 6.0781314, 6.0779901),
    ("48P_COMPRIMENTO 1", 48.200, 0.05, -0.05, 48.2123, 48.2098),
    ("48P_COMPRIMENTO 2", 48.200, 0.05, -0.05, 48.2087, 48.2102),
    ("30P_PLANICIDADE", 0.000, 0.02, -0.02, 0.0081, 0.0079),
    ("15P_DIAMETRO 1", 15.300, 0.015, -0.015, 15.3092, 15.3088),
    ("15P_DIAMETRO 2", 15.300, 0.015, -0.015, 15.3079, 15.3084),
    ("22P_PROFUNDIDADE", 22.500, 0.03, -0.03, 22.5121, 22.5109),
]


def _escrever(caminho, caracteristicas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Importacao"
    ws.append(["Relatorio de medicao - Calypso (amostra para teste do MVP)"])
    ws.append([])
    ws.append(CABECALHO)
    for linha in caracteristicas:
        ws.append(list(linha))
    wb.save(caminho)


def main():
    pasta = os.path.dirname(__file__)

    _escrever(os.path.join(pasta, "amostra_aprovado.xlsx"), CARACTERISTICAS_BASE)

    reprovado = list(CARACTERISTICAS_BASE)
    nome, nominal, tol_mais, tol_menos, m1, m2 = reprovado[2]
    reprovado[2] = (nome, nominal, tol_mais, tol_menos, 48.28, 48.27)  # fora da tolerancia
    _escrever(os.path.join(pasta, "amostra_reprovado.xlsx"), reprovado)

    print("Geradas: amostra_aprovado.xlsx e amostra_reprovado.xlsx")


if __name__ == "__main__":
    main()
