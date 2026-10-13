import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import app

PASTA_AMOSTRAS = os.path.join(os.path.dirname(__file__), "..", "sample_data")


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def _enviar(client, nome, conteudo):
    return client.post(
        "/processar",
        data={"planilha": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data",
    )


def _amostra(nome):
    with open(os.path.join(PASTA_AMOSTRAS, nome), "rb") as f:
        return f.read()


def test_pagina_inicial_carrega(client):
    assert client.get("/").status_code == 200


def test_upload_sem_arquivo_retorna_400(client):
    resposta = client.post("/processar", data={}, content_type="multipart/form-data")
    assert resposta.status_code == 400


def test_extensao_nao_suportada_retorna_400(client):
    assert _enviar(client, "dados.csv", b"a,b").status_code == 400


def test_planilha_aprovada_mostra_parecer(client):
    resposta = _enviar(client, "ok.xlsx", _amostra("amostra_aprovado.xlsx"))
    assert resposta.status_code == 200
    assert b"APROVADO" in resposta.data


def test_planilha_reprovada_mostra_parecer(client):
    resposta = _enviar(client, "ruim.xlsx", _amostra("amostra_reprovado.xlsx"))
    assert resposta.status_code == 200
    assert b"REPROVADO" in resposta.data


def test_arquivo_corrompido_retorna_422(client):
    assert _enviar(client, "quebrado.xlsx", b"nao e xlsx").status_code == 422
