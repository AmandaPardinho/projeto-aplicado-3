// Canais de consulta do instrumento: TAG digitada, leitor USB e camera.
//
// O leitor USB se comporta como teclado: "digita" o codigo inteiro em poucos
// milissegundos e termina com Enter. A diferenca para uma pessoa digitando e
// so a velocidade, e e por ela que o canal e identificado na auditoria.
// Um leitor 2D lendo o QR da etiqueta digita a URL inteira; tagDoCodigo
// extrai o TAG dela.

const INTERVALO_MAXIMO_LEITOR_MS = 35;

export function tagDoCodigo(texto) {
  const valor = (texto || "").trim();
  const rota = valor.match(/#\/consulta\/([^/?#\s]+)/);
  if (rota) return decodeURIComponent(rota[1]);
  return valor;
}

// Liga ao campo de TAG; canalAtual() diz se a ultima entrada veio do leitor
export function detectarLeitor(entrada) {
  let teclas = [];
  entrada.addEventListener("keydown", (evento) => {
    if (evento.key.length === 1) teclas.push(performance.now());
  });
  entrada.addEventListener("input", () => {
    if (!entrada.value) teclas = [];
  });
  return {
    canalAtual() {
      if (teclas.length < 4) return "teclado";
      const intervalos = teclas.slice(1).map((t, i) => t - teclas[i]);
      const medio = intervalos.reduce((a, b) => a + b, 0) / intervalos.length;
      return medio < INTERVALO_MAXIMO_LEITOR_MS ? "leitor" : "teclado";
    },
    limpar() { teclas = []; },
  };
}

export function cameraDisponivel() {
  return "BarcodeDetector" in window && Boolean(navigator.mediaDevices?.getUserMedia);
}

// Le um QR pela camera. Resolve com o texto lido; cancelar() para tudo.
export function lerQrPelaCamera(video) {
  let fluxo;
  let ativo = true;
  const parar = () => {
    ativo = false;
    fluxo?.getTracks().forEach((t) => t.stop());
    video.srcObject = null;
  };
  const promessa = (async () => {
    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    fluxo = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } }, audio: false,
    });
    video.srcObject = fluxo;
    await video.play();
    while (ativo) {
      const codigos = await detector.detect(video).catch(() => []);
      if (codigos.length) {
        parar();
        return codigos[0].rawValue;
      }
      await new Promise((r) => setTimeout(r, 200));
    }
    return null;
  })();
  promessa.catch(parar);
  return { promessa, cancelar: parar };
}

// Aberto como app instalado (PWA) ou no navegador
export function emModoApp() {
  return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}
