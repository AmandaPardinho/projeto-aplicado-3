"""
fn-api: todas as rotas da HTTP API (API Gateway com autorizador JWT do Cognito).

    GET  /me                                     usuario, grupos e permissoes
    POST /calibracoes/upload                     E1: valida TAG/padrao e gera o presigned POST
    GET  /calibracoes?status=...                 fila (padrao: AGUARDANDO_REVISAO)
    GET  /calibracoes/{tag}/{id}                 E6: calibracao + GUM + banda de guarda
    POST /calibracoes/{tag}/{id}/cancelar        com justificativa
    POST /calibracoes/{tag}/{id}/emitir          E7: RN05 e invocacao da fn-emissao
    GET  /quarentena                             arquivos recusados e o motivo
    GET  /instrumentos/{tag}?canal=...           consulta (computador, leitor, camera ou PWA)
    GET  /instrumentos/{tag}/certificados        historico por TAG (RF11)
    GET  /certificados/{numero}                  valores congelados do certificado
    GET  /certificados/{numero}/download         E8: URL pre-assinada de 15 minutos
    GET  /padroes, GET /padroes/{codigo}         cadastro do padrao (RF10)
    PUT  /padroes/{codigo}                       atualizacao do padrao (UC03)
    GET  /auditoria?data=AAAA-MM-DD              trilha AUD# (so auditor)

Toda rota exige login, e toda acao, inclusive leitura, gera registro AUD#.
"""
from __future__ import annotations

import calendar
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from schulz import auditoria, revisao
from schulz.autorizacao import AcessoNegadoError, Usuario, usuario_do_evento
from schulz.erros import ErroDeNegocio, NaoEncontradoError
from schulz.repositorio import (Repositorio, agora, chave_calibracao, chave_padrao, iso,
                                novo_id)

TAMANHO_MAXIMO = 5 * 1024 * 1024
VALIDADE_UPLOAD = 600     # 10 minutos (E1)
VALIDADE_DOWNLOAD = 900   # 15 minutos (E8)
EXTENSOES = (".xlsx", ".xlsm")
# Acao feita na tela por uma pessoa; "sistema" fica para o que as Lambdas
# fazem sozinhas (importacao, quarentena, gravacao do certificado)
CANAL_WEB = "teclado"
STATUS_VALIDOS = {"AGUARDANDO_REVISAO", "EMITINDO", "EMITIDA", "CANCELADA"}
CAMPOS_DO_PADRAO = ("descricao", "tipo", "fabricante", "modelo", "numero_serie",
                    "certificado_externo", "executante", "data_ultima_calibracao",
                    "data_proxima_calibracao", "orcamento")


class Contexto:
    """Dependencias de uma requisicao; os testes trocam por versoes do moto."""

    def __init__(self, repositorio=None, s3=None, emitir: Callable | None = None,
                 hoje: date | None = None):
        self.repositorio = repositorio or Repositorio()
        self.s3 = s3 or _cliente_s3()
        self.emitir = emitir or _invocar_emissao
        self.hoje = hoje or date.today()


def _cliente_s3():
    """Cliente para as URLs pre-assinadas: endpoint regional e SigV4. O padrao
    do boto3 aponta para s3.amazonaws.com, que redireciona buckets novos fora
    de us-east-1 (o navegador nao segue o redirect no upload) e assina o GET
    com SigV2."""
    regiao = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "sa-east-1")
    return boto3.client("s3", region_name=regiao, endpoint_url=f"https://s3.{regiao}.amazonaws.com",
                        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


def _invocar_emissao(payload: dict) -> dict:
    nome = os.environ.get("FUNCAO_EMISSAO")
    if not nome:
        # Execucao local: chama a funcao no mesmo processo
        from handlers import emissao
        resposta = emissao.handler(payload)
    else:
        retorno = boto3.client("lambda").invoke(FunctionName=nome, Payload=json.dumps(payload))
        resposta = json.loads(retorno["Payload"].read())
    if not resposta.get("ok"):
        raise ErroDeNegocio(resposta.get("erro", "falha na emissão"),
                            resposta.get("status", 500), resposta.get("detalhes"))
    return resposta["certificado"]


# --- JSON ----------------------------------------------------------------

def _para_json(valor):
    if isinstance(valor, Decimal):
        # Inteiros como numero; demais como texto, para nao perder casas (RNF10)
        return int(valor) if valor == valor.to_integral_value() and abs(valor) < 2 ** 53 else str(valor)
    if isinstance(valor, (set, frozenset)):
        return sorted(valor)
    raise TypeError(f"tipo nao serializavel: {type(valor)}")


def resposta(status: int, corpo) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(corpo, default=_para_json, ensure_ascii=False)}


def _corpo(evento: dict) -> dict:
    texto = evento.get("body") or "{}"
    if evento.get("isBase64Encoded"):
        import base64
        texto = base64.b64decode(texto).decode("utf-8")
    try:
        corpo = json.loads(texto, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ErroDeNegocio("corpo da requisição não é JSON válido", 400) from exc
    if not isinstance(corpo, dict):
        raise ErroDeNegocio("corpo da requisição deve ser um objeto JSON", 400)
    return corpo


def _sem_chaves(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}


def _resumo_calibracao(item: dict) -> dict:
    campos = ("calibracao_id", "tag", "status", "padrao_codigo", "enviado_por", "tecnico_nome",
              "data_hora_medicao", "criado_em", "numero_certificado")
    resumo = {c: item.get(c) for c in campos}
    resumo["caracteristicas"] = len(item.get("caracteristicas", []))
    return resumo


# --- rotas ---------------------------------------------------------------

def me(usuario: Usuario, ctx: Contexto, evento: dict):
    return 200, {"login": usuario.login, "grupos": sorted(usuario.grupos),
                 "matricula": usuario.matricula, "setor": usuario.setor,
                 "permissoes": usuario.permissoes}


def pedir_upload(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("enviar_relatorio")
    corpo = _corpo(evento)
    tag = str(corpo.get("tag", "")).strip()
    codigo_padrao = str(corpo.get("padrao_codigo", "")).strip()
    nome_arquivo = str(corpo.get("nome_arquivo", "")).strip()
    tamanho = corpo.get("tamanho_bytes")
    temperatura = corpo.get("temperatura_ambiente")

    if not nome_arquivo.lower().endswith(EXTENSOES):
        raise ErroDeNegocio("envie o relatório do Calypso em .xlsx ou .xlsm", 400)
    if not isinstance(tamanho, (int, Decimal)) or not 0 < tamanho <= TAMANHO_MAXIMO:
        raise ErroDeNegocio("o arquivo deve ter até 5 MB", 400)
    try:
        temperatura = Decimal(str(temperatura).replace(",", "."))
    except Exception as exc:
        raise ErroDeNegocio("RN09: informe a temperatura ambiente em °C", 400) from exc
    if not ctx.repositorio.instrumento(tag):
        raise NaoEncontradoError(f"instrumento {tag} não cadastrado")
    padrao = ctx.repositorio.padrao(codigo_padrao)
    if not padrao:
        raise NaoEncontradoError(f"padrão {codigo_padrao} não cadastrado")
    if revisao.padrao_vencido(padrao, ctx.hoje):
        raise ErroDeNegocio(f"RN04: padrão {codigo_padrao} com calibração vencida em "
                            f"{revisao.data_br(padrao['data_proxima_calibracao'])}")

    calibracao_id = novo_id()
    extensao = nome_arquivo.lower().rsplit(".", 1)[-1]
    momento = agora()
    chave = f"entrada/{momento:%Y/%m}/{calibracao_id}.{extensao}"
    metadados = {
        "x-amz-meta-calibracao-id": calibracao_id,
        "x-amz-meta-tag": tag,
        "x-amz-meta-padrao": codigo_padrao,
        "x-amz-meta-temperatura": str(temperatura),
        "x-amz-meta-usuario": usuario.login,
    }
    upload = ctx.s3.generate_presigned_post(
        Bucket=os.environ["BUCKET_ENTRADA"], Key=chave, Fields=metadados,
        Conditions=[["content-length-range", 1, TAMANHO_MAXIMO]]
        + [{campo: valor} for campo, valor in metadados.items()],
        ExpiresIn=VALIDADE_UPLOAD)
    auditoria.registrar(ctx.repositorio, usuario.login, "solicitar_envio",
                        f"INST#{tag}/CAL#{calibracao_id}", CANAL_WEB,
                        detalhes={"padrao": codigo_padrao, "arquivo": nome_arquivo})
    return 201, {"calibracao_id": calibracao_id, "upload": upload,
                 "expira_em_segundos": VALIDADE_UPLOAD}


def listar_calibracoes(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("ver_calibracoes")
    status = (evento.get("queryStringParameters") or {}).get("status", "AGUARDANDO_REVISAO")
    if status not in STATUS_VALIDOS:
        raise ErroDeNegocio(f"status inválido: {status}", 400)
    itens = ctx.repositorio.calibracoes_por_status(status)
    if usuario.eh_somente_tecnico():
        itens = [i for i in itens if i.get("enviado_por") == usuario.login]
    return 200, {"status": status, "calibracoes": [_resumo_calibracao(i) for i in itens]}


def _carregar_calibracao(usuario: Usuario, ctx: Contexto, evento: dict) -> dict:
    p = evento["pathParameters"]
    item = ctx.repositorio.calibracao(p["tag"], p["id"])
    if not item or (usuario.eh_somente_tecnico() and item.get("enviado_por") != usuario.login):
        raise NaoEncontradoError("calibração não encontrada")
    return item


def detalhar_calibracao(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("ver_calibracoes")
    item = _carregar_calibracao(usuario, ctx, evento)
    corpo = {"calibracao": _sem_chaves(item)}
    if item["status"] in ("AGUARDANDO_REVISAO", "EMITINDO"):
        resultado = revisao.revisar(item, revisao.padrao_da_calibracao(item, ctx.repositorio),
                                    ctx.repositorio.instrumento(item["tag"]), ctx.hoje)
        corpo["revisao"] = resultado.como_dict()
    elif item.get("numero_certificado"):
        certificado = ctx.repositorio.certificado(item["numero_certificado"])
        corpo["certificado"] = _sem_chaves(certificado) if certificado else None
    auditoria.registrar(ctx.repositorio, usuario.login, "visualizar_calibracao",
                        f"INST#{item['tag']}/CAL#{item['calibracao_id']}", CANAL_WEB)
    return 200, corpo


def cancelar_calibracao(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("cancelar_calibracao")
    item = _carregar_calibracao(usuario, ctx, evento)
    justificativa = str(_corpo(evento).get("justificativa", "")).strip()
    if len(justificativa) < 10:
        raise ErroDeNegocio("informe uma justificativa (mínimo 10 caracteres)", 400)
    try:
        ctx.repositorio.tabela.update_item(
            Key=chave_calibracao(item["tag"], item["calibracao_id"]),
            UpdateExpression=("SET #s = :cancelada, GSI1PK = :gsi, justificativa_cancelamento = :j,"
                              " cancelado_por = :u, atualizado_em = :agora"),
            ConditionExpression="#s = :aguardando",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":cancelada": "CANCELADA", ":gsi": "STATUS#CANCELADA",
                                       ":j": justificativa, ":u": usuario.login,
                                       ":agora": iso(agora()), ":aguardando": "AGUARDANDO_REVISAO"})
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ErroDeNegocio("só é possível cancelar uma calibração aguardando revisão", 409) from exc
        raise
    auditoria.registrar(ctx.repositorio, usuario.login, "cancelar_calibracao",
                        f"INST#{item['tag']}/CAL#{item['calibracao_id']}", CANAL_WEB,
                        detalhes={"justificativa": justificativa})
    return 200, {"calibracao_id": item["calibracao_id"], "status": "CANCELADA"}


def emitir_certificado(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("emitir_certificado")  # RN05, camada 1: grupo no token
    item = _carregar_calibracao(usuario, ctx, evento)
    signatario = (ctx.repositorio.metrologista(usuario.matricula) if usuario.matricula
                  else ctx.repositorio.metrologista_por_usuario(usuario.login))
    if not signatario or not signatario.get("pode_assinar_certificado"):
        # RN05, camada 2: atributo no cadastro (conferido de novo na transacao)
        raise ErroDeNegocio("RN05: usuário não é signatário autorizado", 403)
    certificado = ctx.emitir({"tag": item["tag"], "calibracao_id": item["calibracao_id"],
                              "login": usuario.login, "matricula": signatario["matricula"]})
    return 201, certificado


def listar_quarentena(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("ver_calibracoes")
    itens = ctx.repositorio.quarentenas()
    if usuario.eh_somente_tecnico():
        itens = [i for i in itens if i.get("enviado_por") == usuario.login]
    return 200, {"quarentena": [_sem_chaves(i) for i in itens]}


def _situacao_instrumento(ultimo: dict | None, instrumento: dict, hoje: date) -> dict:
    if not ultimo:
        return {"situacao": "SEM_CERTIFICADO", "proxima_calibracao": None}
    # A periodicidade conta da data da medicao, nao da emissao (certificados
    # antigos, sem data_calibracao, caem na emissao)
    base = date.fromisoformat((ultimo.get("data_calibracao") or ultimo["emitido_em"])[:10])
    meses = int(instrumento.get("periodicidade_meses") or 12)
    mes = base.month - 1 + meses
    ano, mes = base.year + mes // 12, mes % 12 + 1
    # 31/01 + 1 mes -> 28 ou 29/02: o ultimo dia do mes, nao um dia fixo
    proxima = date(ano, mes, min(base.day, calendar.monthrange(ano, mes)[1]))
    return {"situacao": "VENCIDO" if proxima < hoje else "EM_DIA",
            "proxima_calibracao": proxima.isoformat()}


# Canais que o navegador pode declarar; "sistema" fica so para as Lambdas
CANAIS_DA_CONSULTA = {"teclado", "leitor", "camera", "pwa"}


def _canal_da_consulta(evento: dict) -> str:
    canal = (evento.get("queryStringParameters") or {}).get("canal", "teclado")
    if canal not in CANAIS_DA_CONSULTA:
        raise ErroDeNegocio(f"canal de consulta inválido: {canal}", 400)
    return canal


def consultar_instrumento(usuario: Usuario, ctx: Contexto, evento: dict):
    """Consulta pelo TAG: mesma resposta no computador e no PWA; sempre auditada."""
    usuario.exigir("consultar_instrumento")
    tag = evento["pathParameters"]["tag"].strip()
    canal = _canal_da_consulta(evento)
    instrumento = ctx.repositorio.instrumento(tag)
    auditoria.registrar(ctx.repositorio, usuario.login, "consultar_instrumento",
                        f"INST#{tag}", canal, {"encontrado": bool(instrumento)})
    if not instrumento:
        raise NaoEncontradoError(f"instrumento {tag} não cadastrado")
    certificados = ctx.repositorio.certificados_do_instrumento(tag)
    ultimo = certificados[0] if certificados else None
    return 200, {
        "instrumento": _sem_chaves(instrumento),
        "ultimo_certificado": {k: ultimo.get(k) for k in (
            "numero", "numero_exibicao", "emitido_em", "situacao")} if ultimo else None,
        **_situacao_instrumento(ultimo, instrumento, ctx.hoje),
    }


def historico_instrumento(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("consultar_instrumento")
    tag = evento["pathParameters"]["tag"].strip()
    canal = _canal_da_consulta(evento)
    certificados = ctx.repositorio.certificados_do_instrumento(tag)
    auditoria.registrar(ctx.repositorio, usuario.login, "consultar_historico", f"INST#{tag}", canal)
    return 200, {"tag": tag, "certificados": [
        {k: c.get(k) for k in ("numero", "numero_exibicao", "versao", "emitido_em",
                               "emitido_por", "situacao")} for c in certificados]}


def _carregar_certificado(usuario: Usuario, ctx: Contexto, evento: dict) -> dict:
    usuario.exigir("baixar_certificado")
    certificado = ctx.repositorio.certificado(evento["pathParameters"]["numero"])
    if not certificado:
        raise NaoEncontradoError("certificado não encontrado")
    # Consulta (setor solicitante) so ve certificados do proprio setor (AV2 4.2.4)
    if usuario.grupos <= {"consulta", "tecnico", "admin_padrao"} and \
            certificado.get("setor") != usuario.setor:
        raise AcessoNegadoError("certificado de outro setor")
    return certificado


def detalhar_certificado(usuario: Usuario, ctx: Contexto, evento: dict):
    certificado = _carregar_certificado(usuario, ctx, evento)
    auditoria.registrar(ctx.repositorio, usuario.login, "visualizar_certificado",
                        f"CERT#{certificado['numero']}", CANAL_WEB)
    return 200, _sem_chaves(certificado)


def baixar_certificado(usuario: Usuario, ctx: Contexto, evento: dict):
    certificado = _carregar_certificado(usuario, ctx, evento)
    bucket, chave = certificado["pdf_s3"].removeprefix("s3://").split("/", 1)
    parametros = {"Bucket": bucket, "Key": chave,
                  "ResponseContentDisposition":
                      f'attachment; filename="certificado-{certificado["numero"]}.pdf"'}
    if certificado.get("pdf_versao_s3"):
        parametros["VersionId"] = certificado["pdf_versao_s3"]
    url = ctx.s3.generate_presigned_url("get_object", Params=parametros,
                                        ExpiresIn=VALIDADE_DOWNLOAD)
    auditoria.registrar(ctx.repositorio, usuario.login, "baixar_certificado",
                        f"CERT#{certificado['numero']}", CANAL_WEB)
    return 200, {"url": url, "expira_em_segundos": VALIDADE_DOWNLOAD,
                 "pdf_sha256": certificado["pdf_sha256"]}


def listar_padroes(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("ver_padroes")
    return 200, {"padroes": [_sem_chaves(p) for p in ctx.repositorio.padroes()]}


def detalhar_padrao(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("ver_padroes")
    codigo = evento["pathParameters"]["codigo"]
    padrao = ctx.repositorio.padrao(codigo)
    if not padrao:
        raise NaoEncontradoError(f"padrão {codigo} não cadastrado")
    return 200, {"padrao": _sem_chaves(padrao),
                 "vencido": revisao.padrao_vencido(padrao, ctx.hoje),
                 "historico": [_sem_chaves(v) for v in ctx.repositorio.historico_padrao(codigo)]}


def atualizar_padrao(usuario: Usuario, ctx: Contexto, evento: dict):
    """UC03: nova versao vigente; a anterior fica no historico V#<momento>."""
    usuario.exigir("atualizar_padrao")
    codigo = evento["pathParameters"]["codigo"]
    atual = ctx.repositorio.padrao(codigo)
    if not atual:
        raise NaoEncontradoError(f"padrão {codigo} não cadastrado")
    corpo = _corpo(evento)
    novo = {**atual, **{k: corpo[k] for k in CAMPOS_DO_PADRAO if k in corpo}}
    try:
        for campo in ("data_ultima_calibracao", "data_proxima_calibracao"):
            date.fromisoformat(novo[campo])
    except (KeyError, ValueError) as exc:
        raise ErroDeNegocio("datas do padrão devem estar no formato AAAA-MM-DD", 400) from exc
    if novo["data_proxima_calibracao"] <= novo["data_ultima_calibracao"]:
        raise ErroDeNegocio("a próxima calibração deve ser depois da última", 400)
    try:
        # O orcamento entra no calculo GUM de toda calibracao futura
        novo["orcamento"] = {k: Decimal(str(v)) for k, v in novo.get("orcamento", {}).items()}
        if not all(v.is_finite() for v in novo["orcamento"].values()):
            raise InvalidOperation
    except (InvalidOperation, AttributeError) as exc:
        raise ErroDeNegocio("os valores do orçamento de incerteza devem ser números", 400) from exc
    momento = iso(agora())
    novo.update(atualizado_em=momento, atualizado_por=usuario.login)
    # O historico guarda a versao que sai de vigor, com quando e por quem foi
    # substituida. A chave leva o momento em microssegundos: duas correcoes no
    # mesmo segundo nao se sobrescrevem e o historico continua em ordem.
    anterior = {k: v for k, v in atual.items() if k not in ("GSI1PK", "GSI1SK")}
    anterior.update(chave_padrao(codigo, "V#" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")),
                    substituido_em=momento, substituido_por=usuario.login)
    # Concorrencia otimista por numero de versao (atualizado_em tem resolucao
    # de segundos e repetiria): se outra pessoa salvou entre a leitura e a
    # gravacao, a versao dela nao some sem ir para o historico
    lida = atual.get("versao")
    novo["versao"] = int(lida or 0) + 1
    if lida is None:
        condicao = {"ConditionExpression": "attribute_not_exists(versao)"}
    else:
        condicao = {"ConditionExpression": "versao = :lida",
                    "ExpressionAttributeValues": {":lida": lida}}
    try:
        ctx.repositorio.transacao([
            {"Put": {"Item": novo, **condicao}},
            {"Put": {"Item": anterior}},
            {"Put": {"Item": auditoria.item_auditoria(
                usuario.login, "atualizar_padrao", f"PADRAO#{codigo}", CANAL_WEB,
                {"campos": sorted(k for k in CAMPOS_DO_PADRAO if k in corpo)})}},
        ])
    except ClientError as exc:
        # So a condicao do primeiro Put (a versao) e conflito de edicao; outro
        # cancelamento (capacidade, conflito transacional) segue como erro
        motivos = exc.response.get("CancellationReasons") or [{}]
        if motivos[0].get("Code") == "ConditionalCheckFailed":
            raise ErroDeNegocio("o padrão foi alterado por outra pessoa; recarregue e tente de novo",
                                409) from exc
        raise
    return 200, {"padrao": _sem_chaves(novo)}


def listar_auditoria(usuario: Usuario, ctx: Contexto, evento: dict):
    usuario.exigir("ver_auditoria")
    dia = (evento.get("queryStringParameters") or {}).get("data", ctx.hoje.isoformat())
    try:
        date.fromisoformat(dia)
    except ValueError as exc:
        raise ErroDeNegocio("data deve estar no formato AAAA-MM-DD", 400) from exc
    return 200, {"data": dia, "registros": [_sem_chaves(i) for i in ctx.repositorio.auditoria(dia)]}


ROTAS = {
    "GET /me": me,
    "POST /calibracoes/upload": pedir_upload,
    "GET /calibracoes": listar_calibracoes,
    "GET /calibracoes/{tag}/{id}": detalhar_calibracao,
    "POST /calibracoes/{tag}/{id}/cancelar": cancelar_calibracao,
    "POST /calibracoes/{tag}/{id}/emitir": emitir_certificado,
    "GET /quarentena": listar_quarentena,
    "GET /instrumentos/{tag}": consultar_instrumento,
    "GET /instrumentos/{tag}/certificados": historico_instrumento,
    "GET /certificados/{numero}": detalhar_certificado,
    "GET /certificados/{numero}/download": baixar_certificado,
    "GET /padroes": listar_padroes,
    "GET /padroes/{codigo}": detalhar_padrao,
    "PUT /padroes/{codigo}": atualizar_padrao,
    "GET /auditoria": listar_auditoria,
}


def handler(evento, contexto=None, ctx: Contexto | None = None):
    rota = ROTAS.get(evento.get("routeKey"))
    if rota is None:
        return resposta(404, {"erro": "rota não encontrada"})
    try:
        usuario = usuario_do_evento(evento)
        status, corpo = rota(usuario, ctx or Contexto(), evento)
        return resposta(status, corpo)
    except AcessoNegadoError as exc:
        return resposta(403, {"erro": str(exc)})
    except ErroDeNegocio as exc:
        return resposta(exc.status, exc.como_dict())
