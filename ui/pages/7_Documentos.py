"""Todo currículo e carta que o sistema já gerou, num lugar só.

Até aqui só se chegava a um documento por dentro do cartão da vaga, um por vez,
e só enquanto a vaga estivesse na fila: o currículo de uma vaga encerrada ficava
inalcançável pela interface, embora seja o que mais se quer reaproveitar — o que
você mandou para a vaga parecida do mês passado.

**Tabela, não cartões.** A primeira versão desta página era um cartão por
documento: 200px de altura para duas linhas de texto, três por tela, com os
botões de download ocupando 280px cada e pesando mais que o nome da empresa.
São 590 documentos — isso são 197 rolagens para achar um. Lista longa se lê em
tabela: ordenável por coluna, densa, e a ação fica no item escolhido em vez de
repetida 590 vezes.

A regra de o que existe mora em `jobapplier/documentos.py`. Esta página só
mostra: é o acordo de a interface ser descartável.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

_ui.cabecalho(
    "Currículos e cartas",
    "Tudo que já foi gerado para você. Marque a caixa de uma linha para "
    "baixar o currículo e reler a carta.",
)

try:
    from jobapplier import documentos, empresas
# Cego de propósito: sem banco a página não tem o que mostrar, e o motivo exato
# importa menos que o aviso na tela.
except Exception as exc:
    st.error(f"Não foi possível carregar o backend: {exc}")
    st.stop()


@st.cache_data(ttl=30, show_spinner="Lendo os documentos…")
def _carregar():
    """Cache curto: são ~1.200 arquivos e uma consulta. Trinta segundos seguram
    a digitação na busca sem esconder documento recém-gerado."""
    return [
        {"vaga_id": d.vaga_id, "empresa": d.empresa, "titulo": d.titulo,
         "plataforma": d.plataforma or "", "score": d.score, "perfil": d.perfil,
         "gerado_em": d.gerado_em, "manuscrito": d.manuscrito,
         "exibicao": empresas.nome_exibicao(d.empresa) or d.empresa,
         "curriculo": str(d.curriculo) if d.curriculo else "",
         "carta": str(d.carta) if d.carta else ""}
        for d in documentos.com_vagas()
    ]


try:
    docs = _carregar()
except Exception as exc:
    st.error(f"Não foi possível ler os documentos: {exc}")
    st.stop()

if not docs:
    _ui.vazio("Nenhum documento ainda",
              "Currículos e cartas são gerados pela esteira de candidaturas. "
              "Aprove uma vaga em Revisar e aplicar para o primeiro sair.")
    st.stop()

# ── Filtros ───────────────────────────────────────────────────────────────────
# Sem expander: a busca é a razão de a página existir, e esconder a única coisa
# que se quer usar atrás de um clique é o oposto do ponto.

esq, meio, dir_ = st.columns([4, 2, 2])
with esq:
    termo = st.text_input("Buscar", placeholder="Buscar por empresa, cargo ou id da vaga",
                          label_visibility="collapsed")
with meio:
    plataformas = sorted({d["plataforma"] for d in docs if d["plataforma"]})
    plataforma = st.selectbox("Plataforma", ["Todas as plataformas", *plataformas],
                              label_visibility="collapsed")
with dir_:
    so_carta = st.toggle("Só com carta")

filtrados = [
    d for d in docs
    if (plataforma.startswith("Todas") or d["plataforma"] == plataforma)
    and (not so_carta or d["carta"])
]
if termo.strip():
    import unicodedata

    def _normal(t):
        return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                       if unicodedata.category(c) != "Mn")

    alvo = _normal(termo)
    filtrados = [d for d in filtrados
                 if alvo in _normal(f"{d['empresa']} {d['titulo']} {d['vaga_id']}")]

# Uma linha de contexto, não três cartões de métrica: nenhum daqueles números
# mudava uma decisão aqui, e gastavam 100px no topo da tela.
manuscritos = sum(1 for d in docs if d["manuscrito"])
st.caption(
    f"**{len(filtrados)}** de {len(docs)} documentos · "
    f"{sum(1 for d in docs if d['carta'])} com carta · "
    f"{manuscritos} escritos à mão"
)

if not filtrados:
    _ui.vazio("Nada com esse filtro", "Limpe a busca ou troque a plataforma.")
    st.stop()

# ── Tabela ────────────────────────────────────────────────────────────────────
# `on_select` devolve a linha clicada: a ação vive no documento escolhido, e não
# repetida em cada uma das 590 linhas.

linhas = [
    {"Empresa": d["exibicao"], "Vaga": d["titulo"],
     "Plataforma": d["plataforma"] or "—",
     "Aderência": d["score"], "Gerado": d["gerado_em"],
     "Carta": bool(d["carta"]), "À mão": d["manuscrito"]}
    for d in filtrados
]

selecao = st.dataframe(
    linhas,
    use_container_width=True, hide_index=True, height=560,
    on_select="rerun", selection_mode="single-row",
    column_config={
        "Empresa": st.column_config.TextColumn(width="medium"),
        "Vaga": st.column_config.TextColumn(width="large"),
        "Plataforma": st.column_config.TextColumn(width="small"),
        "Aderência": st.column_config.NumberColumn(format="%.0f%%", width="small"),
        "Gerado": st.column_config.DatetimeColumn(format="DD/MM/YYYY", width="small"),
        "Carta": st.column_config.CheckboxColumn(width="small"),
        "À mão": st.column_config.CheckboxColumn(
            width="small",
            help="Currículo escrito sob medida para aquela vaga, não gerado"),
    },
)

escolhidas = selecao.selection.rows if selecao and selecao.selection else []
if not escolhidas:
    st.caption("Marque a caixa à esquerda de uma linha para ver o documento.")
    st.stop()

# ── Detalhe ───────────────────────────────────────────────────────────────────

from pathlib import Path

doc = filtrados[escolhidas[0]]
st.divider()

topo, baixar = st.columns([5, 2])
with topo:
    st.markdown(f"**{doc['exibicao']}** — {doc['titulo']}")
    quando = doc["gerado_em"].strftime("%d/%m/%Y") if doc["gerado_em"] else "—"
    selo = " · escrito à mão" if doc["manuscrito"] else ""
    st.caption(f"vaga {doc['vaga_id']} · {doc['plataforma'] or '—'} · "
               f"perfil {doc['perfil'] or '—'}{selo} · gerado em {quando}")
with baixar:
    curriculo = Path(doc["curriculo"]) if doc["curriculo"] else None
    if curriculo and curriculo.exists():
        st.download_button("Baixar currículo", curriculo.read_bytes(),
                           file_name=curriculo.name, mime="application/pdf",
                           type="primary", use_container_width=True,
                           key=f"cv_{doc['vaga_id']}")
    carta = Path(doc["carta"]) if doc["carta"] else None
    if carta and carta.exists():
        st.download_button("Baixar carta", carta.read_bytes(),
                           file_name=carta.name, mime="text/plain",
                           use_container_width=True, key=f"ct_{doc['vaga_id']}")

if doc["carta"]:
    carta = Path(doc["carta"])
    if carta.exists():
        # Aberto, não em expander: a carta é curta e é o que se quer conferir
        # antes de reaproveitar. Um clique a mais para ler cinco linhas é tédio.
        st.text_area("Carta", carta.read_text(encoding="utf-8"), height=220,
                     label_visibility="collapsed", key=f"txt_{doc['vaga_id']}")
else:
    st.caption("Esta vaga não tem carta — ela é opcional no dossiê.")
