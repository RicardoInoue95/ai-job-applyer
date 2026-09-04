// Fala com a API local, preenche, e PARA. Não clica em enviar, nunca.
//
// Essa é a linha inteira do projeto num arquivo: preencher formulário na sessão
// que o candidato já abriu é assistência; submeter por ele é o que o CAPTCHA e o
// termo de uso da plataforma existem para impedir. `tests/unit/test_extensao.py`
// falha se aparecer um clique de envio aqui.

// Quem fala com a API é o service worker (`fundo.js`), não este arquivo: no
// Manifest V3 o `fetch` de um content script obedece ao CSP da PÁGINA, e o
// `connect-src` da Gupy não inclui `127.0.0.1`. A requisição morria aqui sem
// nunca sair, e o aviso culpava o backend.
// A URL do formulário da Gupy não carrega o `jobId` — é
// `/candidates/applications/<id>/steps/<id>/...`. O `referrer` costuma ser a
// página pública da vaga, que carrega. Vai junto para o Python decidir; aqui
// não se decide nada.
function sinais() {
  return { titulo: document.title, referrer: document.referrer };
}

async function perguntar(url, campos) {
  const r = await chrome.runtime.sendMessage({ tipo: "responder", url, campos,
                                              sinais: sinais() });
  if (!r) throw Object.assign(new Error("service worker não respondeu"),
                              { status: -1 });
  if (!r.ok) throw Object.assign(new Error(r.erro || "erro"),
                                 { status: r.status || 0, corpo: r.corpo || {} });
  return r.dados;
}

// Estar na página pública da vaga é a única hora em que o `jobId` aparece. O
// service worker guarda por aba, e quando o formulário abrir — onde a URL não
// tem identificador nenhum — ele acompanha.
if (/\/job(s)?\//.test(location.pathname)) {
  chrome.runtime.sendMessage({ tipo: "vi_vaga", url: location.href });
}

// O checkbox da Gupy não tem `value`: todos valem "on". Casar por valor marcaria
// sempre o primeiro da lista — resposta errada com cara de certa. Por isso o
// rótulo da opção também conta, e o seletor dela vem junto da leitura.
function opcaoAlvo(seletor, valor, opcoes) {
  const igual = (a, b) =>
    String(a).trim().toLowerCase() === String(b).trim().toLowerCase();

  const porValor = [...document.querySelectorAll(seletor)]
    .find((r) => r.value && igual(r.value, valor));
  if (porValor) return porValor;

  const escolhida = (opcoes || [])
    .find((o) => igual(o.value, valor) || igual(o.label, valor));
  return escolhida && escolhida.seletor
    ? document.querySelector(escolhida.seletor) : null;
}

function escrever(seletor, valor, opcoes) {
  const campo = document.querySelector(seletor);
  if (!campo) return false;

  if (campo.type === "radio" || campo.type === "checkbox") {
    const alvo = opcaoAlvo(seletor, valor, opcoes);
    if (!alvo) return false;
    alvo.click();   // click e não .checked: o React só escuta o evento
    return true;
  }

  // React sobrescreve o setter de value; sem o setter nativo o framework não
  // vê a mudança e o campo volta ao vazio no próximo render.
  const proto = campo.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(campo, valor);
  campo.dispatchEvent(new Event("input", { bubbles: true }));
  campo.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

// Criado uma vez, nunca recriado. Antes cada aviso era um `remove()` seguido de
// um `appendChild()`, e o observador lá embaixo via as duas mutações como
// mudança de formulário — a extensão se realimentava.
const AVISO = document.createElement("div");
AVISO.id = "aija-aviso";
AVISO.style.cssText = "position:fixed;bottom:16px;right:16px;z-index:2147483647;"
  + "max-width:320px;padding:12px 14px;border-radius:8px;font:13px/1.5 system-ui;"
  + "background:#1E3A5F;color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.3)";
const AVISO_TITULO = document.createElement("div");
const AVISO_DETALHE = document.createElement("div");
AVISO_DETALHE.style.cssText = "margin-top:6px;opacity:.85;font-size:12px";
AVISO.append(AVISO_TITULO, AVISO_DETALHE);

function aviso(texto, detalhe) {
  AVISO_TITULO.textContent = texto;
  AVISO_DETALHE.textContent = detalhe || "";
  // Fora o que `escolher()` tiver anexado: sem isto a lista de vagas continuaria
  // na tela depois que a escolha já foi feita.
  while (AVISO.childNodes.length > 2) AVISO.lastChild.remove();
  if (!AVISO.isConnected) document.body.appendChild(AVISO);
}

// Uma vaga que não está no acervo não passa a estar porque perguntamos de novo.
// Sem isto, cada re-render do React virava outra requisição.
const desistidas = new Set();

async function preencher() {
  if (desistidas.has(location.href)) return;

  const campos = lerCampos();
  if (!campos.length) return;

  let dados;
  try {
    dados = await perguntar(location.href, campos);
  } catch (e) {
    // 409 entra junto: sem isto o re-render do React reabriria o seletor de
    // vagas a cada 800ms. `escolher()` remove ao clicar, e o preenchimento
    // recomeça.
    if (e.status === 404 || e.status === 409) desistidas.add(location.href);
    // Cada falha tem uma causa e uma saída diferentes. Uma mensagem só para as
    // três mandou reiniciar um serviço que estava no ar enquanto o problema era
    // a URL do formulário não bater com a da vaga no banco.
    if (e.status === 409) {
      // Ambiguidade não se resolve por palpite: o PagBank tem duas vagas com o
      // mesmo título, e escolher sozinho preencheria o formulário de uma com a
      // resposta da outra. Você escolhe uma vez; o vínculo fica gravado.
      escolher(e.corpo.candidatas || []);
    } else if (e.status === 404) {
      aviso("Vaga fora do acervo.",
            "O AI Job Applier não achou esta vaga no banco. Colete-a primeiro, "
            + "ou abra pela página Vagas.");
    } else if (e.status === -1) {
      aviso("Extensão desatualizada.",
            "Recarregue em chrome://extensions e atualize esta página.");
    } else {
      aviso("AI Job Applier não respondeu.",
            "Rode `python run.py` ou `jobapplier.api.servir()`.");
    }
    return;
  }

  // As opções ficam do lado de cá: a API devolve só o valor escolhido, e para
  // marcar o checkbox certo é preciso saber qual opção era.
  const lidos = new Map(campos.map((c) => [c.seletor, c]));

  let escritos = 0;
  for (const r of dados.respostas) {
    if (r.valor === null || r.valor === undefined) continue;
    if (escrever(r.seletor, r.valor, (lidos.get(r.seletor) || {}).opcoes)) escritos++;
  }

  observarManuais(dados.respostas, lidos);

  const manuais = dados.manuais || [];
  const doBanco = dados.aprendidas
    ? ` ${dados.aprendidas} do banco de respostas.` : "";
  aviso(`${escritos} campos preenchidos.${doBanco}`,
        manuais.length
          ? `${manuais.length} ficaram para você: ${manuais.slice(0, 3).join(" · ")}`
          : "Confira antes de enviar — o envio é seu.");
}

// Qual das vagas é esta? Só aparece quando o sistema NÃO consegue saber — sem
// jobId na URL, sem vínculo anterior, sem referrer e sem memória da aba. Você
// responde uma vez por candidatura e nunca mais.
function escolher(candidatas) {
  if (!candidatas.length) {
    aviso("Vaga fora do acervo.",
          "Nenhuma vaga desta empresa está no banco.");
    return;
  }
  aviso("Qual vaga é esta?",
        "A página não diz, e adivinhar preencheria com a resposta de outra vaga.");

  const lista = document.createElement("div");
  lista.style.cssText = "margin-top:8px;display:flex;flex-direction:column;gap:4px";
  for (const c of candidatas.slice(0, 6)) {
    const item = document.createElement("button");
    item.type = "button";   // sem isto o botão herda submit do form ao redor
    item.style.cssText = "text-align:left;padding:6px 8px;border-radius:6px;"
      + "border:1px solid rgba(255,255,255,.25);background:transparent;"
      + "color:#fff;font:12px/1.4 system-ui;cursor:pointer";
    const pontos = c.score == null ? "" : ` · ${Math.round(c.score)}`;
    item.textContent = `${c.titulo}${pontos}`;
    item.addEventListener("click", async () => {
      await chrome.runtime.sendMessage({ tipo: "vincular", url: location.href,
                                         vaga_id: c.id });
      desistidas.delete(location.href);
      preencher();
    });
    lista.appendChild(item);
  }
  AVISO.appendChild(lista);
}

// O que você digita num campo que ficou manual é guardado para a próxima vaga.
// No `blur` e não a cada tecla: meio nome digitado não é resposta. E sem botão
// de confirmar — pedir um clique para não redigitar seria trocar um tédio pelo
// outro, que é o que este projeto existe para não fazer.
const observados = new WeakSet();

function observarManuais(respostas, lidos) {
  for (const r of respostas) {
    if (r.valor !== null && r.valor !== undefined) continue;
    const campo = document.querySelector(r.seletor);
    if (!campo || observados.has(campo)) continue;
    observados.add(campo);
    campo.addEventListener("blur", () => {
      const valor = String(campo.value || "").trim();
      if (!valor) return;
      chrome.runtime.sendMessage({
        tipo: "aprender",
        url: location.href,
        campos: [{ label: r.label, valor,
                   opcoes: (lidos.get(r.seletor) || {}).opcoes || [] }],
      });
    });
  }
}

// Formulário de SPA aparece depois do load, e muda de passo sem recarregar.
// Um preenchimento único pegaria a página vazia.
let agendado = null;
const observador = new MutationObserver((mudancas) => {
  // O próprio `aviso()` insere um elemento no DOM, o observador via a mudança e
  // chamava `preencher()` de novo: 1,2 requisição por segundo, para sempre. A
  // extensão estava se realimentando.
  if (mudancas.every((m) => AVISO.contains(m.target))) return;
  clearTimeout(agendado);
  agendado = setTimeout(preencher, 800);
});
observador.observe(document.body, { childList: true, subtree: true });
setTimeout(preencher, 1200);

if (typeof module !== "undefined") module.exports = { escrever, preencher };
