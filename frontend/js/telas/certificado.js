// Valores congelados de um certificado emitido (RNF09) e download do PDF (E8).

import { api, baixarCertificado } from "../api.js";
import { carregando, dataHora, h, montar, notificar, numero, selo, tabela } from "../ui.js";
import { cartao } from "./calibracao.js";

export async function tela(raiz, ctx, [num]) {
  montar(raiz, h("h1", {}, "Certificado"), carregando());
  const cert = await api.certificado(num);
  const v = cert.valores;

  montar(raiz,
    h("p", { class: "migalha" }, h("a", { href: `#/consulta/${encodeURIComponent(cert.tag)}` }, `← Instrumento ${cert.tag}`)),
    h("div", { class: "titulo-com-selo" }, h("h1", {}, `Certificado ${cert.numero_exibicao}`), selo(cert.situacao)),
    h("div", { class: "acoes" },
      h("button", { class: "botao botao-primario",
                    onclick: () => baixarCertificado(cert.numero).catch((e) => notificar(e.message, "erro")) },
        "Baixar PDF")),
    h("div", { class: "cartoes" },
      cartao("Incerteza expandida U", `${numero(v.incerteza.incerteza_expandida_mm, 3)} mm`,
             `k = ${numero(v.incerteza.k)} · Veff = ${v.incerteza.veff}`),
      cartao("Data da calibração", v.data_calibracao, `temperatura ${numero(v.temperatura_ambiente)} °C`),
      cartao("Emitido em", dataHora(cert.emitido_em), `por ${v.signatario.nome}`)),
    h("h2", {}, "Instrumento e padrão"),
    h("dl", { class: "ficha" },
      [["TAG", v.instrumento.tag], ["Código interno", v.instrumento.codigo_interno],
       ["Denominação", v.instrumento.denominacao], ["Fabricante", v.instrumento.fabricante],
       ["Padrão", `${v.padrao.codigo} — ${v.padrao.descricao}`],
       ["Certificado do padrão", `${v.padrao.certificado_externo} (${v.padrao.executante})`],
       ["Validade do padrão", v.padrao.data_proxima_calibracao],
       ["Técnico executante", v.tecnico_executante],
       ["Signatário", `${v.signatario.nome} (matrícula ${v.signatario.matricula})`]]
        .map(([r, valor]) => [h("dt", {}, r), h("dd", {}, valor ?? "—")])),
    h("h2", {}, "Resultados"),
    tabela([
      { titulo: "Característica", valor: (a) => a.nome },
      { titulo: "Nominal", classe: "num", valor: (a) => numero(a.valor_nominal) },
      { titulo: "Média", classe: "num", valor: (a) => numero(a.media) },
      { titulo: "Erro", classe: "num", valor: (a) => numero(a.erro) },
      { titulo: "Situação", valor: (a) => selo(a.situacao) },
    ], v.resultados),
    h("h2", {}, "Integridade"),
    h("dl", { class: "ficha" },
      h("dt", {}, "Código de verificação"), h("dd", {}, h("code", { class: "hash" }, cert.codigo_verificacao)),
      h("dt", {}, "SHA-256 do PDF"), h("dd", {}, h("code", { class: "hash" }, cert.pdf_sha256))));
}
