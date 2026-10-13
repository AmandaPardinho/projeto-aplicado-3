"""
Aplicacao web transacional do MVP - AV3 (Projeto Aplicado III, Grupo 4 / Schulz).

Recebe a planilha de leituras do instrumento, aplica as regras de negocio
e calculos metrologicos definidos no roteiro da AV3 (media, erro
sistematico, validacao por tolerancia e parecer final) e apresenta o
resultado numa interface simples.
"""
import os
import uuid

from flask import Flask, redirect, render_template, request, url_for

from calculo import PlanilhaInvalidaError, processar_planilha

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}

app = Flask(__name__)
app.secret_key = "dev"  # suficiente para o MVP local; nao usar em producao
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def index():
    return render_template("upload.html")


@app.post("/processar")
def processar():
    arquivo = request.files.get("planilha")

    if arquivo is None or arquivo.filename == "":
        return render_template("upload.html", erro="Selecione um arquivo .xlsx antes de enviar."), 400

    extensao = os.path.splitext(arquivo.filename)[1].lower()
    if extensao not in ALLOWED_EXTENSIONS:
        return render_template(
            "upload.html",
            erro=f"Formato '{extensao}' nao suportado. Envie um arquivo .xlsx ou .xlsm.",
        ), 400

    caminho_temp = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{extensao}")
    arquivo.save(caminho_temp)

    try:
        resultado = processar_planilha(caminho_temp)
    except PlanilhaInvalidaError as exc:
        return render_template("upload.html", erro=str(exc)), 422
    finally:
        os.remove(caminho_temp)

    return render_template(
        "resultado.html",
        nome_arquivo=arquivo.filename,
        resultado=resultado,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
