# Automação da Emissão de Certificados de Calibração — Schulz S.A.

Projeto Aplicado III · Grupo 4 · UniSENAI Florianópolis
Empresa parceira: Schulz S.A. · Orientador: Prof. MSc. Hugo Menezes Barra

Prova de conceito serverless na AWS (camada gratuita) que recebe o relatório bruto do Calypso exportado pela MMC, aplica o saneamento do Tema 01, calcula a incerteza pela metodologia GUM, avalia a conformidade com banda de guarda e emite o certificado em PDF com QR Code. A arquitetura é a da AV2: Cognito, API Gateway (HTTP API), três funções Lambda, DynamoDB em tabela única e S3.

## Situação

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 — Backend | parser do Calypso, GUM, banda de guarda, PDF, fn-api / fn-ingestao / fn-emissao, testes | concluída |
| 2 — Frontend | SPA + PWA com login, revisão, emissão, consulta por TAG/QR e trilha de auditoria | concluída |
| 3 — Infraestrutura | template AWS SAM, `deploy.sh`, carga inicial, etiquetas com QR | pronta; falta publicar na conta do grupo |
| 4 — Documentação | matriz de rastreabilidade, roteiro de deploy, relatório e vídeo | a fazer |

O MVP Flask da AV3 está em [`legado-av3/`](legado-av3/) e na tag `av3`.

## Estrutura

```text
backend/
  schulz/                 núcleo (sem dependência de AWS, exceto repositorio/auditoria)
    xlsx.py               abertura do workbook, com reparo do formato OOXML Strict (RNF02)
    calypso.py            leitura e saneamento do Report do Calypso (RF02, RH01–RH17, RN01)
    gum.py                orçamento GUM do bloco volumétrico da MMC (RF03, RF04, RN03)
    conformidade.py       banda de guarda (RN02) e resumo de não conformidades (RF06)
    revisao.py            bloqueios de emissão (RN04, RN06, RN08) e valores do certificado
    certificado.py        PDF do certificado com QR Code (RF08)
    repositorio.py        chaves e operações da tabela única do DynamoDB
    autorizacao.py        grupos do Cognito e permissões por ação (RNF08, RN05)
    auditoria.py          trilha AUD# de quem fez o quê, inclusive consultas
    cadastros_exemplo.py  cadastros do caso 703.1208 (nomes de pessoas fictícios)
  handlers/
    api.py                fn-api: todas as rotas da HTTP API
    ingestao.py           fn-ingestao: evento do S3, ETL, quarentena e persistência
    emissao.py            fn-emissao: número, PDF, Object Lock e certificado imutável
    site.py               fn-site: entrega o frontend pela Function URL (no lugar do CloudFront)
  tests/                  pytest + moto (DynamoDB e S3 simulados)
  servidor_local.py       roda as Lambdas + frontend sem AWS, para testar as telas
frontend/                 SPA estática (HTML, CSS e JS puros, sem etapa de build) + PWA
  index.html, config.js   página única; config.js é gerado no deploy (URL da API, Cognito)
  js/auth.js              login no Cognito Hosted UI (Authorization Code + PKCE)
  js/leitor.js            canais de consulta: TAG digitado, leitor USB e câmera (QR)
  js/telas/               envio, fila, revisão/emissão, quarentena, consulta, certificado,
                          padrões e auditoria
  sw.js, manifest.webmanifest   PWA instalável no celular (guarda só a casca do app)
infra/
  template.yaml           pilha AWS SAM: Cognito, HTTP API, 4 Lambdas (uma entrega o site),
                          DynamoDB, S3, fila de falhas, alarmes e orçamento
  deploy.sh               build + deploy + carga inicial + config.js + site + etiquetas
  seed.py                 cadastros de exemplo no DynamoDB e usuários de teste no Cognito
  etiquetas.py            folha A4 de etiquetas com o QR da consulta de cada TAG
  report_exemplo.py       Report do Calypso de exemplo (703.1208) para testar o envio
docs/
  achados-nas-planilhas.md  erros encontrados nas planilhas da Schulz
legado-av3/               MVP Flask entregue na AV3
```

## Testando as telas sem AWS

```bash
cd backend
python servidor_local.py        # http://localhost:8000
```

O servidor roda as mesmas Lambdas com DynamoDB e S3 simulados em memória. A tela de login lista usuários de teste, um por perfil (técnico, revisor, signatário, admin de padrões, consulta e auditor), sem senha. Uma calibração do 703.1208 já entra na fila, e a tela de envio tem um link para baixar um Report de exemplo. O padrão 500.011 é carregado válido até 2027.

| Perfil | O que vê |
|---|---|
| Técnico | envio do relatório; fila e quarentena só do que enviou |
| Revisor | fila, revisão (GUM + banda de guarda), cancelamento |
| Signatário | tudo do revisor + emissão do certificado (RN05), menos das calibrações que ele mesmo enviou ou executou |
| Admin. de padrões | cadastro e atualização dos padrões (UC03) |
| Consulta | situação do instrumento por TAG/QR e download do certificado do próprio setor |
| Auditor | trilha de auditoria por dia, com usuário, ação, alvo e canal |

A consulta do instrumento registra o canal usado: TAG digitado (teclado ou PWA), leitor USB (detectado pela velocidade da digitação) ou câmera (leitura do QR na tela, ou link aberto pelo QR da etiqueta).

## Publicando na AWS (AWS Academy)

A pilha está adaptada ao Learner Lab do AWS Academy: região `us-east-1`, Lambdas com a `LabRole` do laboratório (a conta não cria roles IAM) e site entregue pela `fn-site` (a conta não tem acesso ao CloudFront).

Pré-requisitos na máquina de quem publica:

- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html);
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html);
- Python 3.12 com a `.venv` do projeto (veja "Rodando os testes").

Credencial, a cada sessão do lab: **Start Lab** → **AWS Details** → **AWS CLI: Show**, e cole o bloco inteiro (com o `aws_session_token`) em `~/.aws/credentials`. A credencial expira quando a sessão acaba; os recursos da pilha continuam lá.

```bash
infra/deploy.sh
```

No Windows, pelo PowerShell (mesmas etapas; precisa do Python 3.12 no PATH e da `.venv` criada com `py -3.12 -m venv .venv`):

```powershell
powershell -ExecutionPolicy Bypass -File infra\deploy.ps1
```

O script cria ou atualiza a pilha `schulz-pa3`, carrega os cadastros e os usuários de teste, publica o site com o `config.js` gerado e salva uma folha de etiquetas do 703.1208 em `infra/saida/`. No fim ele mostra o endereço da plataforma (`https://<id>.lambda-url.us-east-1.on.aws/`). As senhas dos usuários de teste ficam em `infra/senhas-teste.txt`, que não vai para o git. `EMAIL_ALERTAS` é opcional: com ele, a pilha cria o orçamento de US$ 1 e os alarmes, e a AWS manda um e-mail pedindo a confirmação da inscrição. No AWS Academy, publique sem ele: o laboratório pode não permitir o AWS Budgets e já tem o próprio limite de crédito.

Fora do AWS Academy, numa conta com permissão de IAM, a role vem do parâmetro `RoleLambdas` da pilha (padrão `LabRole`).

**Padrão vencido:** o certificado real do padrão 500.011 venceu em 31/08/2026, e a carga inicial usa essa data. Enquanto ele estiver vencido, o envio de relatórios fica bloqueado (RN04). Na demonstração, o usuário `admin.padrao` atualiza o padrão pela tela Padrões (UC03). Para pular esse passo, publique com `PADRAO_VALIDO_ATE=2027-11-20 infra/deploy.sh`.

Rodar o script de novo atualiza a pilha e o site sem apagar dados. Cadastros e usuários que já existem ficam como estão (`infra/seed.py --help` mostra como sobrescrever ou trocar senhas).

Outros comandos:

```bash
python infra/etiquetas.py --url https://<seu-endereco>.cloudfront.net/ 703.1208 700.0001
python infra/report_exemplo.py report.xlsx      # Report novo, com outro SHA-256
```

### O que a pilha cria

| Recurso | Configuração | Camada gratuita |
|---|---|---|
| Cognito | pool sem auto-cadastro, 6 grupos (perfis), atributos `matricula` e `setor` só alteráveis pelo administrador, Hosted UI | 10 mil usuários ativos/mês |
| API Gateway (HTTP API) | autorizador JWT do Cognito em todas as rotas, CORS só para o endereço do CloudFront, limite de 10 req/s | 1 milhão de chamadas/mês (12 meses) |
| Lambda | `schulz-fn-api`, `schulz-fn-ingestao` (evento do S3 em `entrada/`), `schulz-fn-emissao`, `schulz-fn-site` (Function URL que entrega o site); todas com a `LabRole`; logs por 14 dias | 1 milhão de invocações/mês |
| DynamoDB | `schulz-certificacao`, tabela única + GSI1, 20 RCU / 20 WCU | 25 RCU / 25 WCU |
| S3 | entrada (quarentena apaga em 90 dias; originais e logs em 1 ano), certificados (versionamento + Object Lock), site (privado, lido pela `fn-site`) | 5 GB (12 meses) |
| SQS | fila de falhas da ingestão | 1 milhão de requisições/mês |
| CloudWatch, SNS, Budgets | 3 alarmes e orçamento de US$ 1, se houver `EMAIL_ALERTAS` | 10 alarmes, 2 orçamentos |

### Diferenças em relação à AV2

| AV2 | PoC | Motivo |
|---|---|---|
| Object Lock em modo COMPLIANCE pelo prazo legal | modo GOVERNANCE, 1 dia (`DiasRetencaoCertificados`) | permitir limpar a conta depois da avaliação |
| MFA para signatários | desligado | simplificar a demonstração |
| alarmes completos e fn-contencao | 3 alarmes, sem contenção automática | escopo da PoC |
| domínio próprio | endereço `*.lambda-url.us-east-1.on.aws` | sem custo de domínio |
| região `sa-east-1` | `us-east-1` | o AWS Academy só libera `us-east-1` e `us-west-2` |
| role de menor privilégio por função | `LabRole` do laboratório em todas | o AWS Academy não permite criar roles IAM; cada função passa a ter mais permissão do que precisa |
| site por S3 + CloudFront (OAC, cache de borda) | `fn-site` lê o bucket privado e entrega por Function URL, com os mesmos cabeçalhos de segurança | o AWS Academy bloqueia o CloudFront; sem cache de borda, o que não pesa na PoC |

### Se o deploy falhar

- **Pilha em `ROLLBACK_COMPLETE`:** veja o primeiro evento com falha no console (CloudFormation → `schulz-pa3` → Events), apague a pilha (`aws cloudformation delete-stack --stack-name schulz-pa3`) e publique de novo.
- **`ExpiredToken`:** a sessão do lab acabou; copie a credencial de novo.
- **Endereço do site responde `Forbidden`:** a Function URL pública pode precisar também da permissão `lambda:InvokeFunction`:

  ```bash
  aws lambda add-permission --function-name schulz-fn-site --statement-id url-publica-invoke \
    --action lambda:InvokeFunction --principal "*" --invoked-via-function-url
  ```

### Removendo

```bash
aws s3 rm s3://schulz-web-<conta>-us-east-1 --recursive
aws s3 rm s3://schulz-entrada-<conta>-us-east-1 --recursive
aws cloudformation delete-stack --stack-name schulz-pa3 --region us-east-1
```

O bucket de certificados fica retido de propósito. Ele pode ser esvaziado e apagado pelo console depois que a retenção do Object Lock vencer.

## Rodando os testes

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt

cd backend
python -m pytest
```

Os testes geram relatórios no layout do Calypso com os valores reais do caso 703.1208. Para rodar também contra o arquivo real da Schulz (que não fica no repositório):

```bash
SCHULZ_REPORT_REAL="/caminho/Registro_MMC.xlsx" python -m pytest tests/test_gum.py
```

## Critério de aceite do cálculo (RF03)

| Grandeza | Planilha da Schulz | Sistema |
|---|---|---|
| Incerteza combinada uc | 0,931344 µm | 0,931344 µm |
| Graus de liberdade Veff | 12 | 12 |
| Fator de abrangência k | 2,23 | 2,23 |
| Incerteza expandida U | 2,076898 µm → 0,002 mm | 2,076898 µm → 0,002 mm |

## Fluxo

1. **Pedido de envio** (`POST /calibracoes/upload`): o técnico escolhe TAG, padrão e temperatura. A API confere TAG e validade do padrão (RN04) e devolve uma URL de upload direto ao S3 (10 min, até 5 MB).
2. **Ingestão** (S3 → fn-ingestao): hash SHA-256 (RH17), leitura do Report, saneamento, validação do metrologista (RH07), de-para do código da MMC (RH08) e dupla referência instrumento + padrão (RN10; o plano de medição precisa trazer a TAG). A calibração guarda uma cópia do padrão vigente: revisão e emissão usam essa cópia, mesmo que o padrão seja atualizado depois. Qualquer regra bloqueante leva o arquivo para `quarentena/` com a regra, a célula e o valor bruto.
3. **Revisão** (`GET /calibracoes/{tag}/{id}`): GUM, banda de guarda e bloqueios calculados na hora. A banda de guarda usa o U calculado; o certificado imprime U arredondado a 3 casas. A RN04 confere se o padrão estava válido na data da medição.
4. **Emissão** (`POST /calibracoes/{tag}/{id}/emitir`): só signatário autorizado (grupo no token e atributo no cadastro, RN05), e nunca quem enviou ou executou a calibração. Número reservado em contador atômico; uma nova tentativa reaproveita o número.
5. **Consulta** (`GET /instrumentos/{tag}`): mesma resposta no computador (TAG digitada, leitor USB, webcam) e no PWA. Sempre com login e sempre registrada na auditoria, com o canal usado.
