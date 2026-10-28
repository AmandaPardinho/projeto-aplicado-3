import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from calculo import PlanilhaInvalidaError, processar_planilha

PASTA_AMOSTRAS = os.path.join(os.path.dirname(__file__), "..", "sample_data")


def test_planilha_aprovada_gera_parecer_aprovado():
    caminho = os.path.join(PASTA_AMOSTRAS, "amostra_aprovado.xlsx")
    resultado = processar_planilha(caminho)

    assert resultado.parecer == "APROVADO"
    assert resultado.total_reprovadas == 0
    assert len(resultado.caracteristicas) == 8


def test_planilha_reprovada_gera_parecer_reprovado():
    caminho = os.path.join(PASTA_AMOSTRAS, "amostra_reprovado.xlsx")
    resultado = processar_planilha(caminho)

    assert resultado.parecer == "REPROVADO"
    assert resultado.total_reprovadas == 1


def test_media_e_erro_sistematico_calculados_corretamente():
    caminho = os.path.join(PASTA_AMOSTRAS, "amostra_aprovado.xlsx")
    resultado = processar_planilha(caminho)
    primeira = resultado.caracteristicas[0]

    # 62P_DIAMETRO 1: nominal 6.075, medidas 6.0787295 / 6.0780314
    assert primeira.media == (primeira.medida1 + primeira.medida2) / 2
    assert primeira.erro_sistematico == primeira.media - primeira.nominal
    assert primeira.status == "DENTRO_DA_TOLERANCIA"


def test_planilha_sem_cabecalho_valido_levanta_erro(tmp_path):
    import openpyxl

    caminho = tmp_path / "invalida.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["isso", "nao", "e", "uma", "planilha", "valida"])
    wb.save(caminho)

    with pytest.raises(PlanilhaInvalidaError):
        processar_planilha(str(caminho))


def _planilha_com_linhas(tmp_path, linhas):
    import openpyxl

    caminho = tmp_path / "planilha.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["DIMENSION", "NOMINAL", "+TOL", "-TOL", "MEAS 1", "MEAS 2"])
    for linha in linhas:
        ws.append(linha)
    wb.save(caminho)
    return str(caminho)


def test_linha_incompleta_recusa_planilha_e_aponta_a_linha(tmp_path):
    caminho = _planilha_com_linhas(tmp_path, [
        ["A", 10, 0.1, -0.1, 10.01, 10.02],
        ["B", 20, 0.1, -0.1, 20.01, None],  # MEAS 2 ausente
    ])

    with pytest.raises(PlanilhaInvalidaError) as exc:
        processar_planilha(caminho)

    assert "linha 3" in str(exc.value)
    assert "'B'" in str(exc.value)
    assert "MEAS 2" in str(exc.value)


def test_valor_nao_numerico_tambem_recusa_planilha(tmp_path):
    caminho = _planilha_com_linhas(tmp_path, [
        ["A", 10, 0.1, -0.1, 10.01, 10.02],
        ["B", 20, 0.1, -0.1, "abc", 20.02],
    ])

    with pytest.raises(PlanilhaInvalidaError):
        processar_planilha(caminho)


def test_linha_sem_nome_continua_sendo_descartada(tmp_path):
    caminho = _planilha_com_linhas(tmp_path, [
        ["A", 10, 0.1, -0.1, 10.01, 10.02],
        [None, None, None, None, None, None],
    ])

    assert len(processar_planilha(caminho).caracteristicas) == 1


def test_erro_fora_da_faixa_assimetrica_reprova(tmp_path):
    # erro = +0.05, mas o limite superior e apenas +0.02
    caminho = _planilha_com_linhas(tmp_path, [
        ["A", 10, 0.02, -0.2, 10.05, 10.05],
    ])

    assert processar_planilha(caminho).parecer == "REPROVADO"


def test_arquivo_corrompido_levanta_erro(tmp_path):
    caminho = tmp_path / "corrompido.xlsx"
    caminho.write_bytes(b"isto nao e um xlsx")

    with pytest.raises(PlanilhaInvalidaError):
        processar_planilha(str(caminho))
