"""
Geracao do certificado de calibracao em PDF (RF08), no layout da aba Certificado.

Secoes, na mesma ordem da planilha:
    cabecalho      numero, data, solicitante
    1. Descricao do instrumento calibrado
    2. Padrao utilizado (com o certificado externo e a proxima calibracao)
    3. Procedimento de calibracao (texto por tipo de padrao, RN07)
    4. Resultados (mm): nominal, tolerancias, valor obtido (media), erro e
       avaliacao com banda de guarda (RN02 / RF06)
    5. Incerteza de medicao: U, k e Veff
    6. Observacoes, tecnico executante, signatario e notas (EA-4/02)

O PDF recebe um QR Code com o link da consulta do instrumento no sistema.
O QR leva so ao link: a consulta continua exigindo login.

O rodape traz o codigo de verificacao: o SHA-256 dos valores impressos
(abreviado). Nao da para imprimir o hash do proprio PDF dentro dele; o hash do
arquivo fica registrado no item do certificado, e os dois juntos permitem a um
auditor conferir tanto o conteudo quanto o arquivo recebido.
"""
from __future__ import annotations

import hashlib
import io
import json
from decimal import Decimal
from typing import Any

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

TEXTO_PROCEDIMENTO = {
    "MMC": ("O instrumento foi medido na máquina de medição por coordenadas através de "
            "elementos geométricos definidos, sendo o resultado apresentado a média de "
            "duas medições realizadas."),
    "PROJETOR": ("O instrumento de medição foi medido no projetor de perfil, através de "
                 "elementos geométricos definidos, sendo o resultado apresentado a média "
                 "de duas medições realizadas."),
}

NOTA_INCERTEZA = (
    "* A incerteza expandida de medição relatada é declarada como incerteza padrão da "
    "medição multiplicada pelo fator de abrangência k = {k}, o qual para uma distribuição "
    "t com veff = {veff} graus de liberdade efetivos corresponde a uma probabilidade de "
    "abrangência de aproximadamente 95%. A incerteza padrão de medição foi determinada de "
    "acordo com a publicação EA-4/02.")

NOTAS_FIXAS = (
    "* Os resultados deste certificado referem-se exclusivamente ao instrumento submetido "
    "a calibração, nas condições especificadas, não sendo extensivo a quaisquer lotes.",
    "* Não é permitida a reprodução parcial deste certificado.",
)


def _texto(valor: Any) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, Decimal):
        # Ate 7 casas, como o Calypso exporta (RNF10), sem zeros a direita
        texto = format(valor.quantize(Decimal("0.0000001")).normalize(), "f")
        return texto.replace(".", ",")
    return str(valor)


def codigo_verificacao(valores: dict) -> str:
    canonico = json.dumps(valores, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _qr(conteudo: str, tamanho: float) -> Drawing:
    widget = QrCodeWidget(conteudo)
    x0, y0, x1, y1 = widget.getBounds()
    desenho = Drawing(tamanho, tamanho, transform=[tamanho / (x1 - x0), 0, 0,
                                                   tamanho / (y1 - y0), 0, 0])
    desenho.add(widget)
    return desenho


def gerar_pdf(valores: dict) -> bytes:
    """Monta o PDF a partir da copia congelada dos valores impressos.

    `valores` e o mesmo dicionario gravado no item do certificado, para que
    uma reimpressao futura saia identica (AV2 3.2.1).
    """
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("normal", parent=estilos["Normal"], fontSize=8.5, leading=10.5)
    pequeno = ParagraphStyle("pequeno", parent=normal, fontSize=7, leading=8.5)
    secao = ParagraphStyle("secao", parent=normal, fontName="Helvetica-Bold", fontSize=10,
                           spaceBefore=5, spaceAfter=2)
    titulo = ParagraphStyle("titulo", parent=normal, fontName="Helvetica-Bold", fontSize=13)

    inst = valores["instrumento"]
    padrao = valores["padrao"]
    inc = valores["incerteza"]
    lab = valores.get("laboratorio", {})
    verificacao = codigo_verificacao(valores)

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                  topMargin=12 * mm, bottomMargin=18 * mm,
                                  title=f"Certificado {valores['numero_exibicao']}")
    historia = []

    cabecalho = Table([[
        Paragraph(f"{lab.get('nome', 'Laboratório de Metrologia')}<br/>"
                  f"<font size=13><b>Certificado de Calibração nº "
                  f"{valores['numero_exibicao']}</b></font>", normal),
        Paragraph(f"Data: {valores['data_calibracao']}", normal),
        _qr(valores["url_consulta"], 24 * mm),
    ]], colWidths=[110 * mm, 40 * mm, 24 * mm])
    cabecalho.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    historia.append(cabecalho)
    if valores.get("marca_prova_de_conceito"):
        historia.append(Paragraph(
            "<font color='#b00020'>Prova de conceito acadêmica (Projeto Aplicado III) — "
            "documento sem validade metrológica.</font>", pequeno))
    historia.append(Spacer(1, 2 * mm))
    historia.append(Paragraph(f"<b>Solicitante:</b> {_texto(inst.get('solicitante'))}", normal))

    historia.append(Paragraph("1. Descrição do instrumento calibrado", secao))
    for rotulo, campo in (("Denominação", "denominacao"), ("Código", "tag"),
                          ("Fabricante", "fabricante"), ("Nº de série", "numero_serie"),
                          ("Setor", "setor")):
        historia.append(Paragraph(f"<b>{rotulo}:</b> {_texto(inst.get(campo))}", normal))

    historia.append(Paragraph("2. Padrão utilizado", secao))
    historia.append(Paragraph(
        f"*{padrao['descricao']} {padrao['codigo']} - {padrao['fabricante']}", normal))
    historia.append(Paragraph(
        f"Certificado de Calibração n° {padrao['certificado_externo']} - "
        f"{padrao['executante']}; de {padrao['data_ultima_calibracao']} - "
        f"Próxima Calibração: {padrao['data_proxima_calibracao']}", normal))

    historia.append(Paragraph("3. Procedimento de calibração", secao))
    historia.append(Paragraph(f"<b>Nr. do procedimento / revisão:</b> "
                              f"{lab.get('procedimento', '—')}", normal))
    historia.append(Paragraph(TEXTO_PROCEDIMENTO.get(padrao.get("tipo", "MMC"),
                                                     TEXTO_PROCEDIMENTO["MMC"]), normal))
    historia.append(Paragraph(
        "Os resultados estão referenciados a temperatura de 20° Celsius. Temperatura "
        f"ambiente na medição: {_texto(valores.get('temperatura_ambiente'))} °C.", normal))

    historia.append(Paragraph("4. Resultados (mm)", secao))
    linhas = [["Parâmetro avaliado", "Valor nominal", "Tol. +", "Tol. -",
               "Valor obtido", "Erro", "Avaliação"]]
    for r in valores["resultados"]:
        linhas.append([r["nome"], _texto(r["valor_nominal"]), _texto(r["tolerancia_superior"]),
                       _texto(r["tolerancia_inferior"]), _texto(r["media"]), _texto(r["erro"]),
                       "Conforme" if r["situacao"] == "CONFORME" else "Não conforme"])
    tabela = Table(linhas, repeatRows=1,
                   colWidths=[46 * mm, 22 * mm, 16 * mm, 16 * mm, 24 * mm, 22 * mm, 28 * mm])
    estilo = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
        ("ALIGN", (1, 1), (-2, -1), "RIGHT"),
    ]
    for i, r in enumerate(valores["resultados"], start=1):
        if r["situacao"] != "CONFORME":
            estilo.append(("TEXTCOLOR", (-1, i), (-1, i), colors.HexColor("#b00020")))
    tabela.setStyle(TableStyle(estilo))
    historia.append(tabela)

    historia.append(Paragraph("5. Incerteza de medição", secao))
    historia.append(Paragraph(
        f"<b>U = {_texto(inc['incerteza_expandida_mm'])} mm</b> &nbsp;&nbsp; k = "
        f"{_texto(inc['k'])} &nbsp;&nbsp; veff = {inc['veff']} &nbsp;&nbsp; "
        "(Máquina de medição por coordenadas)", normal))

    historia.append(Paragraph("6. Observações", secao))
    resumo = valores["resumo"]
    if resumo["nao_conformes"]:
        historia.append(Paragraph(
            f"{resumo['nao_conformes']} de {resumo['total']} características fora da "
            "tolerância considerando a incerteza como banda de guarda: "
            + ", ".join(resumo["caracteristicas_nao_conformes"]) + ".", normal))
    else:
        historia.append(Paragraph("Todas as características dentro da tolerância, "
                                  "considerando a incerteza como banda de guarda.", normal))

    historia.append(Spacer(1, 4 * mm))
    historia.append(Table([[
        Paragraph(f"<b>Técnico executante:</b><br/>{valores['tecnico_executante']}", normal),
        Paragraph(f"______________________________<br/>{valores['signatario']['nome']}<br/>"
                  "Signatário Autorizado", normal),
    ]], colWidths=[87 * mm, 87 * mm]))

    historia.append(Paragraph("Notas:", secao))
    historia.append(Paragraph(NOTA_INCERTEZA.format(k=_texto(inc["k"]), veff=inc["veff"]), pequeno))
    for nota in NOTAS_FIXAS:
        historia.append(Paragraph(nota, pequeno))

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 10 * mm,
                          f"Certificado {valores['numero_exibicao']} · versão "
                          f"{valores.get('versao', 1)} · verificação {verificacao[:16]}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Folha {doc.page:02d}")
        if lab.get("rodape"):
            canvas.drawString(18 * mm, 6.5 * mm, lab["rodape"])
        canvas.restoreState()

    documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()

