"""
Gera o PDF de entrega da Etapa 3 (AV3) - Construcao da Aplicacao
Transacional do MVP - Projeto Aplicado III, Grupo 4.

Uso:
    python3 gerar_relatorio.py
"""
import os
import re
import subprocess
import sys
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, HRFlowable, ListFlowable, ListItem,
)
from reportlab.lib.enums import TA_CENTER

from calculo import processar_planilha

PASTA = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(PASTA, "evidencias")
SAIDA = os.path.join(PASTA, "Entrega_AV3_Grupo4_MVP.pdf")
URL_REPOSITORIO = "https://github.com/AmandaPardinho/projeto-aplicado-3"

# ---------------------------------------------------------------- estilos
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="TituloCapa", parent=styles["Title"], fontSize=20, leading=24,
    spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="SubtituloCapa", parent=styles["Normal"], fontSize=12,
    alignment=TA_CENTER, textColor=colors.HexColor("#0a4f8f"), spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="H1", parent=styles["Heading1"], fontSize=15,
    textColor=colors.HexColor("#0a4f8f"), spaceBefore=14, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="H2", parent=styles["Heading2"], fontSize=12.5,
    textColor=colors.HexColor("#0a4f8f"), spaceBefore=10, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="CorpoJust", parent=styles["BodyText"], fontSize=10.3, leading=14.5,
    alignment=4, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="Legenda", parent=styles["Normal"], fontSize=9, leading=12,
    alignment=TA_CENTER, textColor=colors.HexColor("#555555"), spaceBefore=4,
    spaceAfter=10, fontName="Helvetica-Oblique",
))
styles.add(ParagraphStyle(
    name="Mono", parent=styles["Normal"], fontName="Courier", fontSize=8.3,
    leading=11, backColor=colors.HexColor("#f3f3f3"),
))

AZUL = colors.HexColor("#0a4f8f")
VERDE = colors.HexColor("#1e7e34")
VERMELHO = colors.HexColor("#b02a2a")
CINZA_CLARO = colors.HexColor("#f0f2f5")

story = []


def h1(texto):
    story.append(Paragraph(texto, styles["H1"]))


def h2(texto):
    story.append(Paragraph(texto, styles["H2"]))


def p(texto):
    story.append(Paragraph(texto, styles["CorpoJust"]))


def bullets(itens):
    story.append(ListFlowable(
        [ListItem(Paragraph(i, styles["CorpoJust"]), bulletColor=AZUL) for i in itens],
        bulletType="bullet", start="circle", leftIndent=14,
    ))
    story.append(Spacer(1, 6))


def imagem_com_legenda(caminho, legenda, largura=15.5 * cm):
    img = Image(caminho)
    razao = img.imageHeight / float(img.imageWidth)
    img.drawWidth = largura
    img.drawHeight = largura * razao
    story.append(img)
    story.append(Paragraph(legenda, styles["Legenda"]))


# ---------------------------------------------------------------- CAPA
story.append(Spacer(1, 4 * cm))
story.append(Paragraph("Projeto Aplicado III", styles["SubtituloCapa"]))
story.append(Paragraph(
    "Automacao da Emissao de Certificados de Calibracao",
    styles["TituloCapa"],
))
story.append(Spacer(1, 0.3 * cm))
story.append(Paragraph(
    "Etapa 3 (AV3) &mdash; Construcao da Aplicacao Transacional do MVP",
    styles["SubtituloCapa"],
))
story.append(Spacer(1, 1.2 * cm))
story.append(HRFlowable(width="60%", color=AZUL, thickness=1.2, hAlign="CENTER"))
story.append(Spacer(1, 1.2 * cm))

dados_capa = [
    ["Empresa parceira", "Schulz S.A."],
    ["Instituicao", "UniSENAI Florianopolis &mdash; Curso ADS"],
    ["Orientador", "Prof. MSc. Hugo Menezes Barra"],
    ["Grupo", "Grupo 4"],
    ["Integrantes", "Amanda Marques Pardinho<br/>"
                     "Daiane Olete da Silva Manicoba<br/>"
                     "Fabiola Reginaldo Correa da Silva<br/>"
                     "Lucas Correa Agostinho<br/>"
                     "Marta Sayuri Mukai"],
    ["Repositorio GitHub", f"<link href='{URL_REPOSITORIO}' color='#0a4f8f'>{URL_REPOSITORIO}</link>"],
]
tabela_capa = Table(
    [[Paragraph(f"<b>{k}</b>", styles["CorpoJust"]), Paragraph(v, styles["CorpoJust"])]
     for k, v in dados_capa],
    colWidths=[4.2 * cm, 11.3 * cm],
)
tabela_capa.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#dddddd")),
]))
story.append(tabela_capa)
story.append(PageBreak())

# ---------------------------------------------------------------- 1. VISAO GERAL
h1("1. Visao Geral da Entrega")
p("Esta entrega corresponde a Etapa 3 (AV3) do Projeto Aplicado III, cujo objetivo "
  "e a construcao de uma primeira versao transacional (MVP) da aplicacao que ira "
  "automatizar a emissao de certificados de calibracao para a Schulz S.A. O escopo "
  "desta etapa segue o roteiro de avaliacao fornecido pelo orientador e cobre o "
  "fluxo essencial do processo: ingestao da planilha de leituras exportada do "
  "software Calypso, aplicacao das regras metrologicas de comparacao com a "
  "tolerancia admissivel e apresentacao do parecer de conformidade ao usuario.")
p("A aplicacao foi desenvolvida em <b>Python</b>, utilizando o microframework web "
  "<b>Flask</b> para a camada de interface transacional e a biblioteca "
  "<b>openpyxl</b> para a leitura dos arquivos <font face='Courier'>.xlsx</font>. "
  "A escolha do openpyxl para a leitura das planilhas reaproveita diretamente a "
  "validacao de compatibilidade de formato (OOXML Strict) ja realizada no "
  "levantamento de requisitos do Tema 01.")
h2("1.1 Fluxo funcional implementado")
bullets([
    "O usuario acessa a tela inicial e faz o upload da planilha de leituras (.xlsx);",
    "A aplicacao le a planilha, localizando automaticamente o cabecalho e as colunas "
    "de interesse (dimensao avaliada, valor nominal, tolerancias e as duas medicoes);",
    "Para cada caracteristica avaliada, calcula a <b>media</b> das duas leituras e o "
    "<b>erro sistematico</b> (media menos o valor nominal);",
    "Compara o erro com o <b>Limite de Erro Admissivel</b> (a tolerancia "
    "superior/inferior informada na planilha; o erro e considerado dentro da tolerancia "
    "quando fica entre o limite inferior e o superior), classificando a caracteristica "
    "como <i>dentro</i> ou <i>fora</i> da tolerancia;",
    "Consolida um <b>parecer final</b> &mdash; APROVADO, se todas as caracteristicas "
    "estiverem dentro da tolerancia, ou REPROVADO, caso qualquer uma esteja fora;",
    "Se alguma caracteristica tiver campo numerico ausente ou invalido, a planilha e "
    "<b>recusada</b> com a indicacao das linhas a corrigir, em vez de gerar um parecer "
    "sobre dados parciais;",
    "Apresenta o resultado em uma tabela, destacando visualmente a(s) caracteristica(s) "
    "reprovada(s), para facilitar a leitura pelo responsavel pela calibracao.",
])
p("Por se tratar de um MVP incremental, esta entrega implementa deliberadamente o "
  "calculo simplificado de erro versus tolerancia descrito no roteiro da AV3, e "
  "<b>nao</b> o calculo completo de incerteza de medicao pela metodologia GUM "
  "(regra RN02 e requisitos RF03/RF04 do Tema 01). Essa decisao de escopo esta "
  "documentada na secao 5 deste relatorio e no README do projeto, e o calculo de "
  "incerteza esta planejado para a proxima etapa (MVP Parte 2).")

# ---------------------------------------------------------------- 2. LOGICA DE NEGOCIO
h1("2. Logica de Negocio Implementada")
p("A logica de calculo foi isolada em um modulo proprio "
  "(<font face='Courier'>calculo.py</font>), independente da camada web, o que "
  "permite testa-la de forma automatizada sem depender de um navegador. As regras "
  "abaixo foram herdadas diretamente do levantamento de requisitos do Tema 01:")

h2("2.1 Regras de negocio e calculos")
tabela_regras = Table([
    [Paragraph("<b>Regra implementada</b>", styles["CorpoJust"]),
     Paragraph("<b>Origem</b>", styles["CorpoJust"])],
    [Paragraph("Exigencia de exatamente duas medicoes por caracteristica", styles["CorpoJust"]),
     Paragraph("RN01 (Tema 01)", styles["CorpoJust"])],
    [Paragraph("Erro sistematico = media &minus; valor nominal", styles["CorpoJust"]),
     Paragraph("Secao de Regras de Negocio do roteiro da AV3", styles["CorpoJust"])],
    [Paragraph("Comparacao do erro com a tolerancia (+TOL / -TOL)", styles["CorpoJust"]),
     Paragraph("Equivalente simplificado da banda de guarda (RN02)", styles["CorpoJust"])],
    [Paragraph("Planilha com campo obrigatorio ausente ou invalido e recusada (nunca ignorada)", styles["CorpoJust"]),
     Paragraph("Decisao de projeto: parecer apenas sobre dados completos", styles["CorpoJust"])],
    [Paragraph("Parecer final APROVADO / REPROVADO", styles["CorpoJust"]),
     Paragraph("RF06 &mdash; resumo de nao conformidades", styles["CorpoJust"])],
    [Paragraph("Tratamento de nulos textuais, espacos e linhas vazias", styles["CorpoJust"]),
     Paragraph("RH01, RH04, RH09 (Tema 01)", styles["CorpoJust"])],
    [Paragraph("Uso do tipo Decimal (nao float) para precisao numerica", styles["CorpoJust"]),
     Paragraph("RNF10 (Tema 01)", styles["CorpoJust"])],
], colWidths=[9.3 * cm, 6.2 * cm])
tabela_regras.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), AZUL),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
]))
story.append(tabela_regras)
story.append(Spacer(1, 10))

h2("2.2 Deteccao flexivel do cabecalho da planilha")
p("Em vez de depender de posicoes fixas de celulas, o parser varre as primeiras "
  "linhas da planilha procurando por um dicionario de sinonimos para cada coluna "
  "esperada (por exemplo, 'DIMENSION' ou 'Parametro avaliado' para a caracteristica "
  "avaliada). Essa abordagem torna a aplicacao mais robusta a pequenas variacoes no "
  "layout de exportacao do Calypso, sem exigir alteracao de codigo.")

# ---------------------------------------------------------------- 3. EVIDENCIAS
h1("3. Evidencias de Funcionamento")
p("As capturas de tela abaixo foram obtidas a partir da execucao real da aplicacao "
  "(servidor Flask local, navegador automatizado), nao sendo mockups estaticos.")

h2("3.1 Tela de upload da planilha")
imagem_com_legenda(
    os.path.join(EVID, "01_tela_upload.png"),
    "Figura 1 &mdash; Tela inicial, com o formulario de envio da planilha de leituras.",
)

h2("3.2 Resultado &mdash; planilha aprovada")
p("Planilha de teste com as 8 caracteristicas avaliadas dentro da tolerancia "
  "admissivel, resultando no parecer <b>APROVADO</b>.")
imagem_com_legenda(
    os.path.join(EVID, "02_resultado_aprovado.png"),
    "Figura 2 &mdash; Resultado do processamento de uma planilha dentro dos padroes "
    "de conformidade.",
)
story.append(PageBreak())

h2("3.3 Resultado &mdash; planilha reprovada")
p("Mesma massa de dados, com uma medicao alterada propositalmente para ficar fora "
  "da tolerancia, validando o caminho de reprovacao e o destaque visual da linha "
  "nao conforme.")
imagem_com_legenda(
    os.path.join(EVID, "03_resultado_reprovado.png"),
    "Figura 3 &mdash; Resultado do processamento de uma planilha com uma "
    "caracteristica fora da tolerancia (parecer REPROVADO, linha destacada).",
)

# ---------------------------------------------------------------- 4. TESTES
h1("4. Testes Automatizados")
p("A logica de calculo foi validada por uma suite de testes automatizados "
  "(<font face='Courier'>pytest</font>), cobrindo o caso aprovado, o caso "
  "reprovado, a correcao aritmetica do calculo de media/erro e o tratamento de "
  "planilhas invalidas (sem cabecalho, arquivo corrompido, linha com campo "
  "ausente ou nao numerico) e as rotas de upload da aplicacao. A saida abaixo "
  "e a de uma execucao real, feita no momento da geracao deste relatorio.")

resultado_amostra = processar_planilha(os.path.join(PASTA, "sample_data", "amostra_aprovado.xlsx"))
primeira = resultado_amostra.caracteristicas[0]

execucao = subprocess.run(
    [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "--color=no"],
    cwd=PASTA, capture_output=True, text=True,
)
linhas_uteis = [
    re.sub(r"\s+", " ", ln).strip()
    for ln in execucao.stdout.splitlines()
    if "::" in ln or re.search(r"\b(passed|failed|error)\b", ln)
]
saida_testes = "\n".join(linhas_uteis)
if execucao.returncode != 0:
    sys.exit(
        "\n".join([
            "=" * 70,
            "GERACAO DO PDF ABORTADA: a suite de testes nao passou.",
            f"O pytest terminou com codigo {execucao.returncode} "
            "(1 = ha teste falhando; 2-5 = erro de execucao/coleta/configuracao).",
            "O relatorio nao pode registrar como evidencia uma execucao que falhou;",
            "corrija o problema abaixo e rode o script novamente. Nenhum PDF foi",
            "gerado nem alterado.",
            "=" * 70,
            "--- saida do pytest (stdout) ---",
            execucao.stdout.strip() or "(vazia)",
            "--- saida de erro (stderr) ---",
            execucao.stderr.strip() or "(vazia)",
        ])
    )

story.append(Paragraph(
    saida_testes.replace("\n", "<br/>"), styles["Mono"],
))
story.append(Spacer(1, 10))
p(f"Exemplo de calculo validado (caracteristica '{primeira.nome}'): "
  f"media = {primeira.media}, erro sistematico = {primeira.erro_sistematico}, "
  f"status = {primeira.status}.")

# ---------------------------------------------------------------- 5. ESCOPO
h1("5. Decisoes de Escopo e Proximos Passos")
p("Para manter esta entrega aderente ao que o roteiro da AV3 solicita (calculo de "
  "erro versus tolerancia e parecer de conformidade), optou-se por <b>nao</b> "
  "implementar ainda o calculo completo de incerteza de medicao pela metodologia "
  "GUM, previsto nos requisitos RF03/RF04 e na regra RN02 do Tema 01. Essa e uma "
  "simplificacao intencional desta etapa, e nao uma omissao.")
h2("5.1 Fora do escopo desta entrega")
bullets([
    "Calculo de incerteza de medicao pela metodologia GUM (RF03/RF04) &mdash; "
    "previsto para a etapa de MVP Parte 2;",
    "Geracao do certificado de calibracao em PDF (RF08) e persistencia em banco de dados;",
    "Autenticacao e perfis de acesso (RNF08).",
])
p("Observacao sobre o repositorio GitHub: o levantamento de requisitos do Tema 01 "
  "(RNF01) registra que a Schulz nao utiliza GitHub em sua operacao, preferindo a "
  "entrega via Docker/Zip. O roteiro desta etapa academica, no entanto, exige "
  "explicitamente um link de repositorio publico. Trata-se de uma distincao entre "
  "a necessidade da submissao academica (esta entrega) e a decisao de entrega em "
  "producao (RNF01), nao de uma contradicao a ser resolvida pela equipe.")

# ---------------------------------------------------------------- build
doc = SimpleDocTemplate(
    SAIDA, pagesize=A4,
    leftMargin=2.2 * cm, rightMargin=2.2 * cm,
    topMargin=2.0 * cm, bottomMargin=2.0 * cm,
    title="Entrega AV3 - Grupo 4 - MVP Schulz",
    author="Grupo 4 - Projeto Aplicado III",
)
doc.build(story)
print(f"PDF gerado em: {SAIDA}")
