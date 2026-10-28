// SPA: login, menu por perfil e roteamento por hash (#/rota/parametros).
// O hash funciona em qualquer hospedagem estatica (S3 + CloudFront, fn-site) e e o
// formato do link impresso no QR do certificado: #/consulta/<TAG>.

import { api } from "./api.js";
import { concluirLogin, entrar, entrarLocal, logado, modoLocal, sair } from "./auth.js";
import { erro, h, montar } from "./ui.js";
import * as envio from "./telas/envio.js";
import * as fila from "./telas/fila.js";
import * as calibracao from "./telas/calibracao.js";
import * as consulta from "./telas/consulta.js";
import * as certificado from "./telas/certificado.js";
import * as padroes from "./telas/padroes.js";
import * as auditoria from "./telas/auditoria.js";

const MENU = [
  { rota: "envio", titulo: "Enviar relatório", permissao: "enviar_relatorio" },
  { rota: "fila", titulo: "Calibrações", permissao: "ver_calibracoes" },
  { rota: "quarentena", titulo: "Quarentena", permissao: "ver_calibracoes" },
  { rota: "consulta", titulo: "Consultar instrumento", permissao: "consultar_instrumento" },
  { rota: "padroes", titulo: "Padrões", permissao: "ver_padroes" },
  { rota: "auditoria", titulo: "Auditoria", permissao: "ver_auditoria" },
];

const ROTAS = {
  envio: { tela: envio.tela, permissao: "enviar_relatorio" },
  fila: { tela: fila.tela, permissao: "ver_calibracoes" },
  quarentena: { tela: fila.telaQuarentena, permissao: "ver_calibracoes" },
  calibracao: { tela: calibracao.tela, permissao: "ver_calibracoes" },
  consulta: { tela: consulta.tela, permissao: "consultar_instrumento" },
  certificado: { tela: certificado.tela, permissao: "baixar_certificado" },
  padroes: { tela: (raiz, ctx, p) => (p.length ? padroes.telaDetalhe(raiz, ctx, p) : padroes.telaLista(raiz, ctx)),
             permissao: "ver_padroes" },
  auditoria: { tela: auditoria.tela, permissao: "ver_auditoria" },
};

const GRUPOS = {
  tecnico: "Técnico", revisor: "Revisor", signatario: "Signatário",
  admin_padrao: "Admin. de padrões", consulta: "Consulta", auditor: "Auditor",
};

const raiz = document.getElementById("conteudo");
let limpezas = [];
let navegacaoAtual = 0;

function decodificar(parte) {
  try { return decodeURIComponent(parte); } catch { return parte; }  // "%ZZ" vindo de QR ou link
}

function rotaAtual() {
  const partes = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodificar);
  return { nome: partes[0] || "", params: partes.slice(1) };
}

async function iniciar() {
  try {
    await concluirLogin();
  } catch (exc) {
    montar(raiz, erro(exc));
  }
  if (!logado()) {
    telaDeLogin();
    return;
  }
  let usuario;
  try {
    usuario = await api.eu();
  } catch (exc) {
    montar(raiz, erro(exc));
    return;
  }
  const permissoes = new Set(usuario.permissoes);
  const ctx = {
    usuario,
    pode: (acao) => permissoes.has(acao),
    somenteTecnico: usuario.grupos.includes("tecnico") &&
      !usuario.grupos.some((g) => ["revisor", "signatario", "auditor"].includes(g)),
    aoSair: (fn) => limpezas.push(fn),
    recarregar: () => navegar(),
  };
  const menu = MENU.filter((m) => ctx.pode(m.permissao));
  desenharCabecalho(usuario, menu);

  async function navegar() {
    limpezas.forEach((fn) => fn());
    limpezas = [];
    // Uma tela lenta que termina depois de o usuario trocar de rota nao pode
    // desenhar por cima da rota nova: cada navegacao so escreve na sua vez
    const geracao = ++navegacaoAtual;
    const destino = {
      replaceChildren: (...filhos) => { if (geracao === navegacaoAtual) raiz.replaceChildren(...filhos); },
    };
    const { nome, params } = rotaAtual();
    const rota = ROTAS[nome];
    if (!rota) {
      location.replace(`#/${menu[0]?.rota || "consulta"}`);
      return;
    }
    marcarMenu(nome === "calibracao" ? "fila" : nome === "certificado" ? "consulta" : nome);
    if (!ctx.pode(rota.permissao)) {
      montar(raiz, erro(new Error("Seu perfil não tem acesso a esta tela.")));
      return;
    }
    try {
      await rota.tela(destino, ctx, params);
    } catch (exc) {
      montar(destino, erro(exc));
    }
    if (geracao === navegacaoAtual) window.scrollTo(0, 0);
  }

  window.addEventListener("hashchange", navegar);
  await navegar();
}

function desenharCabecalho(usuario, menu) {
  const grupos = usuario.grupos.map((g) => GRUPOS[g] || g).join(", ") || "sem perfil";
  montar(document.getElementById("usuario"),
    h("span", { class: "usuario-nome" }, usuario.login),
    h("span", { class: "usuario-grupos" }, grupos),
    h("button", { class: "botao botao-pequeno", onclick: sair }, "Sair"));
  montar(document.getElementById("menu"),
    menu.map((m) => h("a", { href: `#/${m.rota}`, "data-rota": m.rota }, m.titulo)));
}

function marcarMenu(nome) {
  for (const link of document.querySelectorAll("#menu a")) {
    if (link.dataset.rota === nome) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function telaDeLogin() {
  const destino = location.hash;
  const deConsulta = destino.startsWith("#/consulta/");
  const texto = deConsulta
    ? "Para ver a situação deste instrumento, entre com seu usuário. Toda consulta fica registrada."
    : "Entre com seu usuário para continuar.";
  if (!modoLocal) {
    const saida = h("div", { "aria-live": "polite" });
    montar(raiz, h("section", { class: "login" },
      h("h1", {}, "Certificados de calibração"),
      h("p", {}, texto),
      h("button", { class: "botao botao-primario",
                    onclick: () => entrar(destino).catch((exc) => montar(saida, erro(exc))) }, "Entrar"),
      saida));
    return;
  }
  const usuarios = window.SCHULZ_CONFIG.usuariosLocais || [];
  montar(raiz, h("section", { class: "login" },
    h("h1", {}, "Certificados de calibração"),
    h("p", {}, texto),
    h("p", { class: "dica" }, "Modo local: escolha um usuário de teste (sem senha)."),
    h("div", { class: "lista-usuarios" }, usuarios.map((u) => h("button", {
      class: "botao", onclick: () => { entrarLocal(u.login); location.reload(); },
    }, h("strong", {}, u.login), h("small", {}, u.grupos.map((g) => GRUPOS[g] || g).join(", ")))))));
}

if ("serviceWorker" in navigator && !modoLocal) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

iniciar();
