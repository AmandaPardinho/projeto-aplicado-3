"""
Verificacao de ponta a ponta da aplicacao local (python app.py --verificar).

Sobe o servidor, faz por HTTP o mesmo caminho que uma pessoa faz pela tela e
encerra com codigo 0 (tudo certo) ou 1 (alguma etapa falhou). E o teste que o
GitHub Actions roda no Windows a cada push, e serve tambem para o avaliador
confirmar a instalacao sem abrir o navegador.

    1. a interface e servida: index.html, config.js e todos os modulos JS importados
    2. tecnico envia exemplos/1-aprovado.xlsx  -> calibracao CONFORME, emissao liberada
    3. signatario emite o certificado          -> PDF com QR Code disponivel
    4. tecnico envia exemplos/2-reprovado.xlsx -> NAO_CONFORME (tolerancia e banda de guarda)
    5. tecnico envia exemplos/3-com-sujeira.xlsx -> higienizado e CONFORME
    6. tecnico envia exemplos/4-quarentena.xlsx -> recusado, vai para a quarentena
    7. consulta do instrumento pelo TAG mostra o certificado emitido
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import boto3

import servidor_local

EXEMPLOS = Path(__file__).resolve().parents[1] / "exemplos"
TAG, PADRAO = "703.1208", "500.011"


class Cliente:
    def __init__(self, porta: int):
        self.base = f"http://127.0.0.1:{porta}"

    def pedir(self, metodo: str, caminho: str, usuario: str | None = None, corpo=None,
              tipo: str | None = None) -> tuple[int, bytes]:
        dados = json.dumps(corpo).encode() if isinstance(corpo, dict) else corpo
        requisicao = urllib.request.Request(self.base + caminho, data=dados, method=metodo)
        if usuario:
            requisicao.add_header("X-Usuario-Local", usuario)
        if tipo or isinstance(corpo, dict):
            requisicao.add_header("Content-Type", tipo or "application/json")
        try:
            with urllib.request.urlopen(requisicao, timeout=60) as resposta:
                return resposta.status, resposta.read()
        except urllib.error.HTTPError as erro:
            return erro.code, erro.read()

    def api(self, metodo: str, caminho: str, usuario: str, corpo: dict | None = None):
        status, dados = self.pedir(metodo, "/api" + caminho, usuario, corpo)
        return status, json.loads(dados) if dados else {}

    def enviar(self, arquivo: Path) -> str:
        """Pedido de envio + upload multipart, como a tela de envio faz."""
        conteudo = arquivo.read_bytes()
        status, dados = self.api("POST", "/calibracoes/upload", "tecnico.exemplo", {
            "tag": TAG, "padrao_codigo": PADRAO, "nome_arquivo": arquivo.name,
            "tamanho_bytes": len(conteudo), "temperatura_ambiente": "20,4"})
        _exigir(status == 201, f"pedido de envio de {arquivo.name}: HTTP {status} {dados}")
        fronteira = uuid.uuid4().hex
        partes = []
        for nome, valor in dados["upload"]["fields"].items():
            partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"'
                          f"\r\n\r\n{valor}\r\n".encode())
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="file"; '
                      f'filename="{arquivo.name}"\r\nContent-Type: application/octet-stream'
                      "\r\n\r\n".encode() + conteudo + b"\r\n")
        partes.append(f"--{fronteira}--\r\n".encode())
        status, _ = self.pedir("POST", dados["upload"]["url"], corpo=b"".join(partes),
                               tipo=f"multipart/form-data; boundary={fronteira}")
        _exigir(status == 204, f"upload de {arquivo.name}: HTTP {status}")
        return dados["calibracao_id"]

    def revisao(self, calibracao_id: str) -> dict:
        status, dados = self.api("GET", f"/calibracoes/{TAG}/{calibracao_id}", "revisor.exemplo")
        _exigir(status == 200, f"revisao da calibracao {calibracao_id}: HTTP {status} {dados}")
        return dados["revisao"]


class FalhaDeVerificacao(Exception):
    pass


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise FalhaDeVerificacao(mensagem)


def _etapa(numero: int, texto: str) -> None:
    print(f"  [{numero}/7] OK  {texto}", flush=True)


REFERENCIAS_HTML = re.compile(r'(?:src|href)="([^"#:]+)"')
# import x from "./a.js" | export ... from "./a.js" | import "./a.js" | import("./a.js")
IMPORTS_JS = re.compile(r'(?:import|export)\s[^"\';]*?from\s*["\'](\.[^"\']+)["\']'
                        r'|import\s*\(?\s*["\'](\.[^"\']+)["\']')


COMENTARIOS_JS = re.compile(r"/\*.*?\*/|^\s*//.*?$", re.DOTALL | re.MULTILINE)


def _sem_comentarios(codigo: str) -> str:
    """Tira comentarios de bloco e de linha inteira: import comentado nao e dependencia."""
    return COMENTARIOS_JS.sub("", codigo)


def _arquivos_da_interface(cliente: Cliente) -> int:
    """Baixa o index.html e tudo o que ele carrega, seguindo os imports dos modulos JS."""
    status, pagina = cliente.pedir("GET", "/")
    _exigir(status == 200 and b'<script type="module" src="js/app.js">' in pagina,
            f"interface: HTTP {status}, index.html sem o modulo js/app.js")
    pendentes = [p for p in REFERENCIAS_HTML.findall(pagina.decode("utf-8")) if p != "config.js"]
    vistos = set()
    while pendentes:
        caminho = posixpath.normpath(pendentes.pop())
        if caminho in vistos:
            continue
        vistos.add(caminho)
        status, corpo = cliente.pedir("GET", "/" + caminho)
        _exigir(status == 200 and corpo, f"interface: /{caminho} -> HTTP {status}")
        if caminho.endswith(".js"):
            pasta = posixpath.dirname(caminho)
            for estatico, dinamico in IMPORTS_JS.findall(_sem_comentarios(corpo.decode("utf-8"))):
                pendentes.append(posixpath.join(pasta, estatico or dinamico))
    status, config = cliente.pedir("GET", "/config.js")
    _exigir(status == 200 and b'"modo": "local"' in config and b"tecnico.exemplo" in config,
            f"interface: /config.js sem o modo local (HTTP {status})")
    return len(vistos) + 1


def _caracteristica(calibracao: dict, nome: str) -> dict:
    achada = next((c for c in calibracao["caracteristicas"] if c["nome"] == nome), None)
    _exigir(achada is not None, f"caracteristica {nome} nao encontrada")
    return achada


def _roteiro(cliente: Cliente) -> None:
    arquivos = _arquivos_da_interface(cliente)
    _etapa(1, f"interface: index.html, config.js do modo local e {arquivos - 1} arquivos "
              "(CSS, icones e todos os modulos JS importados)")

    id_aprovado = cliente.enviar(EXEMPLOS / "1-aprovado.xlsx")
    aprovado = cliente.revisao(id_aprovado)
    _exigir(aprovado["resumo"]["situacao"] == "CONFORME" and aprovado["resumo"]["total"] == 14,
            f"1-aprovado: esperado CONFORME com 14 caracteristicas, veio {aprovado['resumo']}")
    _exigir(aprovado["pode_emitir"], f"1-aprovado bloqueado: {aprovado['bloqueios']}")
    _etapa(2, f"1-aprovado.xlsx: 14 caracteristicas CONFORMES, "
              f"U = {aprovado['incerteza']['incerteza_expandida_mm']} mm, k = {aprovado['incerteza']['k']}")

    status, certificado = cliente.api(
        "POST", f"/calibracoes/{TAG}/{id_aprovado}/emitir", "signatario.exemplo")
    _exigir(status == 201 and certificado.get("situacao") == "CONFORME",
            f"emissao: HTTP {status} {certificado}")
    numero = certificado["numero"]
    status, link = cliente.api("GET", f"/certificados/{numero}/download", "signatario.exemplo")
    _exigir(status == 200, f"link do PDF: HTTP {status} {link}")
    status, pdf = cliente.pedir("GET", link["url"])
    _exigir(status == 200 and pdf.startswith(b"%PDF"), f"PDF do certificado: HTTP {status}")
    _etapa(3, f"certificado {certificado['numero_exibicao']} emitido ({len(pdf) // 1024} KB de PDF)")

    reprovado = cliente.revisao(cliente.enviar(EXEMPLOS / "2-reprovado.xlsx"))
    motivos = {a["nome"]: a["motivo"] for a in reprovado["avaliacoes"] if a.get("motivo")}
    esperado = {"62P_DIÂMETRO 1": "FORA_DA_TOLERANCIA",
                "13P_DIÂMETRO 2": "FORA_PELA_BANDA_DE_GUARDA"}
    _exigir(reprovado["resumo"]["situacao"] == "NAO_CONFORME" and motivos == esperado,
            f"2-reprovado: esperado {esperado}, veio {motivos}")
    _etapa(4, "2-reprovado.xlsx: NAO_CONFORME (62P_DIAMETRO 1 fora da tolerancia; "
              "13P_DIAMETRO 2 reprovado pela banda de guarda)")

    id_sujo = cliente.enviar(EXEMPLOS / "3-com-sujeira.xlsx")
    status, dados = cliente.api("GET", f"/calibracoes/{TAG}/{id_sujo}", "revisor.exemplo")
    _exigir(status == 200, f"3-com-sujeira: HTTP {status} {dados}")
    calibracao, sujo = dados["calibracao"], dados["revisao"]
    # Cada sujeira da planilha tem que ter virado o valor limpo
    _exigir(calibracao["data_hora_medicao"] == "2026-11-10T16:47:10",
            "3-com-sujeira: data serial do Excel + hora com fracao deveriam virar "
            f"2026-11-10T16:47:10, veio {calibracao['data_hora_medicao']}")
    planicidade = _caracteristica(calibracao, "PLANICIDADE_REF")  # nome com NBSP/espacos/tab
    _exigir(planicidade["medicao_p2"] == "0.002267", f"3-com-sujeira: PLANICIDADE_REF {planicidade}")
    diametro = _caracteristica(calibracao, "62P_DIÂMETRO 1")       # "6,0787295 mm" como texto
    _exigir(diametro["medicao_p1"] == "6.0787295" and diametro["medicao_p2"] == "6.0787295",
            f"3-com-sujeira: numero com virgula e unidade nao foi convertido: {diametro}")
    _exigir(len(calibracao["caracteristicas"]) == 14 and sujo["resumo"]["situacao"] == "CONFORME",
            f"3-com-sujeira: esperado 14 caracteristicas CONFORMES, veio {sujo['resumo']}")
    # O log das regras corretivas fica no S3 ao lado do original (logs/<id>.json). O
    # --verificar roda no mesmo processo do S3 simulado, entao le o log direto: cada
    # sujeira da planilha tem que aparecer com a regra e a celula certas
    log = json.loads(boto3.client("s3").get_object(
        Bucket=os.environ["BUCKET_ENTRADA"], Key=f"logs/{id_sujo}.json")["Body"].read())
    # (regra, celula) -> valor depois da regra. Conjunto EXATO: uma transformacao a
    # mais (higienizacao numa celula limpa) tambem e falha
    aplicadas = {(t["regra"], t["celula"]): t["depois"] for t in log}
    esperadas = {("RH03", "D5"): "2026-11-10T00:00:00",   # data como numero serial do Excel
                 ("RH14", "D8"): "16:47:10",              # hora com fracao espuria
                 ("RH01", "F5"): "None",                  # "---" no campo Order vira nulo
                 ("RH04", "A14"): "PLANICIDADE_REF",      # NBSP e espacos no nome (1a passagem)
                 ("RH04", "A29"): "PLANICIDADE_REF",      # tabulacao no nome (2a passagem)
                 ("RH13", "B16"): "6.0787295",            # "6,0787295 mm"
                 ("RH04", "B31"): "6,0787295mm",          # " 6,0787295mm": espaco inicial...
                 ("RH13", "B31"): "6.0787295"}            # ...e depois virgula e unidade
    _exigir(aplicadas == esperadas,
            "3-com-sujeira: log de higienizacao diferente do esperado. "
            f"Faltando: {sorted(set(esperadas) - set(aplicadas))}; "
            f"a mais: {sorted(set(aplicadas) - set(esperadas))}; "
            f"valores: {[(k, aplicadas[k]) for k in esperadas if k in aplicadas and aplicadas[k] != esperadas[k]]}")
    _etapa(5, "3-com-sujeira.xlsx (OOXML Strict): data serial, hora com fracao, '---', "
              "espacos/NBSP/tab e '6,0787295 mm' higienizados (8 regras no log); CONFORME")

    recusado = cliente.enviar(EXEMPLOS / "4-quarentena.xlsx")
    quarentena = cliente.api("GET", "/quarentena", "revisor.exemplo")[1]["quarentena"]
    item = next((q for q in quarentena if q.get("calibracao_id") == recusado), None)
    _exigir(item is not None, "4-quarentena.xlsx nao apareceu na quarentena")
    violacoes = [(v["regra"], v.get("celula")) for v in item.get("violacoes", [])]
    _exigir(violacoes == [("RN01", "B39")],
            f"4-quarentena: esperado so RN01 na celula B39 (2a passagem), veio {violacoes}")
    status, _ = cliente.api("GET", f"/calibracoes/{TAG}/{recusado}", "revisor.exemplo")
    _exigir(status == 404, f"4-quarentena: a calibracao recusada nao pode ir para a revisao (HTTP {status})")
    _etapa(6, "4-quarentena.xlsx: recusado por RN01 (medicao ausente em B39) e fora da revisao")

    status, consulta = cliente.api("GET", f"/instrumentos/{TAG}?canal=teclado", "consulta.usinagem")
    ultimo = (consulta.get("ultimo_certificado") or {}) if status == 200 else {}
    _exigir(ultimo.get("numero") == numero and consulta.get("situacao") == "EM_DIA",
            f"consulta do {TAG}: esperado o certificado {numero} e EM_DIA, veio HTTP {status} {consulta}")
    _etapa(7, f"consulta do {TAG}: EM_DIA, ultimo certificado {ultimo['numero_exibicao']}")


def verificar(porta: int) -> int:
    resultado = {"codigo": 1}

    def ao_subir(servidor):
        try:
            time.sleep(0.2)
            print("Verificacao de ponta a ponta:", flush=True)
            _roteiro(Cliente(porta))
            print("Tudo certo: a aplicacao esta funcionando.", flush=True)
            resultado["codigo"] = 0
        except FalhaDeVerificacao as falha:
            print(f"FALHOU: {falha}", flush=True)
        except Exception as erro:  # qualquer outra coisa tambem e falha
            print(f"FALHOU: {type(erro).__name__}: {erro}", flush=True)
        finally:
            servidor.shutdown()

    servidor_local.executar(porta, carregar_exemplo=True, ao_subir=ao_subir)
    return resultado["codigo"]
