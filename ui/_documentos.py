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
import unicodedata
from pathlib import Path

import _ui
import streamlit as st

try:
    from jobapplier import documentos, empresas
# Cego de propósito: sem banco a página não tem o que mostrar, e o motivo exato
# importa menos que o aviso na tela.
except Exception as exc:
    documentos = empresas = None
    _ERRO_BACKEND = exc
else:
    _ERRO_BACKEND = None


@st.cache_data(ttl=30, show_spinner="Lendo os documentos…")
def _carregar():
    """Cache curto: são ~1.200 arquivos e uma consulta. Trinta segundos seguram
    a digitação na busca sem esconder documento recém-gerado."""
    return [
        {"vaga_id": d.vaga_id, "empresa": d.empresa, "titulo": d.titulo,
         "plataforma": d.plataforma or "", "score": d.score, "perfil": d.perfil,
         "gerado_em": d.gerado_em, "manuscrito": d.manuscrito,
         # "enviado" = a vaga está em status de envio: é a pergunta "qual
         # currículo eu mandei para a Stone?", que a tabela não respondia.
         "enviado": d.status_vaga in ("candidatada", "enviada_manual"),
         "exibicao": empresas.nome_exibicao(d.empresa) or d.empresa,
         "curriculo": str(d.curriculo) if d.curriculo else "",
         "carta": str(d.carta) if d.carta else ""}
        for d in documentos.com_vagas()
    ]


def _normal(t):
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


def render(com_cabecalho: bool = True) -> None:
    """Desenha a biblioteca. Chamada pela página própria e, sem cabeçalho,
    como seção de Configurações — é acervo, e acervo mora perto do ajuste,
    não na jornada."""
    if com_cabecalho:
        _ui.cabecalho(
            "Currículos e cartas",
            "Tudo que já foi gerado para você. Marque a caixa de uma linha para "
            "baixar o currículo e reler a carta.",
        )
    if _ERRO_BACKEND is not None:
        st.error(f"Não foi possível carregar o backend: {_ERRO_BACKEND}")
        return

    try:
        docs = _carregar()
    except Exception as exc:
        st.error(f"Não foi possível ler os documentos: {exc}")
        return

    # Mais recente primeiro, e dentro do mesmo dia, maior aderência primeiro.
    # Só a data não bastava: 273 documentos foram gerados no mesmo minuto de
    # 21/09, na ordem crescente de score, e a lista continuava começando em
    # 65% (auditoria de design). O timestamp não muda; só a apresentação.
    docs.sort(key=lambda d: (d["gerado_em"] is not None,
                             d["gerado_em"].date() if d["gerado_em"] else None,
                             d["score"] or 0), reverse=True)
    if not docs:
        _ui.vazio("Nenhum documento ainda",
                  "Currículos e cartas são gerados pela esteira de candidaturas. "
                  "Aprove uma vaga em Revisar e aplicar para o primeiro sair.")
        return

    # ── Filtros ───────────────────────────────────────────────────────────────────
    # Sem expander: a busca é a razão de a página existir, e esconder a única coisa
    # que se quer usar atrás de um clique é o oposto do ponto.

    # Chaves fixas para "Limpar filtros"; contêiner com chave para o CSS
    # quebrar a linha em duas onde a coluna é estreita (Configurações, tablet).
    _PADRAO = {"d_termo": "", "d_plataforma": "Todas as plataformas", "d_carta": False,
               "d_atalho": None}
    _ATALHOS = ["Todos", "Enviados", "Melhores", "Escritos à mão"]

    def _limpar() -> None:
        for chave, valor in _PADRAO.items():
            st.session_state[chave] = valor

    with st.container(key="filtros-docs" if com_cabecalho else "filtros-docs-embutido"):
        esq, meio, dir_ = st.columns([4, 2, 2])
    with esq:
        termo = st.text_input("Buscar", placeholder="Buscar por empresa, cargo ou id da vaga",
                              label_visibility="collapsed", key="d_termo")
    with meio:
        plataformas = sorted({d["plataforma"] for d in docs if d["plataforma"]})
        plataforma = st.selectbox("Plataforma", ["Todas as plataformas", *plataformas],
                                  label_visibility="collapsed", key="d_plataforma")
    with dir_:
        so_carta = st.toggle("Só com carta", key="d_carta")
    # Atalhos: os três jeitos de a pessoa procurar sem saber o nome — o que já
    # mandou, os melhores para reaproveitar, os que escreveu à mão.
    atalho = st.pills("Atalhos", _ATALHOS, default=None, key="d_atalho",
                      label_visibility="collapsed") or "Todos"

    def _passa_atalho(d) -> bool:
        if atalho == "Enviados":
            return d["enviado"]
        if atalho == "Melhores":
            return (d["score"] or 0) >= 85
        if atalho == "Escritos à mão":
            return d["manuscrito"]
        return True

    filtrados = [
        d for d in docs
        if (plataforma.startswith("Todas") or d["plataforma"] == plataforma)
        and (not so_carta or d["carta"])
        and _passa_atalho(d)
    ]
    if termo.strip():
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
        st.button("Limpar filtros", icon=":material/filter_alt_off:",
                  type="tertiary", on_click=_limpar)
        return

    # ── Tabela ────────────────────────────────────────────────────────────────────
    # `on_select` devolve a linha clicada: a ação vive no documento escolhido, e não
    # repetida em cada uma das 590 linhas.

    # Colunas em ordem de prioridade: o que decide (empresa, vaga, aderência,
    # data) vem primeiro e cabe em ~560px; plataforma, carta e "à mão" ficam
    # à direita, alcançáveis pela rolagem da própria grade. Antes, "medium" +
    # "large" consumiam a largura toda e a 724px só duas colunas apareciam.
    # Plataforma, carta e "à mão" saíram da tabela: plataforma está no
    # detalhe, carta é o toggle, "à mão" é atalho. Entram Perfil e Enviado —
    # o que distingue um currículo do outro.
    linhas = [
        {"Empresa": d["exibicao"], "Vaga": d["titulo"],
         "Perfil": (d["perfil"] or "—").replace("_", " "),
         "Aderência": d["score"], "Gerado": d["gerado_em"],
         "Enviado": d["enviado"]}
        for d in filtrados
    ]

    # O detalhe vai ACIMA da tabela: renderizado depois (precisa da seleção),
    # mas num espaço reservado antes — a tabela tem 560px e o detalhe caía
    # fora da tela nos dois viewports (auditoria de UX).
    detalhe = st.container()

    selecao = st.dataframe(
        linhas,
        use_container_width=True, hide_index=True, height=560,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "Empresa": st.column_config.TextColumn(width=140),
            "Vaga": st.column_config.TextColumn(width=240),
            "Perfil": st.column_config.TextColumn(width=110,
                                                  help="Ênfase do currículo gerado para a vaga"),
            "Aderência": st.column_config.NumberColumn(format="%.0f%%", width=80),
            "Gerado": st.column_config.DatetimeColumn(format="DD/MM/YYYY", width=95),
            "Enviado": st.column_config.CheckboxColumn(
                width=70, help="A vaga está marcada como enviada"),
        },
    )

    escolhidas = selecao.selection.rows if selecao and selecao.selection else []
    if not escolhidas:
        st.caption("Marque a caixa à esquerda de uma linha para ver o documento.")
        return

    # ── Detalhe ───────────────────────────────────────────────────────────────────

    with detalhe:
        doc = filtrados[escolhidas[0]]

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
                st.markdown(
                    '<div class="carta-leitura">'
                    + carta.read_text(encoding="utf-8").strip().replace("\n", "<br>")
                    + "</div>", unsafe_allow_html=True)
        else:
            st.caption("Esta vaga não tem carta — ela é opcional no dossiê.")
