"""
fn-site: entrega o frontend (SPA + PWA) pela Function URL da Lambda.

No AWS Academy a conta nao tem acesso ao CloudFront. A funcao faz o papel
dele: le o arquivo do bucket do site (privado) e devolve com HTTPS, o tipo do
conteudo e os mesmos cabecalhos de seguranca da Managed-SecurityHeadersPolicy.
O deploy continua publicando o site no bucket com o aws s3 sync.

O frontend usa caminhos relativos e rotas com # (#/consulta/<tag>), entao
todo caminho pedido corresponde a um arquivo; "/" vira index.html.
"""
from __future__ import annotations

import base64
import mimetypes
import os

import boto3
from botocore.exceptions import ClientError

# Mesmos valores da Managed-SecurityHeadersPolicy do CloudFront
CABECALHOS_SEGURANCA = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "1; mode=block",
}
TIPOS = {".js": "text/javascript", ".webmanifest": "application/manifest+json",
         ".svg": "image/svg+xml", ".css": "text/css", ".html": "text/html"}


def handler(evento, contexto=None, s3=None):
    return processar(evento, s3 or boto3.client("s3"), os.environ["BUCKET_SITE"])


def _resposta(status: int, texto: str) -> dict:
    return {"statusCode": status,
            "headers": {"Content-Type": "text/plain; charset=utf-8", **CABECALHOS_SEGURANCA},
            "body": texto}


def chave_do_caminho(caminho: str) -> str | None:
    """Caminho da URL -> chave no bucket; None se o caminho nao for aceito."""
    partes = [p for p in caminho.split("/") if p]
    if any(p in (".", "..") or "\\" in p for p in partes):
        return None
    return "/".join(partes) or "index.html"


def processar(evento: dict, s3, bucket: str) -> dict:
    metodo = evento.get("requestContext", {}).get("http", {}).get("method", "GET")
    if metodo not in ("GET", "HEAD"):
        return _resposta(405, "método não permitido")
    chave = chave_do_caminho(evento.get("rawPath") or "/")
    if chave is None:
        return _resposta(400, "caminho inválido")
    try:
        objeto = s3.get_object(Bucket=bucket, Key=chave)
    except ClientError as exc:
        # Sem s3:ListBucket o S3 responde AccessDenied em vez de NoSuchKey
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "AccessDenied"):
            return _resposta(404, "arquivo não encontrado")
        raise
    extensao = os.path.splitext(chave)[1].lower()
    # A extensao decide; o tipo gravado no S3 pode ser o generico
    # binary/octet-stream, que o navegador nao usa como imagem ou modulo
    tipo = (TIPOS.get(extensao) or mimetypes.guess_type(chave)[0]
            or objeto.get("ContentType") or "application/octet-stream")
    corpo = objeto["Body"].read()
    return {
        "statusCode": 200,
        "headers": {"Content-Type": tipo,
                    "Cache-Control": objeto.get("CacheControl") or "no-cache",
                    **CABECALHOS_SEGURANCA},
        # Function URL: base64 serve para texto e para os icones PNG
        "body": "" if metodo == "HEAD" else base64.b64encode(corpo).decode("ascii"),
        "isBase64Encoded": metodo != "HEAD",
    }
