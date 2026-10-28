// Chamadas a HTTP API. Erros da API viram ErroApi com a mensagem em portugues
// que o backend ja manda (inclusive o codigo da regra: RN04, RH07...).

import { cabecalhos, esquecerSessao } from "./auth.js";

const base = window.SCHULZ_CONFIG.api.replace(/\/$/, "");

export class ErroApi extends Error {
  constructor(mensagem, status, detalhes) {
    super(mensagem);
    this.status = status;
    this.detalhes = detalhes;
  }
}

export async function chamar(metodo, caminho, { corpo, consulta } = {}) {
  const url = new URL(base + caminho, location.href);
  for (const [k, v] of Object.entries(consulta || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const opcoes = { method: metodo, headers: await cabecalhos() };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  let resposta;
  try {
    resposta = await fetch(url, opcoes);
  } catch {
    throw new ErroApi("sem conexão com o servidor", 0);
  }
  const texto = await resposta.text();
  let dados = null;
  try { dados = texto ? JSON.parse(texto) : null; } catch { dados = { erro: texto }; }
  if (resposta.status === 401) {
    esquecerSessao();
    location.reload();
    throw new ErroApi("sessão expirada", 401);
  }
  if (!resposta.ok) {
    throw new ErroApi(dados?.erro || dados?.message || `erro ${resposta.status}`,
                      resposta.status, dados?.detalhes);
  }
  return dados;
}

const enc = encodeURIComponent;

export const api = {
  eu: () => chamar("GET", "/me"),
  pedirUpload: (corpo) => chamar("POST", "/calibracoes/upload", { corpo }),
  calibracoes: (status) => chamar("GET", "/calibracoes", { consulta: { status } }),
  calibracao: (tag, id) => chamar("GET", `/calibracoes/${enc(tag)}/${enc(id)}`),
  cancelar: (tag, id, justificativa) =>
    chamar("POST", `/calibracoes/${enc(tag)}/${enc(id)}/cancelar`, { corpo: { justificativa } }),
  emitir: (tag, id) => chamar("POST", `/calibracoes/${enc(tag)}/${enc(id)}/emitir`, { corpo: {} }),
  quarentena: () => chamar("GET", "/quarentena"),
  instrumento: (tag, canal) => chamar("GET", `/instrumentos/${enc(tag)}`, { consulta: { canal } }),
  historico: (tag, canal) => chamar("GET", `/instrumentos/${enc(tag)}/certificados`, { consulta: { canal } }),
  certificado: (numero) => chamar("GET", `/certificados/${enc(numero)}`),
  download: (numero) => chamar("GET", `/certificados/${enc(numero)}/download`),
  padroes: () => chamar("GET", "/padroes"),
  padrao: (codigo) => chamar("GET", `/padroes/${enc(codigo)}`),
  atualizarPadrao: (codigo, corpo) => chamar("PUT", `/padroes/${enc(codigo)}`, { corpo }),
  auditoria: (dia) => chamar("GET", "/auditoria", { consulta: { data: dia } }),
};

// Envio direto ao S3 com o presigned POST (o arquivo nao passa pela Lambda)
export async function enviarParaS3(upload, arquivo) {
  const formulario = new FormData();
  for (const [k, v] of Object.entries(upload.fields)) formulario.append(k, v);
  formulario.append("file", arquivo);
  let resposta;
  try {
    resposta = await fetch(upload.url, { method: "POST", body: formulario });
  } catch {
    throw new ErroApi("falha ao enviar o arquivo; verifique a conexão", 0);
  }
  if (!resposta.ok) throw new ErroApi(`o armazenamento recusou o arquivo (erro ${resposta.status})`, resposta.status);
}

export async function baixarCertificado(numero) {
  const { url } = await api.download(numero);
  location.assign(url);
}
