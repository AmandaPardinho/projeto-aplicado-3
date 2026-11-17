@echo off
rem ==========================================================================
rem  Automacao da Emissao de Certificados de Calibracao - Schulz S.A.
rem  Projeto Aplicado III - Grupo 4 - UniSENAI Florianopolis
rem
rem  Uso:  iniciar_aplicacao_schulz.bat              (porta 8000)
rem        iniciar_aplicacao_schulz.bat 8080         (outra porta)
rem        iniciar_aplicacao_schulz.bat --verificar  (testa tudo e encerra)
rem
rem  1. confere o Python 3.10+ no PATH
rem  2. cria e ativa o ambiente virtual (.venv)
rem  3. instala o requirements.txt (so quando ele muda)
rem  4. sobe a API e abre a interface no navegador padrao
rem ==========================================================================
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PORTA=8000"
set "MODO=normal"
if /i "%~1"=="--verificar" set "MODO=verificar"
set "PAUSA=pause"
if "%MODO%"=="verificar" set "PAUSA=rem"
if not "%~1"=="" if /i not "%~1"=="--verificar" set "PORTA=%~1"

echo.
echo  Schulz S.A. - Emissao de Certificados de Calibracao
echo  ===================================================
echo.

rem --- 1. Python 3.10+ no PATH ---------------------------------------------
echo [1/4] Procurando o Python 3.10 ou superior...
set "PY="
call :testar_python python
if not defined PY call :testar_python py -3
if not defined PY goto :sem_python
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "VERSAO=%%v"
echo       Encontrado: Python %VERSAO% (%PY%)

rem --- 2. Ambiente virtual -------------------------------------------------
echo [2/4] Preparando o ambiente virtual (.venv)...
rem Uma .venv que nao roda, ou de um Python anterior ao 3.10, e recriada
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || (
        echo       Ambiente virtual antigo ou quebrado; recriando...
        rmdir /s /q ".venv"
    )
)
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 goto :erro_venv
    echo       Ambiente virtual criado.
) else (
    echo       Ambiente virtual ja existe.
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :erro_venv

rem --- 3. Bibliotecas ------------------------------------------------------
echo [3/4] Conferindo as bibliotecas do requirements.txt...
rem Pula a instalacao so se o requirements.txt nao mudou E as bibliotecas importam
fc /b "requirements.txt" ".venv\requirements.instalado" >nul 2>nul || goto :instalar
python -c "import openpyxl, reportlab, boto3, moto" >nul 2>nul || goto :instalar
echo       Bibliotecas ja instaladas.
goto :iniciar
:instalar
echo       Instalando (a primeira vez pode levar alguns minutos)...
python -m pip install --disable-pip-version-check --quiet --upgrade pip
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :erro_pip
copy /y "requirements.txt" ".venv\requirements.instalado" >nul

rem --- 4. API + navegador --------------------------------------------------
:iniciar
if "%MODO%"=="verificar" goto :verificar
echo [4/4] Iniciando a API em http://localhost:%PORTA%/ e abrindo o navegador...
echo       Para encerrar, feche esta janela ou pressione Ctrl+C.
echo.
python app.py --porta %PORTA% --abrir-navegador
if errorlevel 1 (
    echo.
    echo  A aplicacao encerrou com erro. Veja a mensagem acima.
    %PAUSA%
    exit /b 1
)
exit /b 0

:verificar
rem Fora de bloco ( ): dentro dele o %errorlevel% seria lido antes do python rodar
echo [4/4] Verificando a aplicacao de ponta a ponta...
python app.py --verificar --porta %PORTA%
exit /b %errorlevel%

rem --- sub-rotinas e mensagens de erro --------------------------------------
:testar_python
rem Roda o candidato e exige 3.10+. O atalho "python" da Microsoft Store
rem (sem Python instalado) falha aqui e o script tenta o "py -3".
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0

:sem_python
echo.
echo  ERRO: Python 3.10 ou superior nao encontrado no PATH.
echo.
echo  1. Baixe em https://www.python.org/downloads/
echo  2. Na instalacao, marque "Add python.exe to PATH".
echo  3. Abra uma nova janela e rode este arquivo de novo.
echo.
%PAUSA%
exit /b 1

:erro_venv
echo.
echo  ERRO: nao foi possivel criar ou ativar o ambiente virtual (.venv).
echo  Apague a pasta .venv e rode este arquivo de novo.
echo.
%PAUSA%
exit /b 1

:erro_pip
echo.
echo  ERRO: a instalacao das bibliotecas falhou. Confira a conexao com a
echo  internet e rode este arquivo de novo.
echo.
%PAUSA%
exit /b 1
