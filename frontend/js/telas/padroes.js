// Cadastro de padroes (RF10) e atualizacao apos nova calibracao (UC03).

import { api } from "../api.js";
import { aviso, campo, carregando, data, dataHora, erro, h, montar, notificar, numero, selo, tabela } from "../ui.js";

const CAMPOS_TEXTO = [
  ["descricao", "Descrição"], ["fabricante", "Fabricante"], ["modelo", "Modelo"],
  ["numero_serie", "Número de série"], ["certificado_externo", "Certificado externo"],
  ["executante", "Laboratório executante"],
];

const ORCAMENTO = [
  ["incerteza_mmc_um", "Incerteza da MMC (µm)"],
  ["erro_sistematico_mmc_um", "Erro sistemático da MMC (µm)"],
  ["incerteza_esfera_um", "Incerteza da esfera (µm)"],
  ["repetitividade_apalpador_um", "Repetitividade do apalpador (µm)"],
  ["resolucao_um", "Resolução (µm)"],
  ["alfa_objeto", "Coef. de dilatação do objeto (10⁻⁶/°C)"],
  ["variacao_temperatura_20c", "Variação de temperatura em relação a 20 °C"],
  ["diferenca_temperatura_padrao_objeto", "Diferença de temperatura padrão/objeto (°C)"],
];

const vencido = (p) => p.data_proxima_calibracao < new Date().toISOString().slice(0, 10);

export async function telaLista(raiz) {
  montar(raiz, h("h1", {}, "Padrões"), carregando());
  const { padroes } = await api.padroes();
  montar(raiz, h("h1", {}, "Padrões"),
    tabela([
      { titulo: "Código", valor: (p) => h("a", { href: `#/padroes/${encodeURIComponent(p.codigo)}` }, p.codigo) },
      { titulo: "Descrição", valor: (p) => p.descricao },
      { titulo: "Certificado", valor: (p) => p.certificado_externo },
      { titulo: "Válido até", valor: (p) => data(p.data_proxima_calibracao) },
      { titulo: "Situação", valor: (p) => selo(vencido(p) ? "VENCIDO" : "EM_DIA") },
    ], padroes, "Nenhum padrão cadastrado."));
}

export async function telaDetalhe(raiz, ctx, [codigo]) {
  montar(raiz, h("h1", {}, `Padrão ${codigo}`), carregando());
  const { padrao, vencido: estaVencido, historico } = await api.padrao(codigo);

  montar(raiz,
    h("p", { class: "migalha" }, h("a", { href: "#/padroes" }, "← Padrões")),
    h("div", { class: "titulo-com-selo" }, h("h1", {}, `Padrão ${padrao.codigo}`),
      selo(estaVencido ? "VENCIDO" : "EM_DIA")),
    estaVencido
      ? aviso(`RN04: calibração do padrão vencida em ${data(padrao.data_proxima_calibracao)}. ` +
              "Novos envios com este padrão são recusados até a atualização.", "erro")
      : null,
    ctx.pode("atualizar_padrao") ? formulario(padrao) : ficha(padrao),
    h("h2", {}, "Histórico de calibrações do padrão"),
    tabela([
      { titulo: "Calibrado em", valor: (v) => data(v.data_ultima_calibracao) },
      { titulo: "Válido até", valor: (v) => data(v.data_proxima_calibracao) },
      { titulo: "Certificado", valor: (v) => v.certificado_externo },
      { titulo: "Atualizado por", valor: (v) => v.atualizado_por || "—" },
      { titulo: "Em", valor: (v) => dataHora(v.atualizado_em) },
    ], historico, "Sem atualizações registradas."));

  function formulario(p) {
    const entradas = {};
    const saida = h("div", { "aria-live": "polite" });
    const texto = (nome) => (entradas[nome] = h("input", { value: p[nome] ?? "" }));
    const dataEntrada = (nome) => (entradas[nome] = h("input", { type: "date", required: true, value: p[nome] ?? "" }));
    const orcamento = {};
    return h("form", { class: "formulario", onsubmit: async (e) => {
      e.preventDefault();
      const corpo = Object.fromEntries(Object.entries(entradas).map(([k, el]) => [k, el.value.trim()]));
      corpo.orcamento = {};
      for (const [nome, el] of Object.entries(orcamento)) {
        const valor = Number(el.value.trim().replace(",", "."));
        if (el.value.trim() === "" || Number.isNaN(valor)) {
          montar(saida, aviso(`Valor inválido em "${ORCAMENTO.find(([n]) => n === nome)[1]}".`, "erro"));
          return;
        }
        corpo.orcamento[nome] = valor;
      }
      try {
        await api.atualizarPadrao(p.codigo, corpo);
        notificar(`Padrão ${p.codigo} atualizado.`);
        await telaDetalhe(raiz, ctx, [codigo]);
      } catch (exc) {
        montar(saida, erro(exc));
      }
    } },
      h("h2", {}, "Atualizar após nova calibração"),
      h("p", { class: "introducao" },
        "A versão atual vai para o histórico. Os certificados já emitidos não mudam: guardam uma cópia dos dados do padrão."),
      h("div", { class: "grade" },
        CAMPOS_TEXTO.map(([nome, r]) => campo(r, texto(nome))),
        campo("Data da calibração", dataEntrada("data_ultima_calibracao")),
        campo("Próxima calibração", dataEntrada("data_proxima_calibracao"))),
      h("h3", {}, "Orçamento de incerteza"),
      h("div", { class: "grade" },
        ORCAMENTO.map(([nome, r]) => campo(r, (orcamento[nome] = h("input", {
          inputmode: "decimal", required: true, value: numero(p.orcamento?.[nome]).replace(/\./g, "") }))))),
      h("div", { class: "acoes" }, h("button", { type: "submit", class: "botao botao-primario" }, "Salvar nova versão")),
      saida);
  }
}

function ficha(p) {
  return h("dl", { class: "ficha" },
    [...CAMPOS_TEXTO, ["data_ultima_calibracao", "Data da calibração"], ["data_proxima_calibracao", "Próxima calibração"]]
      .map(([nome, r]) => [h("dt", {}, r), h("dd", {}, nome.startsWith("data_") ? data(p[nome]) : p[nome] ?? "—")]),
    ORCAMENTO.map(([nome, r]) => [h("dt", {}, r), h("dd", {}, numero(p.orcamento?.[nome]))]));
}
