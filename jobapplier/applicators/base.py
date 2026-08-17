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

# ── Status de candidatura ─────────────────────────────────────────────────────
#
# Antes eram três: enviada | perguntas_pendentes | erro. O problema não era a
# quantidade, era `enviada` sair de um match de substring: o Greenhouse marcava
# sucesso se a palavra "obrigado" aparecesse em qualquer lugar da página. Um
# rodapé de agradecimento produzia falso positivo — e falso `enviada` é PIOR que
# erro, porque `guard.ja_candidatado()` passa a bloquear aquela vaga para sempre.
#
# Agora sucesso exige prova inequívoca. Na dúvida, o desfecho é revisão humana.

#: Confirmação inequívoca: página/URL de sucesso conhecida, ou protocolo.
ENVIADA_CONFIRMADA = "enviada_confirmada"
#: Formulário provavelmente submetido, mas sem prova. OU perguntas sem resposta.
#: Nunca reenvie automaticamente — pode duplicar.
REVISAO_MANUAL = "revisao_manual"
#: Falha técnica antes ou durante o preenchimento. Nada foi submetido.
FALHA_AUTOMACAO = "falha_automacao"
#: Modo sombra: documentos preparados, envio deliberadamente não executado.
SIMULADA = "simulada"

STATUS_VALIDOS = (ENVIADA_CONFIRMADA, REVISAO_MANUAL, FALHA_AUTOMACAO, SIMULADA)

#: Status que impedem nova tentativa automática: algo pode ter chegado à
#: plataforma. Consultado por `guard.ja_candidatado`.
STATUS_BLOQUEIA_RETENTATIVA = (ENVIADA_CONFIRMADA, REVISAO_MANUAL)

#: Status legados, de antes desta mudança. Mantidos para leitura de linhas
#: antigas do banco; nunca escritos por código novo.
STATUS_LEGADOS = {
    "enviada": ENVIADA_CONFIRMADA,
    "perguntas_pendentes": REVISAO_MANUAL,
    "erro": FALHA_AUTOMACAO,
}


def avaliar_confirmacao(
    sinais_fortes: dict[str, bool],
    perguntas_manuais: list[str] | None = None,
    sinais_fracos: dict[str, bool] | None = None,
) -> tuple[str, str]:
    """Decide o status a partir das evidências. Retorna (status, justificativa).

    ``sinais_fortes`` são provas: URL de confirmação, elemento de sucesso com id
    de candidatura, protocolo. Um só basta para ENVIADA_CONFIRMADA.

    ``sinais_fracos`` são indícios — texto genérico de agradecimento, botão
    clicado sem erro. Nunca promovem a confirmado; servem para distinguir
    "provavelmente submeteu" de "não chegou nem a submeter".

    Pergunta sem resposta sempre resulta em revisão manual, mesmo com sinal
    forte: um formulário aceito com pergunta em branco pede conferência.
    """
    perguntas = perguntas_manuais or []
    fortes = [k for k, v in (sinais_fortes or {}).items() if v]
    fracos = [k for k, v in (sinais_fracos or {}).items() if v]

    if perguntas:
        return REVISAO_MANUAL, (
            f"{len(perguntas)} pergunta(s) sem resposta automática: {perguntas[:3]}"
        )
    if fortes:
        return ENVIADA_CONFIRMADA, f"confirmação inequívoca via {', '.join(fortes)}"
    if fracos:
        return REVISAO_MANUAL, (
            f"apenas indício de envio ({', '.join(fracos)}), sem confirmação "
            "inequívoca — verifique manualmente se a candidatura chegou"
        )
    return FALHA_AUTOMACAO, "nenhum sinal de submissão"


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


# ── Avaliação de preenchimento (application_confidence) ──────────────────────
#
# O modo sombra respondia "eu teria me candidatado?" e não respondia "eu
# conseguiria preencher?". São perguntas diferentes: uma vaga pode ter aderência
# excelente e um formulário que a automação não sabe completar.
#
# Sem isto, o modo sombra não produz a evidência que justificaria desligá-lo —
# nunca se descobre a taxa de formulários desconhecidos, porque o applicator
# nunca é executado.


def avaliacao_indisponivel(plataforma: str, motivo: str) -> dict:
    """Resultado quando não há como inspecionar o formulário sem submetê-lo."""
    return {
        "plataforma": plataforma,
        "metodo": "indisponivel",
        "motivo": motivo,
        "total_campos": None,
        "respondidos": None,
        "desconhecidos": [],
        "bloqueadores": [],
        "application_confidence": None,
    }


def montar_avaliacao(
    plataforma: str,
    metodo: str,
    respondidos: list[str],
    desconhecidos: list[str],
    bloqueadores: list[str] | None = None,
) -> dict:
    """Consolida a avaliação e calcula a confiança de preenchimento.

    Bloqueador zera a confiança, independentemente do resto: uma pergunta
    eliminatória sem resposta significa que a candidatura não deve sair, por
    melhor que seja a aderência.
    """
    bloqueadores = list(bloqueadores or [])
    total = len(respondidos) + len(desconhecidos)

    if bloqueadores:
        confianca = 0.0
    elif total == 0:
        # Formulário só com campos padrão (nome, e-mail, currículo). É o caso
        # mais simples e o mais seguro de automatizar.
        confianca = 1.0
    else:
        confianca = round(len(respondidos) / total, 2)

    return {
        "plataforma": plataforma,
        "metodo": metodo,
        "total_campos": total,
        "respondidos": respondidos,
        "desconhecidos": desconhecidos,
        "bloqueadores": bloqueadores,
        "application_confidence": confianca,
    }


def avaliar_preenchimento(vaga, resume: dict, config_dados: dict | None = None) -> dict:
    """Quanto do formulário desta vaga a automação consegue preencher.

    Nunca submete nada. Onde a plataforma expõe as perguntas por API — hoje só o
    Greenhouse — a avaliação custa uma requisição HTTP e nenhum browser.
    """
    plataforma = (getattr(vaga, "plataforma", "") or "").lower()

    if plataforma == "greenhouse":
        from jobapplier.applicators.greenhouse import avaliar_preenchimento as _gh

        try:
            return _gh(vaga, resume, config_dados)
        except Exception as exc:
            logger.warning("Avaliação de preenchimento falhou: %s", exc)
            return avaliacao_indisponivel(plataforma, f"erro na avaliação: {exc}")

    if plataforma in PLATAFORMAS:
        return avaliacao_indisponivel(
            plataforma,
            "plataforma não expõe as perguntas sem abrir o formulário; "
            "avaliar exigiria dry-run em browser",
        )

    return avaliacao_indisponivel(plataforma or "desconhecida", "sem automação")


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
