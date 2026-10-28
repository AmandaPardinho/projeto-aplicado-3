// Login pelo Cognito Hosted UI com Authorization Code + PKCE, sem biblioteca.
//
// Os tokens ficam no sessionStorage: somem quando a aba fecha. Para quem usa
// o PWA isso significa logar de novo ao reabrir, mas o Hosted UI guarda a
// propria sessao e o login costuma ser um clique. Toda consulta exige login.
//
// Modo local (servidor_local.py): nao ha Cognito; a tela de login lista os
// usuarios de teste e a API recebe o login no cabecalho X-Usuario-Local.

const config = window.SCHULZ_CONFIG;
const CHAVE_TOKENS = "schulz.tokens";
const CHAVE_PKCE = "schulz.pkce";
const CHAVE_LOCAL = "schulz.usuario-local";

function ler(chave) {
  try { return JSON.parse(sessionStorage.getItem(chave)); } catch { return null; }
}

function gravar(chave, valor) {
  try {
    if (valor === null) sessionStorage.removeItem(chave);
    else sessionStorage.setItem(chave, JSON.stringify(valor));
  } catch { /* navegacao privada sem storage: segue so em memoria */ }
}

export const modoLocal = config.modo === "local";

function base64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function aleatorio(tamanho = 32) {
  return base64url(crypto.getRandomValues(new Uint8Array(tamanho)));
}

function redirecionamento() {
  return config.cognito.redirect || `${location.origin}${location.pathname}`;
}

export async function entrar(destino = location.hash) {
  const verificador = aleatorio(48);
  const estado = aleatorio(16);
  const desafio = base64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verificador)));
  gravar(CHAVE_PKCE, { verificador, estado, destino });
  const params = new URLSearchParams({
    response_type: "code",
    client_id: config.cognito.clientId,
    redirect_uri: redirecionamento(),
    scope: "openid email profile",
    code_challenge_method: "S256",
    code_challenge: desafio,
    state: estado,
  });
  location.assign(`${config.cognito.dominio}/oauth2/authorize?${params}`);
}

async function pedirTokens(parametros) {
  const resposta = await fetch(`${config.cognito.dominio}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: config.cognito.clientId, ...parametros }),
  });
  if (!resposta.ok) throw new Error("não foi possível concluir o login");
  const corpo = await resposta.json();
  const anteriores = ler(CHAVE_TOKENS) || {};
  const tokens = {
    id: corpo.id_token,
    refresh: corpo.refresh_token || anteriores.refresh,
    expira: Date.now() + (corpo.expires_in - 60) * 1000,
  };
  gravar(CHAVE_TOKENS, tokens);
  return tokens;
}

// Volta do Hosted UI: troca o ?code= pelos tokens e devolve a rota de destino
export async function concluirLogin() {
  if (modoLocal) return null;
  const params = new URLSearchParams(location.search);
  const codigo = params.get("code");
  if (!codigo) return null;
  const pkce = ler(CHAVE_PKCE);
  gravar(CHAVE_PKCE, null);
  history.replaceState(null, "", location.pathname + (pkce?.destino || ""));
  if (!pkce || pkce.estado !== params.get("state")) throw new Error("login inválido; tente de novo");
  await pedirTokens({ grant_type: "authorization_code", code: codigo,
                      redirect_uri: redirecionamento(), code_verifier: pkce.verificador });
  return pkce.destino;
}

export function logado() {
  return modoLocal ? Boolean(ler(CHAVE_LOCAL)) : Boolean(ler(CHAVE_TOKENS));
}

// Cabecalhos de autenticacao de uma chamada a API. O token enviado e o ID
// token: e nele que o Cognito poe custom:matricula e custom:setor.
export async function cabecalhos() {
  if (modoLocal) return { "X-Usuario-Local": ler(CHAVE_LOCAL) };
  let tokens = ler(CHAVE_TOKENS);
  if (!tokens) return {};
  if (Date.now() > tokens.expira && tokens.refresh) {
    try {
      tokens = await pedirTokens({ grant_type: "refresh_token", refresh_token: tokens.refresh });
    } catch {
      gravar(CHAVE_TOKENS, null);
      return {};
    }
  }
  return { Authorization: `Bearer ${tokens.id}` };
}

export function entrarLocal(login) {
  gravar(CHAVE_LOCAL, login);
}

export function sair() {
  gravar(CHAVE_TOKENS, null);
  gravar(CHAVE_LOCAL, null);
  if (modoLocal) {
    location.hash = "#/";
    location.reload();
    return;
  }
  const params = new URLSearchParams({ client_id: config.cognito.clientId, logout_uri: redirecionamento() });
  location.assign(`${config.cognito.dominio}/logout?${params}`);
}

export function esquecerSessao() {
  gravar(CHAVE_TOKENS, null);
  gravar(CHAVE_LOCAL, null);
}
