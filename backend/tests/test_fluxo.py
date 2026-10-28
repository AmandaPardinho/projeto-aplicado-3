"""Fluxo completo E1-E8 da AV2 contra DynamoDB e S3 simulados (moto)."""
import json
import os

import pytest

from conftest import DIA_DA_CALIBRACAO, evento
from handlers import api, emissao, ingestao
from report_calypso import gerar_report

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


def test_emissao_repetida_nao_gera_novo_numero(ctx):
    calibracao_id, _, _ = enviar(ctx)
    for _ in range(2):
        status, certificado = chamar(ctx, "POST /calibracoes/{tag}/{id}/emitir", SIGNATARIO,
                                     caminho=caminho(calibracao_id))
        assert certificado["numero"] == "2026-00001"


def test_rh17_mesmo_arquivo_duas_vezes_vai_para_quarentena(ctx):
    primeiro_id, _, _ = enviar(ctx)
    _, resultado, _ = enviar(ctx)
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
    assert [h["data_ultima_calibracao"] for h in detalhe["historico"]] == ["2026-08-30"]
    assert chamar(ctx, "PUT /padroes/{codigo}", REVISOR, caminho={"codigo": "500.011"},
                  corpo={})[0] == 403


def test_me_lista_permissoes(ctx):
    status, corpo = chamar(ctx, "GET /me", SIGNATARIO)
    assert "emitir_certificado" in corpo["permissoes"]
    assert "enviar_relatorio" not in corpo["permissoes"]
