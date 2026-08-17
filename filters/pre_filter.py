"""Módulo 4A — Filtros pré-normalização (texto bruto, sem IA)."""
import logging

logger = logging.getLogger(__name__)

# Países/regiões que indicam vaga explicitamente fora do Brasil/remoto
_BLOCOS_GEOGRAFICOS = [
    "usa,", "usa ", "united states", "u.s.", "united kingdom", "uk,", " uk ",
    "canada,", "canada ", "australia,", "australia ", "india,", "india ",
    "germany,", "france,", "spain,", "netherlands,", "singapore,",
    "colombia,", "colombia ", "mexico,", "mexico ", "argentina,", "argentina ",
    "chile,", "chile ", "peru,", "peru ",
]


def _normalize(text: str) -> str:
    return text.lower()


def apply(vaga, config: dict) -> tuple[bool, str]:
    """Retorna (passou, motivo_rejeicao).

    Localização: só rejeita se a localização indicar EXPLICITAMENTE um país fora
    do Brasil e não contiver indicação de remoto — isso evita descartar vagas de
    empresas internacionais que não preencheram a localização corretamente.
    """
    if hasattr(vaga, "titulo"):
        titulo = vaga.titulo or ""
        descricao = vaga.descricao or ""
        localizacao = vaga.localizacao or ""
    else:
        titulo = vaga.get("titulo", "")
        descricao = vaga.get("descricao", "")
        localizacao = vaga.get("localizacao", "")

    titulo_lower = _normalize(titulo)

    cargos_alvo = [_normalize(c) for c in config.get("cargos_alvo", [])]
    palavras_bloqueadas = [_normalize(p) for p in config.get("palavras_bloqueadas", [])]

    # Pelo menos um cargo alvo deve aparecer no título
    if cargos_alvo:
        encontrou_cargo = any(cargo in titulo_lower for cargo in cargos_alvo)
        if not encontrou_cargo:
            return False, f"título sem cargo alvo: '{titulo}'"

    # Nenhuma palavra bloqueada no título
    for palavra in palavras_bloqueadas:
        if palavra in titulo_lower:
            return False, f"palavra bloqueada no título: '{palavra}'"

    # Localização: só rejeita se for explicitamente fora do Brasil E não remota
    if localizacao:
        loc_lower = _normalize(localizacao)
        is_remote = "remot" in loc_lower or "remote" in loc_lower or "híbrido" in loc_lower
        is_brazil = any(br in loc_lower for br in ["brasil", "brazil", "são paulo", "sao paulo",
                                                    "rio de janeiro", "belo horizonte", "curitiba",
                                                    "brasília", "brasilia", "porto alegre", "sp,",
                                                    ", sp", ", rj", ", mg", ", rs"])
        if not is_remote and not is_brazil:
            is_foreign = any(block in loc_lower for block in _BLOCOS_GEOGRAFICOS)
            if is_foreign:
                return False, f"localização fora do Brasil: '{localizacao}'"

    return True, ""
