"""Fundação visual: tokens e componentes compartilhados por todas as páginas.

Substitui `_estilo.py`, que só tinha tipografia. Cada página vinha inventando o
resto — cartão de um jeito no baralho, `st.metric` solto nas candidaturas,
accordion genérico nas vagas, emoji como ícone em toda parte. O resultado
funcionava e parecia composição de componentes padrão, não produto.

Três decisões que governam o arquivo:

**Ícones são Material, não emoji.** O Streamlit 1.36+ aceita `:material/nome:`
em `st.Page`, `st.button`, `st.info` e afins. Emoji vinha de famílias diferentes
(📄 achatado, ⬅️ colorido, ✅ verde vivo) e brigava com qualquer paleta. Ícone
linear herda a cor do texto.

**Cor tem significado, não decoração.** Índigo é ação; verde, sucesso; âmbar,
atenção; vermelho, só descarte e erro. O vermelho era a cor primária do
Streamlit e aparecia em botão comum — o que torna o vermelho de verdade
invisível.

**Componente aqui, não CSS na página.** Havia sete blocos `<style>` espalhados.
Quem consome usa `cabecalho()`, `metrica()`, `badge()`; o CSS mora só aqui.
"""
from __future__ import annotations

import streamlit as st

# ── Tokens ───────────────────────────────────────────────────────────────────

CSS = """
<style>
  :root {
    /* Superfícies: fundo levemente acinzentado, cartão branco. */
    --fundo:      #F7F8FA;
    --superficie: #FFFFFF;
    --borda:      #E4E7EC;
    --borda-forte:#D0D5DD;

    /* Texto: três níveis, e só três. */
    --txt-1: #101828;   /* título, valor */
    --txt-2: #475467;   /* corpo */
    --txt-3: #667085;   /* metadata, label */

    /* Ação. Índigo, não o vermelho padrão do Streamlit. */
    --acao:       #4F46E5;
    --acao-hover: #4338CA;
    --acao-suave: #EEF2FF;

    /* Semânticas. Usadas só pelo que significam. */
    --ok: #067647;      --ok-bg: #ECFDF3;      --ok-borda: #ABEFC6;
    --aviso: #B54708;   --aviso-bg: #FFFAEB;   --aviso-borda: #FEDF89;
    --erro: #B42318;    --erro-bg: #FEF3F2;    --erro-borda: #FECDCA;

    --raio: 10px;
    --raio-p: 8px;
    --sombra: 0 1px 2px rgba(16,24,40,.04);

    --txt: .95rem;
    --txt-apoio: .875rem;
    --txt-meta: .8rem;
    --medida: 68ch;

    /* Escala de espaço (docs/DESIGN_UI.md): sem valor fora dela. */
    --e1: 4px; --e2: 8px; --e3: 12px; --e4: 16px; --e5: 24px; --e6: 32px; --e7: 48px;
  }

  /* ── Chrome do Streamlit ──────────────────────────────────────────────── */
  /* "Deploy", menu de hambúrguer e rodapé "Made with Streamlit" não são do
     produto e confundem quem usa. `stToolbar` NÃO entra na lista: é onde vive
     o botão de reabrir a barra lateral recolhida — escondê-la deixava o
     usuário sem caminho de volta. Deploy e menu já saem por
     `client.toolbarMode = "minimal"` em .streamlit/config.toml. */
  [data-testid="stDecoration"], [data-testid="stMainMenu"],
  #MainMenu, footer, [data-testid="stStatusWidget"] { display: none !important; }

  .stApp { background: var(--fundo); }
  /* O cabeçalho é fixo, transparente e mais alto que o padding antigo (2.2rem):
     o título de toda página ficava cortado embaixo dele. Ele ganha o fundo da
     página e o container começa abaixo dele. */
  [data-testid="stHeader"] { background: var(--fundo); }
  [data-testid="stMainBlockContainer"] { padding-top: 3.75rem; max-width: 1180px; }

  /* ── Tipografia ───────────────────────────────────────────────────────── */
  html, body, [class*="st-"] { color: var(--txt-2); }
  .stMarkdown p, [data-testid="stMarkdownContainer"] p {
    font-size: var(--txt); line-height: 1.6; color: var(--txt-2);
  }
  [data-testid="stMarkdownContainer"] > p { max-width: var(--medida); }
  h1, h2, h3, h4, h5, h6 { color: var(--txt-1); text-wrap: balance; }
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    font-size: var(--txt-apoio) !important; color: var(--txt-3);
    max-width: var(--medida);
  }
  hr { margin: 1.5rem 0; border-color: var(--borda); }

  /* ── Sidebar ──────────────────────────────────────────────────────────── */
  [data-testid="stSidebar"] {
    background: var(--superficie); border-right: 1px solid var(--borda);
  }
  [data-testid="stSidebarNav"] { padding-top: .25rem; }
  /* Item ativo: índigo suave, não a faixa cinza pesada do padrão. */
  [data-testid="stSidebarNav"] a[aria-current="page"] {
    background: var(--acao-suave) !important; border-radius: var(--raio-p);
  }
  [data-testid="stSidebarNav"] a[aria-current="page"] span,
  [data-testid="stSidebarNav"] a[aria-current="page"] * {
    color: var(--acao) !important; font-weight: 600 !important;
  }
  [data-testid="stSidebarNav"] a { border-radius: var(--raio-p); }
  [data-testid="stSidebarNav"] a:focus-visible {
    outline: 2px solid var(--acao); outline-offset: 2px; }

  .marca { padding: .35rem .25rem 1rem; }
  .marca-nome { font-size: 1.02rem; font-weight: 650; color: var(--txt-1);
                letter-spacing: -.01em; }
  .marca-sub { font-size: var(--txt-meta); color: var(--txt-3); margin-top: .1rem; }

  .rodape { border-top: 1px solid var(--borda); margin-top: 1rem;
            padding-top: .75rem; font-size: var(--txt-meta); color: var(--txt-3); }
  .rodape-linha { display: flex; align-items: center; gap: .4rem;
                  padding: .12rem 0; }
  .ponto { width: 7px; height: 7px; border-radius: 50%; flex: none; }

  /* O Streamlit dá margin-bottom:-1rem ao container de markdown supondo que
     o último filho é um <p> com 1rem de margem. Nos blocos em HTML (divs)
     não há margem para compensar — no ritmo normal da página o gap de 16px
     absorve isso, mas dentro de contêineres com gap reduzido o bloco
     seguinte invadia o anterior: 10px no cartão do Início, 16px em Vagas ›
     Detalhes (medidos). A correção é só nesses contêineres. */
  .st-key-proximo [data-testid="stMarkdownContainer"],
  .st-key-lista [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important; }

  /* ── Cabeçalho de página ──────────────────────────────────────────────── */
  .pg { margin-bottom: 1.5rem; }
  /* h1/h2 de verdade (leitor de tela), com o CSS do produto — o estilo
     padrão do Streamlit para headings é zerado aqui. */
  h1.pg-titulo, .pg-titulo { font-size: 1.85rem; font-weight: 700; color: var(--txt-1);
               letter-spacing: -.02em; line-height: 1.15; margin: 0; padding: 0; }
  h1.pg-titulo a, h2.sec a { display: none; }
  .pg-desc { font-size: var(--txt-apoio); color: var(--txt-3); margin-top: .22rem;
             max-width: var(--medida); }

  /* Na lista de vagas, "Detalhes" é um link discreto, não uma segunda caixa
     dentro do cartão: cem cartões com duas bordas cada não se escaneiam. */
  /* No Streamlit 1.58 o container com borda é o próprio stVerticalBlock
     (padding 15px); o cartão da lista usa 12/16 e "Detalhes" cola no texto. */
  .st-key-lista .stVerticalBlock:has(> [data-testid="stLayoutWrapper"] > .stHorizontalBlock) {
    padding: var(--e3) var(--e4); gap: 0; }
  /* O gap zerado é do cartão; dentro de Detalhes volta o ritmo normal — sem
     isto os chips cobriam a última linha de eixo em 16px (medido). */
  .st-key-lista [data-testid="stExpanderDetails"] .stVerticalBlock.stVerticalBlock { gap: var(--e3); }
  .st-key-lista [data-testid="stExpander"] { margin-top: var(--e2); }
  .st-key-lista [data-testid="stExpander"] details { border: 0; background: transparent; }
  .st-key-lista [data-testid="stExpander"] summary { padding: var(--e1) 0; min-height: 24px; line-height: 1.3; }
  .st-key-lista [data-testid="stExpander"] summary:hover,
  .st-key-lista [data-testid="stExpander"] details[open] > summary { background: transparent; }
  .st-key-lista [data-testid="stExpander"] summary p { font-size: var(--txt-apoio); color: var(--txt-3); }
  .st-key-lista [data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding-left: 0; padding-right: 0; }

  /* "Mais" tem só Configurações; Documentos fica roteável (Configurações →
     Documentos e links do produto) sem gastar linha na barra. */
  [data-testid="stSidebarNav"] a[href$="/documentos"] { display: none; }
  /* "Mais" com um item só não é grupo; um traço antes de Configurações basta. */
  [data-testid="stSidebarNav"] a[href$="/configuracoes"] {
    margin-top: var(--e3); position: relative; }
  [data-testid="stSidebarNav"] a[href$="/configuracoes"]::before {
    content: ""; position: absolute; left: 0; right: 0; top: calc(-1 * var(--e2));
    border-top: 1px solid var(--borda); }

  /* Navegação interna de Configurações: um rádio que parece lista de links. */
  .st-key-nav-config [data-testid="stRadio"] label[data-baseweb="radio"] {
    padding: var(--e2) var(--e3); border-radius: var(--raio-p); margin: 0;
    display: flex; align-items: center; }
  .st-key-nav-config [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child { display: none; }
  .st-key-nav-config [data-testid="stRadio"] label[data-baseweb="radio"] p { font-size: var(--txt-apoio); color: var(--txt-2); }
  .st-key-nav-config [data-testid="stRadio"] label[data-baseweb="radio"]:hover { background: var(--fundo); }
  .st-key-nav-config [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) { background: var(--acao-suave); }
  .st-key-nav-config [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p { color: var(--acao); font-weight: 600; }
  .st-key-nav-config [data-testid="stRadio"] > div[role="radiogroup"] { gap: 2px; }

  /* Primeira seção de uma coluna lateral alinha com o topo do cartão. */
  .st-key-lado .sec:first-child, .st-key-lado > div > div:first-child .sec { margin-top: 0; }
  /* O markdown do Streamlit termina com margem negativa; sem margem própria
     o link invadia a linha "✓ Currículo · ✓ Carta" em 10px (medido). */
  .st-key-proximo [data-testid="stPageLink"] { margin-top: var(--e1); }
  .st-key-proximo.stVerticalBlock { padding: var(--e4) var(--e5); gap: var(--e2); }
  .st-key-proximo .destaque-titulo { margin: 0; }

  /* Em Preferências, "Editar", "Filtros avançados" e "Empresas" são links que
     abrem, não caixas dentro da caixa do formulário. */
  .st-key-prefs [data-testid="stExpander"] details { border: 0; background: transparent; }
  .st-key-prefs [data-testid="stExpander"] summary { padding: var(--e1) 0; min-height: 24px; }
  .st-key-prefs [data-testid="stExpander"] summary:hover,
  .st-key-prefs [data-testid="stExpander"] details[open] > summary { background: transparent; }
  .st-key-prefs [data-testid="stExpander"] summary p { font-size: var(--txt-apoio); color: var(--acao); }
  .st-key-prefs [data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding-left: 0; padding-right: 0; }

  /* Checklist de Revisar: grid flexível (as larguras fixas de 6,5rem
     quebravam em três linhas a 1024px). */
  .check-linha { display: grid; grid-template-columns: 1rem minmax(5rem, max-content) 1fr;
                 gap: var(--e2); align-items: baseline; padding: var(--e2) 0;
                 border-bottom: 1px solid var(--borda); }

  /* Tablet: barra lateral fixa de 300px deixa 724px. Abaixo de 1280px o
     workspace de Revisar empilha e a linha de filtros de Vagas quebra em
     duas — em vez de coluna de 195px e rótulos com reticências. */
  @media (max-width: 1280px) {
    .st-key-workspace > [data-testid="stLayoutWrapper"] > .stHorizontalBlock { flex-wrap: wrap; }
    .st-key-workspace > [data-testid="stLayoutWrapper"] > .stHorizontalBlock > .stColumn {
      flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important; }
    .st-key-filtros .stHorizontalBlock { flex-wrap: wrap; }
    .st-key-filtros .stColumn { flex: 1 1 30% !important; min-width: 30% !important; }
  }

  /* Candidaturas enviadas: uma linha por vaga, com traço entre elas. */
  .st-key-envios .stHorizontalBlock { padding: var(--e3) 0; border-bottom: 1px solid var(--borda); }
  .st-key-envios.stVerticalBlock { gap: 0; }

  /* Chips escolhidos do multiselect: valores, não ações — cinza, não índigo. */
  .stMultiSelect span[data-baseweb="tag"] {
    background: var(--fundo); border: 1px solid var(--borda-forte); color: var(--txt-1); }
  .stMultiSelect span[data-baseweb="tag"] span, .stMultiSelect span[data-baseweb="tag"] svg { color: var(--txt-2); fill: var(--txt-2); }

  /* Campo em modo resumo (Configurações): rótulo como o do Streamlit, valor
     em corpo, editor atrás de um clique. */
  .rotulo-campo { font-size: var(--txt-apoio); color: var(--txt-1); font-weight: 400;
                  margin-bottom: var(--e1); }
  .resumo-campo { font-size: var(--txt); color: var(--txt-2); line-height: 1.45; }

  /* Parágrafo de abertura do Início: maior que corpo, menor que título. */
  .lede { font-size: 1.1rem; line-height: 1.5; color: var(--txt-2);
          margin: var(--e2) 0 var(--e4); max-width: var(--medida); }
  .lede b { color: var(--txt-1); }
  /* Cargo em destaque no cartão protagonista: H2 do contrato. */
  .destaque-titulo { font-size: 1.3rem; font-weight: 650; color: var(--txt-1);
                     line-height: 1.25; margin: var(--e1) 0 var(--e1); }
  /* Links do markdown na cor de ação, não no azul padrão do Streamlit:
     um azul só na paleta. */
  [data-testid="stMarkdownContainer"] a { color: var(--acao); }
  .meta-linha { font-size: var(--txt-meta); color: var(--txt-3); }

  /* ── Seção ────────────────────────────────────────────────────────────── */
  h2.sec, .sec { font-size: .78rem; font-weight: 650; letter-spacing: .045em;
         text-transform: uppercase; color: var(--txt-3); line-height: 1.6;
         margin: var(--e6) 0 var(--e3); padding: 0; }

  /* ── Cartão ───────────────────────────────────────────────────────────── */
  /* Mesmo raio, borda e padding do `st.container(border=True)` protagonista
     (Início): um cartão de vaga só, em dois lugares. */
  .cartao { background: var(--superficie); border: 1px solid rgba(71, 84, 103, .2);
            border-radius: var(--raio-p); padding: var(--e4) var(--e5); }

  /* ── Métrica ──────────────────────────────────────────────────────────── */
  .met { background: var(--superficie); border: 1px solid var(--borda);
         border-radius: var(--raio); padding: .85rem 1rem; height: 100%; }
  .met-rot { font-size: var(--txt-meta); color: var(--txt-3); font-weight: 500;
             display: flex; align-items: center; gap: .3rem; }
  .met-val { font-size: 1.65rem; font-weight: 650; color: var(--txt-1);
             line-height: 1.15; margin-top: .2rem;
             font-variant-numeric: tabular-nums; }
  .met-nota { font-size: var(--txt-meta); color: var(--txt-3); margin-top: .1rem; }
  /* Destaque por tamanho, não por índigo: índigo é ação (contrato, regra 6). */
  .met.destaque .met-val { font-size: 2.1rem; }

  /* ── Badge ────────────────────────────────────────────────────────────── */
  .bdg { display: inline-flex; align-items: center; gap: .25rem;
         font-size: var(--txt-meta); font-weight: 550; line-height: 1.5;
         padding: .1rem .45rem; border-radius: 6px; white-space: nowrap;
         border: 1px solid var(--borda); color: var(--txt-2);
         background: var(--superficie); }
  .bdg.ok    { color: var(--ok);    background: var(--ok-bg);    border-color: var(--ok-borda); }
  .bdg.aviso { color: var(--aviso); background: var(--aviso-bg); border-color: var(--aviso-borda); }
  .bdg.erro  { color: var(--erro);  background: var(--erro-bg);  border-color: var(--erro-borda); }
  .bdg.acao  { color: var(--acao);  background: var(--acao-suave); border-color: #C7D2FE; }

  /* ── Linha de vaga ────────────────────────────────────────────────────── */
  .vaga { background: var(--superficie); border: 1px solid var(--borda);
          border-radius: var(--raio); padding: .85rem 1rem; margin-bottom: .55rem; }
  .vaga:hover { border-color: var(--borda-forte); }
  .vaga-topo { display: flex; align-items: baseline; gap: .6rem;
               justify-content: space-between; }
  .vaga-titulo { font-size: 1.05rem; font-weight: 600; color: var(--txt-1);
                 line-height: 1.35; }
  .vaga-empresa { font-size: var(--txt-apoio); color: var(--txt-2); }
  .vaga-porque { font-size: var(--txt-apoio); color: var(--txt-2); margin-top: var(--e2); }
  .vaga-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem;
               margin-top: .45rem; font-size: var(--txt-meta);
               color: var(--txt-3); }
  .vaga-meta .sep { color: var(--borda-forte); }

  /* ── Aderência ────────────────────────────────────────────────────────── */
  .ader { font-variant-numeric: tabular-nums; font-weight: 650;
          font-size: var(--txt-apoio); white-space: nowrap; }
  .ader-barra { height: 4px; border-radius: 2px; background: var(--borda);
                overflow: hidden; margin-top: .3rem; width: 68px; }
  .ader-barra i { display: block; height: 100%; background: var(--borda-forte); }
  /* CTA interno como botão. `st.page_link` é o único jeito de navegar entre
     páginas sem abrir aba nova, e renderiza como link de texto; num container
     com `key="cta"` ele ganha a cara da ação primária. Só um por tela. */
  .st-key-cta [data-testid="stPageLink"] a {
    display: inline-flex; align-items: center; gap: .4rem;
    background: var(--acao); color: #fff !important; font-weight: 550;
    padding: .55rem 1.1rem; border-radius: var(--raio-p); text-decoration: none;
  }
  .st-key-cta [data-testid="stPageLink"] a:hover { background: var(--acao-hover); }
  .st-key-cta [data-testid="stPageLink"] a * { color: #fff !important; }

  /* Nível 1: conclusão. Sem barra na lista — a barra era um segundo número. */
  .concl { font-size: var(--txt-apoio); color: var(--txt-2); margin-top: .35rem; }
  .concl .atencao { color: var(--aviso); }
  /* Nível 2: um eixo por linha, barra cinza com preenchimento neutro. O índigo
     fica para a ação; barra de evidência não é ação. */
  .eixo { display: grid; grid-template-columns: 110px 1fr 44px; gap: .6rem;
          align-items: center; font-size: var(--txt-apoio); color: var(--txt-2);
          padding: var(--e1) 0; border-bottom: 1px solid var(--borda); }
  .eixo .palavra { color: var(--txt-1); font-weight: 550; }
  .eixo .num { text-align: right; color: var(--txt-3); }

  /* ── Estado vazio ─────────────────────────────────────────────────────── */
  .vazio { text-align: center; padding: 2.4rem 1rem; color: var(--txt-3);
           border: 1px dashed var(--borda-forte); border-radius: var(--raio);
           background: var(--superficie); }
  .vazio-t { font-size: var(--txt); font-weight: 600; color: var(--txt-2);
             margin-bottom: .2rem; }

  /* ── Prévia de texto ──────────────────────────────────────────────────── */
  .previa { background: var(--fundo); border: 1px solid var(--borda);
            border-radius: var(--raio-p); padding: .75rem .9rem;
            font-size: var(--txt-apoio); color: var(--txt-2); line-height: 1.55;
            white-space: pre-wrap; max-height: 190px; overflow: hidden;
            position: relative; }
  .previa::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0;
                   height: 44px;
                   background: linear-gradient(transparent, var(--fundo)); }

  /* ── Controles ────────────────────────────────────────────────────────── */
  .stButton button, .stDownloadButton button, .stLinkButton a,
  .stFormSubmitButton button {
    font-size: var(--txt-apoio); font-weight: 550; border-radius: var(--raio-p);
  }
  /* Primário índigo: o vermelho do Streamlit em botão comum torna o vermelho
     de verdade — erro, descarte — invisível.
     A cor do texto precisa ser declarada junto: sem ela o link primário herda
     o texto escuro do tema e fica ilegível sobre o índigo. */
  .stButton button[kind="primary"],
  .stLinkButton a[data-testid="stBaseLinkButton-primary"],
  .stDownloadButton button[kind="primary"],
  .stFormSubmitButton button[kind="primaryFormSubmit"] {
    background: var(--acao) !important; border-color: var(--acao) !important;
    color: #FFFFFF !important;
  }
  /* O submit de formulário tem kind próprio ("primaryFormSubmit"); sem esta
     linha "Salvar preferências" saía com texto cinza sobre índigo. */
  .stButton button[kind="primary"] p,
  .stLinkButton a[data-testid="stBaseLinkButton-primary"] p,
  .stLinkButton a[data-testid="stBaseLinkButton-primary"] span,
  .stDownloadButton button[kind="primary"] p,
  .stFormSubmitButton button[kind="primaryFormSubmit"] p {
    color: #FFFFFF !important;
  }
  .stButton button[kind="primary"]:hover,
  .stFormSubmitButton button[kind="primaryFormSubmit"]:hover,
  .stLinkButton a[data-testid="stBaseLinkButton-primary"]:hover {
    background: var(--acao-hover) !important;
    border-color: var(--acao-hover) !important;
  }
  .stTextInput input, .stNumberInput input, .stTextArea textarea,
  .stSelectbox div[data-baseweb="select"], .stMultiSelect div[data-baseweb="select"] {
    font-size: var(--txt-apoio); border-radius: var(--raio-p);
  }
  /* text_input (38px) e selectbox (40px) na mesma linha de filtros. */
  .stTextInput div[data-baseweb="base-input"], .stTextInput input { min-height: 40px; }
  /* Links de página no ritmo dos demais blocos (16px), não 10. */
  [data-testid="stPageLink"] { margin-top: var(--e2); }
  /* Chips do multiselect. O Streamlit pinta o fundo com primaryColor e o
     texto herdava o --txt-2 da regra global: cinza sobre índigo, ~1,5:1 de
     contraste. Mesmo par do cartão em destaque, ~6,7:1. */
  .stMultiSelect [data-baseweb="tag"] {
    background: var(--acao-suave) !important; color: var(--acao) !important;
    border: 1px solid #C7D2FE;
  }
  .stMultiSelect [data-baseweb="tag"] span, .stMultiSelect [data-baseweb="tag"] svg {
    color: var(--acao) !important; fill: var(--acao);
  }
  [data-testid="stWidgetLabel"] p {
    font-size: var(--txt-meta) !important; font-weight: 600; color: var(--txt-3);
  }
  [data-testid="stExpander"] details {
    border: 1px solid var(--borda); border-radius: var(--raio);
    background: var(--superficie);
  }
  [data-testid="stExpander"] summary { font-size: var(--txt-apoio); font-weight: 550; }

  /* Seletor segmentado e pills: o Streamlit pinta o item ativo com o vermelho
     de marca dele, que aqui significa erro. Índigo é a cor de ação. */
  [data-testid="stButtonGroup"] button[aria-checked="true"],
  [data-testid="stButtonGroup"] button[kind="segmented_controlActive"],
  [data-testid="stButtonGroup"] button[kind="pillsActive"] {
    background: var(--acao-suave) !important;
    border-color: var(--acao) !important;
    color: var(--acao) !important;
  }
  [data-testid="stButtonGroup"] button[aria-checked="true"] p,
  [data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p,
  [data-testid="stButtonGroup"] button[kind="pillsActive"] p {
    color: var(--acao) !important; font-weight: 600;
  }

  /* Cabeçalho de etapa dentro de Configurações: o `st.markdown("#### …")` das
     funções de assistente competia com o título da página. */
  [data-testid="stMainBlockContainer"] h4 {
    font-size: 1.02rem; font-weight: 600; margin-top: .4rem;
  }

  /* Slider é controle do usuário (ação): índigo. Progresso é indicador:
     neutro — índigo em barra é o que fazia tudo parecer clicável. */
  [data-testid="stSlider"] [role="slider"] { background: var(--acao) !important; }
  [data-testid="stProgress"] > div > div > div { background: var(--borda-forte); }

  .num { font-variant-numeric: tabular-nums; }
</style>
"""


def aplicar() -> None:
    """Injeta tokens e chrome. Chamado uma vez, em `app.py`."""
    st.markdown(CSS, unsafe_allow_html=True)


# ── Componentes ──────────────────────────────────────────────────────────────

def cabecalho(titulo: str, descricao: str = "", acao=None) -> None:
    """Cabeçalho padrão de página: título, descrição curta, ação opcional.

    `acao` é um callable que desenha o botão à direita. Título discreto de
    propósito — o cabeçalho orienta, não ocupa a tela.
    """
    if acao is None:
        st.markdown(
            f'<div class="pg"><h1 class="pg-titulo">{titulo}</h1>'
            f'{f"<div class=\'pg-desc\'>{descricao}</div>" if descricao else ""}</div>',
            unsafe_allow_html=True,
        )
        return

    esq, dir_ = st.columns([3, 1], vertical_alignment="center")
    with esq:
        st.markdown(
            f'<div class="pg"><h1 class="pg-titulo">{titulo}</h1>'
            f'{f"<div class=\'pg-desc\'>{descricao}</div>" if descricao else ""}</div>',
            unsafe_allow_html=True,
        )
    with dir_:
        acao()


def local_curto(localizacao: str) -> str:
    """Delegado a `fila.local_exibicao`: webapp e painel encurtam igual."""
    from jobapplier import fila

    return fila.local_exibicao(localizacao)


def secao(rotulo: str) -> None:
    """Divisor de seção. Menos pesado que `st.subheader`, que compete com o
    título da página."""
    st.markdown(f'<h2 class="sec">{rotulo}</h2>', unsafe_allow_html=True)


def metrica(rotulo: str, valor, nota: str = "", destaque: bool = False) -> None:
    classe = "met destaque" if destaque else "met"
    valor_fmt = f"{valor:,}".replace(",", ".") if isinstance(valor, int) else valor
    st.markdown(
        f'<div class="{classe}"><div class="met-rot">{rotulo}</div>'
        f'<div class="met-val">{valor_fmt}</div>'
        f'{f"<div class=\'met-nota\'>{nota}</div>" if nota else ""}</div>',
        unsafe_allow_html=True,
    )


#: Tom do `jobapplier.status` → classe da badge. O vocabulário do domínio decide
#: a cor; a página não escolhe.
_TOM = {"bom": "ok", "aviso": "aviso", "ruim": "erro", "neutro": ""}


def badge(texto: str, tom: str = "neutro") -> str:
    """HTML de uma badge. Devolve string para compor dentro de outro markdown."""
    classe = _TOM.get(tom, tom if tom in ("ok", "aviso", "erro", "acao") else "")
    return f'<span class="bdg {classe}">{texto}</span>'


def badge_status(codigo: str) -> str:
    """Badge a partir do código de status, usando rótulo e tom do domínio."""
    from jobapplier import status as vocab

    s = vocab.de_vaga(codigo)
    return badge(s.rotulo, s.tom)


def aderencia(score: float | None, com_barra: bool = True,
              alinhar: str = "flex-start") -> str:
    """Score como aderência legível. Nunca como número solto sem unidade.

    Empacota texto e barra num bloco vertical: soltos, o pai em flex colocava a
    barra ao lado do texto em vez de abaixo.
    """
    if score is None:
        return ('<span class="ader" style="color:var(--txt-3)">'
                'sem avaliação</span>')
    cor = "var(--ok)" if score >= 85 else ("var(--txt-1)" if score >= 65
                                           else "var(--txt-3)")
    barra = (f'<div class="ader-barra"><i style="width:{min(score, 100):.0f}%">'
             f'</i></div>' if com_barra else "")
    return (f'<div style="display:flex;flex-direction:column;align-items:{alinhar}">'
            f'<span class="ader" style="color:{cor}">{score:.0f}% de aderência</span>'
            f'{barra}</div>')


def titulo_limpo(titulo: str | None) -> str:
    """Delega ao serviço: o painel da extensão e o webapp mostram o mesmo
    título, e a regra mora em `jobapplier.fila.titulo_exibicao`."""
    from jobapplier.fila import titulo_exibicao

    return titulo_exibicao(titulo)


def conclusao(a: dict | None, com_atencao: bool = True, so_titulo: bool = False) -> str:
    """Nível 1 da aderência: `97% · Excelente`, por quê, e o ponto de atenção.

    Só isso na lista. Skills, senioridade e barras são evidência, e evidência
    em todo cartão traz de volta o excesso de informação — vai em `evidencia`,
    no detalhe. `a` é `jobapplier.aderencia.Aderencia.como_dict()`.
    """
    if not a:
        return '<span class="ader" style="color:var(--txt-3)">sem avaliação</span>'
    score = a.get("score") or 0
    cor = "var(--ok)" if score >= 85 else ("var(--txt-1)" if score >= 65
                                           else "var(--txt-3)")
    partes = [f'<span class="ader" style="color:{cor}">{a["titulo"]}</span>']
    # Na listagem, só o título: "97% · Excelente". Por quê e ponto de atenção
    # em todo cartão de uma lista de cem traz de volta o excesso de informação.
    if so_titulo:
        return partes[0]
    if a.get("porque"):
        partes.append(f'<div class="concl">{a["porque"]}</div>')
    if com_atencao and a.get("atencao"):
        partes.append(f'<div class="concl atencao">⚠ {a["atencao"]}</div>')
    return "".join(partes)


def _palavra_do_eixo(pct: int) -> str:
    if pct >= 90:
        return "Excelente"
    if pct >= 70:
        return "Forte"
    if pct >= 40:
        return "Parcial"
    return "Fraca"


def evidencia(a: dict | None) -> None:
    """Nível 2: cada eixo como palavra e número, tecnologias cobertas e ausentes.

    Sem barras: cinco barras quase cheias lado a lado parecem painel de
    métricas, e a decisão não está na barra — está em "Tecnologias: Forte,
    89%" e na lista do que falta. A palavra se lê; o número confere.
    """
    if not a:
        return
    linhas = []
    for e in a.get("eixos") or []:
        # `fracao` vem de `Aderencia.como_dict`; o fallback cobre dict montado à mão.
        fracao = e["fracao"] if "fracao" in e else (
            e["nota"] / e["maximo"] if e.get("maximo") else 0)
        pct = round(fracao * 100)
        linhas.append(
            f'<div class="eixo"><span>{e["nome"]}</span>'
            f'<span class="palavra">{_palavra_do_eixo(pct)}</span>'
            f'<span class="num">{pct}%</span></div>')
    if linhas:
        st.markdown("".join(linhas), unsafe_allow_html=True)
    cobertas = a.get("cobertas") or []
    faltam = a.get("faltam") or []
    if cobertas:
        st.markdown(" ".join(badge(f"✓ {t.replace(' (equivalente)', '')}")
                             for t in cobertas[:10]), unsafe_allow_html=True)
    # O ponto de atenção (nível 1) já está no cartão; aqui só o que ele não
    # disse — a lista completa do que a vaga pede e o currículo não cita.
    # O que o ponto de atenção do cartão já nomeou não se repete aqui.
    atencao = (a.get("atencao") or "").lower()
    restantes = [t for t in faltam if t.lower() not in atencao]
    if restantes:
        st.markdown(
            '<div class="meta-linha" style="color:var(--aviso);margin-top:var(--e2)">'
            f'⚠ Não cita: {", ".join(restantes)}</div>', unsafe_allow_html=True)


def vazio(titulo: str, detalhe: str = "") -> None:
    st.markdown(
        f'<div class="vazio"><div class="vazio-t">{titulo}</div>'
        f'{f"<div>{detalhe}</div>" if detalhe else ""}</div>',
        unsafe_allow_html=True,
    )


def previa(texto: str, limite: int = 600) -> None:
    """Trecho legível de um texto longo, com desvanecimento no fim.

    Carta de apresentação em `st.text_area` gigante era conteúdo editável com
    cara de formulário: o usuário só quer ler e copiar.
    """
    import html

    st.markdown(
        f'<div class="previa">{html.escape(texto[:limite])}</div>',
        unsafe_allow_html=True,
    )


def linha_meta(*partes: str) -> str:
    """Metadados separados por ponto médio, ignorando os vazios."""
    itens = [p for p in partes if p]
    sep = '<span class="sep">·</span>'
    return f'<div class="vaga-meta">{sep.join(itens)}</div>' if itens else ""
