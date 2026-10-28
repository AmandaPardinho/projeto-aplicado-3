<#
Publica a PoC na AWS (us-east-1, AWS Academy) a partir do Windows. Faz o mesmo que o
infra/deploy.sh, do zero ou por cima de uma versao anterior.

    powershell -ExecutionPolicy Bypass -File infra\deploy.ps1
    powershell -ExecutionPolicy Bypass -File infra\deploy.ps1 -EmailAlertas voce@exemplo.com
    powershell -ExecutionPolicy Bypass -File infra\deploy.ps1 -PadraoValidoAte 2027-11-20

Precisa de: AWS CLI v2 com credencial configurada, AWS SAM CLI e Python 3.12
no PATH, com as dependencias de backend\requirements-dev.txt na .venv do
projeto.

Passos:
  1. sam build + sam deploy do infra\template.yaml
  2. seed.py: cadastros no DynamoDB e usuarios de teste no Cognito
  3. config.js com a URL da API e os dados do Cognito, gerado das saidas
  4. frontend + Report de exemplo no bucket do site (entregue pela fn-site)
  5. etiquetas com QR do 703.1208 em infra\saida\
#>
param(
    [string]$Pilha = $(if ($env:PILHA) { $env:PILHA } else { "schulz-pa3" }),
    [string]$Regiao = $(if ($env:REGIAO) { $env:REGIAO } else { "us-east-1" }),
    [string]$EmailAlertas = $env:EMAIL_ALERTAS,
    [string]$PadraoValidoAte = $(if ($env:PADRAO_VALIDO_ATE) { $env:PADRAO_VALIDO_ATE } else { "2026-08-31" })
)

$ErrorActionPreference = "Stop"
# Acentos nas mensagens do seed.py sem UnicodeEncodeError no console do Windows
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Programa externo com erro nao para o PowerShell sozinho: confere o codigo de saida.
# Funcao sem param(): assim --template-file etc. chegam ao programa como texto,
# em vez de o PowerShell tentar le-los como parametros dele.
function Executar {
    $programa, $argumentos = $args
    & $programa @argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falhou ($LASTEXITCODE): $programa $($argumentos -join ' ')" }
}

$Raiz = Split-Path -Parent $PSScriptRoot
Set-Location $Raiz
$Python = $env:PYTHON
if (-not $Python) {
    $Python = Join-Path $Raiz ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) { $Python = "python" }
}
$Saida = Join-Path $Raiz "infra\saida"
New-Item -ItemType Directory -Force -Path $Saida | Out-Null

foreach ($programa in "aws", "sam") {
    if (-not (Get-Command $programa -ErrorAction SilentlyContinue)) {
        throw "Falta o programa '$programa' (veja o README)."
    }
}
& aws sts get-caller-identity --query Account --output text | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Credencial da AWS ausente ou expirada (AWS Academy: copie de novo o bloco de AWS Details para ~\.aws\credentials)." }

Write-Host "==> 1/5 Pilha $Pilha em $Regiao"
Executar sam build --template-file infra/template.yaml --build-dir .aws-sam/build
Executar sam deploy `
    --template-file .aws-sam/build/template.yaml `
    --stack-name $Pilha --region $Regiao `
    --capabilities CAPABILITY_IAM --resolve-s3 `
    --no-confirm-changeset --no-fail-on-empty-changeset `
    --parameter-overrides "EmailAlertas=$EmailAlertas"

function SaidaDaPilha([string]$Chave) {
    $valor = & aws cloudformation describe-stacks --stack-name $Pilha --region $Regiao `
        --query "Stacks[0].Outputs[?OutputKey=='$Chave'].OutputValue" --output text
    if ($LASTEXITCODE -ne 0) { throw "Nao consegui ler a saida $Chave da pilha." }
    return $valor.Trim()
}
$UrlApp = SaidaDaPilha UrlApp
$UrlApi = SaidaDaPilha UrlApi
$CognitoDominio = SaidaDaPilha CognitoDominio
$CognitoCliente = SaidaDaPilha CognitoClientId
$BucketSite = SaidaDaPilha BucketSite

Write-Host "==> 2/5 Carga inicial"
Executar $Python infra/seed.py --pilha $Pilha --regiao $Regiao --padrao-valido-ate $PadraoValidoAte

Write-Host "==> 3/5 config.js"
$Site = Join-Path ([IO.Path]::GetTempPath()) ("schulz-site-" + [guid]::NewGuid())
try {
    New-Item -ItemType Directory -Path $Site | Out-Null
    # -Force inclui arquivos ocultos, como o cp -r frontend/. do deploy.sh; sem eles
    # o sync --delete apagaria esses arquivos do site
    Copy-Item -Recurse -Force -Path (Join-Path $Raiz "frontend\*") -Destination $Site
    New-Item -ItemType Directory -Force -Path (Join-Path $Site "exemplo") | Out-Null
    Executar $Python infra/report_exemplo.py (Join-Path $Site "exemplo\report-703.1208.xlsx") | Out-Null

    $config = [ordered]@{
        modo          = "cognito"
        api           = $UrlApi
        cognito       = [ordered]@{ dominio = $CognitoDominio; clientId = $CognitoCliente; redirect = $null }
        exemploReport = "exemplo/report-703.1208.xlsx"
    }
    $js = "// Gerado pelo infra/deploy.ps1 a partir das saidas da pilha`n" +
          "window.SCHULZ_CONFIG = $($config | ConvertTo-Json -Depth 3);`n"
    # UTF-8 sem BOM, igual ao gerado pelo deploy.sh
    [IO.File]::WriteAllText((Join-Path $Site "config.js"), $js, (New-Object Text.UTF8Encoding $false))

    Write-Host "==> 4/5 Site"
    # Arquivos pequenos e sem build: tudo com no-cache, para o deploy aparecer na hora
    Executar aws s3 sync "$Site/" "s3://$BucketSite/" --delete --region $Regiao `
        --cache-control "no-cache" --exclude "*.DS_Store"
    Executar aws s3 cp "s3://$BucketSite/manifest.webmanifest" "s3://$BucketSite/manifest.webmanifest" `
        --region $Regiao --metadata-directive REPLACE --cache-control "no-cache" `
        --content-type "application/manifest+json" | Out-Null
}
finally {
    Remove-Item -Recurse -Force -Path $Site -ErrorAction SilentlyContinue
}

Write-Host "==> 5/5 Etiquetas"
$Etiquetas = Join-Path $Saida "etiquetas-703.1208.pdf"
Executar $Python infra/etiquetas.py --url $UrlApp --saida $Etiquetas 703.1208

Write-Host ""
Write-Host "Pronto. Plataforma em: $UrlApp"
Write-Host "Usuarios e senhas de teste: infra\senhas-teste.txt"
Write-Host "Etiquetas para imprimir:   infra\saida\etiquetas-703.1208.pdf"
if ($PadraoValidoAte -lt (Get-Date -Format "yyyy-MM-dd")) {
    Write-Host ""
    Write-Host "Atencao: o padrao 500.011 esta vencido ($PadraoValidoAte) e bloqueia novos envios (RN04)."
    Write-Host "Atualize pela tela Padroes com o usuario admin.padrao (UC03) antes de enviar um relatorio."
}
