"""
Gera as planilhas da pasta exemplos/, usadas no manual da AV5.

    python infra/gerar_exemplos.py

Todas sao Reports do Calypso do instrumento 703.1208, com o mesmo layout do
Registro MMC real. O caso real reprova pelas POSICOES, cujo criterio ainda
esta em aberto com a Schulz; por isso o exemplo aprovado traz posicoes
dentro da tolerancia, e o reprovado reprova por DIAMETRO, sem depender dessa
resposta.
"""
from __future__ import annotations

import sys
from datetime import datetime, time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "backend"), str(RAIZ / "backend" / "tests")]

from report_calypso import CASO_703_1208, gerar_report, para_strict  # noqa: E402

DESTINO = RAIZ / "exemplos"
DATA = datetime(2026, 11, 10)
HORA = time(14, 32, 5)

# Posicoes dentro da tolerancia (0 a 0,1 mm), com folga para a banda de guarda
POSICOES_OK = {"62P_POSIÇÃO 1": 0.0429552, "62P_POSIÇÃO 2": 0.0244611,
               "13P_POSIÇÃO 1": 0.0359044, "13P_POSIÇÃO 2": 0.0235576,
               "106P_POSIÇÃO 1": 0.0326890, "106P_POSIÇÃO 2": 0.0367758}


def caso_aprovado():
    return [(nome, POSICOES_OK.get(nome, p1), POSICOES_OK.get(nome, p2), nom, sup, inf)
            for nome, p1, p2, nom, sup, inf in CASO_703_1208]


def indice(nome: str) -> int:
    return [c[0] for c in CASO_703_1208].index(nome)


def main() -> None:
    DESTINO.mkdir(exist_ok=True)
    base = caso_aprovado()
    arquivos = {}

    # 1. Aprovado: todas as caracteristicas dentro da tolerancia e da banda de guarda
    arquivos["1-aprovado.xlsx"] = gerar_report(base, data=DATA, hora=HORA)

    # 2. Reprovado: 62P_DIAMETRO 1 fora da tolerancia (limite 6,085 mm) e
    #    13P_DIAMETRO 2 dentro dela, mas reprovado pela banda de guarda (media + U > limite)
    d1, d2 = indice("62P_DIÂMETRO 1"), indice("13P_DIÂMETRO 2")
    arquivos["2-reprovado.xlsx"] = gerar_report(base, data=DATA, hora=time(15, 2, 41), substituir={
        (1, d1, 1): 6.0871, (2, d1, 1): 6.0869,
        (1, d2, 1): 16.9733, (2, d2, 1): 16.9731,
    })

    # 3. Com sujeira: aprovado depois da higienizacao. Data como numero serial do
    #    Excel, hora com fracao espuria, espacos e NBSP (copiar e colar) no nome,
    #    numero como texto com virgula e unidade, campo "---" e formato OOXML Strict.
    p = indice("PLANICIDADE_REF")
    sujo = gerar_report(base, data=46336.0, hora="16:47:10.0000000046", substituir={
        (1, p, 0): "\u00a0 PLANICIDADE_REF  ", (2, p, 0): "PLANICIDADE_REF\t",
        (1, d1, 1): "6,0787295 mm", (2, d1, 1): " 6,0787295mm",
    })
    arquivos["3-com-sujeira.xlsx"] = para_strict(_order_nulo(sujo))

    # 4. Quarentena: medicao ausente ("---") na 2a passagem do 106P_DIAMETRO 1 (RN01)
    q = indice("106P_DIÂMETRO 1")
    arquivos["4-quarentena.xlsx"] = gerar_report(base, data=DATA, hora=time(16, 10, 0),
                                                 substituir={(2, q, 1): "---"})

    for nome, conteudo in arquivos.items():
        (DESTINO / nome).write_bytes(conteudo)
        print(f"exemplos/{nome}")


def _order_nulo(conteudo: bytes) -> bytes:
    """Poe '---' no campo Order (F5), um nulo textual tipico das planilhas da Schulz."""
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    wb["Report"]["F5"] = "---"
    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()


if __name__ == "__main__":
    main()
