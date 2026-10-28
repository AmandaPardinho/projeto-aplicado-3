// Consulta do instrumento pelo TAG (RF11). Mesma tela no computador e no
// celular; toda consulta vai para a auditoria com o canal usado:
//
//   teclado  TAG digitado no navegador
//   pwa      TAG digitado no app instalado
//   leitor   leitor USB (digita o codigo em poucos milissegundos)
//   camera   QR lido pela webcam/camera nesta tela, ou link aberto a partir
//            do QR da etiqueta/certificado com a camera do celular

import { api, baixarCertificado } from "../api.js";
import { aviso, carregando, data, dataHora, erro, h, montar, notificar, selo, tabela } from "../ui.js";
import { cameraDisponivel, detectarLeitor, emModoApp, lerQrPelaCamera, tagDoCodigo } from "../leitor.js";
import { cartao } from "./calibracao.js";

let canalDaProximaConsulta = null;

export async function tela(raiz, ctx, [tagDaRota]) {
  const entrada = h("input", { name: "tag", autocomplete: "off", autofocus: true, required: true,
                               placeholder: "Digite o TAG ou use o leitor", "aria-label": "TAG do instrumento" });
  const leitor = detectarLeitor(entrada);
  const video = h("video", { class: "camera", playsinline: true, muted: true, hidden: true });
  const resultado = h("div", { "aria-live": "polite" });
  let leitura = null;

  const botaoCamera = cameraDisponivel()
    ? h("button", { type: "button", class: "botao", onclick: abrirCamera }, "Ler QR com a câmera")
    : null;

  montar(raiz,
    h("h1", {}, "Consultar instrumento"),
    h("form", { class: "busca", onsubmit: (e) => {
      e.preventDefault();
      const tag = tagDoCodigo(entrada.value);
      if (!tag) return;
      consultarPorEntrada(tag, leitor.canalAtual() === "leitor" ? "leitor" : emModoApp() ? "pwa" : "teclado");
    } },
      entrada,
      h("button", { type: "submit", class: "botao botao-primario" }, "Consultar"),
      botaoCamera),
    botaoCamera ? null : h("p", { class: "dica" },
      "Este navegador não lê QR pela câmera. No celular, aponte a câmera do aparelho para a etiqueta: ",
      "o link abre esta consulta."),
    video, resultado);

  ctx.aoSair(() => leitura?.cancelar());

  if (tagDaRota) {
    const canal = canalDaProximaConsulta || "camera";
    canalDaProximaConsulta = null;
    entrada.value = tagDaRota;
    await consultar(tagDaRota, canal);
  }

  function consultarPorEntrada(tag, canal) {
    leitor.limpar();
    canalDaProximaConsulta = canal;
    const destino = `#/consulta/${encodeURIComponent(tag)}`;
    if (location.hash === destino) ctx.recarregar();
    else location.hash = destino;
  }

  async function abrirCamera() {
    video.hidden = false;
    montar(resultado, h("div", { class: "acoes" },
      h("button", { class: "botao", onclick: () => { leitura?.cancelar(); video.hidden = true; montar(resultado); } },
        "Fechar câmera")));
    leitura = lerQrPelaCamera(video);
    try {
      const texto = await leitura.promessa;
      video.hidden = true;
      if (texto) consultarPorEntrada(tagDoCodigo(texto), "camera");
    } catch (exc) {
      video.hidden = true;
      montar(resultado, aviso(`Não foi possível usar a câmera: ${exc.message}`, "erro"));
    }
  }

  async function consultar(tag, canal) {
    montar(resultado, carregando());
    try {
      const [dados, historico] = await Promise.all([api.instrumento(tag, canal), api.historico(tag, canal)]);
      montar(resultado, ficha(dados, historico.certificados, ctx));
    } catch (exc) {
      montar(resultado, erro(exc));
    }
  }
}

function ficha(dados, certificados, ctx) {
  const inst = dados.instrumento;
  const ultimo = dados.ultimo_certificado;
  const podeBaixar = ctx.pode("baixar_certificado");
  const baixar = (numero) => baixarCertificado(numero).catch((e) => notificar(e.message, "erro"));

  return h("section", { class: `ficha-instrumento situacao-${dados.situacao.toLowerCase()}` },
    h("div", { class: "situacao" },
      selo(dados.situacao),
      h("h2", {}, `${inst.tag} · ${inst.denominacao || ""}`),
      dados.proxima_calibracao
        ? h("p", {}, dados.situacao === "VENCIDO" ? "Venceu em " : "Próxima calibração em ",
            h("strong", {}, data(dados.proxima_calibracao)))
        : h("p", {}, "Nenhum certificado emitido por este sistema.")),
    h("div", { class: "cartoes" },
      cartao("Código interno", inst.codigo_interno || "—"),
      cartao("Setor", inst.solicitante || inst.setor || "—"),
      cartao("Periodicidade", `${inst.periodicidade_meses || 12} meses`),
      ultimo ? cartao("Último certificado", ultimo.numero_exibicao, `emitido em ${dataHora(ultimo.emitido_em)}`) : null),
    ultimo && podeBaixar
      ? h("div", { class: "acoes" }, h("button", { class: "botao botao-primario", onclick: () => baixar(ultimo.numero) },
          "Baixar último certificado"))
      : null,
    h("h3", {}, "Histórico de certificados"),
    tabela([
      { titulo: "Número", valor: (c) => podeBaixar ? h("a", { href: `#/certificado/${c.numero}` }, c.numero_exibicao) : c.numero_exibicao },
      { titulo: "Emitido em", valor: (c) => dataHora(c.emitido_em) },
      { titulo: "Emitido por", valor: (c) => c.emitido_por },
      { titulo: "Resultado", valor: (c) => selo(c.situacao) },
      { titulo: "", valor: (c) => podeBaixar ? h("button", { class: "botao botao-pequeno", onclick: () => baixar(c.numero) }, "PDF") : null },
    ], certificados, "Nenhum certificado emitido."));
}
