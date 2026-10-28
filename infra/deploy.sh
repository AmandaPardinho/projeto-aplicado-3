#!/usr/bin/env bash
# Publica a PoC na AWS (us-east-1, AWS Academy), do zero ou por cima de uma versao anterior.
#
#   infra/deploy.sh                        # pilha + carga inicial + site
#   EMAIL_ALERTAS=voce@exemplo.com infra/deploy.sh
#   PADRAO_VALIDO_ATE=2027-11-20 infra/deploy.sh
#
# Precisa de: AWS CLI v2 com credencial configurada, AWS SAM CLI e Python 3.12
# com as dependencias de backend/requirements-dev.txt (a .venv do projeto).
#
# Passos:
#   1. sam build + sam deploy do infra/template.yaml
#   2. seed.py: cadastros no DynamoDB e usuarios de teste no Cognito
#   3. config.js com a URL da API e os dados do Cognito, gerado das saidas
#   4. frontend + Report de exemplo no bucket do site (entregue pela fn-site)
#   5. etiquetas com QR do 703.1208 em infra/saida/
set -euo pipefail

PILHA="${PILHA:-schulz-pa3}"
REGIAO="${REGIAO:-us-east-1}"
EMAIL_ALERTAS="${EMAIL_ALERTAS:-}"
PADRAO_VALIDO_ATE="${PADRAO_VALIDO_ATE:-2026-08-31}"

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
PYTHON="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
SAIDA="infra/saida"
mkdir -p "$SAIDA"

for programa in aws sam; do
  command -v "$programa" >/dev/null || { echo "Falta o programa '$programa' (veja o README)." >&2; exit 1; }
done
aws sts get-caller-identity --query Account --output text >/dev/null \
  || { echo "Credencial da AWS ausente ou expirada (AWS Academy: copie de novo o bloco de AWS Details para ~/.aws/credentials)." >&2; exit 1; }

echo "==> 1/5 Pilha $PILHA em $REGIAO"
sam build --template-file infra/template.yaml --build-dir .aws-sam/build
sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name "$PILHA" --region "$REGIAO" \
  --capabilities CAPABILITY_IAM --resolve-s3 \
  --no-confirm-changeset --no-fail-on-empty-changeset \
  --parameter-overrides "EmailAlertas=$EMAIL_ALERTAS"

saida() {
  aws cloudformation describe-stacks --stack-name "$PILHA" --region "$REGIAO" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
URL_APP="$(saida UrlApp)"
URL_API="$(saida UrlApi)"
COGNITO_DOMINIO="$(saida CognitoDominio)"
COGNITO_CLIENTE="$(saida CognitoClientId)"
BUCKET_SITE="$(saida BucketSite)"

echo "==> 2/5 Carga inicial"
"$PYTHON" infra/seed.py --pilha "$PILHA" --regiao "$REGIAO" --padrao-valido-ate "$PADRAO_VALIDO_ATE"

echo "==> 3/5 config.js"
SITE="$(mktemp -d)"
trap 'rm -rf "$SITE"' EXIT
cp -r frontend/. "$SITE/"
mkdir -p "$SITE/exemplo"
"$PYTHON" infra/report_exemplo.py "$SITE/exemplo/report-703.1208.xlsx" >/dev/null
URL_API="$URL_API" COGNITO_DOMINIO="$COGNITO_DOMINIO" COGNITO_CLIENTE="$COGNITO_CLIENTE" \
  "$PYTHON" - > "$SITE/config.js" <<'EOF'
import json, os
config = {
    "modo": "cognito",
    "api": os.environ["URL_API"],
    "cognito": {"dominio": os.environ["COGNITO_DOMINIO"],
                "clientId": os.environ["COGNITO_CLIENTE"], "redirect": None},
    "exemploReport": "exemplo/report-703.1208.xlsx",
}
print("// Gerado pelo infra/deploy.sh a partir das saidas da pilha")
print(f"window.SCHULZ_CONFIG = {json.dumps(config, indent=2)};")
EOF

echo "==> 4/5 Site"
# Arquivos pequenos e sem build: tudo com no-cache, para o deploy aparecer na hora
aws s3 sync "$SITE/" "s3://$BUCKET_SITE/" --delete --region "$REGIAO" \
  --cache-control "no-cache" --exclude "*.DS_Store"
aws s3 cp "s3://$BUCKET_SITE/manifest.webmanifest" "s3://$BUCKET_SITE/manifest.webmanifest" \
  --region "$REGIAO" --metadata-directive REPLACE --cache-control "no-cache" \
  --content-type "application/manifest+json" >/dev/null

echo "==> 5/5 Etiquetas"
"$PYTHON" infra/etiquetas.py --url "$URL_APP" --saida "$SAIDA/etiquetas-703.1208.pdf" 703.1208

cat <<FIM

Pronto. Plataforma em: $URL_APP
Usuarios e senhas de teste: infra/senhas-teste.txt
Etiquetas para imprimir:   $SAIDA/etiquetas-703.1208.pdf
FIM
if [ "$PADRAO_VALIDO_ATE" \< "$(date +%F)" ]; then
  echo
  echo "Atencao: o padrao 500.011 esta vencido ($PADRAO_VALIDO_ATE) e bloqueia novos envios (RN04)."
  echo "Atualize pela tela Padroes com o usuario admin.padrao (UC03) antes de enviar um relatorio."
fi
