"""Erros de regra de negocio, com o status HTTP que a fn-api devolve."""
from __future__ import annotations


class ErroDeNegocio(Exception):
    def __init__(self, mensagem: str, status: int = 422, detalhes=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.detalhes = detalhes

    def como_dict(self) -> dict:
        corpo = {"erro": self.mensagem, "status": self.status}
        if self.detalhes is not None:
            corpo["detalhes"] = self.detalhes
        return corpo


class NaoEncontradoError(ErroDeNegocio):
    def __init__(self, mensagem: str):
        super().__init__(mensagem, 404)
