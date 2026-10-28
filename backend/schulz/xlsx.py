"""
Abertura de workbooks Excel vindos da Schulz (RNF02).

Parte das planilhas da Schulz (Cal_1_5896_1.xlsx, Dispositivo de controle.xlsx)
esta salva em OOXML Strict, que usa namespaces http://purl.oclc.org/ooxml/...
O openpyxl so entende o formato Transitional: diante de um arquivo Strict ele
nao acha nenhuma aba. A correcao e trocar os namespaces em memoria, dentro do
ZIP, antes de entregar o arquivo ao openpyxl. O arquivo original nao e alterado.
"""
from __future__ import annotations

import io
import warnings
import zipfile

import openpyxl
from openpyxl.workbook.workbook import Workbook

# Prefixos Strict -> Transitional. A troca e por prefixo, entao cobre tambem
# os tipos de relacionamento (".../relationships/officeDocument" etc.).
NAMESPACES_STRICT = {
    b"http://purl.oclc.org/ooxml/spreadsheetml/main":
        b"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main":
        b"http://schemas.openxmlformats.org/drawingml/2006/main",
}


class ArquivoIlegivelError(ValueError):
    """O arquivo nao e um xlsx/xlsm valido."""


def eh_strict(conteudo: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            return b"purl.oclc.org/ooxml" in z.read("xl/workbook.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ArquivoIlegivelError("arquivo nao e um workbook Excel") from exc


def converter_para_transitional(conteudo: bytes) -> bytes:
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for item in origem.infolist():
            dados = origem.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                for strict, transitional in NAMESPACES_STRICT.items():
                    dados = dados.replace(strict, transitional)
            destino.writestr(item, dados)
    return saida.getvalue()


def abrir_workbook(conteudo: bytes, data_only: bool = True) -> Workbook:
    """Abre o workbook a partir dos bytes, convertendo Strict se preciso.

    data_only=True le o ultimo valor calculado das formulas, que e o que o
    Calypso/Excel gravou no arquivo (o sistema nunca recalcula formulas).
    """
    if eh_strict(conteudo):
        conteudo = converter_para_transitional(conteudo)
    with warnings.catch_warnings():
        # "Data Validation extension is not supported" etc.: avisos esperados
        warnings.simplefilter("ignore", UserWarning)
        try:
            return openpyxl.load_workbook(io.BytesIO(conteudo), data_only=data_only)
        except (zipfile.BadZipFile, KeyError, OSError) as exc:
            raise ArquivoIlegivelError("arquivo nao e um workbook Excel") from exc
