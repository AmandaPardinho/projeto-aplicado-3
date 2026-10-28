"""
Gera um Report do Calypso de exemplo (caso 703.1208) para testar o envio.

    python infra/report_exemplo.py report-703.1208.xlsx

Leva a hora atual no cabecalho, entao cada arquivo gerado tem SHA-256 novo e
nao cai no RH17 (arquivo ja importado). Enviar o mesmo arquivo duas vezes
mostra a quarentena.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend" / "tests"))

from report_calypso import gerar_report  # noqa: E402


def report_exemplo() -> bytes:
    agora = datetime.now()
    return gerar_report(data=agora.replace(hour=0, minute=0, second=0, microsecond=0),
                        hora=agora.time().replace(microsecond=0))


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "report-703.1208.xlsx")
    destino.write_bytes(report_exemplo())
    print(f"Report de exemplo em {destino}")
