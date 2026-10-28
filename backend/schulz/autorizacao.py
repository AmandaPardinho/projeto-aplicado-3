"""
Perfis do RNF08 como grupos do Cognito (AV2 4.1.1).

O API Gateway ja recusa requisicoes sem token valido; aqui a fn-api confere,
antes de cada acao, se algum grupo do usuario permite aquela acao. Toda
consulta exige login, inclusive a consulta de instrumento pelo QR Code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

TECNICO = "tecnico"
REVISOR = "revisor"
SIGNATARIO = "signatario"
ADMIN_PADRAO = "admin_padrao"
CONSULTA = "consulta"
AUDITOR = "auditor"
TODOS = frozenset({TECNICO, REVISOR, SIGNATARIO, ADMIN_PADRAO, CONSULTA, AUDITOR})

PERMISSOES = {
    "enviar_relatorio": {TECNICO},
    "ver_calibracoes": {TECNICO, REVISOR, SIGNATARIO, AUDITOR},
    "revisar_calibracao": {REVISOR, SIGNATARIO},
    "cancelar_calibracao": {REVISOR, SIGNATARIO},
    "emitir_certificado": {SIGNATARIO},
    "ver_padroes": set(TODOS),
    "atualizar_padrao": {ADMIN_PADRAO},
    "baixar_certificado": {REVISOR, SIGNATARIO, CONSULTA, AUDITOR},
    "consultar_instrumento": set(TODOS),
    "ver_auditoria": {AUDITOR},
}


class AcessoNegadoError(PermissionError):
    pass


@dataclass(frozen=True)
class Usuario:
    login: str
    grupos: frozenset = field(default_factory=frozenset)
    matricula: Optional[str] = None
    setor: Optional[str] = None

    def pode(self, acao: str) -> bool:
        return bool(self.grupos & PERMISSOES[acao])

    def exigir(self, acao: str) -> None:
        if not self.pode(acao):
            raise AcessoNegadoError(f"perfil sem permissao para {acao}")

    def eh_somente_tecnico(self) -> bool:
        """Tecnico sem outro perfil de leitura: ve so o que ele mesmo enviou."""
        return TECNICO in self.grupos and not self.grupos & {REVISOR, SIGNATARIO, AUDITOR}

    @property
    def permissoes(self) -> list[str]:
        return sorted(acao for acao in PERMISSOES if self.pode(acao))


def _ler_grupos(valor) -> frozenset:
    # O autorizador JWT do HTTP API entrega listas como texto: "[revisor signatario]"
    if valor is None:
        return frozenset()
    if isinstance(valor, str):
        valor = valor.strip("[]").replace(",", " ").split()
    return frozenset(g for g in valor if g in TODOS)


def usuario_do_evento(evento: dict) -> Usuario:
    claims = (evento.get("requestContext", {}).get("authorizer", {})
              .get("jwt", {}).get("claims"))
    if not claims:
        raise AcessoNegadoError("requisicao sem token")
    login = claims.get("cognito:username") or claims.get("username") or claims.get("sub")
    return Usuario(
        login=login,
        grupos=_ler_grupos(claims.get("cognito:groups")),
        matricula=claims.get("custom:matricula"),
        setor=claims.get("custom:setor"),
    )
