"""Elegibilidade geográfica: a vaga aceita alguém que mora e trabalha no Brasil?

O baseline mostrou que o gargalo não era "faltam respostas para perguntas
recorrentes". Era: **vaga geograficamente inelegível avança até o formulário e só
ali revela a incompatibilidade**. Das 32 vagas que pediam revisão manual, o topo
das perguntas bloqueantes era país de residência, estado americano, visa
sponsorship e work permit — de vagas às quais o candidato não poderia se
candidatar de qualquer forma.

Modelar respostas antes de corrigir isso aumentaria a capacidade de preencher
candidaturas que não deveriam existir.

Quatro dimensões distintas, que o sistema antes misturava numa só:

- onde a vaga **está** (escritório, sede)
- de onde o trabalho **pode ser executado** (escopo do remoto)
- onde o candidato **precisa residir**
- onde o candidato precisa ter **autorização de trabalho**

Uma vaga em empresa americana pode aceitar Brasil. Uma vaga "remote" pode
significar apenas EUA. Uma presencial pode oferecer relocation e sponsorship.

Estados possíveis, e só um deles descarta automaticamente:

    eligible        aceita quem está no Brasil
    ineligible      exige residência ou autorização que o candidato não tem
    uncertain       há sinal geográfico, mas ambíguo — segue para análise
    not_specified   nada dito sobre geografia
"""
import re
from dataclasses import dataclass, field
from enum import StrEnum


class Elegibilidade(StrEnum):
    ELEGIVEL = "eligible"
    INELEGIVEL = "ineligible"
    INCERTA = "uncertain"
    NAO_ESPECIFICADA = "not_specified"


# ── Sinais EXPLÍCITOS, para o filtro 4A ───────────────────────────────────────
# Só linguagem inequívoca entra aqui. Menção a "United States", cidade
# americana, moeda em dólar, sede da empresa ou "remote" sem qualificação NÃO
# são sinais suficientes — isolados, produziriam falso negativo.

_EXIGE_AUTORIZACAO = (
    r"must be (?:legally )?authorized to work in the (?:us|u\.s\.|united states)",
    r"must be (?:legally )?authorized to work in canada",
    r"must have (?:the )?(?:legal )?right to work in the (?:us|united states)",
    r"requires? (?:us|u\.s\.) work authorization",
    r"(?:us|u\.s\.) work authorization (?:is )?required",
    r"must (?:currently )?hold (?:us|u\.s\.) citizenship",
    r"(?:us|u\.s\.) citizens? (?:or permanent residents? )?only",
    r"security clearance required",
)

_EXIGE_RESIDENCIA = (
    r"must (?:reside|be located|be based) in the (?:us|u\.s\.|united states)",
    r"must (?:reside|be located|be based) in canada",
    r"(?:us|u\.s\.|united states) residents? only",
    r"open (?:only )?to candidates? (?:residing|located|based) in the (?:us|united states)",
    r"this (?:role|position) is (?:only )?available to candidates in the (?:us|united states)",
    r"remote within the (?:us|u\.s\.|united states)",
    r"(?:us|u\.s\.)[- ]based (?:candidates?|applicants?) only",
)

_SEM_SPONSORSHIP = (
    r"we (?:are )?(?:do )?not (?:able to )?(?:provide|offer|sponsor)\w* "
    r"(?:visa )?sponsorship",
    r"(?:visa )?sponsorship (?:is )?not (?:available|offered|provided)",
    r"unable to sponsor",
    r"no visa sponsorship",
)

_PADROES = tuple(
    (categoria, re.compile(p, re.IGNORECASE))
    for categoria, grupo in (
        ("autorizacao", _EXIGE_AUTORIZACAO),
        ("residencia", _EXIGE_RESIDENCIA),
        ("sem_sponsorship", _SEM_SPONSORSHIP),
    )
    for p in grupo
)

#: Contra-sinais: quando presentes, a vaga aceita fora do país mesmo tendo
#: linguagem de autorização em algum trecho.
_ACEITA_BRASIL = (
    re.compile(r"\bbrazil\b|\bbrasil\b", re.IGNORECASE),
    re.compile(r"latam|latin america|américa latina|america latina", re.IGNORECASE),
    re.compile(r"remote (?:from )?anywhere|work from anywhere|globally remote", re.IGNORECASE),
    re.compile(r"(?:contratação|contratacao) (?:via )?(?:pj|clt)", re.IGNORECASE),
)


#: Unidades federativas, por extenso e por sigla. A Gupy devolve `localizacao`
#: como "cidade, estado, país", mas o país às vezes falta — 8 das 320 vagas
#: coletadas vinham só como "São Paulo, São Paulo". Sem reconhecer o estado,
#: essas seriam lidas como estrangeiras e descartadas.
_UF_BRASIL: frozenset[str] = frozenset({
    "acre", "alagoas", "amapa", "amazonas", "bahia", "ceara", "distrito federal",
    "espirito santo", "goias", "maranhao", "mato grosso", "mato grosso do sul",
    "minas gerais", "para", "paraiba", "parana", "pernambuco", "piaui",
    "rio de janeiro", "rio grande do norte", "rio grande do sul", "rondonia",
    "roraima", "santa catarina", "sao paulo", "sergipe", "tocantins",
    # Siglas. "pa" e "pr" também são palavras curtas, mas aqui o casamento é
    # contra um segmento inteiro de `localizacao`, não contra texto corrido.
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms",
    "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc",
    "sp", "se", "to",
})

#: Como o país aparece quando vem preenchido.
_NOMES_BRASIL = frozenset({"brasil", "brazil", "br"})


def pais_de_localizacao(localizacao: str) -> str | None:
    """Classifica o campo estruturado de local: ``"BR"``, ``"XX"`` ou ``None``.

    ``None`` é indeterminado — local vazio, "Remoto", "Home office" — e não
    descarta ninguém. ``"XX"`` é estrangeiro sem dizer qual país, que é tudo o
    que o filtro precisa saber.

    A lógica é invertida de propósito: reconhecer o que é brasileiro e tratar o
    resto como fora. Enumerar países do mundo daria uma lista infinita e sempre
    desatualizada, e o corpus mostra por que não vale — de 320 vagas da Gupy, as
    estrangeiras eram Chile, México e Portugal, nenhum deles na lista de quatro
    países que existia (US, CA, GB, BR), montada quando só havia Greenhouse.

    Trabalha sobre `localizacao`, não sobre a descrição: é campo estruturado da
    API, e "Data Engineer [remote from EU]" com local "Portugal" passava batido
    porque nem "Portugal" nem "remote from EU" apareciam no casamento textual.
    """
    if not localizacao or not localizacao.strip():
        return None

    segmentos = [
        _sem_acento(s.strip().lower())
        for s in localizacao.split(",")
        if s.strip()
    ]
    if not segmentos:
        return None

    if any(s in _NOMES_BRASIL or s in _UF_BRASIL for s in segmentos):
        return "BR"

    # Um segmento só e genérico ("Remoto", "Home office") não afirma país.
    if len(segmentos) == 1 and segmentos[0] in _LOCAIS_GENERICOS:
        return None

    return "XX"


#: Valores que aparecem no lugar do local sem nomear lugar nenhum.
_LOCAIS_GENERICOS = frozenset({
    "remoto", "remote", "home office", "homeoffice", "hibrido", "presencial",
    "a combinar", "diversos", "varios", "nacional",
})


def _sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


@dataclass(frozen=True)
class Avaliacao:
    """Decisão de elegibilidade com a evidência que a sustenta."""

    estado: Elegibilidade
    evidencias: list[str] = field(default_factory=list)
    categoria: str = ""

    @property
    def descarta(self) -> bool:
        """Só INELEGIVEL descarta. INCERTA segue para análise."""
        return self.estado is Elegibilidade.INELEGIVEL

    def para_json(self) -> dict:
        return {
            "geographic_eligibility": str(self.estado),
            "eligibility_evidence": self.evidencias,
            "eligibility_category": self.categoria,
        }


def _perfil_precisa_sponsorship(perfil: dict, pais: str = "US") -> bool:
    """O candidato precisaria de patrocínio de visto para este país?

    Fato, não preferência: derivado dos países em que o candidato declara ter
    autorização de trabalho. Nunca inferido de endereço ou nacionalidade.
    """
    autorizados = {
        str(p).strip().upper()
        for p in (perfil.get("paises_autorizados") or [])
    }
    return pais.upper() not in autorizados


def avaliar_texto(texto: str, perfil: dict | None = None) -> Avaliacao:
    """Elegibilidade a partir de sinais EXPLÍCITOS no texto. Para o filtro 4A.

    Conservador de propósito: na dúvida devolve NAO_ESPECIFICADA, que não
    descarta. O custo de um falso negativo aqui é perder uma vaga boa
    silenciosamente — pior que gastar uma normalização a mais.
    """
    if not texto:
        return Avaliacao(Elegibilidade.NAO_ESPECIFICADA)

    perfil = perfil or {}

    # Contra-sinal primeiro: uma vaga que menciona Brasil ou LATAM não é
    # descartada por conter linguagem de autorização em outro trecho.
    if any(p.search(texto) for p in _ACEITA_BRASIL):
        return Avaliacao(
            Elegibilidade.ELEGIVEL,
            ["texto menciona Brasil, LATAM ou remoto global"],
            "aceita_regiao",
        )

    achados = [(cat, m.group(0).strip()) for cat, p in _PADROES if (m := p.search(texto))]
    if not achados:
        return Avaliacao(Elegibilidade.NAO_ESPECIFICADA)

    categorias = {c for c, _ in achados}
    evidencias = [t[:120] for _, t in achados[:4]]

    # Ausência de sponsorship só é impedimento se o candidato precisaria dele.
    if categorias == {"sem_sponsorship"}:
        if _perfil_precisa_sponsorship(perfil):
            return Avaliacao(Elegibilidade.INELEGIVEL, evidencias, "sem_sponsorship")
        return Avaliacao(Elegibilidade.ELEGIVEL, evidencias, "sponsorship_desnecessario")

    return Avaliacao(
        Elegibilidade.INELEGIVEL, evidencias, sorted(categorias)[0],
    )


def avaliar_normalizado(normalizado: dict, perfil: dict | None = None) -> Avaliacao:
    """Elegibilidade a partir do JSON normalizado. Para o filtro 4B.

    Usa os campos estruturados quando existem; cai para o texto quando não.
    """
    perfil = perfil or {}
    pais_candidato = (perfil.get("pais_residencia") or "BR").strip().upper()

    paises_ok = {
        str(p).strip().upper()
        for p in (normalizado.get("eligible_residence_countries") or [])
    }
    if paises_ok:
        if pais_candidato in paises_ok:
            return Avaliacao(
                Elegibilidade.ELEGIVEL,
                [f"países aceitos incluem {pais_candidato}"], "residencia",
            )
        return Avaliacao(
            Elegibilidade.INELEGIVEL,
            [f"países aceitos: {sorted(paises_ok)}; candidato em {pais_candidato}"],
            "residencia",
        )

    if normalizado.get("work_authorization_required"):
        paises_trabalho = {
            str(p).strip().upper()
            for p in (normalizado.get("work_location_country") or [])
        }
        autorizados = {
            str(p).strip().upper()
            for p in (perfil.get("paises_autorizados") or [pais_candidato])
        }
        if paises_trabalho and not (paises_trabalho & autorizados):
            if normalizado.get("sponsorship_available"):
                return Avaliacao(
                    Elegibilidade.INCERTA,
                    [f"exige autorização em {sorted(paises_trabalho)}, "
                     "mas oferece sponsorship"],
                    "autorizacao",
                )
            return Avaliacao(
                Elegibilidade.INELEGIVEL,
                [f"exige autorização em {sorted(paises_trabalho)}, "
                 f"candidato autorizado em {sorted(autorizados)}"],
                "autorizacao",
            )

    return Avaliacao(Elegibilidade.NAO_ESPECIFICADA)


# ── Extração estruturada, para o normalizador determinístico ──────────────────

#: País → padrões que indicam trabalho ou autorização ali.
#: Fronteira de palavra é obrigatória: sem ela "usa" casa dentro de "causa" e
#: "usar", e em vaga escrita em português isso detectaria os EUA em quase todas.
_PAISES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("US", (r"\bunited states\b", r"\bu\.s\.a?\.?", r"\busa\b", r"\bus[- ]based\b")),
    ("CA", (r"\bcanada\b", r"\bcanadian\b")),
    ("GB", (r"\bunited kingdom\b", r"\buk[- ]based\b")),
    ("BR", (r"\bbrazil\b", r"\bbrasil\b")),
)

_PADROES_PAIS = tuple(
    (codigo, tuple(re.compile(p, re.IGNORECASE) for p in padroes))
    for codigo, padroes in _PAISES
)

#: Nome citado no escopo do remoto → código do país.
_CODIGO_POR_NOME = {
    "united states": "US", "us": "US", "usa": "US",
    "canada": "CA", "uk": "GB", "brazil": "BR", "brasil": "BR",
}

_RE_AUTORIZACAO = re.compile(
    r"authorized to work|work authorization|right to work|work permit"
    r"|autoriza\u00e7\u00e3o de trabalho|visto de trabalho",
    re.IGNORECASE,
)
_RE_SPONSORSHIP_NAO = re.compile(
    r"(?:not|unable to|no)\s+(?:able to\s+)?(?:provide|offer|sponsor)\w*"
    r"|sponsorship (?:is )?not available|no visa sponsorship",
    re.IGNORECASE,
)
_RE_SPONSORSHIP_SIM = re.compile(
    r"sponsorship (?:is )?available|visa sponsorship provided"
    r"|(?:we|company)\s+(?:do|will|can)\s+sponsor",
    re.IGNORECASE,
)
_RE_REMOTO_RESTRITO = re.compile(
    r"remote (?:within|in|from) (?:the )?"
    r"(united states|usa|us|canada|uk|brazil|brasil)\b",
    re.IGNORECASE,
)
_RE_REMOTO_GLOBAL = re.compile(
    r"remote (?:from )?anywhere|work from anywhere|globally remote"
    r"|fully distributed",
    re.IGNORECASE,
)


def extrair_geografia(texto: str) -> dict:
    """Campos geográficos estruturados a partir do texto da vaga.

    Consumido pelo filtro 4B. Conservador: só afirma o que o texto sustenta.
    ``eligible_residence_countries`` fica vazio quando a vaga não restringe
    explicitamente — e vazio não descarta ninguém. Preencher por inferência aqui
    produziria descarte de vaga elegível, que é o erro mais caro deste filtro
    porque é silencioso.
    """
    if not texto:
        return {
            "work_location_country": [],
            "eligible_residence_countries": [],
            "remote_scope": None,
            "work_authorization_required": False,
            "sponsorship_available": None,
        }

    paises = [
        codigo for codigo, padroes in _PADROES_PAIS
        if any(p.search(texto) for p in padroes)
    ]

    escopo = None
    if _RE_REMOTO_GLOBAL.search(texto):
        escopo = "global"
    elif m := _RE_REMOTO_RESTRITO.search(texto):
        codigo = _CODIGO_POR_NOME.get(m.group(1).lower())
        escopo = f"country_only:{codigo}" if codigo else None

    # A negativa é testada primeiro: "we do not offer sponsorship" contém
    # "sponsorship", e a ordem inversa marcaria disponível.
    if _RE_SPONSORSHIP_NAO.search(texto):
        sponsorship = False
    elif _RE_SPONSORSHIP_SIM.search(texto):
        sponsorship = True
    else:
        sponsorship = None

    return {
        "work_location_country": paises,
        "eligible_residence_countries": [],
        "remote_scope": escopo,
        "work_authorization_required": bool(_RE_AUTORIZACAO.search(texto)),
        "sponsorship_available": sponsorship,
    }


# ── Vaga afirmativa ───────────────────────────────────────────────────────────
#
# Vaga afirmativa é reservada por lei ou por política a um grupo. Candidatar-se
# sem pertencer a ele ocupa uma posição criada para corrigir desigualdade, e é
# descartado na primeira triagem — custa tempo dos dois lados.
#
# O acervo tem 136 delas: 119 para PCD, 13 para mulheres, 4 para pessoas negras.
# Cinco chegaram vivas à fila, uma **aprovada com score 84**. O score não tem
# como saber: ele mede aderência técnica, e a barreira aqui não é técnica.
#
# **A elegibilidade é um fato que só o candidato conhece, e o sistema não
# presume nenhum lado.** Sem declaração na config, a vaga é descartada com o
# motivo dizendo como declarar — o oposto (presumir elegível) mandaria
# candidatura que não deveria existir, e presumir em silêncio esconderia de um
# candidato PCD 119 vagas feitas para ele.

#: Marca de que a vaga é afirmativa. Só linguagem inequívoca: "diversidade" e
#: "inclusão" aparecem no rodapé institucional de metade dos anúncios e não
#: reservam nada.
_MARCA_AFIRMATIVA = (
    "afirmativa", "afirmativo", "affirmative action", "exclusiva para",
    "exclusivo para", "vaga destinada", "reservada para", "reservado para",
)

#: Grupo → termos no título. Um grupo por chave; a config usa estas chaves.
PROGRAMAS_AFIRMATIVOS: dict[str, tuple[str, ...]] = {
    "pcd": ("pcd", "deficien", "com deficiencia", "neurodiver"),
    "mulheres": ("mulher", "women", "feminin"),
    "pessoas_negras": ("negra", "negro", "pretas", "pretos", "black", "racial"),
    "lgbtqia": ("lgbt", "trans ", "nao binari"),
    "indigenas": ("indigena",),
    "50_mais": ("50+", "maturidade", "melhor idade"),
    "refugiados": ("refugiad",),
}


def programa_afirmativo(titulo: str, descricao: str = "") -> str | None:
    """Grupo a que a vaga é reservada, `"indeterminado"`, ou None se não é.

    Lê sobretudo o título: é onde a reserva é anunciada, e a descrição costuma
    trazer texto institucional sobre diversidade que não reserva nada. A
    descrição entra só para identificar o grupo quando o título diz "afirmativa"
    sem dizer para quem.
    """
    # `_sem_acento` preserva a caixa, e as listas abaixo são minúsculas:
    # sem o `.lower()` aqui, "Afirmativa PCD" e "Affirmative Action" não
    # casavam — três dos quatro títulos reais do acervo passavam batido.
    t = _sem_acento(titulo or "").lower()
    if not any(m in t for m in _MARCA_AFIRMATIVA):
        return None
    for grupo, termos in PROGRAMAS_AFIRMATIVOS.items():
        if any(x in t for x in termos):
            return grupo
    d = _sem_acento(descricao or "").lower()[:1500]
    for grupo, termos in PROGRAMAS_AFIRMATIVOS.items():
        if any(x in d for x in termos):
            return grupo
    return "indeterminado"


def elegivel_ao_programa(grupo: str | None, perfil: dict | None) -> bool:
    """O candidato declarou pertencer a este grupo?

    Ausência de declaração é "não", nunca "talvez": a vaga é reservada, e quem
    não declarou não pode ocupá-la. `indeterminado` também é "não" — sem saber a
    quem a vaga se destina, não há como afirmar elegibilidade.
    """
    if grupo is None:
        return True
    declarados = {
        str(g).strip().lower()
        for g in ((perfil or {}).get("programas_afirmativos") or [])
    }
    return grupo in declarados
