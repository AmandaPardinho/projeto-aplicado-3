"""
Ponto de entrada local da aplicacao (AV5) - Schulz S.A. / Grupo 4.

    python app.py                    # sobe a API e o frontend em http://localhost:8000
    python app.py --porta 8080       # outra porta
    python app.py --abrir-navegador  # tambem abre a interface no navegador padrao
    python app.py --verificar        # sobe, testa o fluxo de ponta a ponta e encerra

Roda as mesmas funcoes Lambda da nuvem (backend/handlers) com DynamoDB e S3
simulados em memoria pelo moto, servidas pelo backend/servidor_local.py. Tudo
o que for enviado some quando o servidor para.

O script iniciar_aplicacao_schulz.bat (Windows) prepara o ambiente e chama
este arquivo.
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if sys.version_info < (3, 10):
    sys.exit(f"Python 3.10 ou superior e necessario (encontrado {sys.version.split()[0]}).")
sys.path.insert(0, str(RAIZ / "backend"))

import servidor_local  # noqa: E402


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Aplicacao local - Schulz S.A.")
    argumentos.add_argument("--porta", type=int, default=8000)
    argumentos.add_argument("--abrir-navegador", action="store_true",
                            help="abre a interface no navegador padrao quando o servidor subir")
    argumentos.add_argument("--verificar", action="store_true",
                            help="sobe o servidor, testa envio, revisao e emissao e encerra")
    opcoes = argumentos.parse_args()
    if not 1 <= opcoes.porta <= 65535:
        argumentos.error(f"porta invalida: {opcoes.porta} (use um numero de 1 a 65535)")

    if opcoes.verificar:
        from verificar_local import verificar
        sys.exit(verificar(opcoes.porta))

    url = f"http://localhost:{opcoes.porta}/"

    def ao_subir(_servidor):
        # So abre o navegador depois que a porta esta aberta: sem pagina de erro
        print(f"Interface: {url}  (feche esta janela ou use Ctrl+C para parar)", flush=True)
        if opcoes.abrir_navegador:
            webbrowser.open(url)

    servidor_local.executar(opcoes.porta, ao_subir=ao_subir)


if __name__ == "__main__":
    main()
