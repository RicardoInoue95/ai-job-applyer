import json
from pathlib import Path

import streamlit as st

from config.manager import ConfigManager

st.set_page_config(
    page_title="Configuração — AI Job Applier",
    page_icon="⚙️",
    layout="centered",
)

config = ConfigManager()

TOTAL_STEPS = 7
STEP_LABELS = [
    "Provedor IA",
    "Currículo",
    "Preferências",
    "LinkedIn",
    "Gupy",
    "E-mail",
    "Concluído",
]

DATA_DIR = Path("data")
RESUMES_DIR = DATA_DIR / "resumes"
SESSIONS_DIR = DATA_DIR / "sessions"


def _init_session():
    if "setup_step" not in st.session_state:
        completed = config.get("setup_progress", "last_step", default=0)
        st.session_state.setup_step = max(1, int(completed))


def _go_to(step: int):
    st.session_state.setup_step = step
    config.set("setup_progress", "last_step", value=step)
    st.rerun()


def _render_progress(current: int):
    # Indicador visual HTML — mostra status de cada etapa
    parts = []
    for i, label in enumerate(STEP_LABELS, start=1):
        if i < current:
            parts.append(
                f'<span style="color:#27ae60;font-size:12px;white-space:nowrap">'
                f'✓ {label}</span>'
            )
        elif i == current:
            parts.append(
                f'<span style="background:#1E3A5F;color:#fff;font-size:12px;'
                f'font-weight:600;padding:2px 10px;border-radius:12px;white-space:nowrap">'
                f'{label}</span>'
            )
        else:
            parts.append(
                f'<span style="color:#bbb;font-size:12px;white-space:nowrap">'
                f'{label}</span>'
            )
    separator = '<span style="color:#ddd;margin:0 6px">›</span>'
    html = separator.join(parts)
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;'
        f'gap:4px;margin-bottom:6px">{html}</div>',
        unsafe_allow_html=True,
    )
    st.progress((current - 1) / (TOTAL_STEPS - 1))

    # Seletor de navegação
    pill_options = [f"{i}. {STEP_LABELS[i-1]}" for i in range(1, TOTAL_STEPS + 1)]
    selected = st.pills(
        "Ir para:",
        pill_options,
        default=pill_options[current - 1],
        key=f"nav_pills_{current}",
        label_visibility="collapsed",
    )
    if selected:
        target = int(selected.split(".")[0])
        if target != current:
            _go_to(target)

    st.divider()


def _advance(step: int):
    st.session_state.setup_step = step + 1
    config.set("setup_progress", "last_step", value=step + 1)
    st.rerun()


def _back(step: int):
    st.session_state.setup_step = step - 1
    config.set("setup_progress", "last_step", value=step - 1)
    st.rerun()


# ── Etapa 1: Provedor de IA ──────────────────────────────────────────────────

PROVEDOR_INFO = {
    "openai": ("OpenAI (ChatGPT)", "https://platform.openai.com/api-keys", "sk-..."),
    "gemini": ("Google Gemini", "https://aistudio.google.com/apikey", "AI..."),
    "anthropic": ("Anthropic (Claude)", "https://console.anthropic.com/settings/keys", "sk-ant-..."),
}


def step_1():
    from agents.llm import (
        MODELOS_SUGERIDOS,
        ORDEM_PADRAO,
        PROVEDORES,
        chave_do_provedor,
        provedores_configurados,
        testar_conexao,
    )
    from config import secrets

    st.title("Etapa 1 — Provedor de IA")
    st.markdown(
        "Escolha qual API usará para normalizar vagas, pontuar aderência, "
        "otimizar currículo e gerar cover letters. Você pode trocar depois sem "
        "perder nada — o provedor é configuração, não código."
    )

    ja_configurados = provedores_configurados()
    salvo = config.get("llm", "provedor") or (ja_configurados[0] if ja_configurados else "openai")

    opcoes = list(ORDEM_PADRAO)
    provedor = st.selectbox(
        "Provedor",
        opcoes,
        index=opcoes.index(salvo) if salvo in opcoes else 0,
        format_func=lambda p: (
            f"{PROVEDOR_INFO[p][0]}" + (" ✓ chave configurada" if p in ja_configurados else "")
        ),
    )

    rotulo, url_chave, placeholder = PROVEDOR_INFO[provedor]
    st.caption(f"Obtenha a chave em [{rotulo}]({url_chave})")

    # ── Modelo ────────────────────────────────────────────────────────────────
    sugeridos = MODELOS_SUGERIDOS.get(provedor, [])
    padrao_provedor = PROVEDORES[provedor].modelo_padrao
    modelo_salvo = config.get("llm", "modelo")

    ids = [m for m, _ in sugeridos]
    rotulos = {m: r for m, r in sugeridos}
    OUTRO = "__outro__"
    escolha = st.selectbox(
        "Modelo",
        ids + [OUTRO],
        index=ids.index(modelo_salvo) if modelo_salvo in ids else ids.index(padrao_provedor) if padrao_provedor in ids else 0,
        format_func=lambda m: "Outro (digitar ID)" if m == OUTRO else rotulos.get(m, m),
    )
    modelo = st.text_input("ID do modelo", value=modelo_salvo or padrao_provedor) if escolha == OUTRO else escolha

    # ── Chave ─────────────────────────────────────────────────────────────────
    chave_atual = chave_do_provedor(provedor) or ""
    if chave_atual:
        st.success(f"Chave de {rotulo} já configurada (…{chave_atual[-4:]}). Deixe em branco para manter.")

    chave_nova = st.text_input(
        f"API Key — {rotulo}",
        value="",
        type="password",
        placeholder=placeholder,
        help="Gravada em .env, fora do controle de versão. Nunca vai para data/config.json.",
    )
    chave_efetiva = chave_nova or chave_atual

    # ── Fallback ──────────────────────────────────────────────────────────────
    outros = [p for p in ja_configurados if p != provedor]
    usar_fallback = st.checkbox(
        "Usar outros provedores como reserva se este falhar",
        value=bool(config.get("llm", "fallback")),
        disabled=not outros,
        help=(f"Reservas disponíveis: {', '.join(PROVEDOR_INFO[p][0] for p in outros)}"
              if outros else "Configure uma segunda chave para habilitar."),
    )

    if st.button("Testar conexão", type="primary", disabled=not chave_efetiva):
        with st.spinner(f"Conectando ao {rotulo}..."):
            ok, msg = testar_conexao(provedor, api_key=chave_efetiva, modelo=modelo)

        if ok:
            if chave_nova:
                secrets.gravar_env(PROVEDORES[provedor].env_chave, chave_nova)
            config.set("llm", "provedor", value=provedor)
            config.set("llm", "modelo", value=modelo)
            config.set("llm", "fallback", value=True if usar_fallback else None)
            st.success(f"✓ {msg}")
            st.session_state["llm_key_ok"] = True
        else:
            st.error(f"✗ Erro: {msg}")
            st.session_state["llm_key_ok"] = False

    if st.session_state.get("llm_key_ok") or chave_atual:
        st.button(
            "Próximo →", on_click=_advance, args=(1,),
            type="primary" if st.session_state.get("llm_key_ok") else "secondary",
        )


# ── Etapa 2: Upload de Currículo ─────────────────────────────────────────────

def step_2():
    st.title("Etapa 2 — Currículo")
    st.markdown("Envie seu currículo em **PDF** ou **DOCX**. Ele será analisado e convertido para JSON.")

    from agents.llm import provedores_configurados

    if not provedores_configurados():
        st.error("Configure um provedor de IA na Etapa 1 primeiro.")
        st.button("← Voltar", on_click=_back, args=(2,))
        return

    existing = DATA_DIR / "resume.json"
    if existing.exists() and not st.session_state.get("reenviar_curriculo"):
        with open(existing, encoding="utf-8") as f:
            saved_resume = json.load(f)
        st.success(f"✓ Currículo já configurado: **{saved_resume.get('nome', '?')}**")
        st.caption(f"{len(saved_resume.get('experiencias', []))} experiências · {len(saved_resume.get('tecnologias', []))} tecnologias")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Usar este currículo →", type="primary"):
                _advance(2)
        with col2:
            if st.button("Reenviar outro currículo"):
                st.session_state["reenviar_curriculo"] = True
                st.rerun()
        return

    uploaded = st.file_uploader(
        "Selecione seu currículo",
        type=["pdf", "docx"],
        help="PDF ou DOCX, máximo 10 MB",
    )

    if uploaded:
        st.info(f"Arquivo: {uploaded.name} ({uploaded.size // 1024} KB)")

        if st.button("Analisar currículo com IA", type="primary"):
            RESUMES_DIR.mkdir(parents=True, exist_ok=True)
            suffix = Path(uploaded.name).suffix
            resume_path = RESUMES_DIR / f"resume_master{suffix}"
            resume_path.write_bytes(uploaded.getvalue())

            with st.spinner("Analisando currículo... (pode levar 30 segundos)"):
                try:
                    from resume_parser.pipeline import ResumePipeline
                    pipeline = ResumePipeline()
                    resume, profiles = pipeline.run(resume_path, RESUMES_DIR)

                    resume_data = resume.model_dump()
                    output_path = DATA_DIR / "resume.json"
                    output_path.write_text(
                        json.dumps(resume_data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                    st.success(f"✓ Currículo analisado: **{resume.nome}**")
                    st.caption(
                        f"{len(resume.experiencias)} experiências · "
                        f"{len(resume.tecnologias)} tecnologias · "
                        f"{len(profiles)} perfis base gerados"
                    )

                    with st.expander("Ver JSON extraído"):
                        st.json(resume_data)

                    st.session_state["resume_ok"] = True
                    st.session_state.pop("reenviar_curriculo", None)

                except Exception as exc:
                    st.error(f"Erro ao analisar currículo: {exc}")
                    st.session_state["resume_ok"] = False

    if st.session_state.get("resume_ok"):
        st.button("Próximo →", on_click=_advance, args=(2,), type="primary")

    st.button("← Voltar", on_click=_back, args=(2,))


# ── Etapa 3: Preferências de Busca ──────────────────────────────────────────

SETORES_DISPONIVEIS = [
    "Tecnologia / Software",
    "Fintech / Banco Digital",
    "Banco / Serviços Financeiros",
    "Seguros",
    "E-commerce / Marketplace",
    "Saúde / Healthtech",
    "Farmacêutica / Biotech",
    "Educação / Edtech",
    "Logística / Supply Chain",
    "Varejo",
    "Telecomunicações",
    "Mídia / Entretenimento",
    "Agronegócio / Agtech",
    "Energia / Utilities",
    "Consultoria / Serviços Profissionais",
    "Indústria / Manufatura",
    "Imobiliário / Proptech",
    "Segurança / Cibersegurança",
    "RH / Recrutamento",
    "Marketing / Adtech",
    "Mobilidade / Transporte",
    "Jurídico / Legaltech",
    "Governo / Setor Público",
    "ONG / Terceiro Setor",
]

DISCOVER_PROMPT = """Você é especialista em mercado de trabalho de tecnologia no Brasil e internacional.

O candidato trabalha nas áreas: {cargos}
Os setores de interesse são: {setores}

Liste empresas que publicam vagas no Greenhouse (boards.greenhouse.io/v1/boards/SLUG/jobs).
Priorize empresas com operações no Brasil ou que contratem remotamente do Brasil.
Inclua empresas de médio e grande porte, com times de dados/tecnologia relevantes.

Para cada empresa, forneça o slug EXATO da URL do Greenhouse.
Exemplos de slugs corretos:
- Nubank → slug: "nubank"
- Stone → slug: "stone"
- Gympass → slug: "gympass"
- Cloudwalk → slug: "cloudwalk"
- Hotmart → slug: "hotmart"
- Mercado Livre → slug: "mercadolibre"
- Wildlife Studios → slug: "wildlifestudios"
- Nuvemshop → slug: "nuvemshop"

Retorne SOMENTE JSON, sem explicações:
[
  {{"empresa": "Nome", "plataforma": "greenhouse", "slug": "slug-exato", "setor": "Fintech"}},
  ...
]

Liste pelo menos 25 empresas variadas entre os setores solicitados."""


def _descobrir_empresas(setores: str, cargos: str, api_key: str | None = None) -> dict:
    import requests

    from agents.llm import get_client

    # api_key é ignorado: a chave vem do provedor configurado. Parâmetro mantido
    # para não quebrar chamadas existentes.
    client = get_client(use_cache=False)
    prompt = DISCOVER_PROMPT.format(setores=setores, cargos=cargos)

    sugestoes = client.generate_json(prompt, temperature=0.3)

    greenhouse = []
    validos, invalidos = [], []

    for item in sugestoes:
        slug = item.get("slug", "").strip().lower()
        plataforma = item.get("plataforma", "greenhouse").lower()
        empresa = item.get("empresa", slug)
        if not slug:
            continue

        # Lever API pública foi descontinuada — apenas Greenhouse via API REST
        if plataforma != "greenhouse":
            continue

        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("jobs", []))
                greenhouse.append(slug)
                validos.append({"empresa": empresa, "plataforma": "greenhouse", "slug": slug, "vagas": count})
            else:
                invalidos.append({"empresa": empresa, "slug": slug, "status": resp.status_code})
        except Exception:
            invalidos.append({"empresa": empresa, "slug": slug, "status": "timeout"})

    return {"greenhouse": greenhouse, "lever": [], "validos": validos, "invalidos": invalidos}


def step_3():
    st.title("Etapa 3 — Preferências de Busca")
    st.markdown("Configure os critérios de busca e as empresas que serão monitoradas.")

    saved = config.get("coleta") or {}

    from agents.llm import provedores_configurados

    # A descoberta por setor usa o LLM; só é ofertada se houver provedor com chave.
    tem_llm = bool(provedores_configurados())

    # ── Descoberta por setor ──────────────────────────────────────────────────
    with st.expander("✨ Descobrir empresas por setor (recomendado)", expanded=not saved.get("empresas_greenhouse") and not saved.get("empresas_lever")):
        st.markdown("Selecione os setores de interesse e a IA vai sugerir empresas que usam Greenhouse ou Lever, validando cada uma automaticamente.")

        saved_setores = saved.get("setores_interesse", [])
        if isinstance(saved_setores, str):
            saved_setores = [s.strip() for s in saved_setores.split(",") if s.strip()]

        setores_selecionados = st.multiselect(
            "Setores de interesse",
            options=SETORES_DISPONIVEIS,
            default=[s for s in saved_setores if s in SETORES_DISPONIVEIS],
            placeholder="Selecione um ou mais setores...",
        )
        setores_input = ", ".join(setores_selecionados)
        cargos_hint = ", ".join(saved.get("cargos_alvo", ["Data Engineer", "Analytics Engineer"]))

        if st.button("🔍 Descobrir empresas", type="primary", disabled=not setores_selecionados or not tem_llm):
            with st.spinner("Consultando Gemini e validando slugs... (pode levar 1-2 minutos)"):
                try:
                    resultado = _descobrir_empresas(setores_input, cargos_hint)
                    st.session_state["discover_result"] = resultado
                    st.session_state["discover_setores"] = setores_selecionados
                except Exception as exc:
                    st.error(f"Erro na descoberta: {exc}")

        if "discover_result" in st.session_state:
            res = st.session_state["discover_result"]
            validos = res["validos"]
            invalidos = res["invalidos"]

            st.success(f"✓ {len(validos)} empresas validadas | {len(invalidos)} slugs inválidos ignorados")

            if validos:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Greenhouse**")
                    for v in validos:
                        if v["plataforma"] == "greenhouse":
                            st.caption(f"✓ {v['empresa']} — {v['vagas']} vagas")
                with col2:
                    st.markdown("**Lever**")
                    for v in validos:
                        if v["plataforma"] == "lever":
                            st.caption(f"✓ {v['empresa']} — {v['vagas']} vagas")

                if st.button("Adicionar estas empresas às listas abaixo"):
                    existing_gh = set(saved.get("empresas_greenhouse", []))
                    existing_lv = set(saved.get("empresas_lever", []))
                    existing_gh.update(res["greenhouse"])
                    existing_lv.update(res["lever"])

                    cfg = config.load()
                    cfg.setdefault("coleta", {})["empresas_greenhouse"] = sorted(existing_gh)
                    cfg["coleta"]["empresas_lever"] = sorted(existing_lv)
                    cfg["coleta"]["setores_interesse"] = st.session_state["discover_setores"] if isinstance(st.session_state["discover_setores"], list) else [s.strip() for s in st.session_state["discover_setores"].split(",") if s.strip()]
                    config.save(cfg)
                    st.success(f"✓ {len(existing_gh)} Greenhouse + {len(existing_lv)} Lever salvas!")
                    st.session_state.pop("discover_result", None)
                    st.rerun()

    # ── Formulário de preferências ────────────────────────────────────────────
    saved = config.get("coleta") or {}

    with st.form("prefs_form"):
        cargos_raw = st.text_area(
            "Cargos alvo (um por linha)",
            value="\n".join(saved.get("cargos_alvo", ["Data Engineer", "Analytics Engineer", "BI Analyst"])),
            height=100,
        )

        col1, col2 = st.columns(2)
        with col1:
            localizacoes_raw = st.text_area(
                "Localizações aceitas (uma por linha)",
                value="\n".join(saved.get("localizacoes_alvo", ["São Paulo", "Remoto", "Remote"])),
                height=90,
            )
        with col2:
            modalidade = st.selectbox(
                "Modalidade preferida",
                options=["Remoto", "Híbrido", "Presencial", "Qualquer"],
                index=["Remoto", "Híbrido", "Presencial", "Qualquer"].index(
                    saved.get("modalidade_preferida", "Remoto")
                ),
            )

        salario = st.text_input(
            "Expectativa salarial",
            value=saved.get("salario_esperado", ""),
            placeholder="ex: R$ 8.000 - R$ 12.000",
        )

        palavras_bloqueadas_raw = st.text_area(
            "Palavras bloqueadas no título (uma por linha)",
            value="\n".join(saved.get("palavras_bloqueadas", ["Estágio", "Trainee", "Junior"])),
            height=75,
            help="Vagas com essas palavras no título serão ignoradas automaticamente",
        )

        st.markdown("**Thresholds de scoring (0–100)**")
        saved_scoring = config.get("scoring") or {}
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            threshold_excelente = st.slider(
                "Autoaprovação (score ≥)",
                min_value=70, max_value=100,
                value=int(saved_scoring.get("threshold_excelente", 85)),
                help="Vagas acima deste score são aprovadas automaticamente",
            )
        with col_s2:
            threshold_bom = st.slider(
                "Revisão manual (score ≥)",
                min_value=50, max_value=99,
                value=int(saved_scoring.get("threshold_bom", 70)),
                help="Vagas neste range entram na fila de aprovação manual",
            )

        st.markdown("**Empresas monitoradas**")
        greenhouse_raw = st.text_area(
            "Greenhouse (slugs, um por linha)",
            value="\n".join(saved.get("empresas_greenhouse", [])),
            height=130,
            help="Preenchido automaticamente pela descoberta acima, ou adicione manualmente",
        )
        st.caption("🔜 **Lever** — API pública descontinuada. Coleta via browser será implementada na Fase 4 (junto com LinkedIn).")
        lever_raw = "\n".join(saved.get("empresas_lever", []))

        submitted = st.form_submit_button("Salvar preferências", type="primary")

    if submitted:
        prefs = {
            "cargos_alvo": [c.strip() for c in cargos_raw.splitlines() if c.strip()],
            "localizacoes_alvo": [l.strip() for l in localizacoes_raw.splitlines() if l.strip()],
            "modalidade_preferida": modalidade,
            "salario_esperado": salario.strip(),
            "palavras_bloqueadas": [p.strip() for p in palavras_bloqueadas_raw.splitlines() if p.strip()],
            "empresas_greenhouse": [s.strip() for s in greenhouse_raw.splitlines() if s.strip()],
            "empresas_lever": [s.strip() for s in lever_raw.splitlines() if s.strip()],
            "setores_interesse": saved.get("setores_interesse", ""),
        }
        cfg = config.load()
        cfg["coleta"] = prefs
        cfg["scoring"] = {
            "threshold_excelente": threshold_excelente,
            "threshold_bom": threshold_bom,
        }
        config.save(cfg)
        st.success("✓ Preferências salvas!")
        st.session_state["prefs_ok"] = True

    # ── Dados pessoais para candidaturas ─────────────────────────────────────

    st.divider()
    st.markdown("**Dados pessoais para candidaturas automáticas**")
    st.caption("Informações usadas para preencher formulários de candidatura (ex: CPF obrigatório na XP Inc).")

    saved_pessoais = config.get("dados_pessoais") or {}

    OPCOES_GENERO = ["", "Homem cisgênero", "Mulher cisgênera", "Não binário", "Outro / Prefiro não informar"]
    OPCOES_ORIENTACAO = ["", "Heterossexual", "Homossexual", "Bissexual", "Pansexual", "Assexual", "Prefiro não informar"]
    OPCOES_RACA = ["", "Branca", "Parda", "Preta", "Amarela", "Indígena", "Prefiro não informar"]

    def _safe_index(opcoes, valor):
        return opcoes.index(valor) if valor in opcoes else 0

    with st.form("dados_pessoais_form"):
        cpf = st.text_input(
            "CPF (somente números)",
            value=saved_pessoais.get("cpf", ""),
            placeholder="00000000000",
            help="Obrigatório em candidaturas XP Inc e outras empresas",
        )
        st.markdown("**Autodeclaração de diversidade** — campos opcionais, usados quando exigidos pelo formulário")
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            genero = st.selectbox(
                "Identidade de gênero",
                options=OPCOES_GENERO,
                index=_safe_index(OPCOES_GENERO, saved_pessoais.get("diversidade", {}).get("genero", "")),
            )
        with col_d2:
            orientacao = st.selectbox(
                "Orientação sexual",
                options=OPCOES_ORIENTACAO,
                index=_safe_index(OPCOES_ORIENTACAO, saved_pessoais.get("diversidade", {}).get("orientacao", "")),
            )
        with col_d3:
            raca = st.selectbox(
                "Raça/etnia",
                options=OPCOES_RACA,
                index=_safe_index(OPCOES_RACA, saved_pessoais.get("diversidade", {}).get("raca", "")),
            )

        if st.form_submit_button("Salvar dados pessoais"):
            cfg = config.load()
            cfg["dados_pessoais"] = {
                "cpf": cpf.strip(),
                "diversidade": {
                    "genero": genero,
                    "orientacao": orientacao,
                    "raca": raca,
                },
            }
            config.save(cfg)
            st.success("✓ Dados pessoais salvos!")
            st.session_state["pessoais_ok"] = True

    col1, col2 = st.columns(2)
    with col1:
        st.button("← Voltar", on_click=_back, args=(3,))
    with col2:
        if st.session_state.get("prefs_ok") or saved:
            st.button("Próximo →", on_click=_advance, args=(3,), type="primary")


# ── Etapa 4: LinkedIn ────────────────────────────────────────────────────────

def step_4():
    st.title("Etapa 4 — LinkedIn Easy Apply")
    st.markdown(
        "Configure o LinkedIn para automatizar o Easy Apply (até **10 vagas/dia**). "
        "As credenciais ficam salvas localmente — nunca são enviadas a terceiros."
    )

    from applicators.linkedin import SESSION_PATH, check_session_valid, has_session

    session_valid = has_session()

    if session_valid:
        st.success("✓ Sessão LinkedIn configurada e salva.")
        if st.button("Verificar se sessão ainda é válida"):
            with st.spinner("Verificando..."):
                ok = check_session_valid()
            if ok:
                st.success("✓ Sessão válida!")
            else:
                st.warning("Sessão expirada. Faça login novamente.")
                import os
                if SESSION_PATH.exists():
                    os.remove(SESSION_PATH)
                st.rerun()
    else:
        st.info("Configure suas credenciais do LinkedIn para ativar o Easy Apply automático.")

    saved_li = config.get("linkedin") or {}
    with st.form("linkedin_form"):
        li_email = st.text_input("E-mail do LinkedIn", value=saved_li.get("email", ""))
        li_password = st.text_input("Senha do LinkedIn", type="password")
        submit_li = st.form_submit_button("Salvar e fazer login", type="primary" if not session_valid else "secondary")

    if submit_li and li_email and li_password:
        with st.spinner("Fazendo login no LinkedIn... (pode levar até 30 segundos)"):
            try:
                from applicators.linkedin import BLOCKED_MSG, login_and_save_session
                ok, msg = login_and_save_session(li_email, li_password, headless=True)
                if ok:
                    cfg = config.load()
                    cfg["linkedin"] = {"email": li_email}
                    config.save(cfg)
                    st.success(f"✓ {msg}")
                    st.rerun()
                elif msg == BLOCKED_MSG:
                    st.warning(
                        "O LinkedIn bloqueou o login automático (detecção de bot). "
                        "É necessário fazer o login com o **navegador visível** uma vez."
                    )
                    st.info(
                        "**Execute este comando no terminal** (digite `!` antes no prompt do Claude):\n\n"
                        "```\n"
                        ".venv\\Scripts\\python.exe -c \"\n"
                        "from applicators.linkedin import login_and_save_session\n"
                        f"ok, msg = login_and_save_session('{li_email}', 'SUA_SENHA', headless=False)\n"
                        "print(ok, msg)\n"
                        "\"\n"
                        "```\n\n"
                        "Uma janela do Chrome vai abrir, o login será preenchido automaticamente. "
                        "Se aparecer CAPTCHA ou 2FA, complete manualmente. "
                        "Após o feed do LinkedIn carregar, a sessão é salva e a janela fecha sozinha."
                    )
                else:
                    st.error(f"✗ {msg}")
            except Exception as exc:
                st.error(f"Erro: {exc}")

    st.divider()
    st.markdown("**Queries de busca para LinkedIn** — vagas buscadas automaticamente a cada 2h")
    saved_queries = config.get("linkedin", "search_queries") or ["Data Engineer", "Analytics Engineer", "BI Analyst"]
    queries_raw = st.text_area(
        "Cargos para buscar (um por linha)",
        value="\n".join(saved_queries) if isinstance(saved_queries, list) else saved_queries,
        height=100,
    )
    if st.button("Salvar queries"):
        cfg = config.load()
        cfg.setdefault("linkedin", {})["search_queries"] = [q.strip() for q in queries_raw.splitlines() if q.strip()]
        config.save(cfg)
        st.success("✓ Queries salvas!")

    col1, col2 = st.columns(2)
    with col1:
        st.button("← Voltar", on_click=_back, args=(4,))
    with col2:
        st.button("Próximo →" if session_valid else "Pular por ora →",
                  on_click=_advance, args=(4,), type="primary")


# ── Etapa 5: Gupy ────────────────────────────────────────────────────────────

def step_5():
    st.title("Etapa 5 — Gupy")
    st.markdown(
        "O **Gupy** é a plataforma de vagas mais usada no Brasil. "
        "Configure empresas-alvo pelo slug (ex.: `nubank`, `itau`) e palavras-chave de busca."
    )

    saved_gupy = config.get("coleta", "empresas_gupy") or []
    saved_keywords = config.get("gupy", "search_keywords") or ["Engenheiro de Dados", "Analista de BI", "Analytics Engineer"]

    with st.form("gupy_companies_form"):
        st.markdown("**Slugs de empresas no Gupy** — um por linha (ex.: `nubank`, `ifood`, `xpinc`)")
        slugs_raw = st.text_area(
            "Empresas (slugs)",
            value="\n".join(saved_gupy) if isinstance(saved_gupy, list) else "",
            height=120,
            help="Encontre o slug na URL da página de vagas: `empresa.gupy.io`",
        )
        st.markdown("**Busca geral** (vagas de qualquer empresa no Gupy)")
        keywords_raw = st.text_area(
            "Palavras-chave de busca — uma por linha",
            value="\n".join(saved_keywords) if isinstance(saved_keywords, list) else "",
            height=80,
        )
        if st.form_submit_button("Salvar configuração Gupy"):
            new_slugs = [s.strip().lower() for s in slugs_raw.splitlines() if s.strip()]
            new_keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]
            cfg = config.load()
            cfg.setdefault("coleta", {})["empresas_gupy"] = new_slugs
            cfg.setdefault("gupy", {})["search_keywords"] = new_keywords
            config.save(cfg)
            st.success(f"✓ {len(new_slugs)} empresa(s) e {len(new_keywords)} keyword(s) salvos!")

    if saved_gupy:
        st.info(f"Empresas configuradas: **{', '.join(saved_gupy[:5])}**{'…' if len(saved_gupy) > 5 else ''}")

    st.divider()
    st.caption("A coleta Gupy acontece automaticamente a cada 2 horas junto com Greenhouse e Lever.")

    col1, col2 = st.columns(2)
    with col1:
        st.button("← Voltar", on_click=_back, args=(5,))
    with col2:
        st.button("Próximo →" if saved_gupy or saved_keywords else "Pular por ora →",
                  on_click=_advance, args=(5,), type="primary")


# ── Etapa 6: E-mail ──────────────────────────────────────────────────────────

def step_6():
    st.title("Etapa 6 — Notificações por E-mail")
    st.markdown("Configure o envio de relatórios diários por e-mail. Pode ser pulado.")

    saved = config.get("email") or {}

    with st.form("email_form"):
        smtp_host = st.text_input("Servidor SMTP", value=saved.get("smtp_host", "smtp.gmail.com"))
        col1, col2 = st.columns(2)
        with col1:
            smtp_port = st.number_input("Porta", value=saved.get("smtp_port", 587), step=1)
        with col2:
            smtp_user = st.text_input("Usuário", value=saved.get("smtp_user", ""))
        smtp_pass = st.text_input("Senha / App Password", type="password")
        email_dest = st.text_input(
            "E-mail destino dos relatórios",
            value=saved.get("email_destino", ""),
            placeholder="seu@email.com",
        )

        col_test, col_save = st.columns(2)
        with col_save:
            saved_btn = st.form_submit_button("Salvar configuração")
        with col_test:
            test_btn = st.form_submit_button("Testar e-mail")

    if saved_btn or test_btn:
        if smtp_user and (smtp_pass or saved.get("smtp_pass")):
            email_config = {
                "smtp_host": smtp_host,
                "smtp_port": int(smtp_port),
                "smtp_user": smtp_user,
                "smtp_pass": smtp_pass or saved.get("smtp_pass", ""),
                "email_destino": email_dest,
            }
            cfg = config.load()
            cfg["email"] = email_config
            config.save(cfg)

            if test_btn:
                with st.spinner("Enviando e-mail de teste..."):
                    ok, msg = _test_smtp(email_config)
                if ok:
                    st.success("✓ E-mail de teste enviado!")
                else:
                    st.error(f"✗ Erro: {msg}")
            else:
                st.success("✓ Configuração de e-mail salva!")

    if saved and saved.get("smtp_user") and saved.get("smtp_pass"):
        if st.button("Enviar relatório de teste agora"):
            with st.spinner("Gerando e enviando relatório..."):
                try:
                    from notifications.email_sender import send_daily_report
                    ok, msg = send_daily_report(saved)
                    if ok:
                        st.success("✓ Relatório enviado!")
                    else:
                        st.error(f"✗ {msg}")
                except Exception as exc:
                    st.error(f"Erro: {exc}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("← Voltar", on_click=_back, args=(6,))
    with col2:
        st.button("Pular →", on_click=_advance, args=(6,))
    with col3:
        if saved:
            st.button("Próximo →", on_click=_advance, args=(6,), type="primary")


def _test_smtp(cfg: dict) -> tuple[bool, str]:
    import smtplib
    from email.message import EmailMessage

    try:
        msg = EmailMessage()
        msg["Subject"] = "AI Job Applier — Teste de configuração"
        msg["From"] = cfg["smtp_user"]
        msg["To"] = cfg.get("email_destino") or cfg["smtp_user"]
        msg.set_content("Configuração de e-mail funcionando corretamente!")

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=10) as server:
            server.starttls()
            server.login(cfg["smtp_user"], cfg["smtp_pass"])
            server.send_message(msg)

        return True, "E-mail enviado"
    except Exception as exc:
        return False, str(exc)


# ── Etapa 7: Conclusão ───────────────────────────────────────────────────────

def step_7():
    st.title("🎉 Configuração concluída!")
    st.balloons()

    resume_data = {}
    resume_path = DATA_DIR / "resume.json"
    if resume_path.exists():
        with open(resume_path, encoding="utf-8") as f:
            resume_data = json.load(f)

    companies = config.get_target_companies()

    from applicators.linkedin import has_session as li_has_session
    gupy_slugs = config.get("coleta", "empresas_gupy") or []
    li_session = li_has_session()
    email_cfg = config.get("email") or {}

    st.markdown("### Resumo da configuração")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Candidato", resume_data.get("nome", "—"))
        st.metric("Tecnologias", len(resume_data.get("tecnologias", [])))
    with col2:
        st.metric("Greenhouse", len(companies.get("greenhouse", [])))
        st.metric("Lever", len(companies.get("lever", [])))
    with col3:
        st.metric("Gupy", len(gupy_slugs))
        st.metric("LinkedIn", "✓ Ativo" if li_session else "— Não configurado")
    with col4:
        st.metric("E-mail", "✓ Ativo" if email_cfg.get("smtp_user") else "— Não configurado")
        dados_pessoais = config.get("dados_pessoais") or {}
        st.metric("CPF", "✓ OK" if dados_pessoais.get("cpf") else "⚠️ Faltando")

    st.markdown("### O que acontece agora?")
    st.markdown(
        """
- O **orquestrador** coleta vagas a cada 2 horas (Greenhouse, Lever, Gupy, LinkedIn)
- As vagas aparecem no **Dashboard** para aprovação manual ou automática
- Candidaturas são enviadas automaticamente para vagas aprovadas
- Um **relatório diário** é enviado às 8h se o e-mail estiver configurado
        """
    )

    if st.button("Ir para o Dashboard →", type="primary"):
        cfg = config.load()
        cfg["setup_completed"] = True
        cfg.pop("setup_progress", None)
        config.save(cfg)
        st.switch_page("pages/2_Dashboard.py")

    st.button("← Voltar", on_click=_back, args=(7,))


# ── Roteamento de etapas ─────────────────────────────────────────────────────

_init_session()
step = st.session_state.setup_step

st.markdown("# ⚙️ Configuração Inicial")
_render_progress(step)

STEP_HANDLERS = {
    1: step_1,
    2: step_2,
    3: step_3,
    4: step_4,
    5: step_5,
    6: step_6,
    7: step_7,
}

handler = STEP_HANDLERS.get(step, step_7)
handler()
