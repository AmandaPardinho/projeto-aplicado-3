import json
import os
import sys
from datetime import date
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.update({
    "AWS_ACCESS_KEY_ID": "teste",
    "AWS_SECRET_ACCESS_KEY": "teste",
    "AWS_DEFAULT_REGION": "sa-east-1",
    "TABELA": "schulz-certificacao",
    "BUCKET_ENTRADA": "schulz-entrada-teste",
    "BUCKET_CERTIFICADOS": "schulz-certificados-teste",
    "URL_APP": "https://app.exemplo",
    "MARCA_PROVA_DE_CONCEITO": "1",
})

# Dia da calibracao real (26/08/2026): o padrao 500.011 ainda esta valido
DIA_DA_CALIBRACAO = date(2026, 8, 26)


def criar_tabela(dynamodb):
    """Mesma definicao da AV2 3.2.3 (tabela unica + GSI1)."""
    return dynamodb.create_table(
        TableName=os.environ["TABELA"],
        BillingMode="PROVISIONED",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"}
                              for n in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                   {"AttributeName": "SK", "KeyType": "RANGE"}],
        ProvisionedThroughput={"ReadCapacityUnits": 15, "WriteCapacityUnits": 15},
        GlobalSecondaryIndexes=[{
            "IndexName": "GSI1",
            "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                          {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        }],
    )


@pytest.fixture
def aws():
    from schulz import cadastros_exemplo
    from schulz.repositorio import Repositorio

    with mock_aws():
        dynamodb = boto3.resource("dynamodb")
        tabela = criar_tabela(dynamodb)
        s3 = boto3.client("s3")
        for bucket in (os.environ["BUCKET_ENTRADA"], os.environ["BUCKET_CERTIFICADOS"]):
            s3.create_bucket(Bucket=bucket,
                             CreateBucketConfiguration={"LocationConstraint": "sa-east-1"})
        s3.put_bucket_versioning(Bucket=os.environ["BUCKET_CERTIFICADOS"],
                                 VersioningConfiguration={"Status": "Enabled"})
        for item in cadastros_exemplo.todos():
            tabela.put_item(Item=item)
        yield Repositorio(tabela), s3


def evento(rota: str, grupos=(), login="usuario.teste", caminho=None, consulta=None,
           corpo=None, matricula=None, setor=None):
    claims = {"cognito:username": login, "cognito:groups": "[" + " ".join(grupos) + "]"}
    if matricula:
        claims["custom:matricula"] = matricula
    if setor:
        claims["custom:setor"] = setor
    return {
        "routeKey": rota,
        "pathParameters": caminho or {},
        "queryStringParameters": consulta,
        "body": json.dumps(corpo) if corpo is not None else None,
        "requestContext": {"authorizer": {"jwt": {"claims": claims}}},
    }
