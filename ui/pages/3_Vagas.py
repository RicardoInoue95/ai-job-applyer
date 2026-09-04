"""Catálogo: todas as vagas coletadas, de todas as plataformas, num lugar só.

É a tela que dá sentido ao nome do produto — centralizar. Serve para explorar e
comparar; decidir uma a uma é o trabalho da tela Revisar e aplicar.

Reescrita depois de uma revisão de UX. A versão anterior empilhava accordions
idênticos, cada um abrindo para revelar `📍 São Paulo | 🗂️ pendente` — emoji
como ícone, status como texto técnico cru, e nenhuma forma de comparar duas
vagas sem abrir as duas. O score aparecia como `**94**`, número sem unidade.

Agora cada vaga é uma linha escaneável: empresa e título no topo, plataforma,
local, modalidade e senioridade como metadados, aderência com barra, status como
badge. Dá para percorrer trinta sem abrir nenhuma.

Nenhuma regra mudou: os mesmos filtros, a mesma consulta, as mesmas ações de
aprovar e rejeitar, gravando o mesmo histórico.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

from jobapplier.config.manager import ConfigManager
from jobapplier.tempo import agora_utc

config = ConfigManager()

try:
    from sqlalchemy import func

    from jobapplier import status as vocab
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import AprovacoesHistorico, Vaga
except Exception as exc:
    st.error(f"Erro ao conectar ao banco: {exc}", icon=":material/error:")
    st.stop()


_ui.cabecalho("Vagas",
              "Explore oportunidades reunidas de diferentes plataformas.")


# ── Filtros ───────────────────────────────────────────────────────────────────
# Uma barra compacta, não uma coluna de controles soltos. Vagas esperando por
# VOCÊ vêm primeiro: é o que o modo sombra produz e o que a tela existe para
# resolver.

_aguardando = vocab.exigem_sua_acao()
_demais = [c for c in vocab.codigos_vaga() if c not in _aguardando]
_OPCOES = ["aguardando você", *_aguardando, *_demais, "todas"]


def _rotulo_status(codigo: str) -> str:
    if codigo in ("todas", "aguardando você"):
        return codigo.capitalize()
    return vocab.de_vaga(codigo).rotulo


with st.container(border=False):
    c1, c2, c3, c4 = st.columns([1.6, 1.3, 1.2, 1])
    with c1:
        busca = st.text_input("Buscar", placeholder="Título ou empresa",
                              label_visibility="collapsed")
    with c2:
        status_filter = st.selectbox("Status", _OPCOES, index=0,
                                     format_func=_rotulo_status,
                                     label_visibility="collapsed")
    with c3:
        plataformas = st.multiselect(
            "Plataforma", ["greenhouse", "gupy", "linkedin", "inhire", "lever"],
            placeholder="Plataforma", label_visibility="collapsed")
    with c4:
        aderencia_min = st.slider("Aderência mínima", 0, 100, 0, step=5,
                                  format="%d%%")

with st.expander("Mais filtros"):
    m1, m2 = st.columns(2)
    with m1:
        modalidades = st.multiselect("Modalidade",
                                     ["remoto", "híbrido", "presencial"],
                                     placeholder="Todas")
    with m2:
        mostrar_filtradas = st.checkbox(
            "Incluir vagas descartadas pelos filtros", value=False,
            help="Vagas que não passaram nos filtros 4A/4B. Úteis para conferir "
                 "se o filtro está cortando demais.")


# ── Consulta ──────────────────────────────────────────────────────────────────

def _get_vagas(status: str, busca: str) -> list:
    with get_session() as session:
        q = session.query(Vaga)
        if status == "aguardando você":
            q = q.filter(Vaga.status.in_(vocab.exigem_sua_acao()))
        elif status != "todas":
            q = q.filter(Vaga.status == status)
        elif not mostrar_filtradas:
            q = q.filter(Vaga.status.notin_(["filtrada_4a", "filtrada_4b"]))
        if busca:
            termo = f"%{busca.lower()}%"
            q = q.filter(
                func.lower(Vaga.titulo).like(termo) | func.lower(Vaga.empresa).like(termo)
            )
        if plataformas:
            q = q.filter(Vaga.plataforma.in_(plataformas))
        if modalidades:
            q = q.filter(Vaga.modalidade.in_(modalidades))
        if aderencia_min:
            q = q.filter(Vaga.score >= aderencia_min)
        return (q.order_by(Vaga.score.desc().nullslast(), Vaga.criado_em.desc())
                .limit(100).all())


def _aprovar(vaga_id: int, score_val: float | None):
    with get_session() as session:
        session.query(Vaga).filter(Vaga.id == vaga_id).update({"status": "aprovada"})
        if score_val is not None:
            session.add(AprovacoesHistorico(vaga_id=vaga_id, score=score_val,
                                            aprovado=True, criado_em=agora_utc()))


def _rejeitar(vaga_id: int, score_val: float | None):
    with get_session() as session:
        session.query(Vaga).filter(Vaga.id == vaga_id).update(
            {"status": "descartada_por_voce"})
        if score_val is not None:
            session.add(AprovacoesHistorico(vaga_id=vaga_id, score=score_val,
                                            aprovado=False, criado_em=agora_utc()))


vagas = _get_vagas(status_filter, busca)

# ── Ações em lote ─────────────────────────────────────────────────────────────

if status_filter == "pendente" and vagas:
    with st.container(border=True):
        e, d = st.columns([2.4, 1], vertical_alignment="center")
        with e:
            st.markdown(f"**{len(vagas)} possibilidades** nesta seleção — "
                        "aderência abaixo do corte de aprovação.")
        with d:
            if st.button("Aprovar todas", icon=":material/done_all:",
                         use_container_width=True):
                for v in vagas:
                    _aprovar(v.id, v.score)
                st.success(f"{len(vagas)} vagas aprovadas.")
                st.rerun()

# ── Lista ─────────────────────────────────────────────────────────────────────

if not vagas:
    _ui.vazio("Nenhuma vaga com esses filtros",
              "Tente afrouxar a busca, o status ou a aderência mínima.")
    st.stop()

st.caption(f"{len(vagas)} vaga{'s' if len(vagas) != 1 else ''} · "
           "ordenadas por aderência (máx. 100)")

for vaga in vagas:
    normalizado = vaga.normalizado_json if isinstance(vaga.normalizado_json, dict) else {}
    senioridade = normalizado.get("senioridade") or ""
    coletada = vaga.criado_em.strftime("%d/%m") if vaga.criado_em else ""

    meta = _ui.linha_meta(
        _ui.badge((vaga.plataforma or "").title()),
        f"<span>{vaga.localizacao}</span>" if vaga.localizacao else "",
        f"<span>{(vaga.modalidade or '').capitalize()}</span>" if vaga.modalidade else "",
        f"<span>{senioridade}</span>" if senioridade else "",
        f"<span>Coletada em {coletada}</span>" if coletada else "",
    )

    with st.container(border=True):
        esq, dir_ = st.columns([3.2, 1], vertical_alignment="top")
        with esq:
            st.markdown(
                f'<div class="vaga-empresa">{vaga.empresa or "—"}</div>'
                f'<div class="vaga-titulo">{vaga.titulo or "—"}</div>{meta}',
                unsafe_allow_html=True,
            )
        with dir_:
            st.markdown(
                '<div style="display:flex;flex-direction:column;'
                'align-items:flex-end;gap:.45rem">'
                f'{_ui.badge_status(vaga.status)}'
                f'{_ui.aderencia(vaga.score, alinhar="flex-end")}</div>',
                unsafe_allow_html=True,
            )

        with st.expander("Detalhes"):
            d1, d2 = st.columns(2)
            with d1:
                if normalizado.get("tecnologias"):
                    st.markdown("**Tecnologias**")
                    st.caption(", ".join(normalizado["tecnologias"][:12]))
                bd = vaga.score_breakdown_json or {}
                if bd.get("resumo"):
                    st.markdown("**Resumo**")
                    st.caption(bd["resumo"])
            with d2:
                bd = vaga.score_breakdown_json or {}
                if bd.get("motivos_positivos"):
                    st.markdown("**A favor**")
                    for p in bd["motivos_positivos"][:4]:
                        st.caption(f"— {p}")
                if bd.get("gaps"):
                    st.markdown("**Pontos de atenção**")
                    for g in bd["gaps"][:4]:
                        st.caption(f"— {g}")

            a1, a2, a3 = st.columns([1.3, 1, 1])
            with a1:
                st.link_button("Abrir vaga original", vaga.link or "#",
                               icon=":material/open_in_new:",
                               use_container_width=True)
            if vaga.status == "pendente":
                with a2:
                    if st.button("Aprovar", key=f"apr_{vaga.id}", type="primary",
                                 icon=":material/check:", use_container_width=True):
                        _aprovar(vaga.id, vaga.score)
                        st.rerun()
                with a3:
                    if st.button("Descartar", key=f"rej_{vaga.id}",
                                 icon=":material/close:", use_container_width=True):
                        _rejeitar(vaga.id, vaga.score)
                        st.rerun()
            elif vaga.status == "aprovada":
                with a2:
                    if st.button("Desfazer aprovação", key=f"undo_{vaga.id}",
                                 icon=":material/undo:", use_container_width=True):
                        with get_session() as session:
                            session.query(Vaga).filter(Vaga.id == vaga.id).update(
                                {"status": "pendente"})
                        st.rerun()
