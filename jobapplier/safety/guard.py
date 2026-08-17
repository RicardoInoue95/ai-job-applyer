"""Módulo 9 — Controle de Risco.

Antes deste módulo o sistema disparava candidaturas sem freio: a constante
``MAX_DAILY_APPLICATIONS`` existia em ``applicators/linkedin.py`` mas nunca era
consultada. O resultado prático foi ~100 candidaturas em dois dias, o que é
risco concreto de restrição de conta no LinkedIn.

Quatro garantias, todas verificadas ANTES de qualquer trabalho caro
(otimização de currículo, cover letter, abertura de browser):

1. Limite por plataforma numa janela deslizante de 24h
2. Disjuntor para runs que só produzem erro
3. Nunca candidatar duas vezes a mesma vaga
4. Espera aleatória entre candidaturas + jitter de mouse/scroll no browser

Janela deslizante, não dia-calendário: um dia-calendário permite 10 candidaturas
às 23h50 e outras 10 às 00h10 — exatamente o padrão de rajada que a detecção
procura. A janela de 24h fecha esse buraco e ainda evita aritmética de fuso
sobre as colunas naive-UTC do banco.
"""
import logging
import random
import time
from datetime import timedelta

from sqlalchemy import func

from jobapplier.database.connection import get_session
from jobapplier.database.models import Candidatura, Vaga
from jobapplier.tempo import agora_utc

logger = logging.getLogger(__name__)


# Limites conservadores por plataforma. LinkedIn é o mais sensível (detecção
# ativa de automação + conta é a identidade profissional real do usuário).
# Greenhouse e Lever são submissões de formulário público, bem menos expostas.
DEFAULT_LIMITES = {
    "linkedin": 10,
    "gupy": 15,
    "greenhouse": 20,
    "lever": 20,
}
DEFAULT_LIMITE = 15

# Multiplicador do disjuntor: se as TENTATIVAS (incluindo erros) na janela
# passarem de limite * este fator, algo está quebrado — pausa a plataforma em
# vez de martelar o formulário.
FATOR_DISJUNTOR = 3

DEFAULT_DELAY_MIN = 20
DEFAULT_DELAY_MAX = 90

# Status de candidatura que comprovam contato real com a plataforma.
# Erros ficam de fora do limite principal de propósito: uma falha de
# pré-validação (CPF ausente, link inválido, sessão não encontrada) nunca toca a
# plataforma, e contá-la queimaria a cota diária inteira sem uma única
# candidatura enviada. Erros são cobertos pelo disjuntor.
STATUS_CONTATO_REAL = ("enviada", "perguntas_pendentes")



def _cfg_risco(config: dict | None) -> dict:
    return (config or {}).get("risco") or {}


def limite_diario(plataforma: str, config: dict | None = None) -> int:
    """Limite de candidaturas por 24h para a plataforma."""
    plataforma = (plataforma or "").lower()
    limites = _cfg_risco(config).get("limites_diarios") or {}
    if plataforma in limites:
        try:
            return int(limites[plataforma])
        except (TypeError, ValueError):
            logger.warning("Limite inválido para '%s' na config, usando padrão.", plataforma)
    return DEFAULT_LIMITES.get(plataforma, DEFAULT_LIMITE)


def _contar(plataforma: str, apenas_contato_real: bool) -> int:
    desde = agora_utc() - timedelta(hours=24)
    with get_session() as session:
        q = (
            session.query(func.count(Candidatura.id))
            .join(Vaga, Vaga.id == Candidatura.vaga_id)
            .filter(
                func.lower(Vaga.plataforma) == plataforma.lower(),
                Candidatura.criado_em >= desde,
            )
        )
        if apenas_contato_real:
            q = q.filter(Candidatura.status.in_(STATUS_CONTATO_REAL))
        return q.scalar() or 0


def contagem_janela(plataforma: str) -> int:
    """Candidaturas com contato real na plataforma nas últimas 24h."""
    return _contar(plataforma, apenas_contato_real=True)


def tentativas_janela(plataforma: str) -> int:
    """Todas as tentativas na plataforma nas últimas 24h, erros incluídos."""
    return _contar(plataforma, apenas_contato_real=False)


def checar_limite(plataforma: str, config: dict | None = None) -> tuple[bool, str]:
    """Retorna (pode_candidatar, motivo_do_bloqueio).

    Checa limite normal e disjuntor. Chame ANTES de gastar tokens Gemini ou
    abrir browser.
    """
    plataforma = (plataforma or "desconhecida").lower()
    limite = limite_diario(plataforma, config)

    try:
        enviadas = contagem_janela(plataforma)
        tentativas = tentativas_janela(plataforma)
    except Exception as exc:
        # Falha ao consultar o banco não deve virar candidatura sem freio.
        logger.error("Não foi possível verificar limite de '%s': %s", plataforma, exc)
        return False, f"falha ao verificar limite diário: {exc}"

    if enviadas >= limite:
        return False, (
            f"limite de 24h atingido em {plataforma}: {enviadas}/{limite} candidaturas"
        )

    teto_disjuntor = limite * FATOR_DISJUNTOR
    if tentativas >= teto_disjuntor:
        return False, (
            f"disjuntor aberto em {plataforma}: {tentativas} tentativas em 24h "
            f"(teto {teto_disjuntor}) com apenas {enviadas} enviadas — "
            f"investigue os erros antes de continuar"
        )

    logger.debug(
        "Limite %s: %d/%d enviadas, %d tentativas (teto disjuntor %d)",
        plataforma, enviadas, limite, tentativas, teto_disjuntor,
    )
    return True, ""


def ja_candidatado(vaga_id: int) -> bool:
    """True se já existe candidatura com contato real para esta vaga.

    Só considera 'enviada' e 'perguntas_pendentes' — uma vaga cuja única
    candidatura foi erro de pré-validação pode ser retentada depois de corrigir
    a configuração.
    """
    try:
        with get_session() as session:
            existe = (
                session.query(Candidatura.id)
                .filter(
                    Candidatura.vaga_id == vaga_id,
                    Candidatura.status.in_(STATUS_CONTATO_REAL),
                )
                .first()
            )
        return existe is not None
    except Exception as exc:
        logger.error("Não foi possível verificar duplicidade da vaga %s: %s", vaga_id, exc)
        # Na dúvida, trata como já candidatada: candidatura duplicada é pior
        # que candidatura não enviada.
        return True


def espera_humana(config: dict | None = None, contexto: str = "") -> float:
    """Dorme um intervalo aleatório entre candidaturas. Retorna os segundos."""
    risco = _cfg_risco(config)
    try:
        minimo = float(risco.get("delay_min", DEFAULT_DELAY_MIN))
        maximo = float(risco.get("delay_max", DEFAULT_DELAY_MAX))
    except (TypeError, ValueError):
        minimo, maximo = DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX

    if maximo < minimo:
        minimo, maximo = maximo, minimo

    segundos = random.uniform(minimo, maximo)
    logger.info("Aguardando %.0fs antes da próxima candidatura%s.",
                segundos, f" ({contexto})" if contexto else "")
    time.sleep(segundos)
    return segundos


def humanizar(page) -> None:
    """Movimentos de mouse e scroll aleatórios antes de interagir com a página.

    Best effort — qualquer falha é ignorada, jitter nunca deve derrubar uma
    candidatura.
    """
    try:
        largura, altura = 1280, 800
        for _ in range(random.randint(2, 4)):
            page.mouse.move(
                random.randint(80, largura - 80),
                random.randint(80, altura - 80),
                steps=random.randint(5, 15),
            )
            page.wait_for_timeout(random.randint(120, 400))

        page.mouse.wheel(0, random.randint(150, 500))
        page.wait_for_timeout(random.randint(300, 900))
    except Exception as exc:
        logger.debug("Jitter humano ignorado: %s", exc)


def liberar_orfaos() -> int:
    """Devolve vagas travadas em 'em_andamento' para 'aprovada'.

    Uma vaga fica em 'em_andamento' entre o início do processamento e o
    desfecho. Se o processo morre no meio, ela trava nesse estado para sempre:
    nunca reprocessada, nunca visível na fila.

    Chamar no INÍCIO de run_applications é seguro porque o agendador roda esse
    job com max_instances=1 — nenhuma outra execução está candidatando em
    paralelo, logo qualquer 'em_andamento' remanescente é órfão de um crash.
    """
    try:
        with get_session() as session:
            liberadas = (
                session.query(Vaga)
                .filter(Vaga.status == "em_andamento")
                .update({"status": "aprovada"}, synchronize_session=False)
            )
        if liberadas:
            logger.warning(
                "%d vaga(s) travada(s) em 'em_andamento' devolvidas para 'aprovada'.",
                liberadas,
            )
        return liberadas
    except Exception as exc:
        logger.error("Falha ao liberar órfãos: %s", exc)
        return 0
