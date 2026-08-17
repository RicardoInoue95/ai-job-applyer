import json
import streamlit as st
from config.manager import ConfigManager

st.set_page_config(
    page_title="Candidaturas — AI Job Applier",
    page_icon="🎯",
    layout="wide",
)

config = ConfigManager()
if not config.is_setup_complete():
    st.switch_page("pages/1_Setup.py")

st.title("🎯 Candidaturas")

try:
    from database.connection import get_session
    from database.models import Candidatura, Vaga
    from sqlalchemy import func
except Exception as exc:
    st.error(f"Erro ao conectar ao banco: {exc}")
    st.stop()

# ── Métricas ──────────────────────────────────────────────────────────────────

with get_session() as session:
    total = session.query(func.count(Candidatura.id)).scalar() or 0
    enviadas = session.query(func.count(Candidatura.id)).filter(Candidatura.status == "enviada").scalar() or 0
    pendentes = session.query(func.count(Candidatura.id)).filter(Candidatura.status == "perguntas_pendentes").scalar() or 0
    erros = session.query(func.count(Candidatura.id)).filter(Candidatura.status == "erro").scalar() or 0
    ats_med = session.query(func.avg(Candidatura.ats_score_otimizado)).filter(Candidatura.ats_score_otimizado.isnot(None)).scalar()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total", total)
col2.metric("Enviadas", enviadas)
col3.metric("Perguntas pendentes", pendentes)
col4.metric("Erros", erros)
col5.metric("ATS médio", f"{ats_med:.1f}%" if ats_med else "—")

st.divider()

# ── Botão candidatar ──────────────────────────────────────────────────────────

with get_session() as session:
    aprovadas_count = session.query(func.count(Vaga.id)).filter(Vaga.status == "aprovada").scalar() or 0

if aprovadas_count:
    st.info(f"**{aprovadas_count}** vagas aprovadas aguardando candidatura.")
    if st.button("🚀 Candidatar vagas aprovadas agora", type="primary"):
        with st.spinner("Otimizando currículos, gerando cover letters e candidatando..."):
            try:
                from orchestrator import run_applications
                run_applications()
                st.success("✓ Processo de candidatura concluído!")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro: {exc}")
    st.divider()

# ── CPF aviso ─────────────────────────────────────────────────────────────────

dados_pessoais = config.get("dados_pessoais") or {}
if not dados_pessoais.get("cpf"):
    st.warning(
        "⚠️ **CPF não configurado** — necessário para candidaturas XP Inc e outras empresas. "
        "Configure em [Setup → Etapa 3](1_Setup)."
    )

# ── Histórico ─────────────────────────────────────────────────────────────────

st.subheader("Histórico de candidaturas")

with get_session() as session:
    rows = (
        session.query(Candidatura, Vaga)
        .join(Vaga, Candidatura.vaga_id == Vaga.id, isouter=True)
        .order_by(Candidatura.criado_em.desc())
        .limit(50)
        .all()
    )

if not rows:
    st.info("Nenhuma candidatura registrada ainda.")
else:
    for cand, vaga in rows:
        STATUS_ICON = {
            "enviada": "✅",
            "perguntas_pendentes": "⚠️",
            "erro": "❌",
            "pendente": "⏳",
        }.get(cand.status, "○")

        titulo = vaga.titulo if vaga else f"Vaga #{cand.vaga_id}"
        empresa = vaga.empresa if vaga else "?"
        link = vaga.link if vaga else None

        header = (
            f"{STATUS_ICON} **{titulo}** · {empresa} — "
            f"{cand.criado_em.strftime('%d/%m/%Y %H:%M') if cand.criado_em else '?'}"
        )

        with st.expander(header):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.caption(f"Status: **{cand.status}**")
                st.caption(f"Perfil base: {cand.perfil_base or '—'}")
                if link:
                    st.markdown(f"[🔗 Ver vaga]({link})")

            with col2:
                if cand.ats_score_original is not None:
                    delta = (cand.ats_score_otimizado or 0) - cand.ats_score_original
                    st.metric(
                        "ATS Score",
                        f"{cand.ats_score_otimizado:.1f}%" if cand.ats_score_otimizado else "—",
                        delta=f"+{delta:.1f}%" if delta > 0 else f"{delta:.1f}%",
                    )
                if cand.keywords_adicionadas:
                    st.caption(f"Keywords adicionadas: {', '.join(cand.keywords_adicionadas[:6])}")

            with col3:
                if cand.curriculo_path:
                    pdf_path = __import__("pathlib").Path(cand.curriculo_path)
                    if pdf_path.exists():
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                "📄 Baixar currículo PDF",
                                f.read(),
                                file_name=pdf_path.name,
                                mime="application/pdf",
                                key=f"pdf_{cand.id}",
                            )
                if cand.cover_letter_path:
                    cl_path = __import__("pathlib").Path(cand.cover_letter_path)
                    if cl_path.exists():
                        texto = cl_path.read_text(encoding="utf-8")
                        with st.expander("📝 Ver cover letter"):
                            st.text(texto)

            # ── Perguntas pendentes ─────────────────────────────────────────
            if cand.status == "perguntas_pendentes" and cand.erro:
                try:
                    perguntas = json.loads(cand.erro)
                    if isinstance(perguntas, list) and perguntas:
                        st.warning("**Perguntas sem resposta automática** — precisam ser respondidas manualmente no site:")
                        for i, p in enumerate(perguntas, 1):
                            st.caption(f"{i}. {p}")
                        if link:
                            st.markdown(f"[🌐 Completar candidatura manualmente]({link})")
                except (json.JSONDecodeError, TypeError):
                    st.warning(f"Detalhe: {cand.erro}")

            elif cand.status == "erro" and cand.erro:
                st.error(f"Erro: {cand.erro}")

            # ── Botão retry ────────────────────────────────────────────────
            if cand.status in ("perguntas_pendentes", "erro") and vaga:
                if st.button(f"🔄 Tentar novamente", key=f"retry_{cand.id}"):
                    with get_session() as session:
                        session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "aprovada"})
                    st.success("Vaga redefinida para 'aprovada'. Clique em 'Candidatar vagas aprovadas' para tentar novamente.")
                    st.rerun()
