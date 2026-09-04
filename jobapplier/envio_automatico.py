"""Liga/desliga do envio automático, e reenfileiramento das já preparadas.

O modo sombra só era editável em `data/config.json` — ligar o envio real exigia
abrir JSON no editor. Virou botão no Dashboard, e a lógica mora aqui porque
decidir *quem qualifica* (plataforma com automação, score acima do corte) é
regra de negócio, e regra de negócio não vive em `pages/`.

Duas decisões de desenho, ambas deliberadas:

**Ativar e reenfileirar são atos separados.** O botão de ativar libera vagas
futuras; as que já foram preparadas sob o modo sombra só entram na fila de envio
por um segundo botão, que mostra quais são. O mesmo clique nunca liga o sistema
E dispara envios — vaga preparada em sombra foi preparada esperando revisão
humana, e mudar essa expectativa retroativamente precisa ser explícito.

**Reenfileirar devolve a 'aprovada', não envia.** A esteira de candidaturas é o
único caminho de envio (invariante 1), e ela só processa 'aprovada'. O
reenfileiramento entra pela porta oficial: limites diários, disjuntor e delays
do guard continuam valendo.
"""
from __future__ import annotations

import logging

from jobapplier import plataformas

logger = logging.getLogger(__name__)

THRESHOLD_AUTO_PADRAO = 85


def esta_ativo(config) -> bool:
    """O envio automático está ligado? (= modo sombra desligado)."""
    risco = config.load().get("risco") or {}
    return not risco.get("modo_sombra", True)


def threshold_auto(config) -> int:
    scoring = config.load().get("scoring") or {}
    return int(scoring.get("threshold_auto", THRESHOLD_AUTO_PADRAO))


def ativar(config) -> None:
    """Desliga o modo sombra. Vale para vagas futuras; as preparadas ficam."""
    cfg = config.load()
    cfg.setdefault("risco", {})["modo_sombra"] = False
    config.save(cfg)
    logger.warning(
        "Envio automático ATIVADO pelo usuário: vagas com score >= %d em "
        "plataformas com automação serão enviadas sem revisão.",
        threshold_auto(config),
    )


def desativar(config) -> None:
    """Religa o modo sombra. Um clique, sem confirmação: desligar o envio deve
    ser sempre mais fácil que ligar."""
    cfg = config.load()
    cfg.setdefault("risco", {})["modo_sombra"] = True
    config.save(cfg)
    logger.info("Envio automático desativado — de volta ao modo sombra.")


def qualificaveis(config) -> list[dict]:
    """Vagas já preparadas em sombra que qualificariam para envio automático.

    `pronta_para_revisao` + plataforma com automação + score no corte. A lista
    vai para a tela: o usuário vê exatamente o que o reenfileiramento enviaria
    antes de clicar.
    """
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    corte = threshold_auto(config)
    automatizaveis = plataformas.com_automacao()
    if not automatizaveis:
        return []

    with get_session() as sessao:
        linhas = (
            sessao.query(Vaga.id, Vaga.titulo, Vaga.empresa, Vaga.score)
            .filter(
                Vaga.status == "pronta_para_revisao",
                Vaga.plataforma.in_(automatizaveis),
                Vaga.score >= corte,
            )
            .order_by(Vaga.score.desc())
            .all()
        )
    return [
        {"id": i, "titulo": t, "empresa": e, "score": s}
        for i, t, e, s in linhas
    ]


def reenfileirar(config) -> int:
    """Devolve as qualificáveis a 'aprovada', para a esteira enviar no próximo
    ciclo. Retorna quantas foram."""
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    corte = threshold_auto(config)
    automatizaveis = plataformas.com_automacao()
    if not automatizaveis:
        return 0

    with get_session() as sessao:
        n = (
            sessao.query(Vaga)
            .filter(
                Vaga.status == "pronta_para_revisao",
                Vaga.plataforma.in_(automatizaveis),
                Vaga.score >= corte,
            )
            .update({"status": "aprovada"}, synchronize_session=False)
        )
    if n:
        logger.warning(
            "%d vaga(s) reenfileirada(s) para envio automático pelo usuário.", n
        )
    return n
