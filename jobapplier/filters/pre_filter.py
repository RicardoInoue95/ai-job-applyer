"""Módulo 4A — Filtros pré-normalização (texto bruto, sem IA)."""
import logging
import re

logger = logging.getLogger(__name__)

# Países que indicam vaga explicitamente fora do Brasil.
#
# Casado com fronteira de palavra, não substring. A versão anterior desta lista
# exigia vírgula ou espaço DEPOIS do país ("usa,", "usa ", "canada,"), então
# qualquer localização que terminasse no nome do país — "Austin, USA",
# "London, UK", "Toronto, Canada", o formato mais comum dos boards — passava
# batido. Fronteira de palavra também evita o falso positivo oposto:
# "Indiana" não casa com "india".
_PAISES_ESTRANGEIROS = [
    "usa", "united states", "united kingdom", "uk",
    "canada", "australia", "india", "germany", "france", "spain",
    "netherlands", "singapore", "colombia", "mexico", "argentina",
    "chile", "peru",
]

_RE_ESTRANGEIRO = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _PAISES_ESTRANGEIROS) + r")\b",
    re.IGNORECASE,
)

# Abreviações pontuadas ("U.S.", "U.S.A.") não funcionam com \b no fim, porque
# o ponto final já é caractere não-palavra.
_RE_US_ABREV = re.compile(r"\bu\.\s?s\.(?:\s?a\.?)?", re.IGNORECASE)


def _e_estrangeira(localizacao: str) -> bool:
    return bool(_RE_ESTRANGEIRO.search(localizacao) or _RE_US_ABREV.search(localizacao))


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

    # ── Elegibilidade geográfica por sinal EXPLÍCITO ────────────────────────
    # Antes de qualquer chamada de LLM. O baseline mostrou que vaga
    # geograficamente inelegível avançava até o formulário e só ali revelava a
    # incompatibilidade — depois de gastar normalização, scoring, currículo,
    # PDF, cover letter e browser.
    #
    # Só linguagem inequívoca descarta aqui. Menção a "United States", cidade
    # americana ou moeda em dólar não bastam: isolados, produziriam falso
    # negativo. O que é ambíguo segue para o 4B.
    from jobapplier.elegibilidade import avaliar_texto

    avaliacao = avaliar_texto(descricao, config.get("dados_pessoais"))
    if avaliacao.descarta:
        return False, (
            f"inelegível geograficamente ({avaliacao.categoria}): "
            f"{avaliacao.evidencias[0] if avaliacao.evidencias else ''}"
        )

    # Localização: só rejeita se for explicitamente fora do Brasil E não remota
    if localizacao:
        loc_lower = _normalize(localizacao)
        is_remote = "remot" in loc_lower or "remote" in loc_lower or "híbrido" in loc_lower
        is_brazil = any(br in loc_lower for br in ["brasil", "brazil", "são paulo", "sao paulo",
                                                    "rio de janeiro", "belo horizonte", "curitiba",
                                                    "brasília", "brasilia", "porto alegre", "sp,",
                                                    ", sp", ", rj", ", mg", ", rs"])
        if not is_remote and not is_brazil and _e_estrangeira(loc_lower):
            return False, f"localização fora do Brasil: '{localizacao}'"

    return True, ""
