"""Fluxo completo E1-E8 da AV2 contra DynamoDB e S3 simulados (moto)."""
import json
import os
from decimal import Decimal

import pytest

from conftest import DIA_DA_CALIBRACAO, evento
from handlers import api, emissao, ingestao
from report_calypso import gerar_report
from schulz import cadastros_exemplo

TECNICO = dict(grupos=["tecnico"], login="tecnico.exemplo")
REVISOR = dict(grupos=["revisor"], login="revisor.exemplo")
SIGNATARIO = dict(grupos=["revisor", "signatario"], login="signatario.exemplo", matricula="1002")
AUDITOR = dict(grupos=["auditor"], login="auditor.exemplo")


@pytest.fixture
def ctx(aws):
    repositorio, s3 = aws
    contexto = api.Contexto(repositorio, s3, hoje=DIA_DA_CALIBRACAO)
    contexto.emitir = lambda payload: emissao.processar(payload, repositorio, s3,
                                                        DIA_DA_CALIBRACAO)
    return contexto


def chamar(ctx, rota, perfil, **kwargs):
    retorno = api.handler(evento(rota, **perfil, **kwargs), ctx=ctx)
    return retorno["statusCode"], json.loads(retorno["body"])


def enviar(ctx, conteudo=None, tag="703.1208", padrao="500.011"):
    """E1 (pedido) + E2 (upload simulado) + E3/E4 (evento do S3)."""
    status, corpo = chamar(ctx, "POST /calibracoes/upload", TECNICO, corpo={
        "tag": tag, "padrao_codigo": padrao, "temperatura_ambiente": "20,4",
        "nome_arquivo": "Registro_MMC.xlsx", "tamanho_bytes": 20000})
    assert status == 201, corpo
    campos = corpo["upload"]["fields"]
    metadados = {k.removeprefix("x-amz-meta-"): v for k, v in campos.items()
                 if k.startswith("x-amz-meta-")}
    ctx.s3.put_object(Bucket=os.environ["BUCKET_ENTRADA"], Key=campos["key"],
                      Body=conteudo or gerar_report(), Metadata=metadados)
    resultado = ingestao.processar(os.environ["BUCKET_ENTRADA"], campos["key"],
                                   ctx.s3, ctx.repositorio)
    return corpo["calibracao_id"], resultado, campos["key"]


def caminho(calibracao_id, tag="703.1208"):
    return {"tag": tag, "id": calibracao_id}


def test_fluxo_completo_ate_o_certificado(ctx):
    calibracao_id, resultado, _ = enviar(ctx)
    assert resultado["status"] == "AGUARDANDO_REVISAO", resultado

    status, fila = chamar(ctx, "GET /calibracoes", REVISOR)
    assert [c["calibracao_id"] for c in fila["calibracoes"]] == [calibracao_id]

    status, detalhe = chamar(ctx, "GET /calibracoes/{tag}/{id}", REVISOR,
                             caminho=caminho(calibracao_id))
    assert status == 200
    revisao = detalhe["revisao"]
    assert revisao["incerteza"]["incerteza_expandida_mm"] == "0.002"
    assert revisao["incerteza"]["k"] == "2.23" and revisao["incerteza"]["veff"] == 12
    assert revisao["resumo"]["nao_conformes"] == 6
    assert revisao["pode_emitir"] is True
    assert detalhe["calibracao"]["tecnico_nome"] == "Tecnico Exemplo"

    status, certificado = chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO,
                                 caminho=caminho(calibracao_id))
    assert status == 201, certificado
    assert certificado["numero_exibicao"] == "00001/2026"

    pdf = ctx.s3.get_object(Bucket=os.environ["BUCKET_CERTIFICADOS"],
                            Key="certificados/2026/00001.pdf")["Body"].read()
    assert pdf.startswith(b"%PDF")
    calibracao = ctx.repositorio.calibracao("703.1208", calibracao_id)
    assert calibracao["status"] == "EMITIDA"

    # Consulta pelo TAG (computador ou PWA): mesma resposta, sempre auditada
    status, consulta = chamar(ctx, "GET /instrumentos/{tag}", dict(grupos=["consulta"],
                              login="operador.linha"), caminho={"tag": "703.1208"},
                              consulta={"canal": "leitor"})
    assert status == 200
    assert consulta["ultimo_certificado"]["numero_exibicao"] == "00001/2026"
    assert consulta["situacao"] == "EM_DIA"

    status, download = chamar(ctx, "GET /certificados/{numero}/download", REVISOR,
                              caminho={"numero": "2026-00001"})
    assert status == 200 and download["url"].startswith("https://")

    status, trilha = chamar(ctx, "GET /auditoria", AUDITOR,
                            consulta={"data": calibracao["criado_em"][:10]})
    acoes = {r["acao"] for r in trilha["registros"]}
    assert {"solicitar_envio", "importar_relatorio", "visualizar_calibracao",
            "emitir_certificado", "consultar_instrumento", "baixar_certificado"} <= acoes
    consulta_registrada = next(r for r in trilha["registros"] if r["acao"] == "consultar_instrumento")
    assert (consulta_registrada["usuario"], consulta_registrada["canal"]) == ("operador.linha", "leitor")
    # Acao feita na tela fica como teclado; "sistema" e so o que as Lambdas fazem sozinhas
    canais = {r["acao"]: r["canal"] for r in trilha["registros"]}
    assert canais["solicitar_envio"] == canais["visualizar_calibracao"] == "teclado"
    assert canais["baixar_certificado"] == "teclado"
    assert canais["importar_relatorio"] == "sistema"


def test_emissao_repetida_nao_gera_novo_numero(ctx):
    calibracao_id, _, _ = enviar(ctx)
    for _ in range(2):
        status, certificado = chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO,
                                     caminho=caminho(calibracao_id))
        assert certificado["numero"] == "2026-00001"


def test_rh17_mesmo_arquivo_duas_vezes_vai_para_quarentena(ctx):
    # Gerado uma vez so: o xlsx guarda a hora de criacao, e duas geracoes em
    # segundos diferentes teriam SHA-256 diferente
    conteudo = gerar_report()
    primeiro_id, _, _ = enviar(ctx, conteudo)
    _, resultado, _ = enviar(ctx, conteudo)
    assert resultado["status"] == "QUARENTENA"
    assert resultado["violacoes"][0]["regra"] == "RH17"
    assert primeiro_id in resultado["violacoes"][0]["mensagem"]
    status, quarentena = chamar(ctx, "GET /quarentena", TECNICO)
    assert len(quarentena["quarentena"]) == 1


def test_evento_repetido_do_s3_e_idempotente(ctx):
    _, _, chave = enviar(ctx)
    repetido = ingestao.processar(os.environ["BUCKET_ENTRADA"], chave, ctx.s3, ctx.repositorio)
    assert repetido["status"] == "JA_PROCESSADO"


def test_rh07_metrologista_fora_da_lista_mestra(ctx):
    _, resultado, _ = enviar(ctx, gerar_report(metrologista="Fulano Desconhecido"))
    assert [v["regra"] for v in resultado["violacoes"]] == ["RH07"]


def test_emissao_usa_o_padrao_vigente_na_medicao(ctx):
    calibracao_id, _, _ = enviar(ctx)
    original = ctx.repositorio.padrao("500.011")
    # Depois do envio o padrao e recalibrado e o orcamento muda (UC03)
    status, _ = chamar(ctx, "PUT /padroes/{codigo}", dict(grupos=["admin_padrao"], login="admin.padrao"),
                       caminho={"codigo": "500.011"},
                       corpo={"data_ultima_calibracao": "2026-08-30",
                              "data_proxima_calibracao": "2028-05-31",
                              "certificado_externo": "NOVO",
                              "orcamento": {**{k: str(v) for k, v in original["orcamento"].items()},
                                             "incerteza_mmc_um": 5}})
    assert status == 200
    status, certificado = chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO,
                                 caminho=caminho(calibracao_id))
    assert status == 201, certificado
    valores = ctx.repositorio.certificado(certificado["numero"])["valores"]
    assert valores["padrao"]["certificado_externo"] == original["certificado_externo"]
    assert valores["incerteza"]["incerteza_expandida_mm"] == Decimal("0.002")


def test_padrao_recalibrado_antes_do_envio_usa_a_versao_da_medicao(ctx):
    # Medido em 13/08; o padrao e recalibrado em 30/08, antes do envio
    original = ctx.repositorio.padrao("500.011")
    chamar(ctx, "PUT /padroes/{codigo}", dict(grupos=["admin_padrao"], login="admin.padrao"),
           caminho={"codigo": "500.011"},
           corpo={"data_ultima_calibracao": "2026-08-30", "data_proxima_calibracao": "2028-05-31",
                  "certificado_externo": "NOVO"})
    calibracao_id, _, _ = enviar(ctx)
    item = ctx.repositorio.calibracao("703.1208", calibracao_id)
    assert item["padrao_usado"]["certificado_externo"] == original["certificado_externo"]
    _, detalhe = chamar(ctx, "GET /calibracoes/{tag}/{id}", REVISOR, caminho=caminho(calibracao_id))
    assert detalhe["revisao"]["bloqueios"] == []


def test_rn04_medicao_anterior_ao_padrao_sem_versao_que_cubra(ctx):
    calibracao_id, _, _ = enviar(ctx)
    item = ctx.repositorio.calibracao("703.1208", calibracao_id)
    item["padrao_usado"]["data_ultima_calibracao"] = "2026-08-30"
    ctx.repositorio.gravar(item)
    _, detalhe = chamar(ctx, "GET /calibracoes/{tag}/{id}", REVISOR, caminho=caminho(calibracao_id))
    assert any(b.startswith("RN04: medição") for b in detalhe["revisao"]["bloqueios"])


def test_rn04_na_revisao_olha_a_data_da_medicao(ctx):
    # Medido em 13/08 com o padrao valido ate 31/08: emitir em outubro e valido
    calibracao_id, _, _ = enviar(ctx)
    ctx.hoje = ctx.hoje.replace(month=10, day=27)
    _, detalhe = chamar(ctx, "GET /calibracoes/{tag}/{id}", REVISOR, caminho=caminho(calibracao_id))
    assert not any(b.startswith("RN04") for b in detalhe["revisao"]["bloqueios"])


@pytest.mark.parametrize("medicao, meses, proxima", [
    ("2026-08-13T16:16:26", 2, "2026-10-13"),  # conta da medicao, nao da emissao (26/08)
    ("2026-01-31T10:00:00", 1, "2026-02-28"),
    ("2028-01-31T10:00:00", 1, "2028-02-29"),
    ("2026-05-31T10:00:00", 2, "2026-07-31"),  # dia 31 nao vira 28
    ("2026-11-30T10:00:00", 3, "2027-02-28"),
])
def test_proxima_calibracao_do_instrumento(medicao, meses, proxima):
    ultimo = {"data_calibracao": medicao, "emitido_em": "2026-08-26T19:47:10Z"}
    situacao = api._situacao_instrumento(ultimo, {"periodicidade_meses": meses},
                                         DIA_DA_CALIBRACAO)
    assert situacao["proxima_calibracao"] == proxima


def test_quem_enviou_nao_assina_o_proprio_certificado(ctx):
    calibracao_id, _, _ = enviar(ctx)
    tecnico_e_signatario = dict(grupos=["tecnico", "signatario"], login=TECNICO["login"],
                                matricula="1002")
    status, corpo = chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", tecnico_e_signatario,
                           caminho=caminho(calibracao_id))
    assert status == 403, corpo
    assert ctx.repositorio.calibracao("703.1208", calibracao_id)["status"] == "AGUARDANDO_REVISAO"
    # Outra pessoa signataria emite normalmente
    assert chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO,
                  caminho=caminho(calibracao_id))[0] == 201


@pytest.mark.parametrize("plano", ["", "PLANO_TESTE"])
def test_rn10_plano_sem_tag_vai_para_quarentena(ctx, plano):
    _, resultado, _ = enviar(ctx, gerar_report(plano=plano))
    assert resultado["status"] == "QUARENTENA", resultado
    assert [v["regra"] for v in resultado["violacoes"]] == ["RN10"]


def test_rn10_plano_de_outro_instrumento(ctx):
    _, resultado, _ = enviar(ctx, gerar_report(plano="999.0001_TESTE"))
    assert [v["regra"] for v in resultado["violacoes"]] == ["RN10"]


def test_rn01_arquivo_com_uma_passagem_vai_para_quarentena(ctx):
    calibracao_id, resultado, _ = enviar(ctx, gerar_report(passagens=1))
    assert resultado["status"] == "QUARENTENA"
    assert ctx.repositorio.calibracao("703.1208", calibracao_id) is None
    copia = f"quarentena/{calibracao_id}/"
    objetos = ctx.s3.list_objects_v2(Bucket=os.environ["BUCKET_ENTRADA"], Prefix=copia)
    assert objetos["KeyCount"] == 1


def test_rn04_padrao_vencido_recusa_o_envio(ctx):
    ctx.hoje = ctx.hoje.replace(month=10, day=27)
    status, corpo = chamar(ctx, "POST /calibracoes/upload", TECNICO, corpo={
        "tag": "703.1208", "padrao_codigo": "500.011", "temperatura_ambiente": 20.4,
        "nome_arquivo": "r.xlsx", "tamanho_bytes": 1000})
    assert status == 422 and corpo["erro"].startswith("RN04")


def test_upload_recusa_tag_inexistente_e_arquivo_grande(ctx):
    base = {"tag": "703.1208", "padrao_codigo": "500.011", "temperatura_ambiente": 20.4,
            "nome_arquivo": "r.xlsx", "tamanho_bytes": 1000}
    assert chamar(ctx, "POST /calibracoes/upload", TECNICO,
                  corpo={**base, "tag": "000"})[0] == 404
    assert chamar(ctx, "POST /calibracoes/upload", TECNICO,
                  corpo={**base, "tamanho_bytes": 6 * 1024 * 1024})[0] == 400
    assert chamar(ctx, "POST /calibracoes/upload", TECNICO,
                  corpo={**base, "nome_arquivo": "r.csv"})[0] == 400


def test_rn05_so_signatario_autorizado_emite(ctx):
    calibracao_id, _, _ = enviar(ctx)
    assert chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", REVISOR,
                  caminho=caminho(calibracao_id))[0] == 403
    # Grupo certo no token, mas sem pode_assinar_certificado no cadastro
    sem_permissao = dict(grupos=["signatario"], login="tecnico.exemplo", matricula="1001")
    status, corpo = chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", sem_permissao,
                           caminho=caminho(calibracao_id))
    assert status == 403 and corpo["erro"].startswith("RN05")


def test_tecnico_ve_so_o_que_enviou(ctx):
    calibracao_id, _, _ = enviar(ctx)
    outro = dict(grupos=["tecnico"], login="outro.tecnico")
    assert chamar(ctx, "GET /calibracoes", outro)[1]["calibracoes"] == []
    assert chamar(ctx, "GET /calibracoes/{tag}/{id}", outro,
                  caminho=caminho(calibracao_id))[0] == 404
    assert len(chamar(ctx, "GET /calibracoes", TECNICO)[1]["calibracoes"]) == 1


def test_cancelamento_exige_justificativa(ctx):
    calibracao_id, _, _ = enviar(ctx)
    rota = "POST /calibracoes/{tag}/{id}/cancelar"
    assert chamar(ctx, rota, REVISOR, caminho=caminho(calibracao_id),
                  corpo={"justificativa": "curta"})[0] == 400
    status, corpo = chamar(ctx, rota, REVISOR, caminho=caminho(calibracao_id),
                           corpo={"justificativa": "Peça medida com fixação errada"})
    assert (status, corpo["status"]) == (200, "CANCELADA")
    assert chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO,
                  caminho=caminho(calibracao_id))[0] == 409


def test_consulta_de_outro_setor_nao_baixa_certificado(ctx):
    calibracao_id, _, _ = enviar(ctx)
    chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO, caminho=caminho(calibracao_id))
    rota = "GET /certificados/{numero}/download"
    outro_setor = dict(grupos=["consulta"], login="c1", setor="montagem")
    mesmo_setor = dict(grupos=["consulta"], login="c2", setor="usinagem-1")
    assert chamar(ctx, rota, outro_setor, caminho={"numero": "2026-00001"})[0] == 403
    assert chamar(ctx, rota, mesmo_setor, caminho={"numero": "2026-00001"})[0] == 200


def test_consulta_de_tag_inexistente_tambem_e_auditada(ctx):
    status, _ = chamar(ctx, "GET /instrumentos/{tag}", dict(grupos=["consulta"], login="c1"),
                       caminho={"tag": "000.0000"}, consulta={"canal": "camera"})
    assert status == 404
    registros = ctx.repositorio.auditoria(api.agora().date().isoformat())
    assert registros[0]["alvo"] == "INST#000.0000" and registros[0]["canal"] == "camera"


def test_canal_da_consulta_so_aceita_os_do_navegador(ctx):
    consulta = dict(grupos=["consulta"], login="c1")
    for canal in ("sistema", "<script>"):
        status, _ = chamar(ctx, "GET /instrumentos/{tag}", consulta, caminho={"tag": "703.1208"},
                           consulta={"canal": canal})
        assert status == 400
    assert ctx.repositorio.auditoria(api.agora().date().isoformat()) == []


def test_sem_login_nao_acessa_nada(ctx):
    sem_token = evento("GET /instrumentos/{tag}", caminho={"tag": "703.1208"})
    sem_token["requestContext"] = {}
    assert api.handler(sem_token, ctx=ctx)["statusCode"] == 403


def test_uc03_atualizar_padrao_guarda_historico(ctx):
    admin = dict(grupos=["admin_padrao"], login="admin.padrao")
    status, corpo = chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
                           corpo={"data_ultima_calibracao": "2026-08-30",
                                  "data_proxima_calibracao": "2028-05-31",
                                  "certificado_externo": "260830502390"})
    assert status == 200, corpo
    status, detalhe = chamar(ctx, "GET /padroes/{codigo}", REVISOR, caminho={"codigo": "500.011"})
    assert detalhe["padrao"]["certificado_externo"] == "260830502390"
    # O historico guarda a versao que saiu de vigor, nao uma copia da nova
    anterior = cadastros_exemplo.padrao_mmc()
    assert [(h["data_ultima_calibracao"], h["certificado_externo"], h["substituido_por"])
            for h in detalhe["historico"]] == \
        [(anterior["data_ultima_calibracao"], anterior["certificado_externo"], "admin.padrao")]

    # Segunda atualizacao no mesmo dia: as duas versoes antigas continuam
    chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
           corpo={"certificado_externo": "260830502391"})
    _, detalhe = chamar(ctx, "GET /padroes/{codigo}", REVISOR, caminho={"codigo": "500.011"})
    assert [h["certificado_externo"] for h in detalhe["historico"]] == \
        ["260830502390", anterior["certificado_externo"]]


def test_uc03_gravacao_concorrente_nao_perde_versao(ctx, monkeypatch):
    momento = api.agora()
    monkeypatch.setattr(api, "agora", lambda: momento)
    admin = dict(grupos=["admin_padrao"], login="admin.padrao")
    # Parte de um padrao ja atualizado, e as duas gravacoes seguintes caem no
    # mesmo segundo: o controle nao pode depender de atualizado_em
    chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
           corpo={"certificado_externo": "INICIAL"})
    lido = ctx.repositorio.padrao("500.011")
    chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
           corpo={"certificado_externo": "A"})
    assert ctx.repositorio.padrao("500.011")["atualizado_em"] == lido["atualizado_em"]
    # Outra aba ainda tem a versao lida antes da gravacao acima
    original = ctx.repositorio.padrao
    ctx.repositorio.padrao = lambda codigo: lido
    try:
        status, corpo = chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
                               corpo={"certificado_externo": "B"})
    finally:
        ctx.repositorio.padrao = original
    assert status == 409, corpo
    assert ctx.repositorio.padrao("500.011")["certificado_externo"] == "A"
    assert chamar(ctx, "PUT /padroes/{codigo}", REVISOR, caminho={"codigo": "500.011"},
                  corpo={})[0] == 403


def test_uc03_orcamento_precisa_ser_numerico(ctx):
    admin = dict(grupos=["admin_padrao"], login="admin.padrao")
    datas = {"data_ultima_calibracao": "2026-08-30", "data_proxima_calibracao": "2028-05-31"}
    status, corpo = chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
                           corpo={**datas, "orcamento": {"incerteza_mmc_um": "abc"}})
    assert status == 400, corpo
    status, corpo = chamar(ctx, "PUT /padroes/{codigo}", admin, caminho={"codigo": "500.011"},
                           corpo={**datas, "orcamento": {"incerteza_mmc_um": 0.4,
                                                         "erro_sistematico_mmc_um": "-0.8"}})
    assert status == 200, corpo
    assert corpo["padrao"]["orcamento"] == {"incerteza_mmc_um": "0.4",
                                            "erro_sistematico_mmc_um": "-0.8"}


def test_me_lista_permissoes(ctx):
    status, corpo = chamar(ctx, "GET /me", SIGNATARIO)
    assert "emitir_certificado" in corpo["permissoes"]
    assert "enviar_relatorio" not in corpo["permissoes"]


def test_consultas_trazem_todas_as_paginas(ctx):
    # O DynamoDB corta a resposta em 1 MB; com Limit pequeno o corte aparece
    # ja com poucos itens e a consulta tem de seguir o LastEvaluatedKey
    for i in range(7):
        ctx.repositorio.gravar({"PK": "AUD#2026-08-26", "SK": f"2026-08-26T10:00:0{i}Z#{i}",
                                "acao": "teste"})
    consultar = ctx.repositorio.tabela.query
    ctx.repositorio.tabela.query = lambda **kw: consultar(**kw, Limit=2)
    try:
        assert len(ctx.repositorio.auditoria("2026-08-26")) == 7
    finally:
        ctx.repositorio.tabela.query = consultar
