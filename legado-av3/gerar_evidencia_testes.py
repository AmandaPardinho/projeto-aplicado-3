"""
Gera dois PDFs de evidencia de testes para anexar ao trabalho (AV3):

    evidencias/Evidencia_Testes_1_execucao_correta.pdf
        Execucao real da suite de testes sobre o codigo do repositorio (tudo passa).

    evidencias/Evidencia_Testes_2_execucao_com_falha.pdf
        Execucao SIMULADA de falha: o script copia o projeto para uma pasta
        temporaria, introduz de proposito um defeito na regra de tolerancia
        (apenas na copia) e roda os testes e o gerar_relatorio.py nessa copia,
        mostrando que os testes detectam o defeito e que a geracao do relatorio
        e abortada. O codigo do repositorio nao e alterado.

Uso:
    python3 gerar_evidencia_testes.py
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle,
)

PASTA = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(PASTA, "evidencias")
SAIDA_OK = os.path.join(EVID, "Evidencia_Testes_1_execucao_correta.pdf")
SAIDA_FALHA = os.path.join(EVID, "Evidencia_Testes_2_execucao_com_falha.pdf")

AZUL = colors.HexColor("#0a4f8f")
VERDE = colors.HexColor("#1b7a3a")
VERMELHO = colors.HexColor("#b3261e")
CINZA = colors.HexColor("#f2f2f2")

# defeito introduzido APENAS na copia temporaria: a comparacao com a tolerancia
# passa a aceitar qualquer erro (aprova pontos fora da tolerancia).
DEFEITO_ORIGINAL = "dentro = self.tol_menos <= self.erro_sistematico <= self.tol_mais"
DEFEITO_INJETADO = "dentro = True  # DEFEITO SIMULADO: ignora a tolerancia"

styles = getSampleStyleSheet()
corpo = ParagraphStyle("Corpo", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14)
h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=13, textColor=AZUL,
                    spaceBefore=12, spaceAfter=6)
mono = ParagraphStyle("Mono", parent=styles["Normal"], fontName="Courier", fontSize=7.4, leading=9.2)


def titulo_doc(texto, cor):
    return Paragraph(texto, ParagraphStyle("T", parent=styles["Title"], fontName="Helvetica-Bold",
                                           fontSize=17, leading=21, textColor=cor, alignment=0))


def rodar(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def pytest_cmd():
    return [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "--color=no"]


def info_git():
    _, h, _ = rodar(["git", "rev-parse", "--short", "HEAD"], PASTA)
    _, st, _ = rodar(["git", "status", "--porcelain"], PASTA)
    return h.strip() or "n/d", ("com alteracoes nao commitadas" if st.strip() else "arvore limpa")


def tabela_contexto(linhas):
    t = Table([[Paragraph(f"<b>{escape(k)}</b>", corpo), Paragraph(escape(v), corpo)] for k, v in linhas],
              colWidths=[4.2 * cm, 12.4 * cm])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, CINZA]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def bloco(texto):
    """Saida de terminal em fonte monoespacada, com quebra automatica de pagina."""
    linhas = []
    for ln in (texto.strip() or "(vazia)").splitlines():
        while len(ln) > 118:
            linhas.append(ln[:118])
            ln = "    " + ln[118:]
        linhas.append(ln)
    return Preformatted("\n".join(linhas), mono, dedent=0)


def selo(texto, cor):
    t = Table([[Paragraph(f"<font color='white'><b>{escape(texto)}</b></font>",
                          ParagraphStyle("S", parent=corpo, fontSize=11, alignment=1))]], colWidths=[16.6 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), cor),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def construir(caminho, story, titulo):
    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=2.0 * cm, bottomMargin=2.0 * cm, title=titulo,
                            author="Grupo 4 - Projeto Aplicado III")
    doc.build(story)


def contexto_comum():
    commit, estado = info_git()
    return [
        ("Projeto", "Projeto Aplicado III - Grupo 4 - Schulz S.A. (MVP AV3)"),
        ("Data/hora da execucao", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        ("Commit do codigo", f"{commit} ({estado})"),
        ("Ambiente", f"Python {platform.python_version()} em {platform.system()} {platform.release()}"),
        ("Repositorio", "https://github.com/AmandaPardinho/projeto-aplicado-3"),
    ]


# ---------------------------------------------------------------- 1. execucao correta
def gerar_correta():
    codigo, saida, erro = rodar(pytest_cmd(), PASTA)
    if codigo != 0:
        sys.exit("A suite real de testes falhou; evidencia 'correta' nao gerada:\n" + saida + erro)
    passou = [l for l in saida.splitlines() if " PASSED" in l]
    story = [
        titulo_doc("Evidencia de testes automatizados<br/>Execucao correta", VERDE),
        HRFlowable(width="100%", color=AZUL, thickness=1.2),
        Spacer(1, 8),
        tabela_contexto(contexto_comum() + [("Comando", "python -m pytest -v")]),
        Spacer(1, 10),
        selo(f"RESULTADO: {len(passou)} TESTES PASSARAM - NENHUMA FALHA", VERDE),
        Paragraph("O que foi verificado", h1),
        Paragraph(
            "A suite cobre o calculo metrologico (media, erro sistematico, comparacao com a tolerancia e parecer "
            "final), o tratamento de planilhas invalidas (sem cabecalho, arquivo corrompido, linha com campo "
            "ausente ou nao numerico) e as rotas de upload da aplicacao web. Esta saida e a de uma execucao real, "
            "feita sobre o codigo do repositorio no momento da geracao deste documento.", corpo),
        Paragraph("Saida completa do pytest", h1),
        bloco(saida),
    ]
    construir(SAIDA_OK, story, "Evidencia de testes - execucao correta")
    print("PDF gerado:", SAIDA_OK)


# ---------------------------------------------------------------- 2. execucao com falha
def gerar_com_falha():
    tmp = tempfile.mkdtemp(prefix="evidencia_falha_")
    try:
        copia = os.path.join(tmp, "projeto")
        shutil.copytree(PASTA, copia, ignore=shutil.ignore_patterns(
            ".venv", "venv", ".git", "__pycache__", ".pytest_cache", "uploads", "*.pdf"))
        os.makedirs(os.path.join(copia, "uploads"), exist_ok=True)
        calculo = os.path.join(copia, "calculo.py")
        fonte = open(calculo, encoding="utf-8").read()
        if DEFEITO_ORIGINAL not in fonte:
            sys.exit("Trecho esperado nao encontrado em calculo.py; ajuste DEFEITO_ORIGINAL.")
        open(calculo, "w", encoding="utf-8").write(fonte.replace(DEFEITO_ORIGINAL, DEFEITO_INJETADO))

        cod_t, saida_t, erro_t = rodar(pytest_cmd() + ["--tb=short"], copia)
        assert cod_t != 0, "o defeito simulado deveria derrubar ao menos um teste"
        falhas = [l for l in saida_t.splitlines() if " FAILED" in l and "::" in l]
        passaram = [l for l in saida_t.splitlines() if " PASSED" in l]

        cod_g, saida_g, erro_g = rodar([sys.executable, "gerar_relatorio.py"], copia)
        pdf_gerado = os.path.exists(os.path.join(copia, "Entrega_AV3_Grupo4_MVP.pdf"))
        assert cod_g != 0 and not pdf_gerado, "o gerador deveria abortar sem criar o PDF"
        # o gerador imprime a mensagem de aborto em stderr (sys.exit com texto)
        mensagem_gerador = (saida_g + erro_g).strip()
        # a mensagem do gerador embute toda a saida do pytest; no PDF mostramos so o cabecalho dela
        cabecalho_gerador = mensagem_gerador.split("--- saida do pytest (stdout) ---")[0].strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    story = [
        titulo_doc("Evidencia de testes automatizados<br/>Execucao com falha (simulada)", VERMELHO),
        HRFlowable(width="100%", color=AZUL, thickness=1.2),
        Spacer(1, 8),
        tabela_contexto(contexto_comum() + [
            ("Natureza", "SIMULACAO CONTROLADA: o defeito foi introduzido de proposito, apenas em uma copia "
                         "temporaria do projeto. O codigo do repositorio nao foi alterado."),
            ("Defeito introduzido", f"calculo.py: '{DEFEITO_ORIGINAL}' foi trocado por "
                                    f"'{DEFEITO_INJETADO}'"),
            ("Comandos", "python -m pytest -v --tb=short ; python gerar_relatorio.py (ambos na copia)"),
        ]),
        Spacer(1, 10),
        selo(f"RESULTADO: {len(falhas)} TESTE(S) FALHARAM, {len(passaram)} PASSARAM - GERACAO DO PDF ABORTADA",
             VERMELHO),
        Paragraph("O que ocorreu", h1),
        Paragraph(
            "A regra que compara o erro sistematico com a tolerancia (+TOL / -TOL) foi desativada na copia, de "
            "modo que qualquer ponto passaria a ser considerado dentro da tolerancia. Esse e o tipo de defeito "
            "mais grave para o sistema, pois levaria a aprovar um instrumento fora da especificacao.", corpo),
        Paragraph("Por que falhou", h1),
        Paragraph(
            "Os testes que dependem da classificacao DENTRO/FORA da tolerancia deixaram de receber o resultado "
            "esperado (por exemplo, a planilha reprovada passou a ser APROVADA). Os testes que nao dependem "
            "dessa regra (rotas, planilhas invalidas, linhas incompletas) continuaram passando, o que ajuda a "
            "localizar o problema. Os testes que falharam:", corpo),
        Spacer(1, 4),
        bloco("\n".join(l.split(" FAILED")[0] for l in falhas)),
        Paragraph("Comportamento do gerador de relatorio", h1),
        Paragraph(
            "Ao detectar a falha, o gerar_relatorio.py aborta e NAO gera nem altera o PDF da entrega, para que o "
            "relatorio nunca registre como evidencia uma execucao que falhou. Mensagem exibida pelo script:", corpo),
        Spacer(1, 4),
        bloco(cabecalho_gerador),
        Spacer(1, 4),
        Paragraph(f"Verificacao: codigo de saida do gerar_relatorio.py = {cod_g} (diferente de zero); "
                  f"PDF criado pela execucao: {'sim' if pdf_gerado else 'nao'}.", corpo),
        Paragraph("Saida completa do pytest nesta execucao", h1),
        bloco(saida_t),
    ]
    construir(SAIDA_FALHA, story, "Evidencia de testes - execucao com falha (simulada)")
    print("PDF gerado:", SAIDA_FALHA)


if __name__ == "__main__":
    os.makedirs(EVID, exist_ok=True)
    gerar_correta()
    gerar_com_falha()
