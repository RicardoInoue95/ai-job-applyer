import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import structlog

from config.manager import ConfigManager
from collectors.greenhouse import GreenhouseCollector
from collectors.lever import LeverCollector
from collectors.base import CollectedJob
from database.connection import get_session, DATABASE_URL
from database.models import Vaga
from database.repository import VagaRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("orchestrator")


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
            criado_em=datetime.utcnow(),
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


def run_collection():
    config = ConfigManager()
    companies = config.get_target_companies()

    greenhouse_slugs: list[str] = companies.get("greenhouse", [])
    lever_slugs: list[str] = companies.get("lever", [])

    all_jobs: list[CollectedJob] = []

    # Greenhouse: sempre usa DEFAULT_SLUGS embutida + slugs extras configurados
    from collectors.greenhouse import DEFAULT_SLUGS as GH_DEFAULT_SLUGS
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
        from collectors.gupy import GupyCollector
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
        from applicators.linkedin import has_session, collect_jobs as li_collect_jobs
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
        return

    logger.info("Total coletado: %d vagas", len(all_jobs))

    inserted, skipped = persist_jobs(all_jobs)
    logger.info("Inseridas: %d | Duplicatas ignoradas: %d", inserted, skipped)


def run_pipeline():
    """Módulos 4A → 2 → 4B → 3: filtra, normaliza e pontua vagas novas."""
    config = ConfigManager()
    api_key = config.get_gemini_key()

    if not api_key:
        logger.warning("Gemini API key não configurada. Pipeline de inteligência ignorado.")
        return

    resume_path = Path("data/resume.json")
    if not resume_path.exists():
        logger.warning("Currículo não encontrado em data/resume.json. Pipeline ignorado.")
        return

    resume_json = json.loads(resume_path.read_text(encoding="utf-8"))
    coleta_config = config.get("coleta") or {}
    scoring_config = config.get("scoring") or {}
    threshold_excelente = int(scoring_config.get("threshold_excelente", 65))
    threshold_bom = int(scoring_config.get("threshold_bom", 45))

    from agents.gemini_client import GeminiClient
    from agents.normalizer import normalize
    from agents.scorer import score
    from filters import pre_filter, post_filter

    client = GeminiClient(api_key=api_key, use_cache=True)

    with get_session() as session:
        vagas_novas = (
            session.query(Vaga)
            .filter(Vaga.status == "nova")
            .order_by(Vaga.criado_em.desc())
            .all()
        )

    if not vagas_novas:
        logger.info("Nenhuma vaga nova para processar.")
        return

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


def run_applications():
    """Módulos 12 → 6 → 13: otimiza currículo, gera cover letter e candidata vagas aprovadas."""
    config = ConfigManager()
    api_key = config.get_gemini_key()

    if not api_key:
        logger.warning("Gemini API key não configurada.")
        return

    resume_path = Path("data/resume.json")
    resumes_dir = Path("data/resumes")
    cover_letters_dir = Path("data/cover_letters")
    cover_letters_dir.mkdir(parents=True, exist_ok=True)

    if not resume_path.exists():
        logger.warning("Currículo não encontrado.")
        return

    resume_json = json.loads(resume_path.read_text(encoding="utf-8"))

    from agents.gemini_client import GeminiClient
    from agents.resume_optimizer import optimize
    from agents.cover_letter import generate as gen_cover_letter
    from generators.pdf import generate_pdf
    from applicators import greenhouse as gh_applicator
    import applicators.linkedin as li_applicator
    import applicators.gupy as gupy_applicator
    from database.models import Candidatura

    client = GeminiClient(api_key=api_key, use_cache=True)

    with get_session() as session:
        vagas_aprovadas = (
            session.query(Vaga)
            .filter(Vaga.status.in_(["aprovada", "pendente"]))
            .order_by(Vaga.score.desc())
            .all()
        )

    if not vagas_aprovadas:
        logger.info("Nenhuma vaga aprovada ou pendente aguardando candidatura.")
        return

    logger.info("Candidatando %d vagas (aprovadas + pendentes)...", len(vagas_aprovadas))

    for vaga in vagas_aprovadas:
        logger.info("Processando vaga id=%d '%s'", vaga.id, vaga.titulo[:50])

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
            plataforma = (vaga.plataforma or "").lower()
            if plataforma == "linkedin":
                logger.info("Enviando candidatura via LinkedIn Easy Apply...")
                resultado_app = li_applicator.apply(vaga, resume_json, pdf_path, cover_letter_text)
            elif plataforma == "gupy":
                logger.info("Enviando candidatura via Gupy...")
                resultado_app = gupy_applicator.apply(vaga, resume_json, pdf_path, cover_letter_text)
            else:
                logger.info("Enviando candidatura via Greenhouse...")
                resultado_app = gh_applicator.apply(vaga, resume_json, pdf_path, cover_letter_text)

            status_cand = resultado_app["status"]
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
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update({"status": "erro"})
                cand = Candidatura(
                    vaga_id=vaga.id,
                    status="erro",
                    erro=str(exc),
                )
                session.add(cand)


def main():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
        scheduler = BlockingScheduler(jobstores=jobstores, timezone="America/Sao_Paulo")

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
            email_cfg = cfg.get("email")
            if email_cfg and email_cfg.get("smtp_user") and email_cfg.get("smtp_pass"):
                from notifications.email_sender import send_daily_report
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
