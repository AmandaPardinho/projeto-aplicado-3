# MVP — Automação da Emissão de Certificados de Calibração

Projeto Aplicado III · Grupo 4 · UniSENAI Florianópolis
Empresa parceira: Schulz S.A. · Orientador: Prof. MSc. Hugo Menezes Barra

Aplicação web transacional (AV3 — Construção da Aplicação Transacional do MVP) que recebe a planilha de leituras exportada do Calypso, aplica as regras metrológicas definidas no Tema 01 e apresenta o parecer de conformidade numa interface simples.

## O que a aplicação faz

1. Recebe o upload de uma planilha `.xlsx` com as leituras do instrumento e os valores do padrão (colunas `DIMENSION`, `NOMINAL`, `+TOL`, `-TOL`, `MEAS 1`, `MEAS 2`).
2. Para cada característica avaliada:
   - calcula a **média** das duas medições (RN01 do Tema 01 exige exatamente duas);
   - calcula o **erro sistemático** (média − valor nominal);
   - compara o erro absoluto com o **Limite de Erro Admissível** (a tolerância `+TOL`/`-TOL`), classificando como `DENTRO_DA_TOLERANCIA` ou `FORA_DA_TOLERANCIA`.
3. Atribui o **parecer final**: `APROVADO` se todas as características estiverem dentro da tolerância, `REPROVADO` caso qualquer uma esteja fora.
4. Apresenta o resultado numa tabela, com a linha da(s) característica(s) reprovada(s) destacada.

Se alguma característica tiver campo numérico ausente ou inválido, a planilha é **recusada** (HTTP 422) com a indicação das linhas a corrigir; o sistema nunca emite parecer sobre dados parciais.

A leitura da planilha reaproveita as regras de higienização já definidas no Tema 01 (RH01 — nulos textuais, RH04 — espaços em branco, RH09 — descarte de linhas de característica vazias).

## Como rodar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python3 sample_data/gerar_amostra.py   # gera as planilhas de teste
python3 app.py                          # sobe em http://localhost:5000
```

Abra `http://localhost:5000`, envie `sample_data/amostra_aprovado.xlsx` (todas as características dentro da tolerância) ou `sample_data/amostra_reprovado.xlsx` (uma característica fora, para testar o caminho de reprovação).

## Rodando os testes automatizados

```bash
pip install -r requirements.txt   # inclui o pytest
python3 -m pytest tests/ -v
```

## Estrutura do projeto

```
app.py                     # rotas Flask (upload e processamento)
calculo.py                 # regras de negócio e cálculos (testável isoladamente)
templates/                 # upload.html, resultado.html
static/style.css           # estilo da interface
sample_data/                # gerador de planilhas de teste + amostras
tests/test_calculo.py      # testes automatizados das regras de cálculo
evidencias/                 # screenshots reais da aplicação em funcionamento
```

## Rastreabilidade com o Tema 01

| Regra implementada | Origem no Tema 01 |
|---|---|
| Duas medições obrigatórias por característica | RN01 |
| Erro sistemático = média − nominal | Seção "Regras de Negócio e Cálculos Metrológicos" do roteiro AV3 |
| Comparação com tolerância (`+TOL`/`-TOL`) | Equivalente simplificado da banda de guarda da RN02 |
| Parecer `APROVADO`/`REPROVADO` | RF06 (resumo de não conformidades) |
| Nulos textuais, espaços, linhas vazias | RH01, RH04, RH09 |

## Próximos passos (fora do escopo desta entrega)

- Cálculo de incerteza de medição pela metodologia GUM (RF03/RF04), previsto para a etapa de MVP Parte 2.
- Geração do certificado em PDF (RF08) e persistência em banco de dados.
- Autenticação e perfis de acesso (RNF08).
