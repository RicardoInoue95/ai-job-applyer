"""Módulo 4B — Filtros pós-normalização (opera sobre JSON normalizado)."""
import logging

logger = logging.getLogger(__name__)

# AINDA NÃO USADO. O filtro por senioridade consta do plano (Módulo 4B) mas nunca
# foi implementado: este mapa e a variável `senioridade` que era extraída de
# `normalizado` ficavam ambos sem uso. A variável morta foi removida; o mapa fica
# como registro da lacuna. Implementar exige decidir a política — rejeitar vaga
# acima do nível do candidato, abaixo, ou ambos — e isso muda quais vagas passam.
SENIORIDADE_ORDEM = {
    "junior": 1,
    "pleno": 2,
    "senior": 3,
    "especialista": 4,
    "gerente": 5,
    "desconhecida": 0,
}


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

    # ── Filtro de anos de experiência ────────────────────────────────────────
    anos_max_aceito = config.get("anos_experiencia_maximo")
    if anos_min and anos_max_aceito:
        if anos_min > anos_max_aceito:
            return False, f"experiência mínima exigida ({anos_min} anos) acima do máximo aceito ({anos_max_aceito})"

    return True, ""
