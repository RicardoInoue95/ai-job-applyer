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

// No LinkedIn o formulário é o diálogo do Easy Apply, aberto por cima da
// página de vagas — que tem a busca, filtros e mensagens, todos <input>. Ler a
// página inteira mandaria "Pesquisar vagas" para a API como pergunta. Fora do
// LinkedIn, o formulário é a página.
const NO_LINKEDIN = /(^|\.)linkedin\.com$/.test(location.hostname);
function raizDoFormulario() {
  if (!NO_LINKEDIN) return document;
  return document.querySelector(
    ".jobs-easy-apply-modal, [data-test-modal], div[role=dialog]") || null;
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
  if (!escolhida || !escolhida.seletor) return null;
  // Pelo índice, não por `querySelector`: o seletor é o do grupo, e o primeiro
  // do grupo não é a opção escolhida — ver `opcoesDe` em campos.js.
  const grupo = [...document.querySelectorAll(escolhida.seletor)];
  return grupo[escolhida.indice >= 0 ? escolhida.indice : 0] || null;
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

// Erro do catálogo do Python: `{codigo, titulo, detalhe, acao, auto}`. Mostra o
// título e, embaixo, o que fazer — que é a parte que importa para quem está
// cansado. O código vai para o console, onde serve a quem for investigar.
function avisoDoErro(erro) {
  if (!erro || !erro.titulo) {
    // A API respondeu algo que esta versão não entende — extensão mais nova que
    // o backend, ou o contrário.
    erro = LOCAIS["contrato-desconhecido"];
  }
  console.info(`[AI Job Applier] ${erro.codigo}: ${erro.detalhe}`);
  aviso(erro.titulo, [erro.detalhe, erro.acao].filter(Boolean).join(" "));
}

// Os dois únicos erros que NÃO podem vir do catálogo do Python, porque em
// ambos o Python não foi alcançado. Mesma forma dos outros de propósito: quem
// lê `avisoDoErro` não precisa saber de onde veio.
const LOCAIS = {
  "extensao-desatualizada": {
    codigo: "extensao-desatualizada",
    titulo: "A extensão está numa versão antiga",
    detalhe: "O service worker não respondeu à página.",
    acao: "Abra chrome://extensions, recarregue a extensão e atualize esta aba.",
  },
  "api-fora": {
    codigo: "api-fora",
    titulo: "O AI Job Applier não está rodando",
    detalhe: "O serviço local do AI Job Applier não respondeu.",
    acao: "Rode `python run.py` na pasta do projeto.",
  },
  "contrato-desconhecido": {
    codigo: "contrato-desconhecido",
    titulo: "Não deu para preencher",
    detalhe: "A resposta veio num formato que esta versão não entende.",
    acao: "Recarregue a extensão e reinicie o `python run.py`.",
  },
};

// O status separa o que o catálogo não consegue: -1 é o service worker mudo e
// 0 é a API inalcançável — nos dois o backend não respondeu, então ele não
// pôde dizer o que houve.
function erroDaFalha(e) {
  if (e.status === -1) return LOCAIS["extensao-desatualizada"];
  if (!e.status) return LOCAIS["api-fora"];
  return e.erro;
}

// Uma vaga que não está no acervo não passa a estar porque perguntamos de novo.
// Sem isto, cada re-render do React virava outra requisição.
const desistidas = new Set();

// O que a API respondeu para o formulário atual, esperando o clique. Guardado
// com a "assinatura" do formulário (os rótulos, em ordem): se o SPA trocar de
// passo, a assinatura muda e se pergunta de novo; se só re-renderizar, não.
let preparado = null;

function assinaturaDe(campos) {
  return campos.map((c) => c.label + "|" + c.tipo).join("\n");
}

// Botão "Preencher tudo". Fica no aviso, e é o único jeito de escrever no
// formulário: a versão anterior preenchia sozinha 1,2 s depois do load, e quem
// estava lendo o anúncio via o formulário mudar sem ter pedido — não dava para
// saber o que tinha sido escrito nem por quê. Agora o aviso diz antes ("12
// perguntas, 10 o sistema sabe"), e o clique é seu.
const BOTAO = document.createElement("button");
BOTAO.id = "aija-preencher";
BOTAO.type = "button";
BOTAO.textContent = "Preencher tudo";
BOTAO.style.cssText = "margin-top:8px;padding:7px 12px;border:0;border-radius:6px;"
  + "background:#4F46E5;color:#fff;font:600 13px system-ui,sans-serif;cursor:pointer";
BOTAO.addEventListener("click", () => { if (preparado) aplicar(preparado); });

// 1ª etapa: lê o formulário e pergunta à API. Não escreve nada.
async function preparar() {
  if (desistidas.has(location.href)) return;

  const raiz = raizDoFormulario();
  if (!raiz) return;
  const campos = lerCampos(raiz);
  if (!campos.length) return;
  const assinatura = assinaturaDe(campos);
  if (preparado && preparado.assinatura === assinatura) return;

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
      avisoDoErro(e.erro);
      escolher(e.corpo.candidatas || []);
    } else {
      // Texto e ação vêm do catálogo do Python (`jobapplier/erros.py`), não
      // daqui: mensagem duplicada em JavaScript diverge do backend no primeiro
      // dia, e foi assim que o aviso mandou reiniciar um serviço que estava no
      // ar enquanto o problema era outro.
      avisoDoErro(erroDaFalha(e));
    }
    return;
  }

  preparado = { assinatura, campos, dados };
  const sabe = dados.respostas.filter((r) => r.valor !== null && r.valor !== undefined).length;
  const manuais = dados.manuais || [];
  const anexo = dados.curriculo && campoDeArquivo(raiz)
    ? ` Anexa o currículo desta vaga (${dados.curriculo}).` : "";
  aviso(`${campos.length} perguntas neste passo · ${sabe} o sistema sabe responder.${anexo}`,
        manuais.length
          ? `${manuais.length} ficam para você: ${manuais.slice(0, 3).join(" · ")}`
          : "Todas têm resposta. O envio continua sendo seu.");
  AVISO.appendChild(BOTAO);
}

// O campo de arquivo do currículo. Na Gupy o <input type=file> fica escondido
// atrás de uma área de arrastar; no Easy Apply é o "Upload resume". Um só
// candidato: se houver vários campos de arquivo (portfólio, carta), só o que
// fala em currículo/CV/resume — anexar o PDF no campo errado é pior que não
// anexar.
function campoDeArquivo(raiz) {
  const todos = [...(raiz || document).querySelectorAll('input[type="file"]')]
    .filter((c) => !c.disabled);
  if (!todos.length) return null;
  if (todos.length === 1) return todos[0];
  const texto = (c) => [c.id, c.name, c.getAttribute("aria-label") || "",
    (c.labels && [...c.labels].map((l) => l.textContent).join(" ")) || "",
    c.closest("label, fieldset, div")?.textContent || ""].join(" ").toLowerCase();
  return todos.find((c) => /curr[ií]culo|resume|\bcv\b/.test(texto(c))) || null;
}

// Anexa o PDF feito para a vaga. Só no clique, como tudo aqui: o service
// worker traz os bytes (o content script não pode buscar), e o arquivo entra
// pelo mesmo caminho de um arrasto — `DataTransfer` + evento `change`, que é
// o que o React da plataforma escuta. Não clica em nada.
async function anexarCurriculo(raiz, dados) {
  const campo = campoDeArquivo(raiz);
  if (!campo || !dados.curriculo) return null;
  const r = await chrome.runtime.sendMessage({ tipo: "curriculo", vaga_id: dados.vaga_id });
  if (!r || !r.ok) return { erro: (r && r.erro) || "sem resposta" };
  const bytes = Uint8Array.from(atob(r.base64), (ch) => ch.charCodeAt(0));
  const arquivo = new File([bytes], r.nome, { type: "application/pdf" });
  const dt = new DataTransfer();
  dt.items.add(arquivo);
  campo.files = dt.files;
  campo.dispatchEvent(new Event("input", { bubbles: true }));
  campo.dispatchEvent(new Event("change", { bubbles: true }));
  return { nome: r.nome };
}

// 2ª etapa: escreve. Só depois do clique.
async function aplicar({ campos, dados }) {
  // As opções ficam do lado de cá: a API devolve só o valor escolhido, e para
  // marcar o checkbox certo é preciso saber qual opção era.
  const lidos = new Map(campos.map((c) => [c.seletor, c]));

  let escritos = 0;
  for (const r of dados.respostas) {
    if (r.valor === null || r.valor === undefined) continue;
    if (escrever(r.seletor, r.valor, (lidos.get(r.seletor) || {}).opcoes)) escritos++;
  }

  observarManuais(dados.respostas, lidos);

  let anexo = "";
  const resultado = await anexarCurriculo(raizDoFormulario(), dados);
  if (resultado && resultado.nome) anexo = ` Currículo anexado: ${resultado.nome}.`;
  else if (resultado && resultado.erro) anexo = ` Não consegui anexar o currículo (${resultado.erro}).`;

  const manuais = dados.manuais || [];
  const doBanco = dados.aprendidas
    ? ` ${dados.aprendidas} do banco de respostas.` : "";
  aviso(`${escritos} campos preenchidos.${doBanco}${anexo}`,
        manuais.length
          ? `${manuais.length} ficaram para você: ${manuais.slice(0, 3).join(" · ")}`
          : "Confira antes de enviar — o envio é seu.");
}

// Nome antigo, mantido para quem chama de fora (testes): preparar e, se houver
// o que escrever, aplicar. Não é o caminho da interface — lá o clique separa
// as duas etapas.
async function preencher() {
  await preparar();
  if (preparado) await aplicar(preparado);
}

// Qual das vagas é esta? Só aparece quando o sistema NÃO consegue saber — sem
// jobId na URL, sem vínculo anterior, sem referrer e sem memória da aba. Você
// responde uma vez por candidatura e nunca mais.
function escolher(candidatas) {
  // O texto já foi posto por `avisoDoErro` com o erro `vaga-ambigua` do
  // catálogo. Aqui só se acrescenta a lista: reescrever o aviso apagaria a
  // mensagem do backend e traria de volta a duplicação que este arquivo
  // acabou de perder.
  if (!candidatas.length) return;

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
  agendado = setTimeout(preparar, 800);
});
observador.observe(document.body, { childList: true, subtree: true });
setTimeout(preparar, 1200);

if (typeof module !== "undefined") module.exports = { escrever, preencher, preparar, aplicar };
