"""
Servidor local para testar o frontend sem conta AWS.

    cd backend
    python servidor_local.py          # http://localhost:8000

Roda as mesmas funcoes Lambda (fn-api, fn-ingestao, fn-emissao) com DynamoDB
e S3 simulados pelo moto, em memoria: tudo some quando o servidor para.

Diferencas em relacao a AWS, todas so de infraestrutura:
  - login: sem Cognito; a tela lista usuarios de teste e o navegador manda o
    login no cabecalho X-Usuario-Local, que vira as claims do token;
  - upload: o presigned POST aponta para /_local/s3, que grava no S3 simulado
    e chama a fn-ingestao na hora (na AWS e o evento do S3);
  - download: a URL pre-assinada vira /_local/download/<numero>.

O padrao 500.011 e carregado valido ate 2027 (o real venceu em 31/08/2026),
e uma calibracao do 703.1208 ja entra na fila para a revisao.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from email.parser import BytesParser
from email.policy import default as politica_email
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

RAIZ = Path(__file__).resolve().parent
FRONTEND = RAIZ.parent / "frontend"
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ.parent / "infra"))  # report_exemplo: Report do Calypso gerado na hora

os.environ.update({
    "AWS_ACCESS_KEY_ID": "local",
    "AWS_SECRET_ACCESS_KEY": "local",
    "AWS_DEFAULT_REGION": "sa-east-1",
    "TABELA": "schulz-certificacao",
    "BUCKET_ENTRADA": "schulz-entrada-local",
    "BUCKET_CERTIFICADOS": "schulz-certificados-local",
    "MARCA_PROVA_DE_CONCEITO": "1",
})
os.environ.pop("FUNCAO_EMISSAO", None)  # emissao roda no mesmo processo

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

from report_exemplo import report_exemplo  # noqa: E402
from schulz.cadastros_exemplo import USUARIOS_TESTE as USUARIOS  # noqa: E402


TAMANHO_MAXIMO = 5 * 1024 * 1024
TIPOS = {".js": "text/javascript", ".webmanifest": "application/manifest+json",
         ".svg": "image/svg+xml", ".css": "text/css", ".html": "text/html"}


def _rotas():
    from handlers.api import ROTAS
    rotas = []
    for chave in ROTAS:
        metodo, caminho = chave.split(" ", 1)
        padrao = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", caminho)
        rotas.append((metodo, re.compile(f"^{padrao}$"), chave))
    return rotas


def preparar(carregar_exemplo: bool):
    from schulz import cadastros_exemplo
    from schulz.repositorio import Repositorio, criar_tabela, novo_id
    from handlers import ingestao

    tabela = criar_tabela(boto3.resource("dynamodb"))
    s3 = boto3.client("s3")
    for bucket in (os.environ["BUCKET_ENTRADA"], os.environ["BUCKET_CERTIFICADOS"]):
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "sa-east-1"})
    s3.put_bucket_versioning(Bucket=os.environ["BUCKET_CERTIFICADOS"],
                             VersioningConfiguration={"Status": "Enabled"})
    for item in cadastros_exemplo.todos(data_proxima_padrao="2027-11-20"):
        tabela.put_item(Item=item)

    if carregar_exemplo:
        chave = "entrada/exemplo/703.1208.xlsx"
        s3.put_object(Bucket=os.environ["BUCKET_ENTRADA"], Key=chave, Body=report_exemplo(),
                      Metadata={"calibracao-id": novo_id(),
                                "tag": "703.1208", "padrao": "500.011",
                                "temperatura": "20.4", "usuario": "tecnico.exemplo"})
        ingestao.processar(os.environ["BUCKET_ENTRADA"], chave, s3, Repositorio(tabela))


class Manipulador(BaseHTTPRequestHandler):
    rotas = []
    porta = 8000

    def log_message(self, formato, *args):
        sys.stderr.write(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")

    # --- respostas ---------------------------------------------------------

    def _enviar(self, status: int, corpo: bytes, tipo: str, extras: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extras or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, status: int, dados):
        self._enviar(status, json.dumps(dados, ensure_ascii=False).encode(), "application/json")

    def _ler_corpo(self) -> bytes:
        tamanho = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(tamanho) if tamanho else b""

    # --- metodos HTTP ------------------------------------------------------

    def do_GET(self):
        caminho = urlsplit(self.path).path
        if caminho.startswith("/api/"):
            return self._api()
        if caminho == "/config.js":
            return self._config()
        if caminho == "/_local/report-exemplo.xlsx":
            return self._enviar(200, report_exemplo(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                {"Content-Disposition": 'attachment; filename="report-703.1208.xlsx"'})
        if caminho.startswith("/_local/download/"):
            return self._download(unquote(caminho.rsplit("/", 1)[-1]))
        return self._estatico(caminho)

    def do_POST(self):
        caminho = urlsplit(self.path).path
        if caminho == "/_local/s3":
            return self._upload()
        return self._api()

    def do_PUT(self):
        return self._api()

    # --- API ---------------------------------------------------------------

    def _api(self):
        from handlers import api

        partes = urlsplit(self.path)
        caminho = partes.path.removeprefix("/api")
        login = self.headers.get("X-Usuario-Local")
        if login not in USUARIOS:
            return self._json(401, {"erro": "não autenticado"})
        for metodo, regex, chave in self.rotas:
            achado = regex.match(caminho)
            if metodo == self.command and achado:
                break
        else:
            return self._json(404, {"erro": "rota não encontrada"})

        perfil = USUARIOS[login]
        claims = {"cognito:username": login, "cognito:groups": "[" + " ".join(perfil["grupos"]) + "]"}
        if perfil.get("matricula"):
            claims["custom:matricula"] = perfil["matricula"]
        if perfil.get("setor"):
            claims["custom:setor"] = perfil["setor"]
        corpo = self._ler_corpo()
        evento = {
            "routeKey": chave,
            "pathParameters": {k: unquote(v) for k, v in achado.groupdict().items()},
            "queryStringParameters": dict(parse_qsl(partes.query)) or None,
            "body": corpo.decode("utf-8") if corpo else None,
            "requestContext": {"authorizer": {"jwt": {"claims": claims}}},
        }
        resposta = api.handler(evento)
        dados = json.loads(resposta["body"])
        if resposta["statusCode"] < 300:
            if chave == "POST /calibracoes/upload":
                dados["upload"]["url"] = "/_local/s3"
            elif chave == "GET /certificados/{numero}/download":
                dados["url"] = f"/_local/download/{evento['pathParameters']['numero']}"
        self._json(resposta["statusCode"], dados)

    def _config(self):
        config = {
            "modo": "local",
            "api": "/api",
            "cognito": {},
            "usuariosLocais": [{"login": k, "grupos": v["grupos"]} for k, v in USUARIOS.items()],
            "exemploReport": "/_local/report-exemplo.xlsx",
        }
        self._enviar(200, f"window.SCHULZ_CONFIG = {json.dumps(config)};\n".encode(), "text/javascript")

    # --- S3 simulado -------------------------------------------------------

    def _upload(self):
        """Faz o papel do S3 (presigned POST) e do evento que dispara a fn-ingestao."""
        from handlers import ingestao
        from schulz.repositorio import Repositorio

        corpo = self._ler_corpo()
        if len(corpo) > TAMANHO_MAXIMO + 64 * 1024:
            return self._enviar(400, b"EntityTooLarge", "text/plain")
        mensagem = BytesParser(policy=politica_email).parsebytes(
            f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + corpo)
        campos, arquivo = {}, None
        for parte in mensagem.iter_parts():
            nome = parte.get_param("name", header="content-disposition")
            if nome == "file":
                arquivo = parte.get_payload(decode=True)
            else:
                campos[nome] = parte.get_content()
        if not arquivo or "key" not in campos:
            return self._enviar(400, b"campos do formulario incompletos", "text/plain")
        metadados = {k.removeprefix("x-amz-meta-"): v for k, v in campos.items()
                     if k.startswith("x-amz-meta-")}
        s3 = boto3.client("s3")
        s3.put_object(Bucket=os.environ["BUCKET_ENTRADA"], Key=campos["key"], Body=arquivo,
                      Metadata=metadados)
        ingestao.processar(os.environ["BUCKET_ENTRADA"], campos["key"], s3, Repositorio())
        self._enviar(204, b"", "text/plain")

    def _download(self, numero: str):
        from schulz.repositorio import Repositorio

        certificado = Repositorio().certificado(numero)
        if not certificado:
            return self._enviar(404, b"certificado nao encontrado", "text/plain")
        bucket, chave = certificado["pdf_s3"].removeprefix("s3://").split("/", 1)
        pdf = boto3.client("s3").get_object(Bucket=bucket, Key=chave)["Body"].read()
        self._enviar(200, pdf, "application/pdf",
                     {"Content-Disposition": f'inline; filename="certificado-{numero}.pdf"'})

    # --- arquivos do frontend ----------------------------------------------

    def _estatico(self, caminho: str):
        relativo = unquote(caminho).lstrip("/") or "index.html"
        arquivo = (FRONTEND / relativo).resolve()
        if not arquivo.is_relative_to(FRONTEND.resolve()) or not arquivo.is_file():
            return self._enviar(404, b"nao encontrado", "text/plain")
        tipo = TIPOS.get(arquivo.suffix) or mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
        self._enviar(200, arquivo.read_bytes(), tipo)


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argumentos.add_argument("--porta", type=int, default=8000)
    argumentos.add_argument("--vazio", action="store_true", help="não carregar a calibração de exemplo")
    opcoes = argumentos.parse_args()

    os.environ["URL_APP"] = f"http://localhost:{opcoes.porta}/"
    with mock_aws():
        preparar(carregar_exemplo=not opcoes.vazio)
        Manipulador.rotas = _rotas()
        servidor = ThreadingHTTPServer(("127.0.0.1", opcoes.porta), Manipulador)
        print(f"Servidor local em http://localhost:{opcoes.porta}  (Ctrl+C para parar)")
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
