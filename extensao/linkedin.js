// Lê o SEU perfil do LinkedIn e manda para a análise. Só isso.
//
// Roda apenas em `linkedin.com/in/*` — a página de perfil — e nunca em `/jobs`:
// o manifest não o carrega lá, e `tests/unit/test_extensao.py` falha se o match
// alcançar vagas. Não preenche nada, não clica em nada, não candidata. O Easy
// Apply fica fora por decisão (invariante 6 do CLAUDE.md), e este arquivo não
// muda isso: é leitura do DOM de uma página que VOCÊ abriu, quando VOCÊ clica.
//
// Os seletores foram escritos sobre a estrutura conhecida da página (âncoras
// `#about`, `#experience`, `#skills`, `#education` no início de cada <section>,
// texto duplicado em <span aria-hidden="true">) e não contra uma captura real,
// que teria dado pessoal demais para o repositório. Se a leitura vier vazia, o
// aviso diz o que achou — e é esse o sinal para ajustar aqui.

const CAMINHO = location.pathname;
const E_DETALHE_COMPETENCIAS = /\/in\/[^/]+\/details\/skills\/?/.test(CAMINHO);
const E_PERFIL = /^\/in\/[^/]+\/?$/.test(CAMINHO);

// O texto visível de um elemento, sem a cópia para leitor de tela que o
// LinkedIn põe ao lado (senão "Coordenador de Dados" vira "Coordenador de
// DadosCoordenador de Dados").
function textoDe(el) {
  if (!el) return "";
  const visivel = el.querySelector('span[aria-hidden="true"]');
  return (visivel ? visivel.textContent : el.textContent).replace(/\s+/g, " ").trim();
}

function secao(ancora) {
  const el = document.getElementById(ancora);
  return el ? el.closest("section") : null;
}

function itens(sec) {
  return sec ? [...sec.querySelectorAll("li.artdeco-list__item")] : [];
}

function lerTitulo() {
  const el = document.querySelector(
    ".pv-text-details__left-panel .text-body-medium, main .text-body-medium.break-words");
  return el ? el.textContent.replace(/\s+/g, " ").trim() : "";
}

function lerSobre() {
  const sec = secao("about");
  if (!sec) return "";
  const corpo = sec.querySelector(
    '.inline-show-more-text span[aria-hidden="true"], .pv-shared-text-with-see-more span[aria-hidden="true"]');
  if (corpo) return corpo.textContent.replace(/\s+/g, " ").trim();
  // Sem o contêiner conhecido: o texto da seção menos o cabeçalho "Sobre".
  return sec.innerText.replace(/^\s*Sobre\s*/i, "").replace(/\s+/g, " ").trim();
}

function lerExperiencias() {
  return itens(secao("experience")).map((li) => {
    const linhas = [...li.querySelectorAll('span[aria-hidden="true"]')]
      .map((s) => s.textContent.replace(/\s+/g, " ").trim()).filter(Boolean);
    // Ordem típica: cargo · "Empresa · Tempo integral" · "ago de 2025 - o momento · 1 ano" · local · descrição
    const cargo = textoDe(li.querySelector(".t-bold")) || linhas[0] || "";
    const empresa = (linhas[1] || "").split("·")[0].trim();
    const periodo = linhas.find((l) => /(19|20)\d{2}/.test(l)) || "";
    const descricao = linhas.slice(3).join(" ");
    return { cargo, empresa, periodo, descricao };
  }).filter((e) => e.cargo || e.empresa);
}

function lerFormacao() {
  return itens(secao("education")).map((li) => ({
    instituicao: textoDe(li.querySelector(".t-bold")),
    curso: textoDe(li.querySelector(".t-normal")),
  })).filter((f) => f.instituicao);
}

function lerCompetencias(raiz) {
  return itens(raiz).map((li) => textoDe(li.querySelector(".t-bold"))).filter(Boolean);
}

// A página do perfil mostra só as primeiras competências; a lista inteira vive
// em `/details/skills/`. Quem visitar essa página deixa a lista guardada, e o
// envio do perfil a usa no lugar da amostra.
async function competenciasGuardadas() {
  const { competencias_linkedin } = await chrome.storage.local.get("competencias_linkedin");
  return Array.isArray(competencias_linkedin) ? competencias_linkedin : null;
}

async function lerPerfil() {
  const daPagina = lerCompetencias(secao("skills"));
  const guardadas = await competenciasGuardadas();
  return {
    titulo: lerTitulo(),
    sobre: lerSobre(),
    experiencias: lerExperiencias(),
    formacao: lerFormacao(),
    competencias: guardadas && guardadas.length > daPagina.length ? guardadas : daPagina,
  };
}

// ── Aviso e botão ────────────────────────────────────────────────────────────

const AVISO = document.createElement("div");
AVISO.id = "aija-aviso";
AVISO.style.cssText = "position:fixed;right:16px;bottom:72px;z-index:2147483647;"
  + "max-width:360px;padding:10px 14px;border-radius:8px;background:#1F2937;"
  + "color:#F9FAFB;font:13px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.25);"
  + "display:none;white-space:pre-line";

function aviso(texto) {
  AVISO.textContent = texto;
  AVISO.style.display = "block";
}

const BOTAO = document.createElement("button");
BOTAO.id = "aija-analisar";
BOTAO.type = "button";
BOTAO.textContent = "Analisar meu perfil";
BOTAO.title = "AI Job Applier: compara este perfil com o currículo mestre e com as vagas da fila. Não altera nada.";
BOTAO.style.cssText = "position:fixed;right:16px;bottom:24px;z-index:2147483647;"
  + "padding:9px 14px;border:0;border-radius:8px;background:#4F46E5;color:#fff;"
  + "font:600 13px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.25)";

async function analisar(motivo) {
  BOTAO.disabled = true;
  aviso(motivo === "auto" ? "Lendo o seu perfil (última leitura há mais de 7 dias)…"
                          : "Lendo o perfil…");
  try {
    const perfil = await lerPerfil();
    const achou = `título ${perfil.titulo ? "✓" : "—"} · sobre ${perfil.sobre ? "✓" : "—"} · `
      + `${perfil.experiencias.length} experiências · ${perfil.competencias.length} competências`;
    const r = await chrome.runtime.sendMessage({ tipo: "perfil_linkedin", url: location.href, perfil });
    if (!r) throw new Error("service worker não respondeu — recarregue a extensão.");
    if (!r.ok) throw new Error(r.erro || "erro");
    const n = (r.dados.ajustes || []).length;
    const [c, t] = r.dados.cobertura || [0, 0];
    aviso(`Lido: ${achou}.\n${n} ajuste(s) sugerido(s); o perfil cita ${c} de ${t} tecnologias mais pedidas.\n`
      + "Detalhes em Configurações → LinkedIn, no AI Job Applier.");
  } catch (e) {
    aviso(`Não deu: ${e.message}`);
  } finally {
    BOTAO.disabled = false;
  }
}

BOTAO.addEventListener("click", () => analisar("clique"));

// Só o SEU perfil, e só se a última leitura estiver velha. Quem sabe qual é o
// seu slug é o backend (`resume.json.linkedin`) — a permissão desta extensão
// cobre `/in/*` inteiro e ela não tem como saber sozinha. Perfil de outra
// pessoa nunca é lido sem clique, e mesmo com clique a API recusa (403).
async function lerSozinhoSeForMeuEVelho() {
  let r;
  try {
    r = await chrome.runtime.sendMessage({ tipo: "situacao_perfil" });
  } catch {
    return; // sem API não há o que comparar; o botão continua lá
  }
  if (!r || !r.ok || !r.dados || !r.dados.slug) return;
  const meuSlug = String(r.dados.slug).toLowerCase();
  const daPagina = (CAMINHO.match(/^\/in\/([^/]+)/) || [])[1];
  if (!daPagina || daPagina.toLowerCase() !== meuSlug) return;

  const dias = Number(r.dados.dias_para_reler) || 7;
  const lidoEm = r.dados.lido_em ? Date.parse(r.dados.lido_em) : 0;
  const velho = !lidoEm || Date.now() - lidoEm > dias * 24 * 3600 * 1000;
  if (!velho) return;
  // A página do LinkedIn monta as seções depois do load; sem a espera a leitura
  // vinha com "0 experiências" e a análise ficava errada por uma semana.
  setTimeout(() => analisar("auto"), 2500);
}

if (E_PERFIL) {
  document.body.append(AVISO, BOTAO);
  lerSozinhoSeForMeuEVelho();
} else if (E_DETALHE_COMPETENCIAS) {
  // Sem botão aqui: só guarda a lista completa para o envio na página do perfil.
  const guardar = () => {
    const lista = lerCompetencias(document.querySelector("main"));
    if (lista.length) chrome.storage.local.set({ competencias_linkedin: lista });
  };
  setTimeout(guardar, 1500);
  new MutationObserver(guardar).observe(document.body, { childList: true, subtree: true });
}

if (typeof module !== "undefined") {
  module.exports = { lerTitulo, lerSobre, lerExperiencias, lerFormacao, lerCompetencias };
}
