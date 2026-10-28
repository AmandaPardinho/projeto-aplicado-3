"""
Nucleo da PoC de emissao de certificados de calibracao (AV4).

Modulos sem dependencia de AWS (podem ser testados isoladamente):
    xlsx          abertura do workbook, com reparo do formato OOXML Strict
    calypso       leitura e saneamento do relatorio bruto do Calypso (ETL)
    gum           orcamento de incerteza GUM do bloco volumetrico da MMC
    conformidade  banda de guarda (RN02) e resumo de nao conformidades
    certificado   geracao do PDF do certificado com QR Code

Modulos que falam com a AWS (testados com moto):
    repositorio   chaves e operacoes no DynamoDB (tabela unica)
    auditoria     trilha AUD# de quem fez o que
    autorizacao   grupos do Cognito e regras de acesso por acao
"""
