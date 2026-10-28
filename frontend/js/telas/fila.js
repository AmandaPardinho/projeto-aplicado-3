// Fila de calibracoes por status e lista da quarentena.

import { api } from "../api.js";
import { carregando, dataHora, h, montar, rotulo, selo, tabela } from "../ui.js";

const STATUS = ["AGUARDANDO_REVISAO", "EMITINDO", "EMITIDA", "CANCELADA"];

export async function tela(raiz, ctx, [status = "AGUARDANDO_REVISAO"]) {
  const abas = h("nav", { class: "abas", "aria-label": "Status" },
    STATUS.map((s) => h("a", { href: `#/fila/${s}`, "aria-current": s === status ? "page" : null }, rotulo(s))));
  montar(raiz, h("h1", {}, "Calibrações"), abas, carregando());

  const { calibracoes } = await api.calibracoes(status);
  const link = (c) => `#/calibracao/${encodeURIComponent(c.tag)}/${c.calibracao_id}`;
  montar(raiz, h("h1", {}, "Calibrações"), abas,
    ctx.somenteTecnico ? h("p", { class: "introducao" }, "Mostrando só os relatórios que você enviou.") : null,
    tabela([
      { titulo: "TAG", valor: (c) => h("a", { href: link(c) }, c.tag) },
      { titulo: "Medição", valor: (c) => dataHora(c.data_hora_medicao) },
      { titulo: "Técnico", valor: (c) => c.tecnico_nome || c.enviado_por },
      { titulo: "Padrão", valor: (c) => c.padrao_codigo },
      { titulo: "Características", classe: "num", valor: (c) => c.caracteristicas },
      { titulo: "Certificado", valor: (c) => c.numero_certificado || "—" },
      { titulo: "Status", valor: (c) => selo(c.status) },
    ], calibracoes, `Nenhuma calibração com status "${rotulo(status)}".`));
}

export async function telaQuarentena(raiz) {
  montar(raiz, h("h1", {}, "Quarentena"), carregando());
  const { quarentena } = await api.quarentena();
  montar(raiz,
    h("h1", {}, "Quarentena"),
    h("p", { class: "introducao" },
      "Arquivos recusados na importação, com a regra que bloqueou. Ficam guardados por 90 dias. ",
      "Corrija a origem e envie o relatório de novo."),
    tabela([
      { titulo: "Recebido", valor: (q) => dataHora(q.criado_em) },
      { titulo: "TAG", valor: (q) => q.tag },
      { titulo: "Enviado por", valor: (q) => q.enviado_por },
      { titulo: "Motivo", valor: (q) => h("ul", { class: "lista-violacoes" }, q.violacoes.map((v) => h("li", {},
          h("b", {}, v.regra), " ", v.mensagem,
          v.celula ? ` (célula ${v.celula})` : "",
          v.valor_bruto !== undefined ? ` — valor lido: ${v.valor_bruto}` : ""))) },
    ], quarentena, "Nenhum arquivo em quarentena."));
}
