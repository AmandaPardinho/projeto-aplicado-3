"""
Incerteza de medicao pela metodologia GUM (RF03, RF04, RN03).

Replica o bloco "CONTROLE DIMENSIONAL - Volumetrico" da aba Incerteza, que e
o bloco usado no certificado quando o padrao e a MMC (Registro!C12 = 1):

    componente                       valor (um)            divisor   ci    vi
    dispersao das medidas (s)        max(desvio)*1000      raiz(n)   1     n-1
    incerteza da MMC - vol.          Padroes!C5            2         1     1000
    incerteza da esfera padrao       0,6                   2         1     1000
    repetitividade do apalpador      0,9                   raiz(3)   1     1000
    resolucao da maquina             0,1                   2*raiz(3) 1     1000
    erro sistematico da MMC - vol.   Padroes!B5            raiz(3)   1     1000
    dif. de temp. em relacao a 20 C  var_max*2e-6          raiz(18)  L*1000        1000
    dif. de temp. padrao x objeto    dif (C)               raiz(3)   L*alfa*0,001  1000

    uc   = raiz(soma ui^2)
    Veff = INT(uc^4 / soma(ui^4 / vi))       (Welch-Satterthwaite)
    k    = tabela de cobertura por faixa de Veff (t-Student, ~95%)
    U    = k * uc

onde L e o maior valor nominal absoluto entre as caracteristicas (mm) e o
desvio de cada caracteristica e o desvio padrao amostral das duas passagens.
Os valores fixos (esfera, apalpador, resolucao, temperaturas) ficam no cadastro
do padrao, nao no codigo, para a Schulz poder atualiza-los (UC03).

Calculo todo em Decimal (RNF10). Caso de aceite: 703.1208 -> uc = 0,9313 um,
Veff = 12, k = 2,23, U = 2,0769 um, impresso como 0,002 mm (RF03).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Iterable, Sequence

getcontext().prec = 28

DOIS = Decimal(2)
TRES = Decimal(3)
MIL = Decimal(1000)
GRAUS_DE_LIBERDADE_TIPO_B = Decimal(1000)

# Tabela de cobertura das formulas da aba Incerteza (celulas E60:E63).
# Cada par e (limite superior exclusivo de Veff, k).
TABELA_K = (
    (2, "13.97"), (3, "4.53"), (4, "3.31"), (5, "2.87"), (6, "2.65"), (7, "2.52"),
    (8, "2.43"), (10, "2.37"), (12, "2.28"), (14, "2.23"), (16, "2.2"), (18, "2.17"),
    (20, "2.15"), (25, "2.13"), (30, "2.11"), (35, "2.09"), (40, "2.07"), (50, "2.06"),
    (60, "2.05"), (80, "2.04"), (100, "2.03"),
)


@dataclass(frozen=True)
class ParametrosMMC:
    """Valores do orcamento que vem do cadastro do padrao (Padroes / Incerteza)."""
    incerteza_mmc_um: Decimal          # Padroes!C5
    erro_sistematico_mmc_um: Decimal   # Padroes!B5
    incerteza_esfera_um: Decimal = Decimal("0.6")
    repetitividade_apalpador_um: Decimal = Decimal("0.9")
    resolucao_um: Decimal = Decimal("0.1")
    alfa_objeto: Decimal = Decimal("11.5")           # 10^-6 / C
    variacao_temperatura_20c: Decimal = Decimal("1")  # C
    diferenca_temperatura_padrao_objeto: Decimal = Decimal("0.5")  # C

    @classmethod
    def de_item(cls, item: dict) -> "ParametrosMMC":
        campos = cls.__dataclass_fields__
        return cls(**{k: Decimal(str(v)) for k, v in item.items() if k in campos})


@dataclass(frozen=True)
class Componente:
    nome: str
    valor: Decimal
    divisor: Decimal
    distribuicao: str
    ci: Decimal
    vi: Decimal

    @property
    def u_xi(self) -> Decimal:
        return self.valor / self.divisor

    @property
    def ui(self) -> Decimal:
        return self.u_xi * self.ci


@dataclass(frozen=True)
class ResultadoIncerteza:
    componentes: tuple[Componente, ...]
    comprimento_avaliado_mm: Decimal
    incerteza_combinada_um: Decimal
    veff: int
    k: Decimal
    incerteza_expandida_um: Decimal

    @property
    def incerteza_expandida_mm(self) -> Decimal:
        """U arredondado a 3 casas em mm, como Registro!D66 e o certificado."""
        return (self.incerteza_expandida_um / MIL).quantize(Decimal("0.001"), ROUND_HALF_UP)

    def como_item(self) -> dict:
        return {
            "comprimento_avaliado_mm": self.comprimento_avaliado_mm,
            "incerteza_combinada_um": self.incerteza_combinada_um,
            "veff": self.veff,
            "k": self.k,
            "incerteza_expandida_um": self.incerteza_expandida_um,
            "incerteza_expandida_mm": self.incerteza_expandida_mm,
            "componentes": [
                {"nome": c.nome, "valor": c.valor, "divisor": c.divisor,
                 "distribuicao": c.distribuicao, "ci": c.ci, "vi": c.vi, "ui": c.ui}
                for c in self.componentes
            ],
        }


def desvio_padrao(valores: Sequence[Decimal]) -> Decimal:
    """Desvio padrao amostral (n-1), igual ao DESVPAD/STDEV do Excel."""
    n = len(valores)
    media = sum(valores) / n
    return (sum((v - media) ** 2 for v in valores) / (n - 1)).sqrt()


def fator_k(veff: int) -> Decimal:
    if veff > 100:
        return Decimal(2)
    if veff == 100:
        return Decimal("2.02")
    for limite, k in TABELA_K:
        if veff < limite:
            return Decimal(k)
    raise AssertionError("faixa de Veff nao coberta")  # inalcancavel


def calcular_volumetrico(medicoes: Iterable[tuple[Decimal, Decimal]],
                         nominais: Iterable[Decimal],
                         parametros: ParametrosMMC) -> ResultadoIncerteza:
    """Orcamento de incerteza do bloco volumetrico da MMC.

    medicoes: pares (passagem 1, passagem 2) de cada caracteristica, em mm.
    nominais: valores nominais das caracteristicas, em mm.
    """
    pares = list(medicoes)
    if not pares:
        raise ValueError("sem medicoes para calcular a incerteza")
    n = Decimal(len(pares[0]))
    dispersao_um = max(desvio_padrao(p) for p in pares) * MIL
    comprimento = max(abs(v) for v in nominais)
    p = parametros

    componentes = (
        Componente("Dispersao das medidas (s)", dispersao_um, n.sqrt(), "Normal",
                   Decimal(1), n - 1),
        Componente("Incerteza da MMC - vol.", p.incerteza_mmc_um, DOIS, "Normal",
                   Decimal(1), GRAUS_DE_LIBERDADE_TIPO_B),
        Componente("Incerteza da esfera padrao", p.incerteza_esfera_um, DOIS, "Normal",
                   Decimal(1), GRAUS_DE_LIBERDADE_TIPO_B),
        Componente("Repetitividade do apalpador", p.repetitividade_apalpador_um, TRES.sqrt(),
                   "Retangular", Decimal(1), GRAUS_DE_LIBERDADE_TIPO_B),
        Componente("Resolucao da maquina", p.resolucao_um, DOIS * TRES.sqrt(), "Retangular",
                   Decimal(1), GRAUS_DE_LIBERDADE_TIPO_B),
        Componente("Erro sistematico da MMC - vol.", p.erro_sistematico_mmc_um, TRES.sqrt(),
                   "Retangular", Decimal(1), GRAUS_DE_LIBERDADE_TIPO_B),
        Componente("Dif. de temp. em relacao a 20 C",
                   p.variacao_temperatura_20c * Decimal("0.000002"),
                   TRES.sqrt() * Decimal(6).sqrt(), "Retangular",
                   comprimento * MIL, GRAUS_DE_LIBERDADE_TIPO_B),
        Componente("Dif. de temp. entre padrao e objeto", p.diferenca_temperatura_padrao_objeto,
                   TRES.sqrt(), "Retangular", comprimento * p.alfa_objeto * Decimal("0.001"),
                   GRAUS_DE_LIBERDADE_TIPO_B),
    )

    uc = sum(c.ui ** 2 for c in componentes).sqrt()
    denominador = sum(c.ui ** 4 / c.vi for c in componentes)
    # Sem nenhuma contribuicao (caso teorico), Veff e infinito -> k = 2
    veff = int(uc ** 4 / denominador) if denominador else 10 ** 6
    k = fator_k(veff)
    return ResultadoIncerteza(
        componentes=componentes,
        comprimento_avaliado_mm=comprimento,
        incerteza_combinada_um=uc,
        veff=veff,
        k=k,
        incerteza_expandida_um=k * uc,
    )
