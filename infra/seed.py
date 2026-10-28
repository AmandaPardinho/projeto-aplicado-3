"""
Carga inicial da PoC na AWS: cadastros no DynamoDB e usuarios de teste no Cognito.

    python infra/seed.py                      # usa as saidas da pilha schulz-pa3
    python infra/seed.py --padrao-valido-ate 2027-11-20

Os cadastros sao os de schulz.cadastros_exemplo (instrumento 703.1208, padrao
500.011, metrologistas e laboratorio). Rodar de novo nao apaga nada: item que
ja existe fica como esta (por exemplo, um padrao atualizado pela tela, UC03),
a menos que se passe --sobrescrever.

Os usuarios sao os de USUARIOS_TESTE, um por perfil, com senha aleatoria. As
senhas aparecem na tela e ficam em infra/senhas-teste.txt (fora do git). Para
um usuario que ja existe a senha so muda com --novas-senhas, ou quando ele nao
esta no arquivo. Os grupos ficam exatamente os de USUARIOS_TESTE.
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from schulz import cadastros_exemplo  # noqa: E402
from schulz.cadastros_exemplo import USUARIOS_TESTE  # noqa: E402

ARQUIVO_SENHAS = Path(__file__).resolve().parent / "senhas-teste.txt"


def saidas_da_pilha(pilha: str, regiao: str) -> dict:
    cf = boto3.client("cloudformation", region_name=regiao)
    pilha_ = cf.describe_stacks(StackName=pilha)["Stacks"][0]
    return {s["OutputKey"]: s["OutputValue"] for s in pilha_.get("Outputs", [])}


def carregar_cadastros(tabela, data_proxima_padrao: str, sobrescrever: bool = False) -> dict:
    """Grava os cadastros de exemplo; devolve quantos foram gravados e mantidos."""
    contagem = {"gravados": 0, "mantidos": 0}
    for item in cadastros_exemplo.todos(data_proxima_padrao=data_proxima_padrao):
        extras = {} if sobrescrever else {"ConditionExpression": "attribute_not_exists(PK)"}
        try:
            tabela.put_item(Item=item, **extras)
            contagem["gravados"] += 1
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            contagem["mantidos"] += 1
    return contagem


def gerar_senha() -> str:
    # Politica do pool: 10+ caracteres com maiuscula, minuscula e numero; o
    # simbolo cobre tambem a politica padrao do Cognito
    return f"{secrets.token_urlsafe(12)}Aa7!"


def criar_usuarios(cognito, pool_id: str, novas_senhas: bool = False,
                   senhas_conhecidas: set | None = None) -> dict:
    """Cria (ou completa) os usuarios de teste; devolve {login: senha nova ou None}.

    senhas_conhecidas: logins cuja senha ja esta no arquivo. Um usuario que ja
    existe mas nao esta ali (arquivo perdido, outra maquina) ganha senha nova,
    senao ninguem saberia entrar com ele.
    """
    senhas = {}
    for login, perfil in USUARIOS_TESTE.items():
        atributos = [{"Name": f"custom:{campo}", "Value": perfil[campo]}
                     for campo in ("matricula", "setor") if perfil.get(campo)]
        try:
            cognito.admin_create_user(UserPoolId=pool_id, Username=login,
                                      UserAttributes=atributos, MessageAction="SUPPRESS")
            novo = True
        except cognito.exceptions.UsernameExistsException:
            novo = False
            if atributos:
                cognito.admin_update_user_attributes(UserPoolId=pool_id, Username=login,
                                                     UserAttributes=atributos)
        senhas[login] = None
        sem_senha_conhecida = senhas_conhecidas is not None and login not in senhas_conhecidas
        if novo or novas_senhas or sem_senha_conhecida:
            senhas[login] = gerar_senha()
            cognito.admin_set_user_password(UserPoolId=pool_id, Username=login,
                                            Password=senhas[login], Permanent=True)
        _acertar_grupos(cognito, pool_id, login, set(perfil["grupos"]))
    return senhas


def _acertar_grupos(cognito, pool_id: str, login: str, grupos: set) -> None:
    """Deixa o usuario exatamente nos grupos da lista: tira os que sobraram."""
    atuais = {g["GroupName"] for g in cognito.admin_list_groups_for_user(
        UserPoolId=pool_id, Username=login)["Groups"]}
    for grupo in grupos - atuais:
        cognito.admin_add_user_to_group(UserPoolId=pool_id, Username=login, GroupName=grupo)
    for grupo in atuais - grupos:
        cognito.admin_remove_user_from_group(UserPoolId=pool_id, Username=login, GroupName=grupo)


def ler_senhas() -> dict:
    senhas = {}
    if ARQUIVO_SENHAS.exists():
        for linha in ARQUIVO_SENHAS.read_text().splitlines():
            if "\t" in linha and not linha.startswith("#"):
                login, senha = linha.split("\t", 1)
                senhas[login] = senha
    return senhas


def gravar_senhas(senhas: dict, url_app: str) -> None:
    novas = {k: v for k, v in senhas.items() if v}
    if not novas:
        return
    antigas = ler_senhas()
    antigas.update(novas)
    linhas = [f"# Usuarios de teste da PoC - {url_app}", "# login\tsenha"]
    linhas += [f"{login}\t{senha}" for login, senha in antigas.items()]
    # Criado ja com 0600: nem por um instante fica legivel por outros usuarios
    descritor = os.open(ARQUIVO_SENHAS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "w") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
    ARQUIVO_SENHAS.chmod(0o600)
    if os.name == "nt":
        # No Windows o chmod so mexe no "somente leitura": a ACL tira a heranca
        # da pasta e deixa o arquivo acessivel so ao usuario atual
        subprocess.run(["icacls", str(ARQUIVO_SENHAS), "/inheritance:r",
                        "/grant:r", f"{os.environ['USERNAME']}:F"],
                       check=True, stdout=subprocess.DEVNULL)


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argumentos.add_argument("--pilha", default="schulz-pa3")
    argumentos.add_argument("--regiao", default="us-east-1")
    argumentos.add_argument("--padrao-valido-ate", default="2026-08-31",
                            help="data_proxima_calibracao do 500.011 (a real e 2026-08-31, "
                                 "ja vencida: atualize pela tela de padroes ou passe uma data futura)")
    argumentos.add_argument("--sobrescrever", action="store_true",
                            help="regravar cadastros que ja existem")
    argumentos.add_argument("--novas-senhas", action="store_true",
                            help="trocar a senha de usuarios que ja existem")
    opcoes = argumentos.parse_args()

    saidas = saidas_da_pilha(opcoes.pilha, opcoes.regiao)
    tabela = boto3.resource("dynamodb", region_name=opcoes.regiao).Table(saidas["Tabela"])
    contagem = carregar_cadastros(tabela, opcoes.padrao_valido_ate, opcoes.sobrescrever)
    print(f"Cadastros: {contagem['gravados']} gravados, {contagem['mantidos']} já existiam.")

    cognito = boto3.client("cognito-idp", region_name=opcoes.regiao)
    senhas = criar_usuarios(cognito, saidas["CognitoPoolId"], opcoes.novas_senhas,
                            senhas_conhecidas=set(ler_senhas()))
    gravar_senhas(senhas, saidas["UrlApp"])
    print("Usuários de teste:")
    for login, senha in senhas.items():
        print(f"  {login:<20} {senha or '(já existia; senha mantida)'}")
    if any(senhas.values()):
        print(f"Senhas salvas em {ARQUIVO_SENHAS.relative_to(RAIZ)} (fora do git).")


if __name__ == "__main__":
    main()
