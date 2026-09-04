// Service worker: é ele quem fala com a API local.
//
// Não é organização, é necessidade. No Manifest V3 o `fetch` de um content
// script obedece ao Content-Security-Policy DA PÁGINA, e o da Gupy é:
//
//   connect-src 'self' blob: *.gupy.io *.my.salesforce-scrt.com ...
//
// Sem `127.0.0.1` na lista, a requisição morre antes de sair e o content script
// só vê "Failed to fetch" — indistinguível de backend fora do ar, que foi
// exatamente o diagnóstico errado que o aviso deu na primeira tentativa.
//
// O service worker roda na origem da extensão (`chrome-extension://`), que não
// é regida pelo CSP do site. `host_permissions` autoriza o destino.

const API = "http://127.0.0.1:8787";

// O status volta junto com o erro. Sem ele, um 404 de "vaga fora do acervo" e
// um backend fora do ar chegam ao aviso como a mesma falha — e o aviso escolheu
// culpar o backend, mandando o candidato reiniciar um serviço que estava no ar.
async function chamar(caminho, opcoes) {
  const r = await fetch(API + caminho, opcoes);
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const erro = new Error(corpo.erro || `HTTP ${r.status}`);
    erro.status = r.status;
    // O corpo vai junto: um 409 carrega as vagas candidatas, e sem isto a
    // extensão saberia que houve ambiguidade mas não o que oferecer.
    erro.corpo = corpo;
    throw erro;
  }
  return corpo;
}

const ROTAS = { responder: "/responder", aprender: "/aprender",
                vincular: "/vincular" };

// Qual vaga estava aberta em cada aba. A URL do formulário da Gupy não carrega
// o `jobId`; a da página pública carrega, e é por ela que o candidato passa
// antes de clicar em "Candidatar-se". Por ABA e não global: duas vagas abertas
// em duas abas se sobrescreveriam, e o formulário de uma seria preenchido com a
// resposta da outra.
//
// O service worker é quem guarda isto porque só ele conhece `sender.tab.id` —
// o content script não tem como saber em que aba está.
const vagaDaAba = new Map();

chrome.tabs.onRemoved.addListener((abaId) => vagaDaAba.delete(abaId));

chrome.runtime.onMessage.addListener((msg, remetente, responder) => {
  const aba = remetente?.tab?.id;

  if (msg?.tipo === "vi_vaga") {
    if (aba !== undefined) vagaDaAba.set(aba, msg.url);
    responder({ ok: true });
    return false;
  }

  const rota = ROTAS[msg?.tipo];
  if (!rota) return false;

  if (msg.sinais && aba !== undefined && vagaDaAba.has(aba)) {
    msg.sinais.vaga_da_aba = vagaDaAba.get(aba);
  }

  chamar(rota, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: msg.url, campos: msg.campos,
                           sinais: msg.sinais || {}, vaga_id: msg.vaga_id }),
  })
    .then((dados) => responder({ ok: true, dados }))
    .catch((e) => responder({ ok: false, erro: String(e.message),
                              status: e.status || 0, corpo: e.corpo || {} }));

  // Sem isto o canal fecha antes do await e a resposta se perde.
  return true;
});
