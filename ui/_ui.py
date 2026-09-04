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
  }

  /* ── Chrome do Streamlit ──────────────────────────────────────────────── */
  /* "Deploy", menu de hambúrguer e rodapé "Made with Streamlit" não são do
     produto e confundem quem usa. */
  [data-testid="stToolbar"], [data-testid="stDecoration"],
  #MainMenu, footer, [data-testid="stStatusWidget"] { display: none !important; }

  .stApp { background: var(--fundo); }
  [data-testid="stMainBlockContainer"] { padding-top: 2.2rem; max-width: 1180px; }

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

  .marca { padding: .35rem .25rem 1rem; }
  .marca-nome { font-size: 1.02rem; font-weight: 650; color: var(--txt-1);
                letter-spacing: -.01em; }
  .marca-sub { font-size: var(--txt-meta); color: var(--txt-3); margin-top: .1rem; }

  .rodape { border-top: 1px solid var(--borda); margin-top: 1rem;
            padding-top: .75rem; font-size: var(--txt-meta); color: var(--txt-3); }
  .rodape-linha { display: flex; align-items: center; gap: .4rem;
                  padding: .12rem 0; }
  .ponto { width: 7px; height: 7px; border-radius: 50%; flex: none; }

  /* ── Cabeçalho de página ──────────────────────────────────────────────── */
  .pg { margin-bottom: 1.5rem; }
  .pg-titulo { font-size: 1.5rem; font-weight: 650; color: var(--txt-1);
               letter-spacing: -.018em; line-height: 1.2; }
  .pg-desc { font-size: var(--txt-apoio); color: var(--txt-3); margin-top: .22rem;
             max-width: var(--medida); }

  /* ── Seção ────────────────────────────────────────────────────────────── */
  .sec { font-size: .78rem; font-weight: 650; letter-spacing: .045em;
         text-transform: uppercase; color: var(--txt-3);
         margin: 1.6rem 0 .7rem; }

  /* ── Cartão ───────────────────────────────────────────────────────────── */
  .cartao { background: var(--superficie); border: 1px solid var(--borda);
            border-radius: var(--raio); box-shadow: var(--sombra);
            padding: 1rem 1.15rem; }

  /* ── Métrica ──────────────────────────────────────────────────────────── */
  .met { background: var(--superficie); border: 1px solid var(--borda);
         border-radius: var(--raio); padding: .85rem 1rem; height: 100%; }
  .met-rot { font-size: var(--txt-meta); color: var(--txt-3); font-weight: 500;
             display: flex; align-items: center; gap: .3rem; }
  .met-val { font-size: 1.65rem; font-weight: 650; color: var(--txt-1);
             line-height: 1.15; margin-top: .2rem;
             font-variant-numeric: tabular-nums; }
  .met-nota { font-size: var(--txt-meta); color: var(--txt-3); margin-top: .1rem; }
  .met.destaque { border-color: var(--acao); background: var(--acao-suave); }
  .met.destaque .met-val, .met.destaque .met-rot { color: var(--acao); }

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
  .vaga-titulo { font-size: 1rem; font-weight: 600; color: var(--txt-1);
                 line-height: 1.35; }
  .vaga-empresa { font-size: var(--txt-apoio); color: var(--txt-2); }
  .vaga-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem;
               margin-top: .45rem; font-size: var(--txt-meta);
               color: var(--txt-3); }
  .vaga-meta .sep { color: var(--borda-forte); }

  /* ── Aderência ────────────────────────────────────────────────────────── */
  .ader { font-variant-numeric: tabular-nums; font-weight: 650;
          font-size: var(--txt-apoio); white-space: nowrap; }
  .ader-barra { height: 4px; border-radius: 2px; background: var(--borda);
                overflow: hidden; margin-top: .3rem; width: 68px; }
  .ader-barra i { display: block; height: 100%; background: var(--acao); }

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
  .stButton button, .stDownloadButton button, .stLinkButton a {
    font-size: var(--txt-apoio); font-weight: 550; border-radius: var(--raio-p);
  }
  /* Primário índigo: o vermelho do Streamlit em botão comum torna o vermelho
     de verdade — erro, descarte — invisível.
     A cor do texto precisa ser declarada junto: sem ela o link primário herda
     o texto escuro do tema e fica ilegível sobre o índigo. */
  .stButton button[kind="primary"],
  .stLinkButton a[data-testid="stBaseLinkButton-primary"],
  .stDownloadButton button[kind="primary"] {
    background: var(--acao) !important; border-color: var(--acao) !important;
    color: #FFFFFF !important;
  }
  .stButton button[kind="primary"] p,
  .stLinkButton a[data-testid="stBaseLinkButton-primary"] p,
  .stLinkButton a[data-testid="stBaseLinkButton-primary"] span,
  .stDownloadButton button[kind="primary"] p {
    color: #FFFFFF !important;
  }
  .stButton button[kind="primary"]:hover,
  .stLinkButton a[data-testid="stBaseLinkButton-primary"]:hover {
    background: var(--acao-hover) !important;
    border-color: var(--acao-hover) !important;
  }
  .stTextInput input, .stNumberInput input, .stTextArea textarea,
  .stSelectbox div[data-baseweb="select"], .stMultiSelect div[data-baseweb="select"] {
    font-size: var(--txt-apoio); border-radius: var(--raio-p);
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

  /* Slider e progresso em índigo, não no vermelho de marca. */
  [data-testid="stSlider"] [role="slider"] { background: var(--acao) !important; }
  [data-testid="stProgress"] > div > div > div { background: var(--acao); }

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
            f'<div class="pg"><div class="pg-titulo">{titulo}</div>'
            f'{f"<div class=\'pg-desc\'>{descricao}</div>" if descricao else ""}</div>',
            unsafe_allow_html=True,
        )
        return

    esq, dir_ = st.columns([3, 1], vertical_alignment="center")
    with esq:
        st.markdown(
            f'<div class="pg"><div class="pg-titulo">{titulo}</div>'
            f'{f"<div class=\'pg-desc\'>{descricao}</div>" if descricao else ""}</div>',
            unsafe_allow_html=True,
        )
    with dir_:
        acao()


def secao(rotulo: str) -> None:
    """Divisor de seção. Menos pesado que `st.subheader`, que compete com o
    título da página."""
    st.markdown(f'<div class="sec">{rotulo}</div>', unsafe_allow_html=True)


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
