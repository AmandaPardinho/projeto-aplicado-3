# Achados nas planilhas da Schulz

Problemas encontrados ao reproduzir as fórmulas de `Cal_1_5896_1.xlsx` (caso 703.1208) no sistema. Nenhum deles muda o resultado impresso no certificado real 00091/2026, mas todos foram tratados de forma explícita no código.

## 1. Bloco Linear da aba Incerteza: falta a conversão de mm para µm

- **Onde:** `Incerteza!B11 = MAX(Registro!I30:I64)`.
- **O problema:** o desvio padrão vem em mm (0,000707) e entra numa coluna em µm. O bloco Volumétrico faz a conversão (`B48 = MAX(...)*1000` → 0,707 µm), o Linear não.
- **Efeito:** a dispersão fica mil vezes menor e o Veff sobe para 7413 (k = 2). As células `I17:I21` também apontam uma linha abaixo (`G18/H18` em vez de `G17/H17`).
- **No sistema:** com o padrão MMC (`Registro!C12 = 1`), o certificado usa o bloco **Volumétrico** (`Registro!D66` aponta para `Incerteza!G58`). O Linear não entra no certificado, e o sistema implementa só o Volumétrico.

## 2. Coluna M da aba Registro: limite inferior com sinal trocado

- **Onde:** `M32 = IF((H32-$D$66)<(C32-E32),"Rep","")`.
- **O problema:** `Tol. -` já vem negativo (-0,01), então `C32-E32` = 6,075 + 0,01 = 6,085 é o limite **superior**. Qualquer diâmetro abaixo de 6,085 recebe "Rep".
- **No sistema:** o limite inferior é `nominal − |Tol. -|` (6,065), que é o que a RN02 descreve. Teste: `test_diametro_dentro_da_tolerancia_e_conforme`.

## 3. Bloco de Ângulo: função inexistente

- **Onde:** `Incerteza!Q77 = Convert_Decimal("60°15'16""")`.
- **O problema:** `Convert_Decimal` não é uma função do Excel. Provavelmente é uma macro VBA que não veio no arquivo, e o resultado é `#NAME?`. O bloco "Projetor de perfil" (`G153:G155`) também dá `#VALUE!`.
- **No sistema:** uma característica de ângulo bloqueia a emissão com aviso (RN06) até a Schulz confirmar o cálculo.

## 4. Características de posição fora da tolerância

- **O que acontece:** no 703.1208, as seis características de POSIÇÃO medem de 0,13 a 0,96 para um limite de 0,1. Mesmo assim, o certificado real 00091/2026 foi emitido, porque ele registra o resultado e não traz um parecer de aprovação.
- **No sistema:** a emissão não é bloqueada por não conformidade. O PDF mostra a avaliação de cada característica e um resumo nas observações (RF06).
- **Em aberto:** confirmar com a Schulz se posição tem regra própria.

## 5. Arquivo de entrada

O `dados.xlsx` do protótipo TesteSchulz tem as mesmas 11 abas da pasta de calibração preenchida pelo técnico (Registro, Incerteza, Certificado...). Ele não é a saída do Calypso. A entrada do sistema é o Report do Calypso (`Registro_MMC.xlsx`), como definido na AV1 e na AV2.
