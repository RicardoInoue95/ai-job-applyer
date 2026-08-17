from pathlib import Path

import streamlit as st

from config.manager import ConfigManager

st.set_page_config(
    page_title="Dashboard — AI Job Applier",
    page_icon="💼",
    layout="wide",
)

config = ConfigManager()

if not config.is_setup_complete():
    st.switch_page("pages/1_Setup.py")

st.title("💼 Dashboard")
st.caption("AI Job Applier — visão geral")

# ── Métricas ─────────────────────────────────────────────────────────────────

try:
    from sqlalchemy import func

    from database.connection import get_session
    from database.models import Candidatura, Vaga

    with get_session() as session:
        total_vagas = session.query(func.count(Vaga.id)).scalar() or 0
        novas = session.query(func.count(Vaga.id)).filter(Vaga.status == "nova").scalar() or 0
        pendentes = session.query(func.count(Vaga.id)).filter(Vaga.status == "pendente").scalar() or 0
        aprovadas = session.query(func.count(Vaga.id)).filter(Vaga.status == "aprovada").scalar() or 0
        rejeitadas = session.query(func.count(Vaga.id)).filter(Vaga.status == "rejeitada").scalar() or 0
        filtradas = (
            session.query(func.count(Vaga.id))
            .filter(Vaga.status.in_(["filtrada_4a", "filtrada_4b"]))
            .scalar() or 0
        )
        score_medio = (
            session.query(func.avg(Vaga.score))
            .filter(Vaga.score.isnot(None))
            .scalar()
        )
        total_candidaturas = session.query(func.count(Candidatura.id)).scalar() or 0
        enviadas = (
            session.query(func.count(Candidatura.id))
            .filter(Candidatura.status == "candidatada")
            .scalar() or 0
        )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Vagas coletadas", total_vagas)
    col2.metric("Aguardando pipeline", novas, help="Vagas ainda não normalizadas/pontuadas")
    col3.metric("Revisão manual", pendentes, help="Score 70–84, aguardando aprovação")
    col4.metric("Aprovadas", aprovadas)

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Rejeitadas", rejeitadas)
    col6.metric("Filtradas (sem IA)", filtradas, help="Descartadas pelos filtros 4A/4B")
    col7.metric("Score médio", f"{score_medio:.1f}" if score_medio else "—")
    col8.metric("Candidaturas enviadas", enviadas)

    # ── Vagas por plataforma ──────────────────────────────────────────────────
    st.divider()
    st.markdown("##### Vagas por plataforma")

    with get_session() as session:
        por_plataforma = (
            session.query(Vaga.plataforma, func.count(Vaga.id))
            .group_by(Vaga.plataforma)
            .order_by(func.count(Vaga.id).desc())
            .all()
        )

    PLATFORM_META = {
        "greenhouse": ("🌿", "Greenhouse"),
        "lever":      ("⚙️",  "Lever"),
        "linkedin":   ("💼", "LinkedIn"),
        "gupy":       ("🇧🇷", "Gupy"),
    }

    if por_plataforma:
        cols = st.columns(max(len(por_plataforma), 4))
        for i, (plat, count) in enumerate(por_plataforma):
            icon, label = PLATFORM_META.get(plat or "", ("🔗", (plat or "Outro").title()))
            with cols[i]:
                st.markdown(
                    f"""<div style="border:1px solid #e0e0e0;border-radius:10px;
                        padding:14px 10px;text-align:center;background:#fafafa">
                        <div style="font-size:24px">{icon}</div>
                        <div style="font-size:22px;font-weight:700;margin:4px 0">{count}</div>
                        <div style="font-size:12px;color:#666">{label}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
    else:
        st.info("Nenhuma vaga coletada ainda.")

except Exception as exc:
    st.warning(f"Banco de dados não disponível: {exc}")
    st.info("Execute `python run.py` para iniciar o sistema completo.")

st.divider()

# ── Ações manuais ─────────────────────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    st.subheader("Coleta de vagas")

    # Resumo das plataformas configuradas
    companies  = config.get_target_companies()
    gh_slugs   = companies.get("greenhouse", [])
    lv_slugs   = companies.get("lever", [])
    gupy_slugs = config.get("coleta", "empresas_gupy") or []
    li_queries = config.get("linkedin", "search_queries") or []

    from applicators.linkedin import has_session as _li_has_session
    li_ok = _li_has_session()

    platform_lines = []
    if gh_slugs:
        platform_lines.append(f"🌿 Greenhouse: {', '.join(gh_slugs)}")
    if lv_slugs:
        platform_lines.append(f"⚙️ Lever: {', '.join(lv_slugs)}")
    if gupy_slugs:
        platform_lines.append(f"🇧🇷 Gupy: {', '.join(gupy_slugs)}")
    DEFAULT_LI_QUERIES = [
        # ── Analista de BI ────────────────────────────────────────────────
        "Analista de BI",
        "Analista de BI Pleno",
        "Analista de BI Sênior",
        "Analista de Business Intelligence",
        "Analista Business Intelligence Pleno",
        "Analista Business Intelligence Sênior",
        "BI Analyst",
        "BI Analyst Pleno",
        "BI Analyst Senior",
        "Business Intelligence Analyst",
        "BI Developer",
        "BI Engineer",
        "Power BI Analyst",
        "Power BI Developer",
        "Power BI Specialist",
        "Especialista Power BI",
        # ── Analista de Dados ────────────────────────────────────────────
        "Analista de Dados",
        "Analista de Dados Júnior",
        "Analista de Dados Pleno",
        "Analista de Dados Sênior",
        "Analista de Dados Especialista",
        "Data Analyst",
        "Data Analyst Junior",
        "Data Analyst Pleno",
        "Data Analyst Senior",
        "Especialista em Dados",
        "Especialista em Análise de Dados",
        # ── Analytics Engineer ───────────────────────────────────────────
        "Analytics Engineer",
        "Analytics Engineer Pleno",
        "Analytics Engineer Sênior",
        "Engenheiro Analytics",
        # ── Engenheiro de Dados ──────────────────────────────────────────
        "Engenheiro de Dados",
        "Engenheiro de Dados Pleno",
        "Engenheiro de Dados Sênior",
        "Engenheiro de Dados Especialista",
        "Data Engineer",
        "Data Engineer Pleno",
        "Data Engineer Senior",
        "Especialista em Engenharia de Dados",
        # ── Coordenação e liderança ──────────────────────────────────────
        "Coordenador de Dados",
        "Coordenador de BI",
        "Coordenador de Analytics",
        "Coordenador de Business Intelligence",
        "Lead Data Engineer",
        "Tech Lead Dados",
        "Tech Lead Data",
        # ── Plataforma / infraestrutura ──────────────────────────────────
        "Snowflake Developer",
        "Snowflake Data Engineer",
        "Databricks Engineer",
        "Azure Data Engineer",
        "Data Platform Engineer",
        # ── Modelagem e governança ───────────────────────────────────────
        "Analista de Modelagem de Dados",
        "Data Modeler",
        "Especialista em Governança de Dados",
        "Data Governance Analyst",
        "Analista de Qualidade de Dados",
        # ── Ciência de Dados (adjacente) ─────────────────────────────────
        "Analista de Ciência de Dados",
        "Data Scientist",
    ]

    if li_queries:
        status = "✓ sessão ativa" if li_ok else "⚠️ sem sessão"
        platform_lines.append(f"💼 LinkedIn ({status}): {len(li_queries)} queries")
    if not platform_lines:
        platform_lines.append("Nenhuma plataforma configurada — vá ao Setup.")

    st.caption("  ·  ".join(platform_lines))

    # ── Greenhouse slugs ──────────────────────────────────────────────────
    DEFAULT_GH_SLUGS = {
        # Fintechs / Bancos BR
        "nubank": "Nubank",
        "xpinc": "XP Inc",
        "creditas": "Creditas",
        "stone": "Stone",
        "neon": "Neon",
        "cloudwalk": "CloudWalk",
        "pismo": "Pismo",
        "dock": "Dock",
        "cora": "Cora",
        "matera": "Matera",
        "meliuz": "Méliuz",
        "warren": "Warren",
        # PropTech / E-commerce / Marketplace BR
        "quintoandar": "QuintoAndar",
        "loft": "Loft",
        "luizalabs": "Luizalabs (Magazine Luiza)",
        "olist": "Olist",
        "loggi": "Loggi",
        "getninjas": "GetNinjas",
        # SaaS / Tech BR
        "vtex": "VTEX",
        "hotmart": "Hotmart",
        "contaazul": "Conta Azul",
        "rdstation": "RD Station",
        "totvs": "TOTVS",
        # Healthtech / Outros BR
        "wellhub": "Wellhub (Gympass)",
        "vr": "VR Benefícios",
        # Consultorias / Serviços Tech
        "ciandt": "CI&T",
        "thoughtworks": "Thoughtworks",
        "stefanini": "Stefanini",
        # Data & Cloud (internacionais com escritório BR)
        "databricks": "Databricks",
        "snowflake": "Snowflake",
        "fivetran": "Fivetran",
        "dbtlabs": "dbt Labs",
        "airbyte": "Airbyte",
        "confluent": "Confluent",
        "mongodb": "MongoDB",
        "elastic": "Elastic",
        "cloudflare": "Cloudflare",
        # Big Tech com vagas no BR
        "stripe": "Stripe",
        "twilio": "Twilio",
        "zendesk": "Zendesk",
        "hubspot": "HubSpot",
    }

    with st.expander(f"Editar slugs Greenhouse ({len(gh_slugs)} configurados)"):
        all_suggested = [s for s in DEFAULT_GH_SLUGS if s not in gh_slugs]
        if all_suggested:
            st.caption(f"**{len(all_suggested)} empresas sugeridas** não estão na sua lista:")
            col_a, col_b, col_c = st.columns(3)
            to_add = []
            for i, slug in enumerate(all_suggested):
                col = [col_a, col_b, col_c][i % 3]
                if col.checkbox(f"{DEFAULT_GH_SLUGS[slug]}", key=f"gh_{slug}"):
                    to_add.append(slug)
            if st.button("Adicionar selecionadas", key="add_gh_slugs", disabled=not to_add):
                cfg = config.load()
                new_list = sorted(set(gh_slugs) | set(to_add))
                cfg.setdefault("coleta", {})["empresas_greenhouse"] = new_list
                config.save(cfg)
                st.success(f"✓ {len(to_add)} empresa(s) adicionadas!")
                st.rerun()
            st.divider()

        edited_gh = st.text_area(
            "Lista completa (um slug por linha)",
            value="\n".join(sorted(gh_slugs)),
            height=180,
            label_visibility="collapsed",
        )
        if st.button("Salvar lista completa", key="save_gh_slugs"):
            cfg = config.load()
            cfg.setdefault("coleta", {})["empresas_greenhouse"] = [
                s.strip() for s in edited_gh.splitlines() if s.strip()
            ]
            config.save(cfg)
            st.success("✓ Slugs salvos!")
            st.rerun()

    # ── LinkedIn queries ──────────────────────────────────────────────────
    if li_ok or li_queries:
        with st.expander(f"Editar queries LinkedIn ({len(li_queries)} configuradas)"):
            current = li_queries if li_queries else DEFAULT_LI_QUERIES
            edited = st.text_area(
                "Uma por linha",
                value="\n".join(current),
                height=260,
                label_visibility="collapsed",
            )
            if st.button("Salvar queries", key="save_li_queries"):
                new_queries = [q.strip() for q in edited.splitlines() if q.strip()]
                cfg = config.load()
                cfg.setdefault("linkedin", {})["search_queries"] = new_queries
                config.save(cfg)
                st.success(f"✓ {len(new_queries)} queries salvas!")
                st.rerun()

    if st.button("▶ Coletar vagas agora", type="primary"):
        with st.spinner("Coletando vagas de todas as plataformas..."):
            try:
                from orchestrator import run_collection
                run_collection()
                st.success("✓ Coleta concluída!")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro na coleta: {exc}")

with col2:
    st.subheader("Pipeline de inteligência")
    api_key = config.get_gemini_key()
    resume_exists = Path("data/resume.json").exists()

    if not api_key:
        st.warning("Configure a Gemini API Key no setup para habilitar o pipeline.")
    elif not resume_exists:
        st.warning("Currículo não encontrado. Faça o upload no setup.")
    else:
        st.caption("Filtros 4A → Normalização Gemini → Filtros 4B → Scoring IA")
        if st.button("⚡ Executar pipeline agora", type="primary"):
            with st.spinner("Processando vagas com IA... (pode levar alguns minutos)"):
                try:
                    from orchestrator import run_pipeline
                    run_pipeline()
                    st.success("✓ Pipeline concluído! Veja os resultados em Vagas.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro no pipeline: {exc}")

st.divider()

# ── Candidaturas ──────────────────────────────────────────────────────────────

try:
    from sqlalchemy import func

    from database.connection import get_session
    from database.models import Vaga

    with get_session() as session:
        aprovadas_count = session.query(func.count(Vaga.id)).filter(Vaga.status == "aprovada").scalar() or 0

    with get_session() as session:
        pendentes_count = session.query(func.count(Vaga.id)).filter(Vaga.status == "pendente").scalar() or 0
        rejeitadas_count = session.query(func.count(Vaga.id)).filter(Vaga.status == "rejeitada").scalar() or 0

    total_candidataveis = aprovadas_count + pendentes_count
    if total_candidataveis:
        st.subheader(f"Candidaturas — {total_candidataveis} vaga(s) para enviar")
        st.caption(f"✅ {aprovadas_count} aprovadas (score ≥ 65) · 🟡 {pendentes_count} pendentes (score ≥ 45)")
        if st.button("🚀 Candidatar vagas aprovadas + pendentes", type="primary"):
            with st.spinner("Otimizando currículos e candidatando..."):
                try:
                    from orchestrator import run_applications
                    run_applications()
                    st.success("✓ Processo concluído! Veja detalhes em Candidaturas.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro: {exc}")
        if rejeitadas_count:
            if st.button(f"🔄 Re-avaliar {rejeitadas_count} rejeitadas com novos critérios", key="reavaliar"):
                with st.spinner("Re-avaliando vagas com threshold 65/45..."):
                    try:
                        from database.connection import get_session as _gs
                        from database.models import Vaga as _V
                        with _gs() as s:
                            s.query(_V).filter(
                                _V.status == "rejeitada",
                                _V.score >= 45,
                                _V.score.isnot(None),
                            ).update({"status": "pendente"})
                            upgraded = s.query(func.count(_V.id)).filter(
                                _V.status == "pendente",
                                _V.score >= 65,
                            ).scalar() or 0
                            s.query(_V).filter(
                                _V.status == "pendente",
                                _V.score >= 65,
                            ).update({"status": "aprovada"})
                        st.success("✓ Vagas re-avaliadas! Verifique os novos totais.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro: {exc}")

        st.divider()
except Exception:
    pass

# ── Últimas vagas pontuadas ────────────────────────────────────────────────────

st.subheader("Últimas vagas pontuadas")

try:
    from database.connection import get_session
    from database.models import Vaga

    with get_session() as session:
        vagas = (
            session.query(Vaga)
            .filter(Vaga.score.isnot(None))
            .order_by(Vaga.score.desc())
            .limit(10)
            .all()
        )

    if vagas:
        for vaga in vagas:
            status_icon = {"aprovada": "✅", "pendente": "🟡", "rejeitada": "❌"}.get(vaga.status, "○")
            with st.expander(f"{status_icon} **{vaga.score:.0f}** — {vaga.titulo} · {vaga.empresa}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"📍 {vaga.localizacao or '—'} | 🗂️ {vaga.status}")
                    if vaga.normalizado_json:
                        techs = ", ".join(vaga.normalizado_json.get("tecnologias", [])[:6])
                        st.caption(f"🔧 {techs or '—'}")
                with col2:
                    if vaga.score_breakdown_json:
                        resumo = vaga.score_breakdown_json.get("resumo", "")
                        if resumo:
                            st.caption(f"💬 _{resumo}_")
                st.markdown(f"[Ver vaga]({vaga.link})")
    else:
        st.info("Execute o pipeline acima para pontuar as vagas coletadas.")

except Exception:
    pass

st.divider()

# ── Distribuição por status ────────────────────────────────────────────────────

st.subheader("Distribuição por status")

try:
    from sqlalchemy import func

    from database.connection import get_session
    from database.models import Vaga

    with get_session() as session:
        dist = (
            session.query(Vaga.status, func.count(Vaga.id))
            .group_by(Vaga.status)
            .all()
        )

    if dist:
        STATUS_LABELS = {
            "nova": "🆕 Nova",
            "pendente": "🟡 Pendente",
            "aprovada": "✅ Aprovada",
            "rejeitada": "❌ Rejeitada",
            "filtrada_4a": "⛔ Filtrada (pré-IA)",
            "filtrada_4b": "⛔ Filtrada (pós-IA)",
            "candidatada": "🎉 Candidatada",
            "em_andamento": "⏳ Em andamento",
        }
        cols = st.columns(min(len(dist), 4))
        for i, (status, count) in enumerate(sorted(dist, key=lambda x: -x[1])):
            cols[i % 4].metric(STATUS_LABELS.get(status, status), count)

except Exception:
    pass
