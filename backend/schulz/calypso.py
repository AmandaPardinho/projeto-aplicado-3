"""
Leitura do relatorio bruto do Calypso (RF02) com o saneamento do Tema 01.

O arquivo de entrada e o "Calypso Measuring Result" exportado pela MMC Zeiss
(Registro_MMC.xlsx, aba Report), nao a pasta de calibracao preenchida a mao
pelo tecnico (aba Registro). Estrutura do Report:

    linhas 4-11   metadados: rotulo numa linha, valor na linha de baixo
                  (Measurement Plan, Date, Time, Metrologista, MMC...)
    linha 13      cabecalho: Characteristic | Actual | Nominal | Upper Tol |
                  Lower Tol | Deviation
    bloco 1       1a passagem de medicao, uma linha por caracteristica
    (linha vazia)
    bloco 2       2a passagem, mesmas caracteristicas na mesma ordem

Os passos seguem a ordem do ETL da AV2 (secao 3.1.2): estruturar, limpar,
tipar e validar. Toda regra bloqueante vira uma Violacao; o relatorio so e
devolvido se nao houver nenhuma. Regras corretivas (ex.: "20,4°" -> 20.4)
ficam registradas em `transformacoes`, com o valor antes e depois.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .xlsx import ArquivoIlegivelError, abrir_workbook

# RH01: marcadores que significam "campo vazio"
NULOS_TEXTUAIS = {"", "-", "--", "---", "----", "-----", "???", "00/00/0000"}

# RH16: erros de formula herdados do Excel
ERROS_DE_FORMULA = {"#VALUE!", "#REF!", "#N/A", "#NAME?", "#DIV/0!", "#NUM!", "#NULL!"}

# RH12: abas com formulas quebradas, nunca lidas
ABAS_IGNORADAS = {"vik", "kvi"}

# Cabecalhos aceitos (normalizados: minusculo, sem acento). O Calypso exporta
# em ingles; os sinonimos em portugues cobrem a aba Registro e variacoes.
SINONIMOS_CABECALHO = {
    "nome": {"characteristic", "caracteristica", "parametro avaliado", "dimension"},
    "medido": {"actual", "medido", "valor medido", "valor obtido"},
    "nominal": {"nominal", "valor nominal"},
    "tol_sup": {"upper tol", "tol +", "tol+", "+tol", "tolerancia superior"},
    "tol_inf": {"lower tol", "tol -", "tol-", "-tol", "tolerancia inferior"},
}
COLUNAS_OBRIGATORIAS = ("nome", "medido", "nominal", "tol_sup", "tol_inf")

# Rotulos de metadados do Report (rotulo numa celula, valor logo abaixo)
ROTULOS_METADADOS = {
    "measurement plan": "plano",
    "plano de medicao": "plano",
    "date": "data",
    "data": "data",
    "time": "hora",
    "hora": "hora",
    "order": "ordem",
    "drawing no.": "desenho",
    "part no.": "peca",
    "metrologista": "metrologista",
    "mmc": "codigo_mmc",
    "fornecedor": "fornecedor",
}

# RH15: "62P_DIAMETRO 1" -> cota "62P", grandeza "DIAMETRO 1"
PADRAO_COTA = re.compile(r"^(\d+P)_(.+)$", re.IGNORECASE)
CARACTERES_DE_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EPOCA_EXCEL = datetime(1899, 12, 30)
LINHAS_DE_BUSCA_DO_CABECALHO = 60


@dataclass
class Violacao:
    regra: str
    mensagem: str
    celula: Optional[str] = None
    valor_bruto: Optional[str] = None

    def como_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class RelatorioInvalidoError(ValueError):
    """Uma ou mais regras bloqueantes falharam; o arquivo vai para quarentena."""

    def __init__(self, violacoes: list[Violacao]):
        self.violacoes = violacoes
        resumo = "; ".join(f"{v.regra}: {v.mensagem}" for v in violacoes[:3])
        super().__init__(resumo)


@dataclass
class Caracteristica:
    nome: str
    cota_desenho: Optional[str]
    grandeza: str
    valor_nominal: Decimal
    tolerancia_superior: Decimal
    tolerancia_inferior: Decimal
    medicao_p1: Decimal
    medicao_p2: Decimal
    celula_p1: str
    celula_p2: str

    def como_item(self) -> dict:
        return dict(self.__dict__)


@dataclass
class RelatorioCalypso:
    plano: Optional[str]
    data_hora: Optional[datetime]
    metrologista: Optional[str]
    codigo_mmc: Optional[str]
    fornecedor: Optional[str]
    ordem: Optional[str]
    peca: Optional[str]
    caracteristicas: list[Caracteristica]
    transformacoes: list[dict] = field(default_factory=list)

    @property
    def tag_do_plano(self) -> Optional[str]:
        """TAG embutido no nome do plano ("703.1208_TESTE" -> "703.1208")."""
        if not self.plano:
            return None
        m = re.match(r"^(\d+(?:\.\d+)+)", self.plano)
        return m.group(1) if m else None


def normalizar(texto: Any) -> str:
    """Minusculo, sem acento e com espacos simples, para comparar rotulos."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


class _Leitor:
    """Acumula violacoes e transformacoes enquanto le as celulas."""

    def __init__(self) -> None:
        self.violacoes: list[Violacao] = []
        self.transformacoes: list[dict] = []

    def violar(self, regra: str, mensagem: str, celula: str = None, bruto: Any = None) -> None:
        self.violacoes.append(Violacao(regra, mensagem, celula,
                                       None if bruto is None else str(bruto)))

    def transformar(self, regra: str, celula: str, antes: Any, depois: Any) -> None:
        self.transformacoes.append({"regra": regra, "celula": celula,
                                    "antes": str(antes), "depois": str(depois)})

    def texto(self, valor: Any, celula: str) -> Optional[str]:
        """RH05 + RH04 + RH01 + RH16 para um campo de texto."""
        if valor is None:
            return None
        if not isinstance(valor, str):
            return str(valor)
        limpo = CARACTERES_DE_CONTROLE.sub("", valor).strip()
        if limpo in ERROS_DE_FORMULA:
            self.violar("RH16", "erro de formula herdado", celula, valor)
            return None
        if limpo in NULOS_TEXTUAIS:
            if valor != "":
                self.transformar("RH01", celula, valor, None)
            return None
        if limpo != valor:
            self.transformar("RH04", celula, valor, limpo)
        return limpo

    def decimal(self, valor: Any, celula: str) -> Optional[Decimal]:
        """Converte para Decimal exato (RNF10), removendo unidades (RH13)."""
        if valor is None or isinstance(valor, bool):
            return None
        if isinstance(valor, (int, float)):
            # repr() do float devolve a menor representacao que volta ao mesmo
            # numero: 0.002167 continua 0.002167, sem o ruido binario
            return Decimal(repr(valor)) if isinstance(valor, float) else Decimal(valor)
        texto = self.texto(valor, celula)
        if texto is None:
            return None
        numero = re.sub(r"[^0-9,.\-+eE]", "", texto)
        if "," in numero:
            numero = numero.replace(".", "").replace(",", ".")
        try:
            resultado = Decimal(numero)
        except InvalidOperation:
            self.violar("RH13", "valor numerico invalido", celula, valor)
            return None
        if numero != texto:
            self.transformar("RH13", celula, valor, resultado)
        return resultado

    def data(self, valor: Any, celula: str) -> Optional[date]:
        """RH02/RH03/RH14: datas em qualquer das quatro formas vistas na Schulz."""
        if isinstance(valor, datetime):
            return valor.replace(microsecond=0)
        if isinstance(valor, date):
            return valor
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            convertido = (EPOCA_EXCEL + timedelta(days=float(valor))).replace(microsecond=0)
            self.transformar("RH03", celula, valor, convertido.isoformat())
            return convertido
        texto = self.texto(valor, celula)
        if texto is None:
            return None
        # RH14: corta a fracao de segundo espuria ("16:47:10.0000000046")
        cortado = re.sub(r"(\d{2}:\d{2}:\d{2})\.\d+", r"\1", texto)
        for formato in (None, "%d/%m/%Y", "%d/%m/%Y %H:%M:%S"):
            try:
                convertido = (datetime.fromisoformat(cortado) if formato is None
                              else datetime.strptime(cortado, formato))
            except ValueError:
                continue
            self.transformar("RH14", celula, valor, convertido.isoformat())
            return convertido
        self.violar("RH03", "data invalida", celula, valor)
        return None

    def hora(self, valor: Any, celula: str) -> Optional[time]:
        if isinstance(valor, time):
            return valor.replace(microsecond=0)
        if isinstance(valor, datetime):
            return valor.time().replace(microsecond=0)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            segundos = round(float(valor) * 86400) % 86400
            convertido = time(segundos // 3600, segundos % 3600 // 60, segundos % 60)
            self.transformar("RH03", celula, valor, convertido.isoformat())
            return convertido
        texto = self.texto(valor, celula)
        if texto is None:
            return None
        cortado = re.sub(r"(\d{2}:\d{2}:\d{2})\.\d+", r"\1", texto)
        try:
            convertido = time.fromisoformat(cortado)
        except ValueError:
            self.violar("RH14", "hora invalida", celula, valor)
            return None
        if cortado != texto:
            self.transformar("RH14", celula, valor, convertido.isoformat())
        return convertido


def _escolher_aba(workbook):
    """Aba Report pelo nome; senao, a primeira que tiver o titulo do Calypso."""
    candidatas = [ws for ws in workbook.worksheets if normalizar(ws.title) not in ABAS_IGNORADAS]
    for ws in candidatas:
        if normalizar(ws.title) == "report":
            return ws
    for ws in candidatas:
        for linha in ws.iter_rows(max_row=5, values_only=True):
            if any(normalizar(v) == "calypso measuring result" for v in linha):
                return ws
    return None


def _localizar_cabecalho(ws) -> tuple[Optional[int], dict[str, int]]:
    for linha in ws.iter_rows(max_row=LINHAS_DE_BUSCA_DO_CABECALHO):
        colunas: dict[str, int] = {}
        for celula in linha:
            rotulo = normalizar(celula.value)
            for campo, sinonimos in SINONIMOS_CABECALHO.items():
                if rotulo in sinonimos and campo not in colunas:
                    colunas[campo] = celula.column
        if "nome" in colunas and "medido" in colunas:
            return linha[0].row, colunas
    return None, {}


def _ler_metadados(ws, linha_cabecalho: int, leitor: _Leitor) -> dict:
    meta: dict[str, Any] = {}
    for linha in ws.iter_rows(max_row=linha_cabecalho - 1):
        for celula in linha:
            campo = ROTULOS_METADADOS.get(normalizar(celula.value))
            if campo is None or campo in meta:
                continue
            abaixo = ws.cell(row=celula.row + 1, column=celula.column)
            meta[campo] = (abaixo.value, abaixo.coordinate)

    def pegar(campo, conversor):
        valor, coord = meta.get(campo, (None, None))
        return conversor(valor, coord) if coord else None

    data = pegar("data", leitor.data)
    hora = pegar("hora", leitor.hora)
    data_hora = None
    if data is not None:
        data_hora = datetime.combine(data if not isinstance(data, datetime) else data.date(),
                                     hora or (data.time() if isinstance(data, datetime) else time()))
    return {
        "plano": pegar("plano", leitor.texto),
        "data_hora": data_hora,
        "metrologista": pegar("metrologista", leitor.texto),
        "codigo_mmc": pegar("codigo_mmc", leitor.texto),
        "fornecedor": pegar("fornecedor", leitor.texto),
        "ordem": pegar("ordem", leitor.texto),
        "peca": pegar("peca", leitor.texto),
    }


def _ler_blocos(ws, linha_cabecalho: int, colunas: dict, leitor: _Leitor) -> list[list[dict]]:
    """Separa as passagens: cada sequencia de linhas com nome e um bloco (RH09)."""
    blocos: list[list[dict]] = []
    atual: list[dict] = []
    for numero in range(linha_cabecalho + 1, ws.max_row + 1):
        def celula(campo):
            return ws.cell(row=numero, column=colunas[campo])

        nome = leitor.texto(celula("nome").value, celula("nome").coordinate)
        if nome is None:
            if atual:
                blocos.append(atual)
                atual = []
            continue
        linha = {"nome": nome, "linha": numero}
        for campo in ("medido", "nominal", "tol_sup", "tol_inf"):
            c = celula(campo)
            linha[campo] = leitor.decimal(c.value, c.coordinate)
            linha[f"celula_{campo}"] = c.coordinate
        atual.append(linha)
    if atual:
        blocos.append(atual)
    return blocos


def _montar_caracteristicas(blocos: list[list[dict]], leitor: _Leitor) -> list[Caracteristica]:
    # RN01: exatamente duas passagens
    if len(blocos) != 2:
        leitor.violar("RN01", f"o relatorio deve ter 2 passagens de medicao; tem {len(blocos)}")
        return []
    p1, p2 = blocos
    for bloco, passagem in ((p1, 1), (p2, 2)):
        vistos = set()
        for linha in bloco:
            # RH17: chave (calibracao, caracteristica, passagem) unica
            if linha["nome"] in vistos:
                leitor.violar("RH17", f"caracteristica repetida na passagem {passagem}",
                              f"A{linha['linha']}", linha["nome"])
            vistos.add(linha["nome"])
    nomes_p1 = [l["nome"] for l in p1]
    nomes_p2 = [l["nome"] for l in p2]
    if set(nomes_p1) != set(nomes_p2):
        faltando = sorted(set(nomes_p1) ^ set(nomes_p2))
        leitor.violar("RN01", "caracteristicas sem as duas passagens: " + ", ".join(faltando))
        return []

    segunda = {l["nome"]: l for l in p2}
    caracteristicas = []
    for l1 in p1:
        l2 = segunda[l1["nome"]]
        for campo, regra in (("medido", "RN01"), ("nominal", "RN08"),
                             ("tol_sup", "RN08"), ("tol_inf", "RN08")):
            for linha in (l1, l2):
                if linha[campo] is None:
                    leitor.violar(regra, f"campo obrigatorio vazio em {linha['nome']}",
                                  linha[f"celula_{campo}"])
        for campo in ("nominal", "tol_sup", "tol_inf"):
            if None not in (l1[campo], l2[campo]) and l1[campo] != l2[campo]:
                leitor.violar("RN01", f"{campo} diferente entre as passagens de {l1['nome']}",
                              l2[f"celula_{campo}"], l2[campo])
        if any(l[c] is None for l in (l1, l2) for c in ("medido", "nominal", "tol_sup", "tol_inf")):
            continue
        m = PADRAO_COTA.match(l1["nome"])
        caracteristicas.append(Caracteristica(
            nome=l1["nome"],
            cota_desenho=m.group(1).upper() if m else None,
            grandeza=m.group(2) if m else l1["nome"],
            valor_nominal=l1["nominal"],
            tolerancia_superior=l1["tol_sup"],
            tolerancia_inferior=l1["tol_inf"],
            medicao_p1=l1["medido"],
            medicao_p2=l2["medido"],
            celula_p1=l1["celula_medido"],
            celula_p2=l2["celula_medido"],
        ))
    return caracteristicas


def ler_relatorio(conteudo: bytes) -> RelatorioCalypso:
    """Le e saneia o relatorio do Calypso. Levanta RelatorioInvalidoError."""
    leitor = _Leitor()
    try:
        workbook = abrir_workbook(conteudo)
    except ArquivoIlegivelError as exc:
        raise RelatorioInvalidoError([Violacao("RNF02", str(exc))]) from exc

    ws = _escolher_aba(workbook)
    if ws is None:
        raise RelatorioInvalidoError([Violacao("RF02", "aba Report do Calypso nao encontrada")])
    linha_cabecalho, colunas = _localizar_cabecalho(ws)
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if linha_cabecalho is None or faltando:
        raise RelatorioInvalidoError([Violacao(
            "RF02", "cabecalho do Report incompleto; faltam: " + ", ".join(faltando),
            f"linha {linha_cabecalho}" if linha_cabecalho else None)])

    meta = _ler_metadados(ws, linha_cabecalho, leitor)
    blocos = _ler_blocos(ws, linha_cabecalho, colunas, leitor)
    caracteristicas = _montar_caracteristicas(blocos, leitor)
    if not caracteristicas and not leitor.violacoes:
        leitor.violar("RF02", "nenhuma caracteristica encontrada no Report")
    if leitor.violacoes:
        raise RelatorioInvalidoError(leitor.violacoes)
    return RelatorioCalypso(caracteristicas=caracteristicas,
                            transformacoes=leitor.transformacoes, **meta)
