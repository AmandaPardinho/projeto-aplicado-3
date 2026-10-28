// Configuracao do ambiente. O deploy (Fase 3) sobrescreve este arquivo com
// os valores reais da pilha; o servidor_local.py serve a versao de modo local.
window.SCHULZ_CONFIG = {
  modo: "cognito",
  api: "https://SUBSTITUIR.execute-api.sa-east-1.amazonaws.com",
  cognito: {
    dominio: "https://SUBSTITUIR.auth.sa-east-1.amazoncognito.com",
    clientId: "SUBSTITUIR",
    redirect: null, // null = endereco da propria pagina
  },
};
