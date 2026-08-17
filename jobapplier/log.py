"""Logging estruturado com `run_id`, para stdout e arquivo.

Antes: `logging.basicConfig` para stdout e nada mais. O `structlog` estava no
requirements e não era importado por ninguém; `data/logs/` existia vazio. O
orquestrador roda a cada 2h — se uma candidatura falhasse às 3h da manhã, a
única evidência era o scrollback do terminal, se ele ainda estivesse aberto.

Decisão central: **os módulos não mudam.** Todos usam
`logging.getLogger(__name__)`, e este módulo instala o structlog como
*formatter* dos handlers da stdlib. Assim cada `logger.info("vaga %d", id)` que
já existe passa pelos processadores, ganha o `run_id` do contexto e sai
formatado — sem tocar em 40 arquivos.

Duas saídas, propósitos diferentes:

- **stdout**: legível por humano, para acompanhar rodando.
- **`data/logs/jobapplier.jsonl`**: uma linha JSON por evento, com rotação.
  É o que permite responder "quantas candidaturas falharam ontem e por quê"
  depois do fato.

Uso:

    from jobapplier import log

    log.configurar()
    with log.execucao("coleta") as run_id:
        ...   # todo log daqui pra dentro carrega run_id
"""
import logging
import logging.handlers
import uuid
from contextlib import contextmanager

import structlog

from jobapplier import paths

ARQUIVO_LOG = paths.DATA / "logs" / "jobapplier.jsonl"
MAX_BYTES = 10 * 1024 * 1024
BACKUPS = 5

_configurado = False


def novo_run_id() -> str:
    """Identificador curto de execução. Curto porque vai em toda linha de log."""
    return uuid.uuid4().hex[:12]


def _processadores_comuns() -> list:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def configurar(nivel: int = logging.INFO, arquivo: bool = True) -> None:
    """Instala structlog sobre a stdlib. Idempotente.

    ``arquivo=False`` só para testes, que não devem escrever em data/logs.
    """
    global _configurado
    if _configurado:
        return

    structlog.configure(
        processors=[
            *_processadores_comuns(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    raiz = logging.getLogger()
    # Remove handlers de um basicConfig anterior, senão cada evento sai duplicado.
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
    raiz.setLevel(nivel)

    console = logging.StreamHandler()
    console.setFormatter(structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_processadores_comuns(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    ))
    raiz.addHandler(console)

    if arquivo:
        try:
            ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
            arq = logging.handlers.RotatingFileHandler(
                ARQUIVO_LOG, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8",
            )
            arq.setFormatter(structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=_processadores_comuns(),
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.dict_tracebacks,
                    structlog.processors.JSONRenderer(),
                ],
            ))
            raiz.addHandler(arq)
        except OSError as exc:
            # Sem log em arquivo o sistema ainda funciona; sem stdout também.
            # Não vale derrubar a aplicação por isso.
            console.handle(logging.LogRecord(
                "jobapplier.log", logging.WARNING, __file__, 0,
                "Log em arquivo desabilitado: %s", (exc,), None,
            ))

    # Bibliotecas verbosas que não agregam ao diagnóstico do projeto.
    for nome in ("urllib3", "httpx", "httpcore", "apscheduler.executors",
                 "google_genai", "openai._base_client", "PIL"):
        logging.getLogger(nome).setLevel(logging.WARNING)

    _configurado = True


def obter_logger(nome: str | None = None):
    return structlog.get_logger(nome)


@contextmanager
def contexto(**valores):
    """Anexa pares chave/valor a todo log emitido dentro do bloco."""
    structlog.contextvars.bind_contextvars(**valores)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars(*valores.keys())


@contextmanager
def execucao(tipo: str, persistir: bool = True, **extra):
    """Delimita uma execução: gera `run_id`, registra na tabela e cronometra.

    Todo log dentro do bloco carrega `run_id` e `execucao`, então uma falha pode
    ser rastreada até o ciclo que a produziu. A linha em `execucoes` é o registro
    durável — e é a mesma linha que serve de item de fila quando o sistema virar
    multi-usuário.

    Falha de persistência não interrompe o trabalho: se a tabela ainda não
    existir (migration não aplicada), loga aviso e segue.
    """
    from jobapplier.tempo import agora_utc

    run_id = novo_run_id()
    inicio = agora_utc()
    execucao_id = None

    if persistir:
        fechar_execucoes_orfas()
        execucao_id = _abrir_execucao(run_id, tipo, inicio)

    logger = structlog.get_logger("jobapplier.execucao")
    structlog.contextvars.bind_contextvars(run_id=run_id, execucao=tipo, **extra)
    logger.info("execução iniciada", tipo=tipo)

    status, erro = "sucesso", None
    try:
        yield run_id
    except BaseException as exc:
        status, erro = "erro", f"{type(exc).__name__}: {exc}"
        logger.error("execução falhou", tipo=tipo, erro=erro)
        raise
    finally:
        fim = agora_utc()
        duracao = (fim - inicio).total_seconds()
        logger.info("execução concluída", tipo=tipo, status=status,
                    duracao_s=round(duracao, 1))
        if execucao_id is not None:
            _fechar_execucao(execucao_id, status, fim, erro)
        structlog.contextvars.unbind_contextvars(
            "run_id", "execucao", *extra.keys()
        )


#: Uma esteira que passa disto quase certamente morreu com o processo. A coleta
#: completa leva minutos; candidaturas, com espera humana entre elas, mais.
HORAS_ATE_ORFA = 6


def fechar_execucoes_orfas() -> int:
    """Marca como interrompidas as execuções que ficaram penduradas.

    Processo morto no meio (Ctrl+C, timeout, crash) deixa a linha em
    'em_andamento' para sempre — o `finally` do context manager nunca roda. Sem
    isto, o histórico de execuções acumula lixo que parece trabalho em curso, e
    a pergunta "o que rodou ontem" fica sem resposta confiável.

    Chamado no início de cada execução: se outra está pendurada há horas, ela
    não está mais viva.
    """
    from datetime import timedelta

    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Execucao
    from jobapplier.tempo import agora_utc

    limite = agora_utc() - timedelta(hours=HORAS_ATE_ORFA)
    try:
        with get_session() as session:
            fechadas = (
                session.query(Execucao)
                .filter(
                    Execucao.status == "em_andamento",
                    Execucao.iniciado_em < limite,
                )
                .update(
                    {"status": "interrompida",
                     "erro": "processo encerrado sem concluir a execução"},
                    synchronize_session=False,
                )
            )
        if fechadas:
            logging.getLogger(__name__).warning(
                "%d execução(ões) pendurada(s) marcada(s) como interrompida(s).",
                fechadas,
            )
        return fechadas
    except Exception as exc:
        logging.getLogger(__name__).warning("Não foi possível fechar órfãs: %s", exc)
        return 0


def _abrir_execucao(run_id: str, tipo: str, inicio) -> int | None:
    try:
        from jobapplier.database.connection import get_session
        from jobapplier.database.models import Execucao

        with get_session() as session:
            registro = Execucao(
                run_id=run_id, tipo=tipo, status="em_andamento", iniciado_em=inicio,
            )
            session.add(registro)
            session.flush()
            return registro.id
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Não foi possível registrar execução '%s' no banco: %s", tipo, exc
        )
        return None


def _fechar_execucao(execucao_id: int, status: str, fim, erro: str | None) -> None:
    try:
        from jobapplier.database.connection import get_session
        from jobapplier.database.models import Execucao

        with get_session() as session:
            session.query(Execucao).filter(Execucao.id == execucao_id).update({
                "status": status, "terminado_em": fim, "erro": erro,
            })
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Não foi possível fechar execução %s: %s", execucao_id, exc
        )


def registrar_metricas(run_id: str, metricas: dict) -> None:
    """Grava o resumo numérico de uma execução (vagas coletadas, aprovadas…)."""
    try:
        from jobapplier.database.connection import get_session
        from jobapplier.database.models import Execucao

        with get_session() as session:
            session.query(Execucao).filter(Execucao.run_id == run_id).update(
                {"metricas_json": metricas}
            )
    except Exception as exc:
        logging.getLogger(__name__).warning("Não foi possível gravar métricas: %s", exc)
