"""
Avaliacao de conformidade com banda de guarda (RN02) e resumo (RF06).

RN02: a caracteristica e REPROVADA quando a media das medicoes, somada ou
subtraida da incerteza expandida U, ultrapassa os limites de tolerancia.
Replica as colunas L/M da aba Registro, com uma correcao: a coluna M da
planilha compara com (nominal - Tol.-), e como Tol.- ja vem negativo (-0,01)
o limite inferior fica acima do nominal e marca "Rep" em todo diametro. Aqui o
limite inferior e nominal - |Tol.-|, que e o que a regra descreve.

O U usado e o mesmo do certificado: um valor por calibracao, em mm, ja
arredondado (Registro!D66).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

CONFORME = "CONFORME"
NAO_CONFORME = "NAO_CONFORME"

# Motivo da reprovacao, para o revisor entender o resultado
FORA_DA_TOLERANCIA = "FORA_DA_TOLERANCIA"        # a propria media esta fora
FORA_PELA_BANDA_DE_GUARDA = "FORA_PELA_BANDA_DE_GUARDA"  # media dentro, media +- U fora


@dataclass(frozen=True)
class Avaliacao:
    nome: str
    valor_nominal: Decimal
    tolerancia_superior: Decimal
    tolerancia_inferior: Decimal
    media: Decimal
    erro: Decimal
    limite_inferior: Decimal
    limite_superior: Decimal
    situacao: str
    motivo: str | None

    def como_item(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class Parecer:
    avaliacoes: tuple[Avaliacao, ...]
    incerteza_mm: Decimal

    @property
    def nao_conformes(self) -> list[Avaliacao]:
        return [a for a in self.avaliacoes if a.situacao == NAO_CONFORME]

    @property
    def situacao(self) -> str:
        return NAO_CONFORME if self.nao_conformes else CONFORME

    def resumo(self) -> dict:
        """RF06: contagem e lista das nao conformidades, sem checar linha a linha."""
        return {
            "situacao": self.situacao,
            "total": len(self.avaliacoes),
            "nao_conformes": len(self.nao_conformes),
            "caracteristicas_nao_conformes": [a.nome for a in self.nao_conformes],
        }


def avaliar(nome: str, nominal: Decimal, tol_sup: Decimal, tol_inf: Decimal,
            p1: Decimal, p2: Decimal, incerteza_mm: Decimal) -> Avaliacao:
    media = (p1 + p2) / 2
    limite_superior = nominal + abs(tol_sup)
    limite_inferior = nominal - abs(tol_inf)
    if media > limite_superior or media < limite_inferior:
        situacao, motivo = NAO_CONFORME, FORA_DA_TOLERANCIA
    elif media + incerteza_mm > limite_superior or media - incerteza_mm < limite_inferior:
        situacao, motivo = NAO_CONFORME, FORA_PELA_BANDA_DE_GUARDA
    else:
        situacao, motivo = CONFORME, None
    return Avaliacao(nome, nominal, tol_sup, tol_inf, media, media - nominal,
                     limite_inferior, limite_superior, situacao, motivo)


def avaliar_calibracao(caracteristicas: Iterable[dict], incerteza_mm: Decimal) -> Parecer:
    """caracteristicas: itens com os campos de calypso.Caracteristica."""
    avaliacoes = tuple(
        avaliar(c["nome"], c["valor_nominal"], c["tolerancia_superior"],
                c["tolerancia_inferior"], c["medicao_p1"], c["medicao_p2"], incerteza_mm)
        for c in caracteristicas
    )
    return Parecer(avaliacoes, incerteza_mm)
