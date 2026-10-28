"""
fn-emissao: reserva o numero, gera o PDF e grava o certificado (E7, AV2 3.1.3).

Ordem pensada para nao deixar o sistema inconsistente se algo falhar no meio:

    1. revisa de novo (RN04, RN06, RN08) e confere o signatario (RN05)
    2. reserva o numero no contador atomico e passa a calibracao a EMITINDO;
       uma nova tentativa reaproveita o numero ja reservado
    3. gera o PDF a partir da copia congelada dos valores
    4. grava em certificados/<ano>/<numero>.pdf (Object Lock no bucket)
    5. transacao: item imutavel do certificado (V#0001), nova checagem de
       pode_assinar_certificado, calibracao -> EMITIDA e auditoria

Invocada pela fn-api; tambem pode ser chamada direto (testes e execucao local).
"""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import date

import boto3
from botocore.exceptions import ClientError

from schulz import auditoria, revisao
from schulz.certificado import codigo_verificacao, gerar_pdf
from schulz.erros import ErroDeNegocio, NaoEncontradoError
from schulz.repositorio import (Repositorio, agora, chave_calibracao, chave_certificado,
                                chave_metrologista, iso, numero_exibicao)


def handler(evento, contexto=None):
    try:
        return {"ok": True, "certificado": processar(evento, Repositorio(), boto3.client("s3"))}
    except ErroDeNegocio as exc:
        return {"ok": False, **exc.como_dict()}


def processar(evento: dict, repositorio: Repositorio, s3, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    tag, calibracao_id = evento["tag"], evento["calibracao_id"]
    login, matricula = evento["login"], evento["matricula"]

    calibracao = repositorio.calibracao(tag, calibracao_id)
    if calibracao is None:
        raise NaoEncontradoError("calibração não encontrada")
    if calibracao["status"] == "EMITIDA":
        return _resumo(repositorio.certificado(calibracao["numero_certificado"]))
    if calibracao["status"] not in ("AGUARDANDO_REVISAO", "EMITINDO"):
        raise ErroDeNegocio(f"calibração com status {calibracao['status']} não pode ser emitida", 409)

    instrumento = repositorio.instrumento(tag)
    padrao = repositorio.padrao(calibracao["padrao_codigo"])
    signatario = repositorio.metrologista(matricula)
    if not signatario or not signatario.get("pode_assinar_certificado"):
        raise ErroDeNegocio("RN05: usuário não é signatário autorizado", 403)
    resultado = revisao.revisar(calibracao, padrao, instrumento, hoje)
    if resultado.bloqueios:
        raise ErroDeNegocio("emissão bloqueada", 422, list(resultado.bloqueios))

    numero = calibracao.get("numero_certificado") or _reservar_numero(repositorio, calibracao, hoje)

    momento = agora()
    laboratorio = repositorio.laboratorio()
    valores = revisao.valores_do_certificado(
        numero=numero, numero_exibicao=numero_exibicao(numero), calibracao=calibracao,
        instrumento=instrumento, padrao=padrao, signatario=signatario,
        laboratorio=laboratorio, revisao=resultado,
        url_consulta=f"{os.environ.get('URL_APP', '').rstrip('/')}/#/consulta/{tag}",
        emitido_em=iso(momento),
        marca_prova_de_conceito=os.environ.get("MARCA_PROVA_DE_CONCEITO", "1") == "1",
    )
    pdf = gerar_pdf(valores)
    resumo = hashlib.sha256(pdf).digest()
    sha256_pdf = resumo.hex()
    ano, sequencial = numero.split("-")
    bucket = os.environ["BUCKET_CERTIFICADOS"]
    chave_pdf = f"certificados/{ano}/{sequencial}.pdf"
    # Com Object Lock o S3 exige checksum no PUT; o SHA-256 tambem garante
    # que o arquivo gravado e o mesmo cujo hash vai para o certificado
    gravado = s3.put_object(Bucket=bucket, Key=chave_pdf, Body=pdf,
                            ContentType="application/pdf",
                            ChecksumSHA256=base64.b64encode(resumo).decode(),
                            Metadata={"numero": numero, "sha256": sha256_pdf})

    certificado = {
        **chave_certificado(numero),
        "GSI1PK": f"INST#{tag}",
        "GSI1SK": f"CERT#{iso(momento)}#{numero}",
        "tipo": "CERTIFICADO",
        "numero": numero,
        "numero_exibicao": numero_exibicao(numero),
        "versao": 1,
        "tag": tag,
        "setor": instrumento.get("setor"),
        "calibracao_id": calibracao_id,
        "situacao": resultado.parecer.situacao,
        "emitido_em": iso(momento),
        "emitido_por": login,
        "pdf_s3": f"s3://{bucket}/{chave_pdf}",
        "pdf_versao_s3": gravado.get("VersionId"),
        "pdf_sha256": sha256_pdf,
        "codigo_verificacao": codigo_verificacao(valores),
        "valores": valores,
    }
    try:
        repositorio.transacao([
            {"Put": {"Item": certificado, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"ConditionCheck": {"Key": chave_metrologista(matricula),
                                "ConditionExpression": "pode_assinar_certificado = :sim",
                                "ExpressionAttributeValues": {":sim": True}}},
            {"Update": {"Key": chave_calibracao(tag, calibracao_id),
                        "UpdateExpression": "SET #s = :emitida, GSI1PK = :gsi, atualizado_em = :agora",
                        "ConditionExpression": "#s = :emitindo",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {":emitida": "EMITIDA", ":emitindo": "EMITINDO",
                                                      ":gsi": "STATUS#EMITIDA", ":agora": iso(momento)}}},
            {"Put": {"Item": auditoria.item_auditoria(
                login, "emitir_certificado", f"CERT#{numero}", "sistema",
                {"tag": tag, "calibracao_id": calibracao_id, "pdf_sha256": sha256_pdf},
                momento)}},
        ])
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            raise ErroDeNegocio("emissão não concluída; a calibração continua EMITINDO com o "
                                f"número {numero_exibicao(numero)} reservado", 409) from exc
        raise
    return _resumo(certificado)


def _reservar_numero(repositorio: Repositorio, calibracao: dict, hoje: date) -> str:
    numero = repositorio.proximo_numero_certificado(hoje.year)
    try:
        repositorio.tabela.update_item(
            Key=chave_calibracao(calibracao["tag"], calibracao["calibracao_id"]),
            UpdateExpression="SET #s = :emitindo, GSI1PK = :gsi, numero_certificado = :n",
            ConditionExpression="#s = :aguardando",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":emitindo": "EMITINDO", ":gsi": "STATUS#EMITINDO",
                                       ":n": numero, ":aguardando": "AGUARDANDO_REVISAO"})
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ErroDeNegocio("a calibração mudou de status durante a emissão; tente de novo",
                                409) from exc
        raise
    return numero


def _resumo(certificado: dict) -> dict:
    return {campo: certificado.get(campo) for campo in (
        "numero", "numero_exibicao", "versao", "tag", "calibracao_id", "situacao",
        "emitido_em", "emitido_por", "pdf_sha256", "codigo_verificacao")}
