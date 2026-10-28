// Trilha AUD#: quem fez o que, quando e por qual canal (so perfil auditor).

import { api } from "../api.js";
import { carregando, dataHora, h, montar, tabela } from "../ui.js";

const ACOES = {
  solicitar_envio: "Pediu envio de relatório",
  importar_relatorio: "Relatório importado",
  relatorio_em_quarentena: "Relatório em quarentena",
  visualizar_calibracao: "Abriu calibração",
  cancelar_calibracao: "Cancelou calibração",
  emitir_certificado: "Emitiu certificado",
  consultar_instrumento: "Consultou instrumento",
  consultar_historico: "Consultou histórico",
  visualizar_certificado: "Abriu certificado",
  baixar_certificado: "Baixou certificado",
  atualizar_padrao: "Atualizou padrão",
};

const CANAIS = {
  teclado: "Teclado", leitor: "Leitor USB", camera: "Câmera / QR", pwa: "App (PWA)", sistema: "Sistema",
};

function hoje() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export async function tela(raiz, ctx, [dia = hoje()]) {
  const seletor = h("input", { type: "date", value: dia, max: hoje(),
                               onchange: (e) => { if (e.target.value) location.hash = `#/auditoria/${e.target.value}`; } });
  const filtro = h("input", { type: "search", placeholder: "Filtrar por usuário, ação ou alvo" });
  const area = h("div");
  montar(raiz, h("h1", {}, "Trilha de auditoria"),
    h("div", { class: "busca" }, seletor, filtro), area);
  montar(area, carregando());

  // A trilha e particionada por dia em UTC (AUD#<aaaa-mm-dd>). Um dia no
  // horario local cruza dois dias UTC: busca os dois e filtra pelo intervalo.
  const inicio = new Date(`${dia}T00:00:00`);
  const fim = new Date(inicio.getTime() + 24 * 3600 * 1000);
  const diasUtc = [...new Set([inicio, new Date(fim.getTime() - 1)].map((d) => d.toISOString().slice(0, 10)))];
  const partes = await Promise.all(diasUtc.map((d) => api.auditoria(d)));
  const registros = partes.flatMap((p) => p.registros)
    .filter((r) => { const t = new Date(r.quando); return t >= inicio && t < fim; })
    .sort((a, b) => b.quando.localeCompare(a.quando));
  const desenhar = () => {
    const termo = filtro.value.trim().toLowerCase();
    const visiveis = registros.filter((r) => !termo ||
      [r.usuario, r.acao, ACOES[r.acao], r.alvo].some((v) => (v || "").toLowerCase().includes(termo)));
    montar(area,
      h("p", { class: "introducao" }, `${visiveis.length} de ${registros.length} registros em ${dia.split("-").reverse().join("/")}.`),
      tabela([
        { titulo: "Quando", valor: (r) => dataHora(r.quando) },
        { titulo: "Usuário", valor: (r) => r.usuario },
        { titulo: "Ação", valor: (r) => ACOES[r.acao] || r.acao },
        { titulo: "Alvo", valor: (r) => h("code", {}, r.alvo) },
        { titulo: "Canal", valor: (r) => CANAIS[r.canal] || r.canal },
        { titulo: "Detalhes", valor: (r) => r.detalhes ? h("code", { class: "detalhes" }, JSON.stringify(r.detalhes)) : "—" },
      ], visiveis, "Nenhum registro neste dia."));
  };
  filtro.addEventListener("input", desenhar);
  desenhar();
}
