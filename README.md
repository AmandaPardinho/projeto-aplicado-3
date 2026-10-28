# Automação da Emissão de Certificados de Calibração — Schulz S.A.

Projeto Aplicado III · Grupo 4 · UniSENAI Florianópolis
Empresa parceira: Schulz S.A. · Orientador: Prof. MSc. Hugo Menezes Barra

Prova de conceito serverless na AWS (camada gratuita) que recebe o relatório bruto do Calypso exportado pela MMC, aplica o saneamento do Tema 01, calcula a incerteza pela metodologia GUM, avalia a conformidade com banda de guarda e emite o certificado em PDF com QR Code. A arquitetura é a da AV2: Cognito, API Gateway (HTTP API), três funções Lambda, DynamoDB em tabela única e S3.

## Situação

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 — Backend | parser do Calypso, GUM, banda de guarda, PDF, fn-api / fn-ingestao / fn-emissao, testes | concluída |
| 2 — Frontend | SPA + PWA com login, revisão, emissão, consulta por TAG/QR e trilha de auditoria | a fazer |
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
docs/
  achados-nas-planilhas.md  erros encontrados nas planilhas da Schulz
legado-av3/               MVP Flask entregue na AV3
```

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
