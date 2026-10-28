"""Fase 3: template SAM coerente com o codigo, carga inicial e etiquetas."""
import importlib
import os
import sys
from pathlib import Path

import boto3
import pytest
import yaml
from moto import mock_aws

INFRA = Path(__file__).resolve().parents[2] / "infra"
sys.path.insert(0, str(INFRA))


class _CarregadorCloudFormation(yaml.SafeLoader):
    """Le !Ref, !Sub, !GetAtt etc. como valores comuns."""


def _tag(carregador, sufixo, no):
    if isinstance(no, yaml.ScalarNode):
        return {sufixo: carregador.construct_scalar(no)}
    if isinstance(no, yaml.SequenceNode):
        return {sufixo: carregador.construct_sequence(no)}
    return {sufixo: carregador.construct_mapping(no)}


_CarregadorCloudFormation.add_multi_constructor("!", _tag)


@pytest.fixture(scope="module")
def template():
    return yaml.load((INFRA / "template.yaml").read_text(), Loader=_CarregadorCloudFormation)


def _funcoes(template):
    return {nome: r for nome, r in template["Resources"].items()
            if r["Type"] == "AWS::Serverless::Function"}


def test_rotas_do_template_sao_as_da_api(template):
    from handlers.api import ROTAS

    eventos = _funcoes(template)["FnApi"]["Properties"]["Events"].values()
    rotas = {f"{e['Properties']['Method']} {e['Properties']['Path']}" for e in eventos}
    assert rotas == set(ROTAS)


def test_handlers_do_template_existem(template):
    for funcao in _funcoes(template).values():
        modulo, nome = funcao["Properties"]["Handler"].rsplit(".", 1)
        assert callable(getattr(importlib.import_module(modulo), nome))


def test_tabela_do_template_igual_a_dos_testes(template):
    from schulz.repositorio import criar_tabela

    propriedades = template["Resources"]["Tabela"]["Properties"]
    with mock_aws():
        local = criar_tabela(boto3.resource("dynamodb")).meta.client.describe_table(
            TableName=os.environ["TABELA"])["Table"]
    assert propriedades["TableName"] == local["TableName"]
    assert propriedades["KeySchema"] == local["KeySchema"]
    gsi = propriedades["GlobalSecondaryIndexes"][0]
    assert gsi["IndexName"] == local["GlobalSecondaryIndexes"][0]["IndexName"]
    assert gsi["KeySchema"] == local["GlobalSecondaryIndexes"][0]["KeySchema"]
    # Camada gratuita: 25 RCU/WCU no total (AV2: 20/20)
    total = propriedades["ProvisionedThroughput"]["ReadCapacityUnits"] + \
        gsi["ProvisionedThroughput"]["ReadCapacityUnits"]
    assert total <= 25


def test_ingestao_so_dispara_em_entrada(template):
    # quarentena/ e logs/ ficam no mesmo bucket: sem o filtro a funcao se
    # dispararia de novo a cada arquivo que ela mesma grava
    evento = _funcoes(template)["FnIngestao"]["Properties"]["Events"]["RelatorioRecebido"]
    assert evento["Properties"]["Filter"]["S3Key"]["Rules"] == [{"Name": "prefix", "Value": "entrada/"}]


def test_grupos_do_cognito_sao_os_perfis(template):
    from schulz.autorizacao import TODOS

    grupos = {r["Properties"]["GroupName"] for r in template["Resources"].values()
              if r["Type"] == "AWS::Cognito::UserPoolGroup"}
    assert grupos == set(TODOS)


def test_usuario_nao_altera_matricula_nem_setor(template):
    cliente = template["Resources"]["UsuariosCliente"]["Properties"]
    assert not any(a.startswith("custom:") for a in cliente["WriteAttributes"])
    assert "aws.cognito.signin.user.admin" not in cliente["AllowedOAuthScopes"]


def test_urls_pre_assinadas_regionais_e_sigv4():
    from handlers.api import _cliente_s3

    s3 = _cliente_s3()
    bucket = "schulz-entrada-123456789012-sa-east-1"
    assert s3.generate_presigned_post(bucket, "k")["url"] == f"https://{bucket}.s3.sa-east-1.amazonaws.com/"
    url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": "k"})
    assert url.startswith(f"https://{bucket}.s3.sa-east-1.amazonaws.com/k?") and "X-Amz-Signature" in url


# --- seed ----------------------------------------------------------------

@pytest.fixture
def cognito():
    from schulz.autorizacao import TODOS

    with mock_aws():
        cliente = boto3.client("cognito-idp")
        pool = cliente.create_user_pool(
            PoolName="schulz-usuarios",
            Schema=[{"Name": "matricula", "AttributeDataType": "String", "Mutable": True},
                    {"Name": "setor", "AttributeDataType": "String", "Mutable": True}],
        )["UserPool"]["Id"]
        for grupo in TODOS:
            cliente.create_group(UserPoolId=pool, GroupName=grupo)
        yield cliente, pool


def test_seed_cria_usuarios_com_perfil_matricula_e_setor(cognito):
    import seed
    from schulz.cadastros_exemplo import USUARIOS_TESTE

    cliente, pool = cognito
    senhas = seed.criar_usuarios(cliente, pool)
    assert set(senhas) == set(USUARIOS_TESTE) and all(senhas.values())

    usuario = cliente.admin_get_user(UserPoolId=pool, Username="signatario.exemplo")
    atributos = {a["Name"]: a["Value"] for a in usuario["UserAttributes"]}
    assert atributos["custom:matricula"] == "1002"
    assert usuario["UserStatus"] == "CONFIRMED"
    grupos = cliente.admin_list_groups_for_user(UserPoolId=pool, Username="signatario.exemplo")
    assert {g["GroupName"] for g in grupos["Groups"]} == {"revisor", "signatario"}

    # Segunda execucao nao troca senha de quem ja existe
    assert not any(seed.criar_usuarios(cliente, pool).values())
    assert all(seed.criar_usuarios(cliente, pool, novas_senhas=True).values())


def test_seed_nao_sobrescreve_padrao_atualizado(aws):
    import seed
    from schulz.repositorio import chave_padrao

    repositorio, _ = aws  # a fixture ja gravou os cadastros
    repositorio.tabela.update_item(Key=chave_padrao("500.011"),
                                   UpdateExpression="SET data_proxima_calibracao = :d",
                                   ExpressionAttributeValues={":d": "2027-11-20"})
    contagem = seed.carregar_cadastros(repositorio.tabela, "2026-08-31")
    assert contagem["gravados"] == 0 and contagem["mantidos"] > 0
    assert repositorio.padrao("500.011")["data_proxima_calibracao"] == "2027-11-20"

    seed.carregar_cadastros(repositorio.tabela, "2026-08-31", sobrescrever=True)
    assert repositorio.padrao("500.011")["data_proxima_calibracao"] == "2026-08-31"


def test_senha_gerada_atende_a_politica_do_pool():
    import seed

    for _ in range(50):
        senha = seed.gerar_senha()
        assert len(senha) >= 10
        assert any(c.islower() for c in senha) and any(c.isupper() for c in senha)
        assert any(c.isdigit() for c in senha)


# --- etiquetas -----------------------------------------------------------

def test_etiquetas(tmp_path):
    import etiquetas

    assert etiquetas.url_consulta("https://d1.cloudfront.net/", "703.1208") == \
        "https://d1.cloudfront.net/#/consulta/703.1208"
    destino = tmp_path / "etiquetas.pdf"
    assert etiquetas.gerar("https://d1.cloudfront.net/", ["703.1208"], destino) == 24
    assert destino.read_bytes().startswith(b"%PDF")
    assert etiquetas.gerar("https://d1.cloudfront.net/", ["703.1208", "703.1209"], destino,
                           preencher=False) == 2
