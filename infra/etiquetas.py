"""
Etiquetas com QR Code para colar nos instrumentos.

    python infra/etiquetas.py --url https://dxxxx.cloudfront.net/ 703.1208 [TAG ...]

O QR leva a <url>#/consulta/<TAG>, o mesmo link impresso no certificado. Quem
le com a camera do celular cai na consulta do instrumento, depois do login.
Folha A4 com 3 x 8 etiquetas de 63,5 x 33,9 mm (padrao das folhas adesivas
A4 de 24 etiquetas); a TAG repetida preenche a folha.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from schulz.certificado import _qr  # noqa: E402

COLUNAS, LINHAS = 3, 8
LARGURA, ALTURA = 63.5 * mm, 33.9 * mm
MARGEM_X = (A4[0] - COLUNAS * LARGURA) / 2
MARGEM_Y = (A4[1] - LINHAS * ALTURA) / 2
QR = 27 * mm


def url_consulta(url_app: str, tag: str) -> str:
    return f"{url_app.rstrip('/')}/#/consulta/{quote(tag, safe='.-_')}"


def desenhar_etiqueta(pdf: canvas.Canvas, x: float, y: float, url_app: str, tag: str) -> None:
    folga = (ALTURA - QR) / 2
    _qr(url_consulta(url_app, tag), QR).drawOn(pdf, x + folga, y + folga)
    texto_x = x + QR + 2 * folga
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(texto_x, y + ALTURA - 8 * mm, "Schulz Metrologia")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(texto_x, y + ALTURA - 15 * mm, tag)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(texto_x, y + 10 * mm, "Situação da calibração:")
    pdf.drawString(texto_x, y + 7 * mm, "aponte a câmera para o QR")
    pdf.drawString(texto_x, y + 4 * mm, "(acesso com login)")


def gerar(url_app: str, tags: list[str], destino: Path, preencher: bool = True) -> int:
    """Gera o PDF; devolve o numero de etiquetas."""
    por_folha = COLUNAS * LINHAS
    lista = list(tags)
    if preencher and len(lista) < por_folha:
        lista = [tags[i % len(tags)] for i in range(por_folha)]
    pdf = canvas.Canvas(str(destino), pagesize=A4)
    pdf.setTitle("Etiquetas de instrumentos - Schulz Metrologia")
    for i, tag in enumerate(lista):
        if i and i % por_folha == 0:
            pdf.showPage()
        posicao = i % por_folha
        coluna, linha = posicao % COLUNAS, posicao // COLUNAS
        x = MARGEM_X + coluna * LARGURA
        y = A4[1] - MARGEM_Y - (linha + 1) * ALTURA
        desenhar_etiqueta(pdf, x, y, url_app, tag)
    pdf.save()
    return len(lista)


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argumentos.add_argument("--url", required=True, help="endereço da plataforma (saída UrlApp da pilha)")
    argumentos.add_argument("--saida", type=Path, default=Path("etiquetas.pdf"))
    argumentos.add_argument("--sem-repetir", action="store_true",
                            help="uma etiqueta por TAG, sem preencher a folha")
    argumentos.add_argument("tags", nargs="+")
    opcoes = argumentos.parse_args()
    total = gerar(opcoes.url, opcoes.tags, opcoes.saida, preencher=not opcoes.sem_repetir)
    print(f"{total} etiquetas em {opcoes.saida}")


if __name__ == "__main__":
    main()
