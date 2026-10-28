from datetime import date
from decimal import Decimal

from report_calypso import gerar_report
from schulz import cadastros_exemplo, revisao
from schulz.calypso import ler_relatorio
from schulz.certificado import codigo_verificacao, gerar_pdf


def valores():
    caracteristicas = [c.como_item() for c in ler_relatorio(gerar_report()).caracteristicas]
    calibracao = {"calibracao_id": "abc", "caracteristicas": caracteristicas,
                  "data_hora_medicao": "2026-08-13T16:16:26", "temperatura_ambiente": "20.4",
                  "tecnico_nome": "Tecnico Exemplo"}
    padrao = cadastros_exemplo.padrao_mmc()
    instrumento = cadastros_exemplo.instrumento_703_1208()
    resultado = revisao.revisar(calibracao, padrao, instrumento, date(2026, 8, 26))
    return revisao.valores_do_certificado(
        "2026-00091", "00091/2026", calibracao, instrumento, padrao,
        {"matricula": "1002", "nome": "Signatario Exemplo"}, cadastros_exemplo.laboratorio(),
        resultado, "https://app.exemplo/#/consulta/703.1208", "2026-08-26T19:47:10Z", True)


def test_gera_pdf():
    pdf = gerar_pdf(valores())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3000


def test_codigo_de_verificacao_estavel():
    assert codigo_verificacao(valores()) == codigo_verificacao(valores())
    alterado = valores()
    alterado["resultados"][0]["media"] = "0"
    assert codigo_verificacao(alterado) != codigo_verificacao(valores())


def test_valores_impressos_do_caso_real():
    v = valores()
    assert v["incerteza"]["incerteza_expandida_mm"] == Decimal("0.002")
    assert v["incerteza"]["k"] == Decimal("2.23")
    assert v["padrao"]["data_proxima_calibracao"] == "31/08/2026"
    assert v["resumo"]["nao_conformes"] == 6


def test_revisao_bloqueia_padrao_vencido_rn04():
    caracteristicas = [c.como_item() for c in ler_relatorio(gerar_report()).caracteristicas]
    resultado = revisao.revisar({"caracteristicas": caracteristicas},
                                cadastros_exemplo.padrao_mmc(),
                                cadastros_exemplo.instrumento_703_1208(), date(2026, 10, 27))
    assert resultado.bloqueios and resultado.bloqueios[0].startswith("RN04")


def test_revisao_bloqueia_angulo_rn06():
    report = gerar_report([("10P_ÂNGULO 1", 60.08, 60.08, 60, 0.1, -0.1)])
    caracteristicas = [c.como_item() for c in ler_relatorio(report).caracteristicas]
    resultado = revisao.revisar({"caracteristicas": caracteristicas},
                                cadastros_exemplo.padrao_mmc(),
                                cadastros_exemplo.instrumento_703_1208(), date(2026, 8, 26))
    assert any(b.startswith("RN06") for b in resultado.bloqueios)


def test_revisao_bloqueia_cadastro_incompleto_rn08():
    caracteristicas = [c.como_item() for c in ler_relatorio(gerar_report()).caracteristicas]
    instrumento = {**cadastros_exemplo.instrumento_703_1208(), "fabricante": "???"}
    resultado = revisao.revisar({"caracteristicas": caracteristicas},
                                cadastros_exemplo.padrao_mmc(), instrumento, date(2026, 8, 26))
    assert any("fabricante" in b for b in resultado.bloqueios)
