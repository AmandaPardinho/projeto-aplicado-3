"""
fn-ingestao: disparada pelo S3 quando o relatorio chega em entrada/ (E3-E5).

    0. integridade   SHA-256 do arquivo; hash repetido -> RH17
    1-6. ETL         calypso.ler_relatorio (formato, estruturar, limpar, tipar,
                     validar)
    5. padronizar    RH07 metrologista na lista mestra; RH08 de-para do codigo
                     da MMC; RN10 TAG e padrao do relatorio batem com o pedido
    E5. persistir    uma transacao: ARQ# (so se nao existir), checagem do
                     instrumento e do padrao, item da calibracao e auditoria

Qualquer regra bloqueante manda o arquivo para quarentena/<calibracao_id>/ e
grava so o registro de quarentena; nada vai para os itens operacionais.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import boto3
from botocore.exceptions import ClientError

from schulz import auditoria
from schulz.calypso import RelatorioInvalidoError, Violacao, ler_relatorio
from schulz.repositorio import (Repositorio, agora, chave_arquivo, chave_calibracao,
                                chave_instrumento, chave_padrao, chave_quarentena, iso)

DIAS_NA_QUARENTENA = 90


def handler(evento, contexto=None):
    s3 = boto3.client("s3")
    repositorio = Repositorio()
    resultados = []
    for registro in evento.get("Records", []):
        bucket = registro["s3"]["bucket"]["name"]
        chave = urllib.parse.unquote_plus(registro["s3"]["object"]["key"])
        resultados.append(processar(bucket, chave, s3, repositorio))
    return {"resultados": resultados}


def processar(bucket: str, chave: str, s3, repositorio: Repositorio) -> dict:
    objeto = s3.get_object(Bucket=bucket, Key=chave)
    meta = objeto.get("Metadata", {})
    conteudo = objeto["Body"].read()
    calibracao_id = meta["calibracao-id"]
    tag = meta["tag"]
    login = meta.get("usuario", "desconhecido")
    contexto = {"bucket": bucket, "chave": chave, "calibracao_id": calibracao_id,
                "tag": tag, "login": login}

    # Passo 0 - integridade e idempotencia (RH17)
    sha256 = hashlib.sha256(conteudo).hexdigest()
    ja_importado = repositorio.arquivo(sha256)
    if ja_importado:
        if ja_importado["calibracao_id"] == calibracao_id:
            # O S3 pode entregar o mesmo evento duas vezes: nada a fazer
            return {"calibracao_id": calibracao_id, "status": "JA_PROCESSADO"}
        return _quarentena(repositorio, s3, contexto, [Violacao(
            "RH17", "arquivo já importado na calibração "
            f"{ja_importado['calibracao_id']} do instrumento {ja_importado['tag']}")])

    try:
        relatorio = ler_relatorio(conteudo)
    except RelatorioInvalidoError as exc:
        return _quarentena(repositorio, s3, contexto, exc.violacoes)

    violacoes = []
    try:
        temperatura = Decimal(meta.get("temperatura", "").replace(",", "."))
    except InvalidOperation:
        temperatura = None
        violacoes.append(Violacao("RN09", "temperatura ambiente não informada no envio"))

    tecnico = repositorio.metrologista_por_nome(relatorio.metrologista or "")
    if tecnico is None:
        violacoes.append(Violacao("RH07", "metrologista do relatório não está na lista mestra",
                                  valor_bruto=relatorio.metrologista))
    if not relatorio.codigo_mmc:
        violacoes.append(Violacao("RN08", "código da MMC ausente no relatório"))
    else:
        codigo_padrao = repositorio.resolver_codigo_padrao(relatorio.codigo_mmc)
        if codigo_padrao is None:
            violacoes.append(Violacao("RN10", "padrão do relatório não cadastrado",
                                      valor_bruto=relatorio.codigo_mmc))
        elif codigo_padrao != meta["padrao"]:
            violacoes.append(Violacao(
                "RN10", f"o relatório foi medido no padrão {codigo_padrao}, "
                f"mas o envio indicou {meta['padrao']}", valor_bruto=relatorio.codigo_mmc))
    if relatorio.tag_do_plano and relatorio.tag_do_plano != tag:
        violacoes.append(Violacao("RN10", f"o plano de medição é do instrumento "
                                  f"{relatorio.tag_do_plano}, não de {tag}",
                                  valor_bruto=relatorio.plano))
    if violacoes:
        return _quarentena(repositorio, s3, contexto, violacoes)

    # Log das regras corretivas, guardado ao lado do original (fora de entrada/)
    if relatorio.transformacoes:
        s3.put_object(Bucket=bucket, Key=f"logs/{calibracao_id}.json",
                      Body=json.dumps(relatorio.transformacoes, ensure_ascii=False).encode(),
                      ContentType="application/json")

    momento = agora()
    calibracao = {
        **chave_calibracao(tag, calibracao_id),
        "GSI1PK": "STATUS#AGUARDANDO_REVISAO",
        "GSI1SK": f"{iso(momento)}#{calibracao_id}",
        "tipo": "CALIBRACAO",
        "calibracao_id": calibracao_id,
        "tag": tag,
        "status": "AGUARDANDO_REVISAO",
        "padrao_codigo": meta["padrao"],
        "temperatura_ambiente": temperatura,
        "enviado_por": login,
        "tecnico_matricula": tecnico["matricula"],
        "tecnico_nome": tecnico["nome"],
        "metrologista_relatorio": relatorio.metrologista,
        "codigo_mmc_relatorio": relatorio.codigo_mmc,
        "plano": relatorio.plano,
        "data_hora_medicao": relatorio.data_hora.isoformat() if relatorio.data_hora else None,
        "arquivo_sha256": sha256,
        "arquivo_s3": f"s3://{bucket}/{chave}",
        "caracteristicas": [c.como_item() for c in relatorio.caracteristicas],
        "criado_em": iso(momento),
    }
    try:
        repositorio.transacao([
            {"Put": {"Item": {**chave_arquivo(sha256), "calibracao_id": calibracao_id,
                              "tag": tag, "importado_em": iso(momento)},
                     "ConditionExpression": "attribute_not_exists(PK)"}},
            {"ConditionCheck": {"Key": chave_instrumento(tag),
                                "ConditionExpression": "attribute_exists(PK)"}},
            {"ConditionCheck": {"Key": chave_padrao(meta["padrao"]),
                                "ConditionExpression": "attribute_exists(PK)"}},
            {"Put": {"Item": calibracao, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"Put": {"Item": auditoria.item_auditoria(
                login, "importar_relatorio", f"INST#{tag}/CAL#{calibracao_id}", "sistema",
                {"sha256": sha256, "caracteristicas": len(relatorio.caracteristicas)})}},
        ])
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        motivos = [m.get("Code") for m in exc.response.get("CancellationReasons", [])]
        if motivos and motivos[0] == "ConditionalCheckFailed":
            violacao = Violacao("RH17", "arquivo já importado (gravação concorrente)")
        else:
            violacao = Violacao("RN10", "instrumento ou padrão não cadastrado")
        return _quarentena(repositorio, s3, contexto, [violacao])
    return {"calibracao_id": calibracao_id, "status": "AGUARDANDO_REVISAO"}


def _quarentena(repositorio: Repositorio, s3, contexto: dict, violacoes: list[Violacao]) -> dict:
    momento = agora()
    nome = contexto["chave"].rsplit("/", 1)[-1]
    destino = f"quarentena/{contexto['calibracao_id']}/{nome}"
    s3.copy_object(Bucket=contexto["bucket"], Key=destino,
                   CopySource={"Bucket": contexto["bucket"], "Key": contexto["chave"]})
    repositorio.gravar({
        **chave_quarentena(contexto["calibracao_id"], momento),
        "GSI1PK": "QUARENTENA",
        "GSI1SK": f"{iso(momento)}#{contexto['calibracao_id']}",
        "tipo": "QUARENTENA",
        "calibracao_id": contexto["calibracao_id"],
        "tag": contexto["tag"],
        "enviado_por": contexto["login"],
        "arquivo_s3": f"s3://{contexto['bucket']}/{destino}",
        "violacoes": [v.como_dict() for v in violacoes],
        "criado_em": iso(momento),
        "expira_em": int((momento + timedelta(days=DIAS_NA_QUARENTENA)).timestamp()),
    })
    auditoria.registrar(repositorio, contexto["login"], "relatorio_em_quarentena",
                        f"INST#{contexto['tag']}/CAL#{contexto['calibracao_id']}", "sistema",
                        {"regras": sorted({v.regra for v in violacoes})})
    return {"calibracao_id": contexto["calibracao_id"], "status": "QUARENTENA",
            "violacoes": [v.como_dict() for v in violacoes]}
