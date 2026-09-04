import json
import logging
import time

from jobapplier import dossie, log, paths
from jobapplier.collectors.base import CollectedJob
from jobapplier.collectors.greenhouse import GreenhouseCollector
from jobapplier.collectors.lever import LeverCollector
from jobapplier.config import secrets
from jobapplier.config.manager import ConfigManager
from jobapplier.database.connection import DATABASE_URL, get_session
from jobapplier.database.models import Vaga
from jobapplier.database.repository import CandidaturaRepository, VagaRepository
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
            fonte_vaga_id=job.fonte_vaga_id,
            fonte_empresa_id=job.fonte_empresa_id,
            content_hash=job.content_hash,
            criado_em=agora_utc(),
        )
        vagas.append(vaga)

    with get_session() as session:
        repo = VagaRepository(session)
        inserted, skipped = repo.bulk_create_if_not_exists(vagas)
        # As ignoradas já existiam: registra que continuam publicadas, para que
        # `encerrada_em` possa ser inferido depois.
        repo.marcar_revistas([v for v in vagas if v not in session.new])

    return inserted, skipped


#: Status que colocam a vaga na frente do usuário. Só eles são varridos por
#: `varrer_encerradas`: vaga já descartada ou já candidatada não ganha nada em
#: ser reclassificada, e cada checagem é uma requisição em board de terceiro.
STATUS_NA_FILA = ("aprovada", "pendente", "pronta_envio_manual",
                  "pronta_para_revisao", "aguardando_revisao", "adiada")

#: Status da candidatura → status da vaga. 'aguardando_revisao' substitui o
#: antigo 'aguardando_resposta', que sugeria espera pela empresa quando na
#: verdade quem o sistema espera é VOCÊ.
MAPA_STATUS_VAGA = {
    "enviada_confirmada": "candidatada",
    "revisao_manual": "aguardando_revisao",
    "falha_automacao": "erro",
    # Não é erro: o formulário foi preenchido e parou num código que só o
    # candidato tem. A vaga volta para a fila de revisão, onde
    # `scripts/finalizar.py` a retoma numa sessão assistida.
    "aguardando_verificacao": "pronta_para_revisao",
    "simulada": "pronta_para_revisao",
}


GUPY_DEFAULT_KEYWORDS = [
    "Analista de BI", "Analista de Dados", "Analista de Business Intelligence",
    "Data Analyst", "BI Analyst", "Data Engineer", "Engenheiro de Dados",
    "Analytics Engineer", "Data Scientist", "Cientista de Dados",
    "Power BI", "Tableau", "Looker", "Databricks", "dbt",
    "Engenheiro de Analytics", "Especialista em Dados",
]


def _executar_coleta() -> dict:
    config = ConfigManager()
    greenhouse_slugs: list[str] = config.empresas("greenhouse")
    lever_slugs: list[str] = config.empresas("lever")

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
        gupy_slugs: list[str] = config.empresas("gupy")
        gupy_keywords: list[str] = config.keywords("gupy")
        effective_keywords = gupy_keywords if gupy_keywords else GUPY_DEFAULT_KEYWORDS
        if gupy_slugs:
            logger.info("Coletando Gupy empresas: %s", gupy_slugs)
            all_jobs.extend(gc_gupy.collect_all(gupy_slugs))
        logger.info("Coletando Gupy por busca: %d keywords", len(effective_keywords))
        all_jobs.extend(gc_gupy.collect_by_search(effective_keywords, max_per_keyword=30))
    except Exception as exc:
        logger.warning("Coleta Gupy ignorada: %s", exc)

    # inhire — ATS brasileiro, coleta por empresa
    #
    # A lista não traz descrição, e sem descrição a vaga não passa no filtro 4A.
    # Buscar a descrição de todas custaria uma requisição por vaga (126 numa só
    # empresa), então o filtro por título vem antes: só o que interessa é
    # detalhado. É a mesma economia do pipeline — gastar o caro o mais tarde
    # possível.
    try:
        from jobapplier.collectors.inhire import InhireCollector
        from jobapplier.filters import pre_filter

        inhire_slugs: list[str] = config.empresas("inhire")
        if inhire_slugs:
            coletor_inhire = InhireCollector()
            coleta_cfg = config.get("coleta") or {}
            logger.info("Coletando inhire: %s", inhire_slugs)
            for slug in inhire_slugs:
                vagas_inhire = coletor_inhire.collect(slug)
                interessantes = [
                    v for v in vagas_inhire
                    if pre_filter.apply(
                        {"titulo": v.titulo, "descricao": "", "empresa": v.empresa,
                         "localizacao": v.localizacao or ""}, coleta_cfg)[0]
                ]
                logger.info("inhire '%s': %d de %d passam pelo título.",
                            slug, len(interessantes), len(vagas_inhire))
                coletor_inhire.detalhar(interessantes, slug)
                all_jobs.extend(v for v in interessantes if v.descricao)
    except Exception as exc:
        logger.warning("Coleta inhire ignorada: %s", exc)

    # LinkedIn (se sessão configurada)
    try:
        from jobapplier.applicators.linkedin import collect_jobs as li_collect_jobs
        from jobapplier.applicators.linkedin import has_session
        if has_session():
            li_queries = config.keywords("linkedin") or ["Data Engineer", "Analytics Engineer"]
            if isinstance(li_queries, str):
                li_queries = [li_queries]
            logger.info("Coletando LinkedIn: %s", li_queries)
            raw_jobs = li_collect_jobs(li_queries, location="São Paulo, BR", max_per_query=25)
            descartadas = 0
            for j in raw_jobs:
                # Vaga sem título real ou sem descrição não tem como ser
                # avaliada: o filtro 4A e o scorer trabalham sobre o texto.
                # Gravá-la só produz linha morta no banco — foi assim que 200
                # vagas do LinkedIn viraram 192 'filtrada_4a' e 8 'erro'.
                if j.get("titulo_provisorio") or not (j.get("descricao") or "").strip():
                    descartadas += 1
                    continue
                all_jobs.append(CollectedJob(
                    titulo=j["titulo"],
                    empresa=j["empresa"],
                    plataforma="linkedin",
                    link=j["link"],
                    descricao=j.get("descricao", ""),
                    localizacao=j.get("localizacao"),
                    fonte_vaga_id=j.get("fonte_vaga_id"),
                ))
            logger.info("LinkedIn: %d vagas aproveitadas, %d descartadas por "
                        "falta de título ou descrição.",
                        len(raw_jobs) - descartadas, descartadas)
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


def varrer_encerradas():
    """Tira da fila as vagas que não existem mais.

    Uma amostra de 40 vagas do Greenhouse na fila devolveu **22% encerradas**, e
    as 8 da inhire estavam todas mortas. Sem esta passada, o usuário escolhe o
    cartão, lê o dossiê, decide candidatar — e leva 404. Fila com uma em cada
    cinco morta não é fila, é sorteio.

    Roda depois da coleta de propósito: é quando a fila acabou de crescer, e é o
    único momento em que gastar centenas de requisições em board de terceiro se
    justifica. `INDETERMINADA` nunca encerra — erro de rede não mata vaga viva.
    """
    from jobapplier.vigencia import Vigencia, checar

    marcadas = 0
    with log.execucao("varredura", persistir=False):
        with get_session() as sessao:
            vagas = sessao.query(Vaga).filter(Vaga.status.in_(STATUS_NA_FILA)).all()
            for vaga in vagas:
                sessao.expunge(vaga)

        encerradas = []
        for vaga in vagas:
            estado, motivo = checar(vaga)
            if estado is Vigencia.ENCERRADA:
                encerradas.append((vaga.id, motivo))
            time.sleep(0.4)   # não martelar board de terceiro

        with get_session() as sessao:
            for vaga_id, _ in encerradas:
                registro = sessao.get(Vaga, vaga_id)
                if registro is not None:
                    registro.status = "encerrada"
                    marcadas += 1

        logger.info("Varredura: %d de %d vagas da fila estavam encerradas.",
                    marcadas, len(vagas))
    return {"fila": len(vagas), "encerradas": marcadas}


def _obter_cliente_llm(config):
    """Cliente de LLM, ou None para o caminho determinístico.

    Sem provedor configurado o pipeline NÃO para: normalização e scoring têm
    implementação determinística em `agents.extracao`, que é onde estava o
    grosso do custo de API — milhares de vagas por ciclo. O sistema roda
    inteiro sem gastar um centavo.
    """
    from jobapplier.llm import LLMError, get_client

    if (config.get("llm") or {}).get("modo_sem_api"):
        logger.info("modo_sem_api ativo: usando extração determinística.")
        return None
    try:
        return get_client(config=config, use_cache=True)
    except LLMError as exc:
        logger.info(
            "Sem provedor de LLM (%s). Seguindo pelo caminho determinístico, "
            "sem custo. Para usar um modelo, configure uma chave no .env ou "
            "rode um local com: ollama serve",
            exc,
        )
        return None


def _executar_pipeline() -> dict:
    """Módulos 4A → 2 → 4B → 3: filtra, normaliza e pontua vagas novas."""
    config = ConfigManager()

    resume_path = paths.RESUME_JSON
    if not resume_path.exists():
        logger.warning("Currículo não encontrado em %s. Pipeline ignorado.", resume_path)
        return {}

    resume_json = json.loads(resume_path.read_text(encoding="utf-8"))
    coleta_config = config.get("coleta") or {}
    scoring_config = config.get("scoring") or {}
    threshold_excelente = int(scoring_config.get("threshold_excelente", 65))
    # `threshold_bom` deixou de existir como leitura: score não rejeita mais,
    # então não há segunda fronteira. A chave pode seguir na config sem efeito.

    from jobapplier.agents.normalizer import normalize
    from jobapplier.agents.scorer import score
    from jobapplier.filters import post_filter, pre_filter

    client = _obter_cliente_llm(config)

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
    stats = {"filtradas_4a": 0, "normalizadas": 0, "filtradas_4b": 0, "pontuadas": 0, "aprovadas": 0, "pendentes": 0}

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

        # Score nunca rejeita. Abaixo do corte a vaga vira 'pendente' —
        # possibilidade acessível baixando o filtro da fila, não lixo. O score
        # não é probabilidade calibrada (nunca foi validado contra desfecho
        # real), e descartar terminalmente por ele joga fora vaga que só ele
        # achou ruim. `threshold_bom` deixou de separar qualquer coisa; fica na
        # config por compatibilidade.
        if vaga_score >= threshold_excelente:
            novo_status = "aprovada"
            stats["aprovadas"] += 1
        else:
            novo_status = "pendente"
            stats["pendentes"] += 1

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
        "pontuadas=%d (aprovadas=%d pendentes=%d)",
        stats["filtradas_4a"], stats["normalizadas"], stats["filtradas_4b"],
        stats["pontuadas"], stats["aprovadas"], stats["pendentes"],
    )
    return {"vagas_novas": len(vagas_novas), **stats}


def run_pipeline():
    """Esteira 2 — filtros e scoring."""
    with log.execucao("pipeline") as run_id:
        log.registrar_metricas(run_id, _executar_pipeline())


def _executar_candidaturas(run_id: str = "manual",
                           apenas_ids: list[int] | None = None,
                           revisado: bool = False,
                           visivel: bool = False,
                           ao_verificar=None) -> dict:
    """Módulos 12 → 6 → 13: otimiza currículo, gera cover letter e candidata vagas aprovadas.

    Só processa vagas com status 'aprovada'. Vagas 'pendente' aguardam revisão
    humana na página Vagas — o agendador não decide por você. Para voltar ao
    comportamento antigo, defina risco.auto_aplicar_pendentes = true na config.

    `apenas_ids` restringe a fila a vagas específicas, para enviar uma escolhida
    a dedo **pelos mesmos gates** — limite, duplicidade, disjuntor, corte de
    score. A alternativa seria chamar o applicator direto, que a invariante 2
    proíbe, ou mexer no status das outras vagas para esvaziar a fila, que é pior:
    perderia o estado real delas para controlar um efeito colateral.

    `revisado=True` dispensa **apenas** o corte de `threshold_auto`, e só para as
    vagas em `apenas_ids`. Esse corte existe porque o score não é probabilidade
    calibrada — é um substituto de julgamento humano. Quando o julgamento humano
    de fato aconteceu numa vaga específica, o substituto não tem mais função.
    Exige `apenas_ids` de propósito: sem essa amarra viraria "desligar o corte",
    que é outra coisa. Limite diário, duplicidade e disjuntor seguem valendo.
    """
    if revisado and not apenas_ids:
        raise ValueError(
            "revisado=True exige apenas_ids: dispensar o corte de score para a "
            "fila inteira não é revisão, é desligar a guarda."
        )
    if (visivel or ao_verificar) and not apenas_ids:
        raise ValueError(
            "sessão assistida exige apenas_ids: abrir a fila inteira num "
            "navegador visível é envio em lote com o candidato de espectador."
        )
    config = ConfigManager()

    resume_path = paths.RESUME_JSON
    resumes_dir = paths.RESUMES
    cover_letters_dir = paths.COVER_LETTERS
    cover_letters_dir.mkdir(parents=True, exist_ok=True)

    if not resume_path.exists():
        logger.warning("Currículo não encontrado.")
        return {}

    resume_json = json.loads(resume_path.read_text(encoding="utf-8"))

    # ── Bloqueio operacional: schema fora de head ────────────────────────────
    # Candidatura é irreversível; rodá-la sobre schema incompatível arrisca
    # falhar no meio, com a vaga já em 'em_andamento'. Coleta e UI seguem
    # funcionando — só a esteira que age em nome do usuário para.
    from jobapplier.database import schema

    estado = schema.exigir_head()
    if not estado.em_head:
        logger.error(
            "Candidaturas suspensas até o banco estar em head. %s", estado.mensagem()
        )
        return {"bloqueado": estado.codigo,
                "revisao_aplicada": estado.aplicada,
                "revisao_esperada": estado.esperada}

    from jobapplier.agents.cover_letter import generate as gen_cover_letter
    from jobapplier.agents.resume_optimizer import optimize
    from jobapplier.applicators import base as applicators
    from jobapplier.generators.pdf import generate_pdf
    from jobapplier.safety import guard

    client = _obter_cliente_llm(config)

    cfg = config.load()
    risco_cfg = cfg.get("risco") or {}

    # Devolve para a fila vagas travadas em 'em_andamento' por crash anterior.
    guard.liberar_orfaos()

    # ── Modo sombra ──────────────────────────────────────────────────────────
    # Padrão LIGADO. O sistema prepara tudo — currículo otimizado, PDF, cover
    # letter — e NÃO submete. A vaga fica em 'pronta_para_revisao' e a candidatura
    # é gravada como 'simulada', registrando o que teria sido enviado.
    #
    # Por que ligado por padrão: score de LLM não é probabilidade calibrada, e o
    # threshold ativo (65) nunca foi validado contra desfecho real. Rode em sombra
    # por algumas semanas, compare as decisões do sistema com as suas, e só então
    # desligue com risco.modo_sombra = false.
    modo_sombra = risco_cfg.get("modo_sombra", True)
    if modo_sombra:
        logger.warning(
            "MODO SOMBRA ativo: candidaturas serão preparadas mas NÃO enviadas. "
            "Para enviar de verdade: risco.modo_sombra = false em data/config.json."
        )

    status_alvo = ["aprovada"]
    if risco_cfg.get("auto_aplicar_pendentes"):
        status_alvo.append("pendente")
        logger.warning(
            "auto_aplicar_pendentes=true — candidatando sem revisão humana."
        )

    with get_session() as session:
        consulta = session.query(Vaga).filter(Vaga.status.in_(status_alvo))
        if apenas_ids:
            consulta = consulta.filter(Vaga.id.in_(apenas_ids))
        vagas_aprovadas = consulta.order_by(Vaga.score.desc()).all()

    if apenas_ids:
        logger.info("Fila restrita a %d vaga(s): %s", len(vagas_aprovadas),
                    sorted(v.id for v in vagas_aprovadas))

    if not vagas_aprovadas:
        logger.info("Nenhuma vaga aguardando candidatura (status: %s).", status_alvo)
        return {"fila": 0}

    logger.info("Fila de candidatura: %d vagas (status: %s)", len(vagas_aprovadas), status_alvo)

    processadas_neste_ciclo = 0
    desfechos = {'enviada': 0, 'perguntas_pendentes': 0, 'erro': 0,
                 'sem_automacao': 0, 'duplicada': 0, 'postergada': 0}

    # Automação exige score alto. Aprovada (>= 65) ganha dossiê; ENVIAR sozinho
    # é outro nível de confiança — o número declarado nunca foi validado contra
    # desfecho real, então o envio automático só acontece acima deste corte.
    # Entre um e outro, a vaga vai para o baralho: o sistema prepara, você decide.
    threshold_auto = int((config.get("scoring") or {}).get("threshold_auto", 85))

    for vaga in vagas_aprovadas:
        plataforma = (vaga.plataforma or "").lower()

        # ── Guarda 1: plataforma sem automação ───────────────────────────────
        # NÃO é motivo para descartar a vaga. O currículo sob medida é o produto;
        # o envio automático é um extra sobre ele. Antes esta guarda vinha antes
        # da geração de documentos, e vaga da Gupy ou da Lever virava
        # 'sem_automacao' sem receber nada — 322 vagas da Gupy morriam aqui, com
        # o trabalho caro (achar, filtrar, pontuar) já pago.
        #
        # O gate de score usa o MESMO caminho: plataforma automatizável com
        # score abaixo de `threshold_auto` é tratada como manual — dossiê pronto,
        # envio seu.
        abaixo_do_auto = (vaga.score or 0) < threshold_auto
        if abaixo_do_auto and revisado:
            logger.warning(
                "Vaga id=%d (%s, score %.0f): abaixo de threshold_auto=%d, "
                "enviando por revisão humana explícita.",
                vaga.id, plataforma, vaga.score or 0, threshold_auto,
            )
            abaixo_do_auto = False
        if abaixo_do_auto and applicators.suportada(plataforma):
            logger.info(
                "Vaga id=%d (%s, score %.0f): abaixo de threshold_auto=%d — "
                "vai para o baralho em vez de envio automático.",
                vaga.id, plataforma, vaga.score or 0, threshold_auto,
            )
        if abaixo_do_auto or not applicators.suportada(plataforma):
            dossie_manual = dossie.montar(vaga, resume_json, client)
            if dossie_manual.pronto:
                logger.info(
                    "Vaga id=%d (%s): sem envio automático, dossiê pronto para "
                    "envio manual — ATS %+.0f%%.",
                    vaga.id, plataforma, dossie_manual.ganho_ats,
                )
                novo_status = "pronta_envio_manual"
            else:
                logger.warning(
                    "Vaga id=%d (%s): sem automação e o dossiê falhou (%s).",
                    vaga.id, plataforma, dossie_manual.erro or "motivo não registrado",
                )
                novo_status = "sem_automacao"

            desfechos["sem_automacao"] += 1
            with get_session() as session:
                session.query(Vaga).filter(Vaga.id == vaga.id).update(
                    {"status": novo_status}
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

        avaliacao = None

        # ── Guarda 4: lease ──────────────────────────────────────────────────
        # Um UPDATE condicional faz a transição para 'em_andamento' e o bloqueio
        # ao mesmo tempo. Se não casar, outra execução tem a vaga ou ela passou
        # do teto de tentativas.
        # `conta_tentativa` só no envio real: ver a docstring de `adquirir_lease`.
        if not guard.adquirir_lease(vaga.id, dono=run_id,
                                    conta_tentativa=not modo_sombra):
            desfechos["postergada"] += 1
            continue

        logger.info("Processando vaga id=%d '%s'", vaga.id, vaga.titulo[:50])
        processadas_neste_ciclo += 1

        try:
            # ── Módulo 12: Seleciona e otimiza perfil base ────────────────────
            # Via `dossie`, não à mão: esta função tinha uma segunda cópia da
            # escolha de perfil, lia o sugerido de outro campo e ignorava o
            # idioma da vaga. Duas cópias da mesma decisão divergem — foi assim
            # que os quatro `resume_base_*.json` apodreceram (invariante 11).
            perfil, base_profile = dossie.perfil_base(vaga, resume_json)

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
            if modo_sombra:
                # Avalia o formulário SEM submeter. É o que produz a evidência
                # que justificaria desligar o modo sombra: a taxa de formulários
                # que a automação não sabe preencher.
                avaliacao = applicators.avaliar_preenchimento(vaga, resume_json)
                perguntas_desconhecidas = (
                    avaliacao.get("desconhecidos", []) + avaliacao.get("bloqueadores", [])
                )
                resultado_app = applicators.resultado(
                    applicators.SIMULADA,
                    f"Modo sombra: documentos preparados para {plataforma}, "
                    "envio não executado.",
                    perguntas_manuais=perguntas_desconhecidas,
                )
                confianca = avaliacao.get("application_confidence")
                logger.info(
                    "MODO SOMBRA — vaga id=%d em %s | fit %.0f | preenchimento %s "
                    "(%s/%s campos) | currículo %s",
                    vaga.id, plataforma, vaga.score or 0,
                    "?" if confianca is None else f"{confianca:.0%}",
                    (avaliacao.get("respondidos") and len(avaliacao["respondidos"])) or 0,
                    avaliacao.get("total_campos") if avaliacao.get("total_campos") is not None else "?",
                    pdf_path.name,
                )
                if avaliacao.get("bloqueadores"):
                    logger.warning(
                        "Vaga id=%d tem bloqueador de preenchimento: %s",
                        vaga.id, avaliacao["bloqueadores"],
                    )
            else:
                # Registry é a fonte única: 'plataforma' já passou por
                # applicators.suportada() na guarda 1, então obter() não falha.
                logger.info("Enviando candidatura via %s...", plataforma)
                extras = {}
                if visivel:
                    extras["visivel"] = True
                if ao_verificar is not None:
                    extras["ao_verificar"] = ao_verificar
                resultado_app = applicators.obter(plataforma)(
                    vaga, resume_json, pdf_path, cover_letter_text, **extras
                )

            status_cand = resultado_app["status"]
            desfechos[status_cand] = desfechos.get(status_cand, 0) + 1
            novo_status_vaga = MAPA_STATUS_VAGA.get(status_cand, "erro")

            if status_cand == applicators.ENVIADA_CONFIRMADA:
                logger.info("Candidatura confirmada: %s", resultado_app["mensagem"])
            elif status_cand == applicators.REVISAO_MANUAL:
                logger.warning(
                    "Requer revisão humana: %s | perguntas: %s",
                    resultado_app["mensagem"], resultado_app["perguntas_manuais"],
                )
            elif status_cand == applicators.FALHA_AUTOMACAO:
                logger.error("Falha na automação: %s", resultado_app["mensagem"])

            # ── Persiste Candidatura ──────────────────────────────────────────
            with get_session() as session:
                perguntas = resultado_app.get("perguntas_manuais", [])
                erro_texto = None
                if perguntas:
                    erro_texto = json.dumps(perguntas, ensure_ascii=False)
                elif status_cand != applicators.ENVIADA_CONFIRMADA:
                    erro_texto = resultado_app.get("mensagem", "")

                # Evidências finalmente gravadas: a coluna screenshots_path
                # existia desde o início e ninguém escrevia nela.
                evidencias = resultado_app.get("evidencias") or []

                # Atualiza se já houver registro daquela tentativa: o modo sombra
                # grava uma 'simulada' antes, e inserir de novo bate na constraint
                # (vaga_id, ciclo) — era o que impedia candidatar de verdade
                # qualquer vaga já rodada em sombra.
                CandidaturaRepository(session).registrar(
                    vaga_id=vaga.id,
                    status=status_cand,
                    perfil_base=perfil,
                    curriculo_path=str(pdf_path),
                    ats_score_original=ats_antes,
                    ats_score_otimizado=ats_depois,
                    keywords_adicionadas=keywords_adicionadas,
                    cover_letter_path=str(cover_letter_path) if cover_letter_path else None,
                    screenshots_path=";".join(evidencias) if evidencias else None,
                    avaliacao_preenchimento_json=avaliacao,
                    erro=erro_texto,
                )

            # Lease liberado junto com o desfecho.
            guard.liberar_lease(vaga.id, novo_status_vaga)

        except Exception as exc:
            logger.error("Erro ao processar vaga id=%d: %s", vaga.id, exc)
            desfechos["erro"] += 1
            guard.liberar_lease(vaga.id, "erro")
            # Este caminho já falhou uma vez pelo mesmo motivo: inserir aqui
            # batia na constraint e a exceção original se perdia atrás de um
            # IntegrityError. Registrar o erro nunca pode causar outro erro.
            try:
                with get_session() as session:
                    CandidaturaRepository(session).registrar(
                        vaga_id=vaga.id, status="erro", erro=str(exc))
            except Exception as falha:
                logger.error("Não consegui registrar o erro da vaga %d: %s",
                             vaga.id, falha)

    logger.info("Ciclo de candidaturas: %s", desfechos)
    return {"fila": len(vagas_aprovadas), "processadas": processadas_neste_ciclo,
            **desfechos}


def run_applications(apenas_ids: list[int] | None = None,
                     revisado: bool = False, visivel: bool = False,
                     ao_verificar=None):
    """Esteira 3 — otimização de currículo, cover letter e candidatura.

    Sem argumento processa a fila inteira, que é como o agendador chama.
    `apenas_ids` envia vagas escolhidas a dedo pelos mesmos gates, `revisado`
    dispensa só o corte de score para elas, e `visivel`/`ao_verificar` levam a
    sessão assistida (`scripts/finalizar.py`) por este mesmo caminho.

    O script chamava o applicator direto e por isso pulava tudo o que mora
    aqui: duplicidade, limite diário, lease, e o registro da candidatura. Uma
    candidatura foi enviada de verdade e o banco não soube — `ja_candidatado()`
    não bloquearia um reenvio, e o funil contaria um envio a menos. A invariante
    2 existe exatamente contra isso.
    """
    with log.execucao("candidaturas") as run_id:
        log.registrar_metricas(
            run_id, _executar_candidaturas(run_id, apenas_ids=apenas_ids,
                                           revisado=revisado, visivel=visivel,
                                           ao_verificar=ao_verificar))


# ── Tarefas agendadas ─────────────────────────────────────────────────────────
# Estas precisam viver no nível do módulo. O jobstore do APScheduler é o
# Postgres, e serializar um job exige uma referência textual `módulo:função` —
# função aninhada em `main()` não tem. Definidas dentro de `main()`, o
# `scheduler.start()` levantava `ValueError: This Job cannot be serialized` e
# derrubava o orquestrador inteiro **depois** de a coleta e o pipeline já terem
# rodado uma vez, o que fazia a falha parecer sucesso parcial no log.

def enviar_relatorio_diario():
    """Relatório das últimas 24h por e-mail. Silencioso se SMTP não configurado."""
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


def backup_diario():
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

        # Depois da coleta, quando a fila acabou de crescer: é o único momento
        # em que gastar centenas de requisições em board de terceiro se paga.
        scheduler.add_job(
            varrer_encerradas,
            "interval",
            hours=6,
            id="varrer_encerradas",
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

        scheduler.add_job(
            enviar_relatorio_diario,
            "cron",
            hour=8,
            minute=0,
            id="daily_report",
            replace_existing=True,
        )

        scheduler.add_job(
            backup_diario,
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
