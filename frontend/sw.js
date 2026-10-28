// Service worker do PWA: guarda so a "casca" do app (HTML, CSS, JS, icones)
// para abrir rapido e instalar no celular. Dados da API nunca sao guardados:
// a consulta precisa estar sempre atualizada e sempre passar pela auditoria.

const VERSAO = "schulz-v1";
const CASCA = [
  "./", "index.html", "config.js", "manifest.webmanifest", "css/app.css",
  "js/app.js", "js/api.js", "js/auth.js", "js/leitor.js", "js/ui.js",
  "js/telas/auditoria.js", "js/telas/calibracao.js", "js/telas/certificado.js",
  "js/telas/consulta.js", "js/telas/envio.js", "js/telas/fila.js", "js/telas/padroes.js",
  "icons/icone.svg", "icons/icone-192.png", "icons/icone-512.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSAO).then((cache) => cache.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(caches.keys()
    .then((nomes) => Promise.all(nomes.filter((n) => n !== VERSAO).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (evento) => {
  const url = new URL(evento.request.url);
  // So arquivos do proprio app; API, Cognito e S3 vao direto para a rede
  if (evento.request.method !== "GET" || url.origin !== self.location.origin) return;
  // Rede primeiro (pega a versao nova depois de um deploy); cache se offline
  evento.respondWith(
    fetch(evento.request)
      .then((resposta) => {
        // Sem guardar a volta do login (?code=...)
        if (resposta.ok && !url.search) {
          const copia = resposta.clone();
          caches.open(VERSAO).then((cache) => cache.put(evento.request, copia));
        }
        return resposta;
      })
      .catch(() => caches.match(evento.request, { ignoreSearch: true })),
  );
});
