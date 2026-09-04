"""Módulo 4B — Filtros pós-normalização (opera sobre JSON normalizado)."""
import logging

logger = logging.getLogger(__name__)

SENIORIDADE_ORDEM = {
    "junior": 1,
    "pleno": 2,
    "senior": 3,
    "especialista": 4,
    "gerente": 5,
    "desconhecida": 0,
}

#: Nível abaixo do qual a vaga é descartada. A política foi decidida com o dado
#: na mão: das 151 vagas aprovadas da Gupy, 12 eram júnior — passo atrás para
#: quem tem 2,2 anos e cargo de Coordenador, e abaixo da faixa pretendida.
#:
#: Só o piso é filtrado. Vaga ACIMA do nível segue passando de propósito: "5+
#: anos" em anúncio brasileiro costuma ser aspiracional, e Especialista/Gerente
#: às vezes descrevem escopo, não tempo de casa. Descartar essas custaria mais
#: que a triagem delas.
NIVEL_MINIMO = "pleno"


def apply(normalizado: dict, config: dict) -> tuple[bool, str]:
    """Retorna (passou, motivo_rejeicao) baseado no JSON normalizado."""
    if not normalizado:
        return True, ""

    anos_min = normalizado.get("anos_experiencia_minimo")
    tecnologias_vaga = [t.lower() for t in (normalizado.get("tecnologias") or [])]

    # ── Filtro de palavras obrigatórias ─────────────────────────────────────
    palavras_obrigatorias = config.get("palavras_obrigatorias", {})
    termos = [t.lower() for t in palavras_obrigatorias.get("termos", [])]
    modo = palavras_obrigatorias.get("modo", "qualquer")

    if termos:
        presentes = [t for t in termos if any(t in tv for tv in tecnologias_vaga)]
        if modo == "todas" and len(presentes) < len(termos):
            faltando = [t for t in termos if t not in presentes]
            return False, f"tecnologias obrigatórias ausentes: {faltando}"
        elif modo == "qualquer" and not presentes:
            return False, f"nenhuma tecnologia obrigatória encontrada: {termos}"

    # ── Elegibilidade geográfica estruturada ────────────────────────────────
    # Só INELEGIVEL descarta. INCERTA segue: vaga que exige autorização mas
    # oferece sponsorship pode ser viável, e descartá-la seria falso negativo.
    from jobapplier.elegibilidade import avaliar_normalizado

    geo = avaliar_normalizado(normalizado, config.get("dados_pessoais"))
    if geo.descarta:
        return False, (
            f"inelegível geograficamente ({geo.categoria}): "
            f"{geo.evidencias[0] if geo.evidencias else ''}"
        )

    # ── Filtro de anos de experiência ────────────────────────────────────────
    anos_max_aceito = config.get("anos_experiencia_maximo")
    if anos_min and anos_max_aceito:
        if anos_min > anos_max_aceito:
            return False, f"experiência mínima exigida ({anos_min} anos) acima do máximo aceito ({anos_max_aceito})"

    # ── Filtro de senioridade ────────────────────────────────────────────────
    passou_nivel, motivo_nivel = _checar_senioridade(normalizado, config)
    if not passou_nivel:
        return False, motivo_nivel

    return True, ""


def _checar_senioridade(normalizado: dict, config: dict) -> tuple[bool, str]:
    """Descarta vaga abaixo do nível mínimo, com escape pela faixa publicada.

    O escape existe porque título e remuneração nem sempre andam juntos: vaga
    "Analista Júnior" em empresa grande às vezes paga dentro da faixa pretendida,
    e aí o rótulo é convenção interna, não descrição do trabalho. Quando a vaga
    publica quanto paga, é ela que decide — o número é evidência mais forte que o
    título.

    Aplicável a poucas vagas: só 1,9% publicam faixa. Nas demais, decide o título.
    """
    from jobapplier import salario

    nivel_vaga = str(normalizado.get("senioridade") or "desconhecida").lower()
    ordem_vaga = SENIORIDADE_ORDEM.get(nivel_vaga, 0)
    ordem_minima = SENIORIDADE_ORDEM[NIVEL_MINIMO]

    # Nível desconhecido (ordem 0) nunca descarta: 23 das 151 vagas não declaram
    # senioridade no título, e presumir júnior nelas seria descarte cego.
    if ordem_vaga == 0 or ordem_vaga >= ordem_minima:
        return True, ""

    texto = " ".join(filter(None, (
        normalizado.get("descricao_resumida"),
        normalizado.get("titulo"),
        normalizado.get("_texto_original"),
    )))
    compativel = salario.compativel_com_faixa(texto, config=config)
    if compativel is True:
        logger.info(
            "Vaga '%s' é %s mas a faixa publicada alcança a pretensão — mantida.",
            str(normalizado.get("titulo"))[:50], nivel_vaga,
        )
        return True, ""

    return False, (
        f"senioridade abaixo do mínimo ({nivel_vaga} < {NIVEL_MINIMO})"
        + ("; faixa publicada abaixo da pretensão" if compativel is False else "")
    )
