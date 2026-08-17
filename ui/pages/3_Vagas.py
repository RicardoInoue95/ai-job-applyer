import _bootstrap  # noqa: F401  # deve vir antes de qualquer import de jobapplier
import streamlit as st

from jobapplier.config.manager import ConfigManager
from jobapplier.tempo import agora_utc

st.set_page_config(
    page_title="Vagas — AI Job Applier",
    page_icon="📋",
    layout="wide",
)

config = ConfigManager()
if not config.is_setup_complete():
    st.switch_page("pages/1_Setup.py")

st.title("📋 Vagas")

try:

    from sqlalchemy import func

    from jobapplier.database.connection import get_session
    from jobapplier.database.models import AprovacoesHistorico, Vaga
except Exception as exc:
    st.error(f"Erro ao conectar ao banco: {exc}")
    st.stop()


# ── Filtros ───────────────────────────────────────────────────────────────────

from jobapplier import status as vocab

# Vagas esperando por VOCÊ vêm primeiro: é o que o modo sombra produz e o que
# a tela existe para resolver. Antes o seletor tinha 6 status fixos e nenhum
# deles era 'pronta_para_revisao', então o resultado do modo sombra era
# invisível na interface.
_aguardando = vocab.exigem_sua_acao()
_demais = [c for c in vocab.codigos_vaga() if c not in _aguardando]
_OPCOES = ["aguardando você", *_aguardando, *_demais, "todas"]

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    status_filter = st.selectbox(
        "Status",
        _OPCOES,
        index=0,
        format_func=lambda c: (
            c if c in ("todas", "aguardando você")
            else f"{vocab.TOM_ICONE[vocab.de_vaga(c).tom]} {vocab.de_vaga(c).rotulo}"
        ),
    )
with col2:
    busca = st.text_input("Buscar por título ou empresa", placeholder="ex: Data Engineer, Nubank")
with col3:
    st.write("")
    st.write("")
    mostrar_filtradas = st.checkbox("Incluir filtradas", value=False)


# ── Query ──────────────────────────────────────────────────────────────────────

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
        return q.order_by(Vaga.score.desc().nullslast(), Vaga.criado_em.desc()).limit(100).all()


def _aprovar(vaga_id: int, score_val: float | None):
    with get_session() as session:
        session.query(Vaga).filter(Vaga.id == vaga_id).update({"status": "aprovada"})
        if score_val is not None:
            hist = AprovacoesHistorico(
                vaga_id=vaga_id,
                score=score_val,
                aprovado=True,
                criado_em=agora_utc(),
            )
            session.add(hist)


def _rejeitar(vaga_id: int, score_val: float | None):
    with get_session() as session:
        session.query(Vaga).filter(Vaga.id == vaga_id).update({"status": "rejeitada"})
        if score_val is not None:
            hist = AprovacoesHistorico(
                vaga_id=vaga_id,
                score=score_val,
                aprovado=False,
                criado_em=agora_utc(),
            )
            session.add(hist)


# ── Ações em lote (só na aba pendente) ───────────────────────────────────────

if status_filter == "pendente":
    with get_session() as session:
        total_pendente = session.query(func.count(Vaga.id)).filter(Vaga.status == "pendente").scalar() or 0
    if total_pendente:
        st.info(f"**{total_pendente}** vagas aguardando revisão manual")
        colA, colB = st.columns(2)
        with colA:
            if st.button("✅ Aprovar todas as pendentes", type="primary"):
                with get_session() as session:
                    pendentes = session.query(Vaga).filter(Vaga.status == "pendente").all()
                    for v in pendentes:
                        session.query(Vaga).filter(Vaga.id == v.id).update({"status": "aprovada"})
                        if v.score:
                            hist = AprovacoesHistorico(vaga_id=v.id, score=v.score, aprovado=True, criado_em=agora_utc())
                            session.add(hist)
                st.success(f"✓ {len(pendentes)} vagas aprovadas")
                st.rerun()
        with colB:
            if st.button("❌ Rejeitar todas as pendentes"):
                with get_session() as session:
                    pendentes = session.query(Vaga).filter(Vaga.status == "pendente").all()
                    for v in pendentes:
                        session.query(Vaga).filter(Vaga.id == v.id).update({"status": "rejeitada"})
                st.success(f"✗ {len(pendentes)} vagas rejeitadas")
                st.rerun()


# ── Lista de vagas ─────────────────────────────────────────────────────────────

vagas = _get_vagas(status_filter, busca)

if not vagas:
    st.info("Nenhuma vaga encontrada com esses filtros.")
else:
    st.caption(f"{len(vagas)} vagas exibidas (máx. 100)")
    st.divider()

    for vaga in vagas:
        score_label = f"**{vaga.score:.0f}**" if vaga.score is not None else "—"

        status_icon = {
            "pendente": "🟡",
            "aprovada": "✅",
            "rejeitada": "❌",
            "nova": "🆕",
            "filtrada_4a": "⛔",
            "filtrada_4b": "⛔",
            "candidatada": "🎉",
            "em_andamento": "⏳",
        }.get(vaga.status, "○")

        header = f"{status_icon} {score_label} — **{vaga.titulo}** · {vaga.empresa} [{vaga.plataforma}]"

        with st.expander(header, expanded=(vaga.status == "pendente")):
            col1, col2, col3 = st.columns([3, 2, 2])

            with col1:
                st.caption(f"📍 {vaga.localizacao or '—'} | 🗂️ {vaga.status}")
                if vaga.normalizado_json:
                    norm = vaga.normalizado_json
                    techs = ", ".join(norm.get("tecnologias", [])[:8])
                    senioridade = norm.get("senioridade", "—")
                    modalidade = norm.get("modalidade", "—")
                    idioma = norm.get("idioma_principal", "—")
                    st.caption(f"🎯 {senioridade} | 🏠 {modalidade} | 🌐 {idioma}")
                    if techs:
                        st.caption(f"🔧 {techs}")

            with col2:
                if vaga.score_breakdown_json:
                    bd = vaga.score_breakdown_json
                    breakdown = bd.get("breakdown", {})
                    if breakdown:
                        st.markdown("**Score breakdown:**")
                        for criterio, pts in breakdown.items():
                            label = {
                                "skills_tecnicas": "Skills",
                                "senioridade": "Senioridade",
                                "setor": "Setor",
                                "idioma": "Idioma",
                                "localizacao": "Localização",
                            }.get(criterio, criterio)
                            st.caption(f"• {label}: {pts}")

                    resumo = bd.get("resumo", "")
                    if resumo:
                        st.caption(f"💬 _{resumo}_")

            with col3:
                if vaga.score_breakdown_json:
                    bd = vaga.score_breakdown_json
                    positivos = bd.get("motivos_positivos", [])
                    gaps = bd.get("gaps", [])
                    if positivos:
                        st.markdown("**✓ Pontos fortes:**")
                        for p in positivos[:3]:
                            st.caption(f"• {p}")
                    if gaps:
                        st.markdown("**△ Gaps:**")
                        for g in gaps[:3]:
                            st.caption(f"• {g}")

            st.markdown(f"[🔗 Ver vaga original]({vaga.link})")

            if vaga.status == "pendente":
                ca, cb = st.columns(2)
                with ca:
                    if st.button("✅ Aprovar", key=f"apr_{vaga.id}", type="primary"):
                        _aprovar(vaga.id, vaga.score)
                        st.rerun()
                with cb:
                    if st.button("❌ Rejeitar", key=f"rej_{vaga.id}"):
                        _rejeitar(vaga.id, vaga.score)
                        st.rerun()
            elif vaga.status == "aprovada":
                if st.button("↩ Desfazer aprovação", key=f"undo_{vaga.id}"):
                    with get_session() as session:
                        session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "pendente"})
                    st.rerun()
