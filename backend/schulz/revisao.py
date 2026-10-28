"""
Revisao de uma calibracao (E6) e montagem dos valores do certificado (E7).

Junta as pecas: orcamento GUM (gum), banda de guarda (conformidade) e as
regras que bloqueiam a emissao:

    RN04  padrao com a proxima calibracao vencida
    RN06  caracteristica de angulo: o bloco de Angulo da planilha da Schulz
          esta quebrado (#NAME?), entao o sistema bloqueia com aviso
    RN08  campo cadastral obrigatorio do instrumento vazio ou sentinela

Uma calibracao NAO_CONFORME pode ser emitida: o certificado registra o
resultado da calibracao (o certificado real 00091/2026 da Schulz saiu com as
posicoes fora). A nao conformidade aparece na avaliacao e nas observacoes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from . import conformidade, gum
from .calypso import NULOS_TEXTUAIS, normalizar

CAMPOS_OBRIGATORIOS_INSTRUMENTO = ("tag", "codigo_interno", "denominacao", "fabricante")


@dataclass(frozen=True)
class Revisao:
    incerteza: gum.ResultadoIncerteza
    parecer: conformidade.Parecer
    bloqueios: tuple[str, ...]

    def como_dict(self) -> dict:
        return {
            "incerteza": self.incerteza.como_item(),
            "avaliacoes": [a.como_item() for a in self.parecer.avaliacoes],
            "resumo": self.parecer.resumo(),
            "bloqueios": list(self.bloqueios),
            "pode_emitir": not self.bloqueios,
        }


def data_br(valor: Optional[str]) -> str:
    """"2026-08-31" -> "31/08/2026"."""
    if not valor:
        return "—"
    return date.fromisoformat(valor[:10]).strftime("%d/%m/%Y")


def padrao_vencido(padrao: dict, hoje: date) -> bool:
    return date.fromisoformat(padrao["data_proxima_calibracao"]) < hoje


def campos_pendentes(instrumento: dict) -> list[str]:
    pendentes = []
    for campo in CAMPOS_OBRIGATORIOS_INSTRUMENTO:
        valor = instrumento.get(campo)
        if valor is None or str(valor).strip() in NULOS_TEXTUAIS:
            pendentes.append(campo)
    return pendentes


def revisar(calibracao: dict, padrao: dict, instrumento: dict, hoje: date) -> Revisao:
    caracteristicas = calibracao["caracteristicas"]
    incerteza = gum.calcular_volumetrico(
        [(c["medicao_p1"], c["medicao_p2"]) for c in caracteristicas],
        [c["valor_nominal"] for c in caracteristicas],
        gum.ParametrosMMC.de_item(padrao["orcamento"]),
    )
    parecer = conformidade.avaliar_calibracao(caracteristicas, incerteza.incerteza_expandida_mm)

    bloqueios = []
    if padrao_vencido(padrao, hoje):
        bloqueios.append(f"RN04: padrão {padrao['codigo']} com calibração vencida em "
                         f"{data_br(padrao['data_proxima_calibracao'])}")
    angulos = [c["nome"] for c in caracteristicas if "angulo" in normalizar(c["grandeza"])]
    if angulos:
        bloqueios.append("RN06: medição de ângulo ainda sem suporte (" + ", ".join(angulos) + ")")
    pendentes = campos_pendentes(instrumento)
    if pendentes:
        bloqueios.append("RN08: cadastro do instrumento incompleto: " + ", ".join(pendentes))
    return Revisao(incerteza, parecer, tuple(bloqueios))


def valores_do_certificado(numero: str, numero_exibicao: str, calibracao: dict,
                           instrumento: dict, padrao: dict, signatario: dict,
                           laboratorio: dict, revisao: Revisao, url_consulta: str,
                           emitido_em: str, marca_prova_de_conceito: bool) -> dict:
    """Copia congelada de tudo o que e impresso (AV2 3.2.1, RNF09)."""
    inc = revisao.incerteza
    return {
        "numero": numero,
        "numero_exibicao": numero_exibicao,
        "versao": 1,
        "emitido_em": emitido_em,
        "data_calibracao": data_br(calibracao.get("data_hora_medicao")),
        "temperatura_ambiente": calibracao.get("temperatura_ambiente"),
        "calibracao_id": calibracao["calibracao_id"],
        "instrumento": {campo: instrumento.get(campo) for campo in (
            "tag", "codigo_interno", "denominacao", "fabricante", "numero_serie",
            "setor", "solicitante")},
        "padrao": {
            "codigo": padrao["codigo"],
            "descricao": padrao["descricao"],
            "tipo": padrao.get("tipo", "MMC"),
            "fabricante": padrao["fabricante"],
            "certificado_externo": padrao["certificado_externo"],
            "executante": padrao["executante"],
            "data_ultima_calibracao": data_br(padrao["data_ultima_calibracao"]),
            "data_proxima_calibracao": data_br(padrao["data_proxima_calibracao"]),
        },
        "laboratorio": {k: laboratorio.get(k) for k in ("nome", "procedimento", "rodape")},
        "resultados": [a.como_item() for a in revisao.parecer.avaliacoes],
        "resumo": revisao.parecer.resumo(),
        "incerteza": {
            "incerteza_combinada_um": inc.incerteza_combinada_um,
            "incerteza_expandida_um": inc.incerteza_expandida_um,
            "incerteza_expandida_mm": inc.incerteza_expandida_mm,
            "k": inc.k,
            "veff": inc.veff,
        },
        "tecnico_executante": calibracao.get("tecnico_nome") or calibracao.get("metrologista_relatorio"),
        "signatario": {"matricula": signatario["matricula"], "nome": signatario["nome"]},
        "url_consulta": url_consulta,
        "marca_prova_de_conceito": marca_prova_de_conceito,
    }
