// E6-E7: revisao da calibracao (GUM + banda de guarda) e emissao.

import { api, baixarCertificado } from "../api.js";
import { aviso, campo, carregando, dataHora, erro, h, montar, notificar, numero, selo, tabela } from "../ui.js";

const MOTIVOS = {
  FORA_DA_TOLERANCIA: "média fora da tolerância",
  FORA_PELA_BANDA_DE_GUARDA: "média ± U fora da tolerância (banda de guarda)",
};

export async function tela(raiz, ctx, [tag, id]) {
  montar(raiz, h("h1", {}, `Calibração ${tag}`), carregando());
  const dados = await api.calibracao(tag, id);
  const cal = dados.calibracao;

  montar(raiz,
    h("p", { class: "migalha" }, h("a", { href: `#/fila/${cal.status}` }, "← Calibrações")),
    h("div", { class: "titulo-com-selo" }, h("h1", {}, `Calibração ${cal.tag}`), selo(cal.status)),
    cabecalho(cal),
    dados.revisao ? revisao(dados.revisao, cal, ctx) : null,
    dados.certificado ? emitida(dados.certificado, ctx) : null,
    cal.status === "CANCELADA"
      ? aviso(`Cancelada por ${cal.cancelado_por}: ${cal.justificativa_cancelamento}`, "neutro") : null,
    h("h2", {}, "Medições"),
    tabelaMedicoes(cal.caracteristicas));

  async function recarregar() {
    await tela(raiz, ctx, [tag, id]);
  }

  function revisao(rev, calibracao, contexto) {
    const resumo = rev.resumo;
    const inc = rev.incerteza;
    const area = h("div", { "aria-live": "polite" });
    const acoes = h("div", { class: "acoes" });

    if (contexto.pode("emitir_certificado")) {
      const rotuloBotao = calibracao.status === "EMITINDO" ? "Tentar emitir de novo" : "Emitir certificado";
      acoes.append(h("button", {
        class: "botao botao-primario", disabled: !rev.pode_emitir,
        onclick: async (e) => {
          const alerta = resumo.situacao === "NAO_CONFORME"
            ? `\n\nAtenção: ${resumo.nao_conformes} de ${resumo.total} características não conformes. ` +
              "O certificado registra o resultado com essa avaliação."
            : "";
          if (!confirm(`Emitir o certificado da calibração ${calibracao.tag}?${alerta}`)) return;
          e.target.disabled = true;
          montar(area, carregando("Emitindo o certificado…"));
          try {
            const certificado = await api.emitir(calibracao.tag, calibracao.calibracao_id);
            notificar(`Certificado ${certificado.numero_exibicao} emitido.`);
            await recarregar();
          } catch (exc) {
            montar(area, erro(exc));
            e.target.disabled = false;
          }
        },
      }, rotuloBotao));
    }
    if (contexto.pode("cancelar_calibracao") && calibracao.status === "AGUARDANDO_REVISAO") {
      acoes.append(h("button", { class: "botao botao-perigo", onclick: () => montar(area, formularioCancelar()) },
        "Cancelar calibração"));
    }

    return h("section", {},
      h("h2", {}, "Revisão"),
      rev.bloqueios.length
        ? h("div", { class: "alerta alerta-erro", role: "alert" },
            h("strong", {}, "A emissão está bloqueada:"),
            h("ul", {}, rev.bloqueios.map((b) => h("li", {}, b))))
        : null,
      h("div", { class: "cartoes" },
        cartao("Incerteza expandida U", `${numero(inc.incerteza_expandida_mm, 3)} mm`,
               `${numero(inc.incerteza_expandida_um, 4)} µm`),
        cartao("Fator de abrangência k", numero(inc.k), `Veff = ${inc.veff}`),
        cartao("Incerteza combinada uc", `${numero(inc.incerteza_combinada_um, 4)} µm`,
               `L = ${numero(inc.comprimento_avaliado_mm)} mm`),
        cartao("Conformidade", selo(resumo.situacao),
               `${resumo.nao_conformes} de ${resumo.total} não conformes`)),
      h("h3", {}, "Avaliação com banda de guarda (RN02)"),
      tabela([
        { titulo: "Característica", valor: (a) => a.nome },
        { titulo: "Nominal", classe: "num", valor: (a) => numero(a.valor_nominal) },
        { titulo: "Limites", classe: "num", valor: (a) => `${numero(a.limite_inferior)} a ${numero(a.limite_superior)}` },
        { titulo: "Média", classe: "num", valor: (a) => numero(a.media) },
        { titulo: "Erro", classe: "num", valor: (a) => numero(a.erro) },
        { titulo: "Situação", valor: (a) => [selo(a.situacao), a.motivo ? h("small", { class: "motivo" }, MOTIVOS[a.motivo] || a.motivo) : null] },
      ], rev.avaliacoes.map((a) => ({ ...a, _classe: a.situacao === "NAO_CONFORME" ? "linha-erro" : null }))),
      h("details", { class: "orcamento" },
        h("summary", {}, "Orçamento de incerteza (GUM)"),
        tabela([
          { titulo: "Componente", valor: (c) => c.nome },
          { titulo: "Valor", classe: "num", valor: (c) => numero(c.valor, 4) },
          { titulo: "Distribuição", valor: (c) => c.distribuicao },
          { titulo: "Divisor", classe: "num", valor: (c) => numero(c.divisor, 4) },
          { titulo: "ci", classe: "num", valor: (c) => numero(c.ci, 4) },
          { titulo: "ui (µm)", classe: "num", valor: (c) => numero(c.ui, 4) },
          { titulo: "νi", classe: "num", valor: (c) => c.vi },
        ], inc.componentes)),
      acoes, area);
  }

  function formularioCancelar() {
    const justificativa = h("textarea", { rows: 3, required: true, minlength: 10 });
    const saida = h("div");
    return h("form", { class: "formulario", onsubmit: async (e) => {
      e.preventDefault();
      try {
        await api.cancelar(cal.tag, cal.calibracao_id, justificativa.value.trim());
        notificar("Calibração cancelada.");
        await recarregar();
      } catch (exc) {
        montar(saida, erro(exc));
      }
    } },
      campo("Justificativa do cancelamento", justificativa, "Mínimo de 10 caracteres. Fica registrada na auditoria."),
      h("div", { class: "acoes" }, h("button", { type: "submit", class: "botao botao-perigo" }, "Confirmar cancelamento")),
      saida);
  }
}

function cabecalho(cal) {
  return h("dl", { class: "ficha" },
    item("Plano de medição", cal.plano),
    item("Data da medição", dataHora(cal.data_hora_medicao)),
    item("Técnico", cal.tecnico_nome || cal.metrologista_relatorio),
    item("Enviado por", cal.enviado_por),
    item("Padrão", cal.padrao_codigo),
    item("MMC no relatório", cal.codigo_mmc_relatorio),
    item("Temperatura ambiente", `${numero(cal.temperatura_ambiente)} °C`),
    item("Importado em", dataHora(cal.criado_em)),
    cal.numero_certificado ? item("Certificado", cal.numero_certificado) : null,
    item("SHA-256 do arquivo", h("code", { class: "hash" }, cal.arquivo_sha256)));
}

function emitida(cert, ctx) {
  return h("section", {},
    h("h2", {}, "Certificado"),
    h("div", { class: "cartoes" },
      cartao("Número", cert.numero_exibicao, `emitido em ${dataHora(cert.emitido_em)}`),
      cartao("Situação", selo(cert.situacao), `por ${cert.emitido_por}`),
      cartao("Incerteza expandida U", `${numero(cert.valores.incerteza.incerteza_expandida_mm, 3)} mm`,
             `k = ${numero(cert.valores.incerteza.k)}`)),
    h("div", { class: "acoes" },
      h("a", { class: "botao", href: `#/certificado/${cert.numero}` }, "Ver certificado"),
      ctx.pode("baixar_certificado")
        ? h("button", { class: "botao botao-primario", onclick: () => baixarCertificado(cert.numero).catch((e) => notificar(e.message, "erro")) }, "Baixar PDF")
        : null));
}

function tabelaMedicoes(caracteristicas) {
  return tabela([
    { titulo: "Característica", valor: (c) => c.nome },
    { titulo: "Grandeza", valor: (c) => c.grandeza },
    { titulo: "Nominal", classe: "num", valor: (c) => numero(c.valor_nominal) },
    { titulo: "Tol. +", classe: "num", valor: (c) => numero(c.tolerancia_superior) },
    { titulo: "Tol. −", classe: "num", valor: (c) => numero(c.tolerancia_inferior) },
    { titulo: "1ª passagem", classe: "num", valor: (c) => numero(c.medicao_p1) },
    { titulo: "2ª passagem", classe: "num", valor: (c) => numero(c.medicao_p2) },
  ], caracteristicas);
}

export function cartao(titulo, valor, detalhe) {
  return h("div", { class: "cartao" },
    h("span", { class: "cartao-titulo" }, titulo),
    h("strong", { class: "cartao-valor" }, valor),
    detalhe ? h("span", { class: "cartao-detalhe" }, detalhe) : null);
}

function item(rotulo, valor) {
  return [h("dt", {}, rotulo), h("dd", {}, valor ?? "—")];
}
