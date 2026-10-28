from decimal import Decimal as D

from report_calypso import gerar_report
from schulz.calypso import ler_relatorio
from schulz.conformidade import (CONFORME, FORA_DA_TOLERANCIA, FORA_PELA_BANDA_DE_GUARDA,
                                 NAO_CONFORME, avaliar, avaliar_calibracao)

U = D("0.002")


def test_caso_703_1208_reprova_as_seis_posicoes():
    caracteristicas = [c.como_item() for c in ler_relatorio(gerar_report()).caracteristicas]
    parecer = avaliar_calibracao(caracteristicas, U)
    assert parecer.situacao == NAO_CONFORME
    assert parecer.resumo()["nao_conformes"] == 6
    assert all("POSIÇÃO" in a.nome for a in parecer.nao_conformes)


def test_diametro_dentro_da_tolerancia_e_conforme():
    # A coluna M da planilha marca "Rep" aqui por erro de sinal; RN02 nao
    a = avaliar("62P_DIÂMETRO 1", D("6.075"), D("0.01"), D("-0.01"),
                D("6.0787295"), D("6.0787295"), U)
    assert (a.situacao, a.limite_inferior, a.limite_superior) == (CONFORME, D("6.065"), D("6.085"))


def test_rn02_banda_de_guarda():
    # media 6,084 esta dentro (limite 6,085), mas 6,084 + 0,002 passa do limite
    a = avaliar("X", D("6.075"), D("0.01"), D("-0.01"), D("6.084"), D("6.084"), U)
    assert (a.situacao, a.motivo) == (NAO_CONFORME, FORA_PELA_BANDA_DE_GUARDA)


def test_fora_da_tolerancia():
    a = avaliar("62P_POSIÇÃO 1", D("0"), D("0.1"), D("0"), D("0.4295522"), D("0.4295522"), U)
    assert (a.situacao, a.motivo) == (NAO_CONFORME, FORA_DA_TOLERANCIA)
    assert a.erro == D("0.4295522")


def test_tolerancia_inferior_positiva_e_tratada_como_modulo():
    a = avaliar("X", D("10"), D("0.1"), D("0.1"), D("9.95"), D("9.95"), U)
    assert a.limite_inferior == D("9.9") and a.situacao == CONFORME


def test_banda_de_guarda_usa_u_calculado_e_nao_o_arredondado():
    # U do caso real: 0,0020769 mm (impresso 0,002). Um diametro a 0,00203 do
    # limite passa com o arredondado e reprova com o calculado.
    from datetime import date

    from schulz import cadastros_exemplo, revisao

    caracteristicas = [c.como_item() for c in ler_relatorio(gerar_report()).caracteristicas]
    diametro = next(c for c in caracteristicas if c["nome"] == "62P_DIÂMETRO 1")
    limite = diametro["valor_nominal"] + abs(diametro["tolerancia_superior"])
    diametro["medicao_p1"] = diametro["medicao_p2"] = limite - D("0.00203")

    resultado = revisao.revisar({"caracteristicas": caracteristicas}, cadastros_exemplo.padrao_mmc(),
                                cadastros_exemplo.instrumento_703_1208(), date(2026, 8, 26))
    assert resultado.incerteza.incerteza_expandida_mm == U
    avaliacao = next(a for a in resultado.parecer.avaliacoes if a.nome == "62P_DIÂMETRO 1")
    assert (avaliacao.situacao, avaliacao.motivo) == (NAO_CONFORME, FORA_PELA_BANDA_DE_GUARDA)
