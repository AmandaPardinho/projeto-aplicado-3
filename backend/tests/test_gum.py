"""Caso de aceite RF03: o 703.1208 reproduz a aba Incerteza (bloco volumetrico)."""
import os
from decimal import Decimal

import pytest

from report_calypso import gerar_report
from schulz import gum
from schulz.cadastros_exemplo import padrao_mmc
from schulz.calypso import ler_relatorio

PARAMETROS = gum.ParametrosMMC.de_item(padrao_mmc()["orcamento"])


def calcular(conteudo):
    caracteristicas = ler_relatorio(conteudo).caracteristicas
    return gum.calcular_volumetrico([(c.medicao_p1, c.medicao_p2) for c in caracteristicas],
                                    [c.valor_nominal for c in caracteristicas], PARAMETROS)


def test_rf03_caso_703_1208_bate_com_a_planilha():
    resultado = calcular(gerar_report())
    # Valores das celulas G56, H57, F58 e G58 da aba Incerteza (Cal_1_5896_1.xlsx)
    assert resultado.comprimento_avaliado_mm == Decimal("16.964")
    assert round(resultado.incerteza_combinada_um, 12) == Decimal("0.931344277264")
    assert resultado.veff == 12
    assert resultado.k == Decimal("2.23")
    assert round(resultado.incerteza_expandida_um, 12) == Decimal("2.076897738300")
    assert resultado.incerteza_expandida_mm == Decimal("0.002")


def test_dispersao_usa_a_maior_diferenca_entre_passagens():
    resultado = calcular(gerar_report())
    dispersao = resultado.componentes[0]
    # 106P_POSICAO 1: 0,1326897 x 0,1316897 -> s = 0,000707 mm = 0,707 um
    assert round(dispersao.valor, 10) == Decimal("0.7071067812")
    assert dispersao.vi == 1


@pytest.mark.parametrize("veff, k", [
    (1, "13.97"), (2, "4.53"), (7, "2.43"), (8, "2.37"), (11, "2.28"), (12, "2.23"),
    (13, "2.23"), (14, "2.2"), (24, "2.13"), (99, "2.03"), (100, "2.02"), (101, "2"),
    (7413, "2"),
])
def test_rn03_k_varia_com_veff(veff, k):
    assert gum.fator_k(veff) == Decimal(k)


def test_desvio_padrao_igual_ao_excel():
    assert round(gum.desvio_padrao([Decimal("72.512"), Decimal("72.511")]), 16) == \
        Decimal("0.0007071067811865")


@pytest.mark.skipif(not os.environ.get("SCHULZ_REPORT_REAL"),
                    reason="defina SCHULZ_REPORT_REAL com o caminho do Registro_MMC.xlsx real")
def test_arquivo_real_da_schulz():
    with open(os.environ["SCHULZ_REPORT_REAL"], "rb") as arquivo:
        resultado = calcular(arquivo.read())
    assert (resultado.veff, resultado.k, resultado.incerteza_expandida_mm) == \
        (12, Decimal("2.23"), Decimal("0.002"))
