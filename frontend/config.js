// Configuracao do ambiente. Este arquivo so tem marcadores: o infra/deploy.sh
// publica no site uma versao gerada com as saidas da pilha, e o
// servidor_local.py serve a versao de modo local.
window.SCHULZ_CONFIG = {
  modo: "cognito",
  api: "https://SUBSTITUIR.execute-api.us-east-1.amazonaws.com",
  cognito: {
    dominio: "https://SUBSTITUIR.auth.us-east-1.amazoncognito.com",
    clientId: "SUBSTITUIR",
    redirect: null, // null = endereco da propria pagina
  },
};
