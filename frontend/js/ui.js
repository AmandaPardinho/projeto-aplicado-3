// Helpers de interface. Todo texto vindo da API entra como textContent,
// nunca como HTML, para nao abrir brecha de XSS.

export function h(tag, atributos = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [nome, valor] of Object.entries(atributos || {})) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (nome.startsWith("on")) el.addEventListener(nome.slice(2), valor);
    else if (nome === "class") el.className = valor;
    else if (valor === true) el.setAttribute(nome, "");
    else el.setAttribute(nome, valor);
  }
  for (const filho of filhos.flat(Infinity)) {
    if (filho === null || filho === undefined || filho === false) continue;
    el.append(filho instanceof Node ? filho : String(filho));
  }
  return el;
}

export function montar(raiz, ...filhos) {
  raiz.replaceChildren(...filhos.flat(Infinity).filter((f) => f !== null && f !== undefined));
}

export function dataHora(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function data(iso) {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

// A API manda decimais como texto para nao perder casas (RNF10)
export function numero(valor, casas) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  if (Number.isNaN(n)) return String(valor);
  const opcoes = casas === undefined
    ? { maximumFractionDigits: 7 }
    : { minimumFractionDigits: casas, maximumFractionDigits: casas };
  return n.toLocaleString("pt-BR", opcoes);
}

const ROTULOS_STATUS = {
  AGUARDANDO_REVISAO: "Aguardando revisão",
  EMITINDO: "Emitindo",
  EMITIDA: "Emitida",
  CANCELADA: "Cancelada",
  QUARENTENA: "Quarentena",
  CONFORME: "Conforme",
  NAO_CONFORME: "Não conforme",
  EM_DIA: "Calibração em dia",
  VENCIDO: "Calibração vencida",
  SEM_CERTIFICADO: "Sem certificado emitido",
};

const CLASSES_STATUS = {
  AGUARDANDO_REVISAO: "aviso", EMITINDO: "aviso", EMITIDA: "ok", CANCELADA: "neutro",
  QUARENTENA: "erro", CONFORME: "ok", NAO_CONFORME: "erro", EM_DIA: "ok",
  VENCIDO: "erro", SEM_CERTIFICADO: "aviso",
};

export function rotulo(status) {
  return ROTULOS_STATUS[status] || status;
}

export function selo(status) {
  return h("span", { class: `selo selo-${CLASSES_STATUS[status] || "neutro"}` }, rotulo(status));
}

export function tabela(colunas, linhas, vazio = "Nada por aqui.") {
  if (!linhas.length) return h("p", { class: "vazio" }, vazio);
  return h("div", { class: "rolagem" },
    h("table", {},
      h("thead", {}, h("tr", {}, colunas.map((c) => h("th", { class: c.classe }, c.titulo)))),
      h("tbody", {}, linhas.map((linha) => h("tr", { class: linha._classe },
        colunas.map((c) => h("td", { class: c.classe, "data-titulo": c.titulo }, c.valor(linha))))))));
}

export function carregando(texto = "Carregando…") {
  return h("p", { class: "carregando", role: "status" }, texto);
}

export function erro(exc) {
  const itens = Array.isArray(exc?.detalhes) ? exc.detalhes : [];
  return h("div", { class: "alerta alerta-erro", role: "alert" },
    h("strong", {}, exc?.message || String(exc)),
    itens.length ? h("ul", {}, itens.map((d) => h("li", {}, d.mensagem || JSON.stringify(d)))) : null);
}

export function aviso(texto, tipo = "aviso") {
  return h("div", { class: `alerta alerta-${tipo}`, role: tipo === "erro" ? "alert" : "status" }, texto);
}

export function campo(rotuloTexto, entrada, ajuda) {
  return h("label", { class: "campo" },
    h("span", { class: "campo-rotulo" }, rotuloTexto), entrada,
    ajuda ? h("small", {}, ajuda) : null);
}

let avisoTemporario;
export function notificar(texto, tipo = "ok") {
  const el = document.getElementById("notificacao");
  el.className = `notificacao notificacao-${tipo} visivel`;
  el.textContent = texto;
  clearTimeout(avisoTemporario);
  avisoTemporario = setTimeout(() => el.classList.remove("visivel"), 4000);
}
