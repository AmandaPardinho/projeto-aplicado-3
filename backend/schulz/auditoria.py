"""
Trilha de auditoria AUD# (rastreabilidade de quem fez o que).

Toda acao registra um item, inclusive leituras: consulta de instrumento,
visualizacao de calibracao e download de certificado. Assim e possivel saber
quem viu o que, quando e por qual canal (teclado, leitor USB, camera, PWA).
O item nunca e alterado depois de gravado; a politica IAM da funcao so
permite PutItem em AUD# (AV2 4.1.3).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .repositorio import Repositorio, agora, iso, novo_id

CANAIS = {"teclado", "leitor", "camera", "pwa", "sistema"}


def item_auditoria(login: str, acao: str, alvo: str, canal: Optional[str] = None,
                   detalhes: Optional[dict] = None, quando: Optional[datetime] = None) -> dict:
    quando = quando or agora()
    item = {
        "PK": f"AUD#{quando:%Y-%m-%d}",
        "SK": f"{iso(quando)}#{novo_id()}",
        "tipo": "AUDITORIA",
        "quando": iso(quando),
        "usuario": login,
        "acao": acao,
        "alvo": alvo,
        "canal": canal if canal in CANAIS else "teclado" if canal else "sistema",
    }
    if detalhes:
        item["detalhes"] = detalhes
    return item


def registrar(repositorio: Repositorio, login: str, acao: str, alvo: str,
              canal: Optional[str] = None, detalhes: Optional[dict] = None) -> dict:
    item = item_auditoria(login, acao, alvo, canal, detalhes)
    repositorio.gravar(item)
    return item
