import json
import logging

from jobapplier import log, paths
from jobapplier.collectors.base import CollectedJob
from jobapplier.collectors.greenhouse import GreenhouseCollector
from jobapplier.collectors.lever import LeverCollector
from jobapplier.config import secrets
from jobapplier.config.manager import ConfigManager
from jobapplier.database.connection import DATABASE_URL, get_session
from jobapplier.database.models import Vaga
from jobapplier.database.repository import VagaRepository
from jobapplier.tempo import agora_utc

# structlog sobre a stdlib: os módulos seguem usando logging.getLogger e ganham
# run_id e saída em arquivo JSONL sem nenhuma alteração. Ver jobapplier/log.py.
log.configurar()
logger = logging.getLogger("orchestrator")

# Carrega .env antes de qualquer acesso a segredo ou ao banco.
secrets.carregar_env()


def persist_jobs(jobs: list[CollectedJob]) -> tuple[int, int]:
    vagas = []
    for job in jobs:
        vaga = Vaga(
            hash=job.hash,
            titulo=job.titulo,
            empresa=job.empresa,
            plataforma=job.plataforma,
            localizacao=job.localizacao,
            modalidade=job.modalidade,
            senioridade=job.senioridade,
            salario=job.salario,
            descricao=job.descricao,
            link=job.link,
            data_publicacao=job.data_publicacao,
            criado_em=agora_utc(),
        )
        vagas.append(vaga)

    with get_session() as session:
        repo = VagaRepository(session)
        inserted, skipped = repo.bulk_create_if_not_exists(vagas)

    return inserted, skipped


GUPY_DEFAULT_KEYWORDS = [
    "Analista de BI", "Analista de Dados", "Analista de Business Intelligence",
    "Data Analyst", "BI Analyst", "Data Engineer", "Engenheiro de Dados",
    "Analytics Engineer", "Data Scientist", "Cientista de Dados",
    "Power BI", "Tableau", "Looker", "Databricks", "dbt",
    "Engenheiro de Analytics", "Especialista em Dados",
]


def _executar_coleta() -> dict:
    config = ConfigManager()
    companies = config.get_target_companies()

    greenhouse_slugs: list[str] = companies.get("greenhouse", [])
    lever_slugs: list[str] = companies.get("lever", [])

    all_jobs: list[CollectedJob] = []

    # Greenhouse: sempre usa DEFAULT_SLUGS embutida + slugs extras configurados
    from jobapplier.collectors.greenhouse import DEFAULT_SLUGS as GH_DEFAULT_SLUGS
    all_gh_slugs = list(set(GH_DEFAULT_SLUGS) | set(greenhouse_slugs))
    logger.info("Coletando Greenhouse: %d empresas (padrão + configuradas)", len(all_gh_slugs))
    gc = GreenhouseCollector()
    all_jobs.extend(gc.collect_all(all_gh_slugs))

    if lever_slugs:
        logger.info("Coletando Lever: %s", lever_slugs)
        lc = LeverCollector()
        all_jobs.extend(lc.collect_all(lever_slugs))

    # Gupy — sempre roda: usa keywords configuradas ou padrão
    try:
        from jobapplier.collectors.gupy import GupyCollector
        gc_gupy = GupyCollector()
        gupy_slugs: list[str] = config.get("coleta", "empresas_gupy") or []
        gupy_keywords: list[str] = config.get("gupy", "search_keywords") or []
        effective_keywords = gupy_keywords if gupy_keywords else GUPY_DEFAULT_KEYWORDS
        if gupy_slugs:
            logger.info("Coletando Gupy empresas: %s", gupy_slugs)
            all_jobs.extend(gc_gupy.collect_all(gupy_slugs))
        logger.info("Coletando Gupy por busca: %d keywords", len(effective_keywords))
        all_jobs.extend(gc_gupy.collect_by_search(effective_keywords, max_per_keyword=30))
    except Exception as exc:
        logger.warning("Coleta Gupy ignorada: %s", exc)

    # LinkedIn (se sessão configurada)
    try:
        from jobapplier.applicators.linkedin import collect_jobs as li_collect_jobs
        from jobapplier.applicators.linkedin import has_session
        if has_session():
            li_queries = config.get("linkedin", "search_queries") or ["Data Engineer", "Analytics Engineer"]
            if isinstance(li_queries, str):
                li_queries = [li_queries]
            logger.info("Coletando LinkedIn: %s", li_queries)
            raw_jobs = li_collect_jobs(li_queries, location="São Paulo, BR", max_per_query=25)
            for j in raw_jobs:
                all_jobs.append(CollectedJob(
                    titulo=j["titulo"],
                    empresa=j["empresa"],
                    plataforma="linkedin",
                    link=j["link"],
                    descricao=j.get("descricao", ""),
                    localizacao=j.get("localizacao"),
                ))
            logger.info("LinkedIn: %d vagas coletadas", len(raw_jobs))
    except Exception as exc:
        logger.warning("Coleta LinkedIn ignorada: %s", exc)

    if not all_jobs:
        logger.warning("Nenhuma empresa configurada para coleta. Configure no wizard.")
        return {"coletadas": 0, "inseridas": 0, "duplicadas": 0}

    logger.info("Total coletado: %d vagas", len(all_jobs))

    inserted, skipped = persist_jobs(all_jobs)
    logger.info("Inseridas: %d | Duplicatas ignoradas: %d", inserted, skipped)
    return {"coletadas": len(all_jobs), "inseridas": inserted, "duplicadas": skipped}


def run_collection():
    """Esteira 1 — coleta. Envolvida por log.execucao para ter run_id e registro."""
    with log.execucao("coleta") as run_id:
        metricas = _executar_coleta()
        log.registrar_metricas(run_id, metricas)


def _executar_pipeline() -> dict:
    """Módulos 4A → 2 → 4B → 3: filtra, normaliza e pontua vagas novas."""
    config = ConfigManager()
    api_key = secrets.gemini_api_key()

    if not api_key:
        logger.warning("Nenhum provedor de LLM configurado. Pipeline ignorado.")
        return {}

    resume_path = paths.RESUME_JSON
    if not resume_path.exists():
        logger.warning("Currículo não encontrado em %s. Pipeline ignorado.", resume_path)
        return {}

    resume_json = json.loads(resume_path.read_text(encoding="utf-8"))
    coleta_config = config.get("coleta") or {}
    scoring_config = config.get("scoring") or {}
    threshold_excelente = int(scoring_config.get("threshold_excelente", 65))
    threshold_bom = int(scoring_config.get("threshold_bom", 45))

    from jobapplier.agents.normalizer import normalize
    from jobapplier.agents.scorer import score
    from jobapplier.filters import post_filter, pre_filter
    from jobapplier.llm import get_client

    client = get_client(config=config, use_cache=True)

    with get_session() as session:
        vagas_novas = (
            session.query(Vaga)
            .filter(Vaga.status == "nova")
            .order_by(Vaga.criado_em.desc())
            .all()
        )

    if not vagas_novas:
        logger.info("Nenhuma vaga nova para processar.")
        return {"vagas_novas": 0}

    logger.info("Pipeline iniciado: %d vagas novas", len(vagas_novas))
    stats = {"filtradas_4a": 0, "normalizadas": 0, "filtradas_4b": 0, "pontuadas": 0, "aprovadas": 0, "pendentes": 0, "rejeitadas": 0}

    for vaga in vagas_novas:
        # ── Módulo 4A: filtro pré-normalização ──────────────────────────────
        passou, motivo = pre_filter.apply(vaga, coleta_config)
        if not passou:
            logger.debug("4A rejeitou id=%d: %s", vaga.id, motivo)
            stats["filtradas_4a"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "filtrada_4a"})
            continue

        # ── Módulo 2: normalização via Gemini ───────────────────────────────
        normalizado = normalize(vaga, client)
        if normalizado:
            stats["normalizadas"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update(
                    {"normalizado_json": normalizado}
                )
            # Atualiza objeto local para usar nos filtros seguintes
            vaga.normalizado_json = normalizado
        else:
            logger.warning("Normalização falhou para vaga id=%d, pulando.", vaga.id)
            continue

        # ── Módulo 4B: filtro pós-normalização ──────────────────────────────
        passou, motivo = post_filter.apply(normalizado, coleta_config)
        if not passou:
            logger.debug("4B rejeitou id=%d: %s", vaga.id, motivo)
            stats["filtradas_4b"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "filtrada_4b"})
            continue

        # ── Módulo 3: scoring IA ─────────────────────────────────────────────
        resultado = score(vaga, resume_json, client)
        if not resultado:
            logger.warning("Scoring falhou para vaga id=%d, pulando.", vaga.id)
            continue

        vaga_score = resultado["score"]
        stats["pontuadas"] += 1

        if vaga_score >= threshold_excelente:
            novo_status = "aprovada"
            stats["aprovadas"] += 1
        elif vaga_score >= threshold_bom:
            novo_status = "pendente"
            stats["pendentes"] += 1
        else:
            novo_status = "rejeitada"
            stats["rejeitadas"] += 1

        with get_session() as session:
            session.query(Vaga).filter(Vaga.id == vaga.id).update({
                "score": vaga_score,
                "score_breakdown_json": resultado,
                "status": novo_status,
            })

        logger.info(
            "Vaga id=%d '%s' → score=%.0f status=%s",
            vaga.id, vaga.titulo[:50], vaga_score, novo_status,
        )

    logger.info(
        "Pipeline concluído: filtradas_4a=%d normalizadas=%d filtradas_4b=%d "
        "pontuadas=%d (aprovadas=%d pendentes=%d rejeitadas=%d)",
        stats["filtradas_4a"], stats["normalizadas"], stats["filtradas_4b"],
        stats["pontuadas"], stats["aprovadas"], stats["pendentes"], stats["rejeitadas"],
    )
    return {"vagas_novas": len(vagas_novas), **stats}


def run_pipeline():
    """Esteira 2 — filtros e scoring."""
    with log.execucao("pipeline") as run_id:
        log.registrar_metricas(run_id, _executar_pipeline())


def _executar_candidaturas() -> dict:
    """Módulos 12 → 6 → 13: otimiza currículo, gera cover letter e candidata vagas aprovadas.

    Só processa vagas com status 'aprovada'. Vagas 'pendente' aguardam revisão
    humana na página Vagas — o agendador não decide por você. Para voltar ao
    comportamento antigo, defina risco.auto_aplicar_pendentes = true na config.
    """
    config = ConfigManager()
    api_key = secrets.gemini_api_key()

    if not api_key:
        logger.warning("Nenhum provedor de LLM configurado.")
        return {}

    resume_path = paths.RESUME_JSON
    resumes_dir = paths.RESUMES
    cover_letters_dir = paths.COVER_LETTERS
    cover_letters_dir.mkdir(parents=True, exist_ok=True)

    if not resume_path.exists():
        logger.warning("Currículo não encontrado.")
        return {}

    resume_json = json.loads(resume_path.read_text(encoding="utf-8"))

    from jobapplier.agents.cover_letter import generate as gen_cover_letter
    from jobapplier.agents.resume_optimizer import optimize
    from jobapplier.applicators import base as applicators
    from jobapplier.database.models import Candidatura
    from jobapplier.generators.pdf import generate_pdf
    from jobapplier.llm import get_client
    from jobapplier.safety import guard

    client = get_client(config=config, use_cache=True)

    cfg = config.load()
    risco_cfg = cfg.get("risco") or {}

    # Devolve para a fila vagas travadas em 'em_andamento' por crash anterior.
    guard.liberar_orfaos()

    status_alvo = ["aprovada"]
    if risco_cfg.get("auto_aplicar_pendentes"):
        status_alvo.append("pendente")
        logger.warning(
            "auto_aplicar_pendentes=true — candidatando sem revisão humana."
        )

    with get_session() as session:
        vagas_aprovadas = (
            session.query(Vaga)
            .filter(Vaga.status.in_(status_alvo))
            .order_by(Vaga.score.desc())
            .all()
        )

    if not vagas_aprovadas:
        logger.info("Nenhuma vaga aguardando candidatura (status: %s).", status_alvo)
        return {"fila": 0}

    logger.info("Fila de candidatura: %d vagas (status: %s)", len(vagas_aprovadas), status_alvo)

    processadas_neste_ciclo = 0
    desfechos = {'enviada': 0, 'perguntas_pendentes': 0, 'erro': 0,
                 'sem_automacao': 0, 'duplicada': 0, 'postergada': 0}

    for vaga in vagas_aprovadas:
        plataforma = (vaga.plataforma or "").lower()

        # ── Guarda 1: plataforma sem automação ───────────────────────────────
        if not applicators.suportada(plataforma):
            logger.info(
                "Vaga id=%d ignorada: plataforma '%s' sem automação implementada.",
                vaga.id, plataforma,
            )
            desfechos["sem_automacao"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update(
                    {"status": "sem_automacao"}
                )
            continue

        # ── Guarda 2: nunca candidatar duas vezes ────────────────────────────
        if guard.ja_candidatado(vaga.id):
            logger.info("Vaga id=%d já tem candidatura enviada — pulando.", vaga.id)
            desfechos["duplicada"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update(
                    {"status": "candidatada"}
                )
            continue

        # ── Guarda 3: limite diário e disjuntor ──────────────────────────────
        # Antes de gastar token Gemini ou abrir browser. Status fica intacto:
        # a vaga volta a ser elegível no próximo ciclo.
        pode, motivo = guard.checar_limite(plataforma, cfg)
        if not pode:
            logger.warning("Vaga id=%d postergada: %s", vaga.id, motivo)
            desfechos["postergada"] += 1
            continue

        # ── Espera humana entre candidaturas ─────────────────────────────────
        if processadas_neste_ciclo > 0:
            guard.espera_humana(cfg, contexto=plataforma)

        logger.info("Processando vaga id=%d '%s'", vaga.id, vaga.titulo[:50])
        processadas_neste_ciclo += 1

        # Marca como em andamento
        with get_session() as session:
            session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "em_andamento"})

        try:
            # ── Módulo 12: Seleciona e otimiza perfil base ────────────────────
            bd_json = vaga.score_breakdown_json or {}
            perfil_sugerido_raw = bd_json.get("perfil_base_sugerido", "data_engineer")
            perfil = perfil_sugerido_raw.split("|")[0].strip()

            base_path = resumes_dir / f"resume_base_{perfil}.json"
            if not base_path.exists():
                perfil = "data_engineer"
                base_path = resumes_dir / f"resume_base_{perfil}.json"

            if base_path.exists():
                base_profile = json.loads(base_path.read_text(encoding="utf-8"))
            else:
                base_profile = resume_json

            logger.info("Otimizando currículo (perfil=%s)...", perfil)
            resultado_opt = optimize(base_profile, vaga, client)
            perfil_otimizado = resultado_opt["perfil_otimizado"]
            ats_antes = resultado_opt["ats_antes"]
            ats_depois = resultado_opt["ats_depois"]
            keywords_adicionadas = resultado_opt["keywords_adicionadas"]

            logger.info("ATS: %.0f%% -> %.0f%% (+%d keywords)", ats_antes, ats_depois, len(keywords_adicionadas))

            # ── Gera PDF ──────────────────────────────────────────────────────
            pdf_path = resumes_dir / f"resume_{perfil}_{vaga.id}.pdf"
            generate_pdf(perfil_otimizado, pdf_path)

            # ── Módulo 6: Cover letter ────────────────────────────────────────
            logger.info("Gerando cover letter...")
            cover_letter_text = gen_cover_letter(resume_json, vaga, client)
            cover_letter_path = None
            if cover_letter_text:
                cover_letter_path = cover_letters_dir / f"cover_letter_{vaga.id}.txt"
                cover_letter_path.write_text(cover_letter_text, encoding="utf-8")

            # ── Módulo 13: Candidatura via plataforma detectada ───────────────
            # O registry é a fonte única de verdade: 'plataforma' já passou por
            # applicators.suportada() na guarda 1, então obter() não falha aqui.
            logger.info("Enviando candidatura via %s...", plataforma)
            resultado_app = applicators.obter(plataforma)(
                vaga, resume_json, pdf_path, cover_letter_text
            )

            status_cand = resultado_app["status"]
            desfechos[status_cand] = desfechos.get(status_cand, 0) + 1
            if status_cand == "enviada":
                novo_status_vaga = "candidatada"
                logger.info("Candidatura enviada com sucesso!")
            elif status_cand == "perguntas_pendentes":
                novo_status_vaga = "aguardando_resposta"
                logger.warning("Perguntas pendentes: %s", resultado_app["perguntas_manuais"])
            else:
                novo_status_vaga = "erro"
                logger.error("Erro na candidatura: %s", resultado_app["mensagem"])

            # ── Persiste Candidatura ──────────────────────────────────────────
            with get_session() as session:
                perguntas = resultado_app.get("perguntas_manuais", [])
                erro_texto = None
                if status_cand == "perguntas_pendentes" and perguntas:
                    erro_texto = json.dumps(perguntas, ensure_ascii=False)
                elif status_cand != "enviada":
                    erro_texto = resultado_app.get("mensagem", "")

                cand = Candidatura(
                    vaga_id=vaga.id,
                    status=status_cand,
                    perfil_base=perfil,
                    curriculo_path=str(pdf_path),
                    ats_score_original=ats_antes,
                    ats_score_otimizado=ats_depois,
                    keywords_adicionadas=keywords_adicionadas,
                    cover_letter_path=str(cover_letter_path) if cover_letter_path else None,
                    erro=erro_texto,
                )
                session.add(cand)
                session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": novo_status_vaga})

        except Exception as exc:
            logger.error("Erro ao processar vaga id=%d: %s", vaga.id, exc)
            desfechos["erro"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "erro"})
                cand = Candidatura(
                    vaga_id=vaga.id,
                    status="erro",
                    erro=str(exc),
                )
                session.add(cand)

    logger.info("Ciclo de candidaturas: %s", desfechos)
    return {"fila": len(vagas_aprovadas), "processadas": processadas_neste_ciclo,
            **desfechos}


def run_applications():
    """Esteira 3 — otimização de currículo, cover letter e candidatura."""
    with log.execucao("candidaturas") as run_id:
        log.registrar_metricas(run_id, _executar_candidaturas())


def main():
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.blocking import BlockingScheduler

        jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}

        # max_instances=1: nenhum job pode rodar concorrente consigo mesmo. Sem
        # isso, uma coleta lenta ou um Playwright travado empilha execuções
        # sobrepostas — e liberar_orfaos() em run_applications passa a ser
        # incorreto, porque haveria outra execução legitimamente 'em_andamento'.
        # coalesce=True: após downtime, executa uma vez em vez de reprocessar
        # toda a fila de disparos perdidos.
        defaults = {
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 600,
        }
        scheduler = BlockingScheduler(
            jobstores=jobstores,
            timezone="America/Sao_Paulo",
            job_defaults=defaults,
        )

        scheduler.add_job(
            run_collection,
            "interval",
            hours=2,
            id="collect_jobs",
            replace_existing=True,
        )

        scheduler.add_job(
            run_pipeline,
            "interval",
            hours=2,
            minutes=5,
            id="run_pipeline",
            replace_existing=True,
        )

        scheduler.add_job(
            run_applications,
            "interval",
            hours=2,
            minutes=15,
            id="run_applications",
            replace_existing=True,
        )

        def _send_daily_report():
            cfg = ConfigManager()
            email_cfg = dict(cfg.get("email") or {})

            # Credenciais do ambiente têm precedência sobre o JSON.
            smtp_user, smtp_pass = secrets.smtp_credenciais()
            if smtp_user:
                email_cfg["smtp_user"] = smtp_user
            if smtp_pass:
                email_cfg["smtp_pass"] = smtp_pass
            email_cfg.setdefault("smtp_host", "smtp.gmail.com")
            email_cfg.setdefault("smtp_port", 587)

            if not (email_cfg.get("smtp_user") and email_cfg.get("smtp_pass")):
                logger.debug("Relatório diário ignorado: SMTP não configurado.")
                return

            from jobapplier.notifications.email_sender import send_daily_report
            ok, msg = send_daily_report(email_cfg)
            if ok:
                logger.info("Relatório diário enviado.")
            else:
                logger.warning("Falha no relatório diário: %s", msg)

        scheduler.add_job(
            _send_daily_report,
            "cron",
            hour=8,
            minute=0,
            id="daily_report",
            replace_existing=True,
        )

        def _backup_diario():
            """Dump do Postgres. O histórico de candidaturas não é recriável."""
            import subprocess
            import sys as _sys

            with log.execucao("backup", persistir=False):
                script = paths.RAIZ / "scripts" / "backup.py"
                r = subprocess.run(
                    [_sys.executable, str(script)],
                    cwd=paths.RAIZ, capture_output=True, text=True, check=False,
                )
                if r.returncode == 0:
                    logger.info("Backup concluído: %s", r.stdout.strip().splitlines()[-1:])
                else:
                    logger.error("Backup FALHOU: %s", (r.stderr or r.stdout)[-500:])

        scheduler.add_job(
            _backup_diario,
            "cron",
            hour=3,
            minute=30,
            id="backup_diario",
            replace_existing=True,
        )

        logger.info("Orquestrador iniciado. Coleta a cada 2 horas.")
        logger.info("Executando coleta inicial...")
        run_collection()

        logger.info("Executando pipeline de inteligência inicial...")
        run_pipeline()

        scheduler.start()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Orquestrador encerrado.")


if __name__ == "__main__":
    main()
