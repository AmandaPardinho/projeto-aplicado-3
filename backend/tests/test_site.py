"""fn-site: entrega do frontend pela Function URL (no lugar do CloudFront)."""
import base64

import boto3
import pytest
from moto import mock_aws

from handlers import site

BUCKET = "schulz-web-teste"


@pytest.fixture
def s3():
    with mock_aws():
        cliente = boto3.client("s3")
        cliente.create_bucket(Bucket=BUCKET,
                              CreateBucketConfiguration={"LocationConstraint": "sa-east-1"})
        cliente.put_object(Bucket=BUCKET, Key="index.html", Body=b"<!doctype html>",
                           ContentType="text/html", CacheControl="no-cache")
        cliente.put_object(Bucket=BUCKET, Key="js/app.js", Body=b"export {};",
                           ContentType="application/javascript")
        cliente.put_object(Bucket=BUCKET, Key="icons/icone-192.png", Body=b"\x89PNG\r\n\x1a\n")
        yield cliente


def pedir(s3, caminho, metodo="GET"):
    evento = {"rawPath": caminho, "requestContext": {"http": {"method": metodo}}}
    return site.processar(evento, s3, BUCKET)


def test_raiz_entrega_index_html(s3):
    resposta = pedir(s3, "/")
    assert resposta["statusCode"] == 200
    assert resposta["isBase64Encoded"] is True
    assert base64.b64decode(resposta["body"]) == b"<!doctype html>"
    assert resposta["headers"]["Content-Type"] == "text/html"
    assert resposta["headers"]["Cache-Control"] == "no-cache"


def test_modulo_js_sai_com_o_tipo_certo(s3):
    # Navegador recusa <script type="module"> com tipo errado; o sync do S3
    # pode gravar outro tipo, entao a extensao decide
    resposta = pedir(s3, "/js/app.js")
    assert resposta["headers"]["Content-Type"] == "text/javascript"


def test_binario_volta_intacto(s3):
    resposta = pedir(s3, "/icons/icone-192.png")
    assert base64.b64decode(resposta["body"]) == b"\x89PNG\r\n\x1a\n"
    assert resposta["headers"]["Content-Type"] == "image/png"


def test_cabecalhos_de_seguranca_do_cloudfront(s3):
    for caminho in ("/", "/nao-existe.js"):
        cabecalhos = pedir(s3, caminho)["headers"]
        assert cabecalhos["Strict-Transport-Security"].startswith("max-age=")
        assert cabecalhos["X-Content-Type-Options"] == "nosniff"
        assert cabecalhos["X-Frame-Options"] == "SAMEORIGIN"


def test_arquivo_inexistente_e_404(s3):
    assert pedir(s3, "/nao-existe.js")["statusCode"] == 404


def test_so_leitura(s3):
    assert pedir(s3, "/", "POST")["statusCode"] == 405
    resposta = pedir(s3, "/", "HEAD")
    assert resposta["statusCode"] == 200 and resposta["body"] == ""


@pytest.mark.parametrize("caminho", ["/../segredo", "/js/../../x", "/js/..\\x"])
def test_caminho_com_subida_de_pasta_e_recusado(s3, caminho):
    assert pedir(s3, caminho)["statusCode"] == 400
