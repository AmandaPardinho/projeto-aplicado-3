// E1-E5: o tecnico envia o Report do Calypso e acompanha a ingestao.

import { api, enviarParaS3, ErroApi } from "../api.js";
import { aviso, campo, carregando, erro, h, montar, numero } from "../ui.js";

const TAMANHO_MAXIMO = 5 * 1024 * 1024;
const TENTATIVAS = 15;
const ESPERA_MS = 2000;

export async function tela(raiz, ctx) {
  montar(raiz, h("h1", {}, "Enviar relatório do Calypso"), carregando());
  const { padroes } = await api.padroes();

  const tag = h("input", { name: "tag", required: true, autocomplete: "off",
                           placeholder: "ex.: 703.1208", inputmode: "decimal" });
  const padrao = h("select", { name: "padrao", required: true },
    padroes.map((p) => h("option", { value: p.codigo },
      `${p.codigo} — ${p.descricao} (válido até ${p.data_proxima_calibracao.split("-").reverse().join("/")})`)));
  const temperatura = h("input", { name: "temperatura", required: true, inputmode: "decimal",
                                   placeholder: "ex.: 20,3" });
  const arquivo = h("input", { name: "arquivo", type: "file", required: true,
                               accept: ".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const botao = h("button", { type: "submit", class: "botao botao-primario" }, "Enviar");
  const resultado = h("div", { class: "resultado-envio", "aria-live": "polite" });

  const formulario = h("form", { class: "formulario", onsubmit: enviar },
    campo("TAG do instrumento", tag),
    campo("Padrão utilizado", padrao),
    campo("Temperatura ambiente (°C)", temperatura, "RN09: obrigatória no envio."),
    campo("Relatório (Report do Calypso)", arquivo, ".xlsx ou .xlsm, até 5 MB."),
    h("div", { class: "acoes" }, botao));

  montar(raiz,
    h("h1", {}, "Enviar relatório do Calypso"),
    h("p", { class: "introducao" },
      "O arquivo vai direto para o armazenamento e é processado em seguida. ",
      "Se alguma regra bloquear a importação, ele fica em quarentena com o motivo."),
    window.SCHULZ_CONFIG.exemploReport
      ? h("p", { class: "dica" }, "Para testar: ",
          h("a", { href: window.SCHULZ_CONFIG.exemploReport }, "baixe um Report de exemplo do 703.1208"),
          " para testar o envio.")
      : null,
    formulario, resultado);

  async function enviar(evento) {
    evento.preventDefault();
    const arq = arquivo.files[0];
    if (!arq) return;
    if (arq.size > TAMANHO_MAXIMO) {
      montar(resultado, aviso("O arquivo passa de 5 MB.", "erro"));
      return;
    }
    botao.disabled = true;
    montar(resultado, carregando("Pedindo autorização de envio…"));
    try {
      const pedido = await api.pedirUpload({
        tag: tag.value.trim(), padrao_codigo: padrao.value, nome_arquivo: arq.name,
        tamanho_bytes: arq.size, temperatura_ambiente: temperatura.value.trim(),
      });
      montar(resultado, carregando("Enviando o arquivo…"));
      await enviarParaS3(pedido.upload, arq);
      montar(resultado, carregando("Arquivo recebido. Processando o relatório…"));
      await acompanhar(tag.value.trim(), pedido.calibracao_id);
      formulario.reset();
    } catch (exc) {
      montar(resultado, erro(exc));
    } finally {
      botao.disabled = false;
    }
  }

  // A ingestao e assincrona (evento do S3): consulta ate a calibracao
  // aparecer ou o arquivo cair na quarentena.
  async function acompanhar(tagEnviada, id) {
    for (let i = 0; i < TENTATIVAS; i++) {
      await new Promise((r) => setTimeout(r, ESPERA_MS));
      try {
        const { calibracao } = await api.calibracao(tagEnviada, id);
        montar(resultado,
          aviso(`Relatório importado: ${calibracao.caracteristicas.length} características, ` +
                `temperatura ${numero(calibracao.temperatura_ambiente)} °C. ` +
                "A calibração está aguardando revisão.", "ok"),
          ctx.pode("ver_calibracoes")
            ? h("a", { class: "botao", href: `#/calibracao/${encodeURIComponent(tagEnviada)}/${id}` }, "Abrir calibração")
            : null);
        return;
      } catch (exc) {
        if (!(exc instanceof ErroApi) || exc.status !== 404) throw exc;
      }
      const { quarentena } = await api.quarentena();
      const recusado = quarentena.find((q) => q.calibracao_id === id);
      if (recusado) {
        montar(resultado, h("div", { class: "alerta alerta-erro", role: "alert" },
          h("strong", {}, "O relatório foi para a quarentena."),
          h("ul", {}, recusado.violacoes.map((v) => h("li", {},
            h("b", {}, v.regra), " ", v.mensagem,
            v.celula ? ` (célula ${v.celula})` : "",
            v.valor_bruto !== undefined ? ` — valor lido: ${v.valor_bruto}` : "")))));
        return;
      }
    }
    montar(resultado, aviso("O processamento está demorando. Confira a fila e a quarentena em alguns minutos."));
  }
}
