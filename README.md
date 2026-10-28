# Automação da Emissão de Certificados de Calibração — Schulz S.A.

Projeto Aplicado III · Grupo 4 · UniSENAI Florianópolis
Empresa parceira: Schulz S.A. · Orientador: Prof. MSc. Hugo Menezes Barra

Prova de conceito serverless na AWS (camada gratuita) que recebe o relatório bruto do Calypso exportado pela MMC, aplica o saneamento do Tema 01, calcula a incerteza pela metodologia GUM, avalia a conformidade com banda de guarda e emite o certificado em PDF com QR Code. A arquitetura é a da AV2: Cognito, API Gateway (HTTP API), três funções Lambda, DynamoDB em tabela única e S3.

## Situação

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 — Backend | parser do Calypso, GUM, banda de guarda, PDF, fn-api / fn-ingestao / fn-emissao, testes | concluída |
| 2 — Frontend | SPA + PWA com login, revisão, emissão, consulta por TAG/QR e trilha de auditoria | concluída |
| 3 — Infraestrutura | template AWS SAM, `deploy.sh`, carga inicial | a fazer |
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
  tests/                  pytest + moto (DynamoDB e S3 simulados)
  servidor_local.py       roda as Lambdas + frontend sem AWS, para testar as telas
frontend/                 SPA estática (HTML, CSS e JS puros, sem etapa de build) + PWA
  index.html, config.js   página única; config.js é gerado no deploy (URL da API, Cognito)
  js/auth.js              login no Cognito Hosted UI (Authorization Code + PKCE)
  js/leitor.js            canais de consulta: TAG digitado, leitor USB e câmera (QR)
  js/telas/               envio, fila, revisão/emissão, quarentena, consulta, certificado,
                          padrões e auditoria
  sw.js, manifest.webmanifest   PWA instalável no celular (guarda só a casca do app)
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
| Signatário | tudo do revisor + emissão do certificado (RN05) |
| Admin. de padrões | cadastro e atualização dos padrões (UC03) |
| Consulta | situação do instrumento por TAG/QR e download do certificado do próprio setor |
| Auditor | trilha de auditoria por dia, com usuário, ação, alvo e canal |

A consulta do instrumento registra o canal usado: TAG digitado (teclado ou PWA), leitor USB (detectado pela velocidade da digitação) ou câmera (leitura do QR na tela, ou link aberto pelo QR da etiqueta).

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
2. **Ingestão** (S3 → fn-ingestao): hash SHA-256 (RH17), leitura do Report, saneamento, validação do metrologista (RH07), de-para do código da MMC (RH08) e dupla referência instrumento + padrão (RN10). Qualquer regra bloqueante leva o arquivo para `quarentena/` com a regra, a célula e o valor bruto.
3. **Revisão** (`GET /calibracoes/{tag}/{id}`): GUM, banda de guarda e bloqueios calculados na hora.
4. **Emissão** (`POST /calibracoes/{tag}/{id}/emitir`): só signatário autorizado (grupo no token e atributo no cadastro, RN05). Número reservado em contador atômico; uma nova tentativa reaproveita o número.
5. **Consulta** (`GET /instrumentos/{tag}`): mesma resposta no computador (TAG digitada, leitor USB, webcam) e no PWA. Sempre com login e sempre registrada na auditoria, com o canal usado.
