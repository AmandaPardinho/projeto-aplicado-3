"""
Cadastros de exemplo para testes e para a carga inicial da PoC (seed).

Valores tecnicos copiados das planilhas da Schulz (Padroes, Complemento,
Incerteza do caso 703.1208). Nomes de pessoas sao ficticios: o repositorio e
publico e nomes/matriculas de metrologistas sao dados pessoais (LGPD, AV2 4.2.5).
"""
from __future__ import annotations

from decimal import Decimal

from .repositorio import (CHAVE_LABORATORIO, chave_instrumento, chave_metrologista,
                          chave_nome_metrologista, chave_padrao, chave_padrao_alternativo)

TAG_EXEMPLO = "703.1208"
PADRAO_MMC = "500.011"
TECNICO_EXEMPLO = "Tecnico Exemplo"  # nome que aparece no Report gerado nos testes

# Usuarios de teste, um por perfil: viram usuarios do Cognito no seed e a
# lista da tela de login no servidor local. Matricula liga o login ao
# metrologista (RN05); setor limita o que o perfil consulta ve (AV2 4.2.4).
USUARIOS_TESTE = {
    "tecnico.exemplo": {"grupos": ["tecnico"], "matricula": "1001", "setor": "usinagem-1"},
    "revisor.exemplo": {"grupos": ["revisor"]},
    "signatario.exemplo": {"grupos": ["revisor", "signatario"], "matricula": "1002"},
    "admin.padrao": {"grupos": ["admin_padrao"]},
    "consulta.usinagem": {"grupos": ["consulta"], "setor": "usinagem-1"},
    "auditor.exemplo": {"grupos": ["auditor"]},
}


def instrumento_703_1208() -> dict:
    return {
        **chave_instrumento(TAG_EXEMPLO),
        "tipo": "INSTRUMENTO",
        "tag": TAG_EXEMPLO,
        "codigo_interno": "5896",           # separado do TAG (anomalia 6 do Tema 01)
        "denominacao": "Dispositivo de controle",
        "fabricante": "Não consta",
        "numero_serie": None,
        "modelo": "Não se aplica",
        "setor": "usinagem-1",
        "solicitante": "Usinagem I",
        "periodicidade_meses": 2,           # aba Criterios: demais calibracoes, 2 meses
    }


def padrao_mmc(data_ultima: str = "2024-11-20", data_proxima: str = "2026-08-31") -> dict:
    return {
        **chave_padrao(PADRAO_MMC),
        "GSI1PK": "PADRAO",
        "GSI1SK": PADRAO_MMC,
        "tipo_item": "PADRAO",
        "codigo": PADRAO_MMC,
        "tipo": "MMC",
        "descricao": "Máquina de medição por coordenadas",
        "fabricante": "Carl Zeiss",
        "modelo": "Contura G2",
        "numero_serie": "502390",
        "certificado_externo": "241120502390",
        "executante": "Carl Zeiss",
        "data_ultima_calibracao": data_ultima,
        "data_proxima_calibracao": data_proxima,
        "orcamento": {
            "incerteza_mmc_um": Decimal("0.4"),
            "erro_sistematico_mmc_um": Decimal("-0.8"),
            "incerteza_esfera_um": Decimal("0.6"),
            "repetitividade_apalpador_um": Decimal("0.9"),
            "resolucao_um": Decimal("0.1"),
            "alfa_objeto": Decimal("11.5"),
            "variacao_temperatura_20c": Decimal("1"),
            "diferenca_temperatura_padrao_objeto": Decimal("0.5"),
        },
    }


def mapa_padrao_legado() -> dict:
    # RH08: o Report traz 500008 no campo MMC; o cadastro oficial e 500.011
    return {**chave_padrao_alternativo("500008"), "codigo": PADRAO_MMC}


def metrologista(matricula: str, nome: str, usuario: str, pode_assinar: bool) -> list[dict]:
    """Item do metrologista + mapa nome -> matricula (RH07)."""
    return [
        {**chave_metrologista(matricula), "GSI1PK": f"USUARIO#{usuario}", "GSI1SK": "METRO",
         "tipo": "METROLOGISTA", "matricula": matricula, "nome": nome, "usuario": usuario,
         "pode_assinar_certificado": pode_assinar},
        {**chave_nome_metrologista(nome), "matricula": matricula},
    ]


def laboratorio() -> dict:
    return {
        **CHAVE_LABORATORIO,
        "nome": "Schulz Metrologia",
        "procedimento": "Calibração de dispositivo de controle - ITL-0026 (revisão 2).",
        "rodape": "Laboratório de Metrologia · Joinville · SC",
    }


def todos(data_proxima_padrao: str = "2026-08-31") -> list[dict]:
    return [
        instrumento_703_1208(),
        padrao_mmc(data_proxima=data_proxima_padrao),
        mapa_padrao_legado(),
        *metrologista("1001", TECNICO_EXEMPLO, "tecnico.exemplo", pode_assinar=False),
        *metrologista("1002", "Signatario Exemplo", "signatario.exemplo", pode_assinar=True),
        laboratorio(),
    ]
