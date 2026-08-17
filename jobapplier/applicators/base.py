"""Contrato comum dos applicators e registro de plataformas.

Os três applicators já viviam em módulos separados — isso estava certo. O que
faltava era o contrato existir **em código**: o formato de retorno era convenção,
e comportamento transversal (captura de evidência na falha, jitter, registro de
tentativa) teria de ser repetido em cada módulo.

Este módulo concentra o que não varia por plataforma:

- ``resultado()`` monta o dicionário de retorno, sempre com as mesmas chaves.
- ``capturar_falha()`` grava screenshot + HTML quando algo quebra. A coluna
  ``candidaturas.screenshots_path`` existia no schema desde o início e ninguém
  escrevia nela; uma falha em produção deixava só a mensagem de erro.
- ``PLATAFORMAS`` é o registro único. Antes o orquestrador tinha um if/elif e um
  conjunto ``PLATAFORMAS_COM_AUTOMACAO`` paralelo — duas fontes de verdade que
  podiam divergir.

O que **não** foi centralizado, e por quê: o ciclo de vida do browser continua em
cada applicator. Greenhouse abre sem sessão, LinkedIn precisa de `storage_state`,
Gupy tem fluxo próprio de múltiplas etapas. Unificar isso pede uma classe base
com método-template, e a hora de fazer é quando `apply()` tiver cobertura de
teste — hoje não tem.
"""
import contextlib
import logging
from collections.abc import Callable
from pathlib import Path

from jobapplier import paths
from jobapplier.tempo import agora_utc

logger = logging.getLogger(__name__)

#: Status possíveis de uma candidatura. `erro` é falha técnica;
#: `perguntas_pendentes` é sucesso parcial que exige intervenção humana.
STATUS_VALIDOS = ("enviada", "perguntas_pendentes", "erro")


def resultado(
    status: str,
    mensagem: str = "",
    application_id: str | None = None,
    perguntas_manuais: list[str] | None = None,
    evidencias: list[Path] | None = None,
) -> dict:
    """Monta o retorno padrão de um applicator.

    Usar isto em vez de montar o dict à mão garante que nenhuma chave falte —
    o orquestrador acessa `resultado_app["status"]` e
    `resultado_app["perguntas_manuais"]` sem `.get()`.
    """
    if status not in STATUS_VALIDOS:
        raise ValueError(f"status inválido: {status!r}. Use um de {STATUS_VALIDOS}.")

    return {
        "status": status,
        "application_id": application_id,
        "mensagem": mensagem,
        "perguntas_manuais": list(perguntas_manuais or []),
        "evidencias": [str(e) for e in (evidencias or [])],
    }


#: Quantos ARQUIVOS de evidência manter (PNG + HTML, ~2 por falha, então ~100
#: falhas). Screenshot full_page de formulário longo passa de 1 MB; sem retenção,
#: data/screenshots cresce sem limite.
RETENCAO_EVIDENCIAS = 200


def _aplicar_retencao_evidencias(destino: Path) -> None:
    arquivos = sorted(destino.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
    for antigo in arquivos[RETENCAO_EVIDENCIAS:]:
        with contextlib.suppress(OSError):
            antigo.unlink()


def capturar_falha(page, plataforma: str, vaga_id: int | str = "?") -> list[Path]:
    """Grava screenshot e HTML da página no momento da falha.

    É a diferença entre "erro: Timeout" e poder ver que o formulário mudou de
    layout. Best effort: se a captura falhar, a candidatura não deve quebrar por
    causa disso — o erro original é o que importa.
    """
    destino = paths.SCREENSHOTS / "falhas"
    capturados: list[Path] = []

    try:
        destino.mkdir(parents=True, exist_ok=True)
        marca = agora_utc().strftime("%Y%m%d_%H%M%S")
        prefixo = f"{plataforma}_{vaga_id}_{marca}"

        png = destino / f"{prefixo}.png"
        try:
            page.screenshot(path=str(png), full_page=True)
            capturados.append(png)
        except Exception as exc:
            logger.debug("Screenshot de falha indisponível: %s", exc)

        # HTML complementa o PNG: o screenshot mostra o que apareceu, o HTML
        # mostra quais seletores existiam.
        html = destino / f"{prefixo}.html"
        try:
            html.write_text(page.content(), encoding="utf-8")
            capturados.append(html)
        except Exception as exc:
            logger.debug("HTML de falha indisponível: %s", exc)

        _aplicar_retencao_evidencias(destino)

        if capturados:
            logger.error(
                "Evidência da falha em %s (vaga %s): %s",
                plataforma, vaga_id, ", ".join(str(c) for c in capturados),
            )
    except Exception as exc:
        logger.debug("Captura de evidência falhou por completo: %s", exc)

    return capturados


# ── Registro de plataformas ───────────────────────────────────────────────────

def _carregar(modulo: str) -> Callable:
    """Import tardio do applicator: Playwright só é carregado quando usado."""
    def _apply(*args, **kwargs):
        import importlib

        mod = importlib.import_module(f"jobapplier.applicators.{modulo}")
        return mod.apply(*args, **kwargs)

    _apply.__name__ = f"apply_{modulo}"
    return _apply


#: Plataforma → função de candidatura. Fonte única de verdade sobre o que tem
#: automação. Lever (Módulo 14) não está aqui de propósito: não foi implementado,
#: e antes as vagas dele caíam no applicator do Greenhouse e falhavam depois de
#: já ter gasto tokens de LLM.
PLATAFORMAS: dict[str, Callable] = {
    "greenhouse": _carregar("greenhouse"),
    "linkedin": _carregar("linkedin"),
    "gupy": _carregar("gupy"),
}


def suportada(plataforma: str) -> bool:
    return (plataforma or "").lower() in PLATAFORMAS


def obter(plataforma: str) -> Callable:
    """Applicator da plataforma. Levanta KeyError com mensagem útil se não houver."""
    chave = (plataforma or "").lower()
    if chave not in PLATAFORMAS:
        raise KeyError(
            f"Sem automação para '{plataforma}'. "
            f"Disponíveis: {', '.join(sorted(PLATAFORMAS))}."
        )
    return PLATAFORMAS[chave]
