"""
Acesso a tabela unica do DynamoDB (schulz-certificacao), conforme a AV2 3.2.

    entidade           PK                     SK                        GSI1PK / GSI1SK
    instrumento        INST#<tag>             PERFIL
    calibracao         INST#<tag>             CAL#<calibracao_id>       STATUS#<status> / <criado_em>#<id>
    certificado        CERT#<ano>-<numero>    V#0001, V#0002...         INST#<tag> / CERT#<emitido_em>
    padrao             PADRAO#<codigo>        ATUAL, V#<data_calib.>    PADRAO / <codigo> (so ATUAL)
    de-para padrao     PADRAO_ALT#<codigo>    MAPA                                         (RH08)
    metrologista       METRO#<matricula>      PERFIL                    USUARIO#<login> / METRO
    nome -> matricula  METRO_NOME#<nome>      MAPA                                         (RH07)
    arquivo importado  ARQ#<sha256>           ARQ                                          (RH17)
    quarentena         QUAR#<aaaa-mm>         <calibracao_id>           QUARENTENA / <criado_em>#<id>
    contador           SEQ#CERT#<ano>         SEQ
    auditoria          AUD#<aaaa-mm-dd>       <data-hora>#<id>
    configuracao       CONFIG                 LABORATORIO

Numeros sempre como Decimal (RNF10); datas como texto ISO 8601.
"""
from __future__ import annotations

import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import boto3
from boto3.dynamodb.conditions import Key

from .calypso import normalizar

# --- chaves --------------------------------------------------------------

def chave_instrumento(tag: str) -> dict:
    return {"PK": f"INST#{tag}", "SK": "PERFIL"}


def chave_calibracao(tag: str, calibracao_id: str) -> dict:
    return {"PK": f"INST#{tag}", "SK": f"CAL#{calibracao_id}"}


def chave_padrao(codigo: str, versao: str = "ATUAL") -> dict:
    return {"PK": f"PADRAO#{codigo}", "SK": versao}


def chave_padrao_alternativo(codigo: str) -> dict:
    return {"PK": f"PADRAO_ALT#{codigo}", "SK": "MAPA"}


def chave_metrologista(matricula: str) -> dict:
    return {"PK": f"METRO#{matricula}", "SK": "PERFIL"}


def chave_nome_metrologista(nome: str) -> dict:
    return {"PK": f"METRO_NOME#{normalizar(nome)}", "SK": "MAPA"}


def chave_arquivo(sha256: str) -> dict:
    return {"PK": f"ARQ#{sha256}", "SK": "ARQ"}


def chave_quarentena(calibracao_id: str, quando: datetime) -> dict:
    return {"PK": f"QUAR#{quando:%Y-%m}", "SK": calibracao_id}


def chave_sequencia(ano: int) -> dict:
    return {"PK": f"SEQ#CERT#{ano}", "SK": "SEQ"}


def chave_certificado(numero: str, versao: int = 1) -> dict:
    return {"PK": f"CERT#{numero}", "SK": f"V#{versao:04d}"}


CHAVE_LABORATORIO = {"PK": "CONFIG", "SK": "LABORATORIO"}


# --- utilitarios ---------------------------------------------------------

def agora() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(momento: datetime) -> str:
    return momento.isoformat().replace("+00:00", "Z")


def novo_id() -> str:
    """UUID versao 7 (ordenavel por tempo), como pede a AV2 3.1.5."""
    milissegundos = int(time.time() * 1000)
    aleatorio = int.from_bytes(secrets.token_bytes(10), "big")
    valor = (milissegundos & ((1 << 48) - 1)) << 80
    valor |= 0x7 << 76                              # versao 7
    valor |= ((aleatorio >> 62) & 0xFFF) << 64      # rand_a (12 bits)
    valor |= 0b10 << 62                             # variante RFC 4122
    valor |= aleatorio & ((1 << 62) - 1)            # rand_b (62 bits)
    return str(uuid.UUID(int=valor))


def numero_exibicao(numero: str) -> str:
    """"2026-00091" -> "00091/2026", formato impresso no certificado."""
    ano, sequencial = numero.split("-")
    return f"{sequencial}/{ano}"


def tabela():
    return boto3.resource("dynamodb").Table(os.environ["TABELA"])


def criar_tabela(dynamodb):
    """Mesma definicao da AV2 3.2.3 (tabela unica + GSI1). Usada nos testes
    e no servidor local; na AWS a tabela vem do template SAM."""
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


# --- leituras ------------------------------------------------------------

class Repositorio:
    def __init__(self, tabela_dynamo=None):
        self.tabela = tabela_dynamo or tabela()
        self.cliente = self.tabela.meta.client

    def obter(self, chave: dict) -> Optional[dict]:
        return self.tabela.get_item(Key=chave).get("Item")

    def instrumento(self, tag: str) -> Optional[dict]:
        return self.obter(chave_instrumento(tag))

    def calibracao(self, tag: str, calibracao_id: str) -> Optional[dict]:
        return self.obter(chave_calibracao(tag, calibracao_id))

    def padrao(self, codigo: str) -> Optional[dict]:
        return self.obter(chave_padrao(codigo))

    def historico_padrao(self, codigo: str) -> list[dict]:
        resposta = self.tabela.query(
            KeyConditionExpression=Key("PK").eq(f"PADRAO#{codigo}") & Key("SK").begins_with("V#"),
            ScanIndexForward=False)
        return resposta["Items"]

    def padroes(self) -> list[dict]:
        return self._consultar_gsi("PADRAO")

    def resolver_codigo_padrao(self, codigo: str) -> Optional[str]:
        """RH08: aceita o codigo oficial (500.011) ou o legado (500008)."""
        if self.padrao(codigo):
            return codigo
        mapa = self.obter(chave_padrao_alternativo(codigo))
        return mapa["codigo"] if mapa else None

    def metrologista(self, matricula: str) -> Optional[dict]:
        return self.obter(chave_metrologista(matricula))

    def metrologista_por_nome(self, nome: str) -> Optional[dict]:
        """RH07: o nome do Report precisa estar na lista mestra."""
        mapa = self.obter(chave_nome_metrologista(nome))
        return self.metrologista(mapa["matricula"]) if mapa else None

    def metrologista_por_usuario(self, usuario: str) -> Optional[dict]:
        itens = self._consultar_gsi(f"USUARIO#{usuario}")
        return itens[0] if itens else None

    def arquivo(self, sha256: str) -> Optional[dict]:
        return self.obter(chave_arquivo(sha256))

    def calibracoes_por_status(self, status: str) -> list[dict]:
        return self._consultar_gsi(f"STATUS#{status}", recentes_primeiro=True)

    def quarentenas(self) -> list[dict]:
        return self._consultar_gsi("QUARENTENA", recentes_primeiro=True)

    def certificado(self, numero: str) -> Optional[dict]:
        """Versao mais recente do certificado (RNF09)."""
        resposta = self.tabela.query(KeyConditionExpression=Key("PK").eq(f"CERT#{numero}"),
                                     ScanIndexForward=False, Limit=1)
        itens = resposta["Items"]
        return itens[0] if itens else None

    def certificados_do_instrumento(self, tag: str) -> list[dict]:
        """RF11: historico por TAG, mais recente primeiro."""
        resposta = self.tabela.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(f"INST#{tag}") & Key("GSI1SK").begins_with("CERT#"),
            ScanIndexForward=False)
        return resposta["Items"]

    def auditoria(self, dia: str) -> list[dict]:
        resposta = self.tabela.query(KeyConditionExpression=Key("PK").eq(f"AUD#{dia}"),
                                     ScanIndexForward=False)
        return resposta["Items"]

    def laboratorio(self) -> dict:
        return self.obter(CHAVE_LABORATORIO) or {}

    def _consultar_gsi(self, gsi1pk: str, recentes_primeiro: bool = False) -> list[dict]:
        itens, inicio = [], None
        while True:
            argumentos: dict[str, Any] = {
                "IndexName": "GSI1",
                "KeyConditionExpression": Key("GSI1PK").eq(gsi1pk),
                "ScanIndexForward": not recentes_primeiro,
            }
            if inicio:
                argumentos["ExclusiveStartKey"] = inicio
            resposta = self.tabela.query(**argumentos)
            itens.extend(resposta["Items"])
            inicio = resposta.get("LastEvaluatedKey")
            if not inicio:
                return itens

    # --- escritas ---------------------------------------------------------

    def gravar(self, item: dict) -> None:
        self.tabela.put_item(Item=item)

    def transacao(self, operacoes: Iterable[dict]) -> None:
        """TransactWriteItems com itens em tipos Python (Decimal, str...).

        Cada operacao e {"Put"|"Update"|"ConditionCheck"|"Delete": {...}}. O
        cliente que vem do resource ja converte os tipos Python para o formato
        do DynamoDB, entao aqui so falta o nome da tabela.
        """
        convertidas = []
        for operacao in operacoes:
            (tipo, corpo), = operacao.items()
            convertidas.append({tipo: dict(corpo, TableName=self.tabela.name)})
        self.cliente.transact_write_items(TransactItems=convertidas)

    def proximo_numero_certificado(self, ano: int) -> str:
        """Contador atomico (UpdateItem com ADD) -> "2026-00092"."""
        resposta = self.tabela.update_item(
            Key=chave_sequencia(ano),
            UpdateExpression="ADD contador :um",
            ExpressionAttributeValues={":um": 1},
            ReturnValues="UPDATED_NEW")
        return f"{ano}-{int(resposta['Attributes']['contador']):05d}"
