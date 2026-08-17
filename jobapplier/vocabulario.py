"""Vocabulário do domínio: tecnologias, senioridade, modalidade, setor.

Existe para que normalização e scoring funcionem **sem nenhuma chamada de LLM**.
Normalizar uma vaga é extração, não julgamento: senioridade está no título,
tecnologias estão num vocabulário fechado, anos de experiência estão numa frase
com número. Nada disso precisa de um modelo — e é justamente o que roda em maior
volume, milhares de vagas por ciclo.

Curado para vagas de dados no Brasil, em português e inglês. Ampliar é editar
listas aqui, não mexer em prompt.
"""
import re

# ── Tecnologias ───────────────────────────────────────────────────────────────
# Nome canônico → variantes que aparecem em anúncio de vaga. O casamento é por
# fronteira de palavra, então entradas curtas ("r", "go") ficariam ambíguas e por
# isso não entram: preferimos perder um match a poluir o score com falso positivo.
TECNOLOGIAS: dict[str, tuple[str, ...]] = {
    # Linguagens e bibliotecas
    "Python": ("python",),
    "SQL": ("sql",),
    "PySpark": ("pyspark",),
    "Spark": ("spark", "apache spark"),
    "Scala": ("scala",),
    "Java": ("java",),
    "JavaScript": ("javascript",),
    "TypeScript": ("typescript",),
    "Pandas": ("pandas",),
    "NumPy": ("numpy",),
    # Data warehouse e lakehouse
    "Snowflake": ("snowflake",),
    "BigQuery": ("bigquery", "big query"),
    "Redshift": ("redshift",),
    "Synapse": ("synapse",),
    "Databricks": ("databricks",),
    "Delta Lake": ("delta lake",),
    # Cloud
    "Azure": ("azure",),
    "AWS": ("aws", "amazon web services"),
    "GCP": ("gcp", "google cloud"),
    # Orquestração e ETL
    "Airflow": ("airflow", "apache airflow"),
    "Azure Data Factory": ("azure data factory", "data factory", "adf"),
    "dbt": ("dbt",),
    "Dagster": ("dagster",),
    "Prefect": ("prefect",),
    "Glue": ("aws glue", "glue"),
    "Fivetran": ("fivetran",),
    "Airbyte": ("airbyte",),
    "NiFi": ("nifi",),
    "Pentaho": ("pentaho",),
    "Informatica": ("informatica",),
    "SSIS": ("ssis",),
    # Streaming
    "Kafka": ("kafka",),
    "Kinesis": ("kinesis",),
    "Event Hubs": ("event hub", "event hubs"),
    "Pub/Sub": ("pub/sub", "pubsub"),
    # BI e visualização
    "Power BI": ("power bi", "powerbi"),
    "Tableau": ("tableau",),
    "Looker": ("looker",),
    "Qlik": ("qlik", "qlikview", "qlik sense"),
    "Metabase": ("metabase",),
    "Superset": ("superset",),
    "Data Studio": ("data studio", "looker studio"),
    "Grafana": ("grafana",),
    # Bancos
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "SQL Server": ("sql server", "sqlserver"),
    "Oracle": ("oracle",),
    "MongoDB": ("mongodb", "mongo"),
    "Cassandra": ("cassandra",),
    "Redis": ("redis",),
    # Infra e DevOps
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "Terraform": ("terraform",),
    "CloudFormation": ("cloudformation",),
    "Git": ("git", "github", "gitlab"),
    "CI/CD": ("ci/cd", "cicd", "integração contínua"),
    "Azure DevOps": ("azure devops",),
    "Jenkins": ("jenkins",),
    "Linux": ("linux",),
    # Modelagem e conceitos
    "Modelagem Dimensional": ("modelagem dimensional", "star schema", "kimball", "snowflake schema"),
    "Data Vault": ("data vault",),
    "Data Mesh": ("data mesh",),
    "Data Lake": ("data lake",),
    "Data Governance": ("governança de dados", "data governance"),
    "ETL/ELT": ("etl", "elt"),
    "Machine Learning": ("machine learning", "aprendizado de máquina"),
    "APIs REST": ("api rest", "apis rest", "rest api", "restful"),
    "GraphQL": ("graphql",),
    "Excel": ("excel",),
}

#: Ferramentas que resolvem o mesmo problema. Experiência numa transfere
#: parcialmente para outra — é o que um avaliador humano consideraria ao ler
#: "Azure Data Factory" no currículo e "AWS Glue" na vaga. Crédito parcial, nunca
#: total: são equivalentes em capacidade, não idênticas.
EQUIVALENCIAS: tuple[frozenset[str], ...] = (
    frozenset({"Azure", "AWS", "GCP"}),
    frozenset({"Snowflake", "BigQuery", "Redshift", "Synapse", "Databricks"}),
    frozenset({"Power BI", "Tableau", "Looker", "Qlik", "Metabase", "Superset", "Data Studio"}),
    frozenset({"Airflow", "Azure Data Factory", "Dagster", "Prefect", "Glue", "NiFi", "SSIS"}),
    frozenset({"Kafka", "Kinesis", "Event Hubs", "Pub/Sub"}),
    frozenset({"Terraform", "CloudFormation"}),
    frozenset({"PostgreSQL", "MySQL", "SQL Server", "Oracle"}),
    frozenset({"Fivetran", "Airbyte"}),
    frozenset({"Spark", "PySpark"}),
)

#: Crédito para tecnologia equivalente mas não idêntica.
PESO_EQUIVALENTE = 0.6

# ── Senioridade ───────────────────────────────────────────────────────────────
# Ordem importa: o primeiro casamento vence, então os termos mais específicos vêm
# antes. "tech lead" tem de ser testado antes de "lead".
SENIORIDADE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Junior", ("júnior", "junior", " jr", "jr.", "trainee", "estágio", "estagiário",
                "estagiario", "entry level", "iniciante", "aprendiz")),
    ("Especialista", ("especialista", "specialist", "staff engineer", "principal",
                      "tech lead", "arquiteto", "architect")),
    ("Gerente", ("gerente", "manager", "coordenador", "coordenadora", "head of",
                 "head de", "diretor", "supervisor")),
    ("Senior", ("sênior", "senior", " sr", "sr.", "pleno/sênior", "pleno/senior")),
    ("Pleno", ("pleno", " pl.", "mid-level", "mid level", "intermediário",
               "intermediario")),
)

#: Escala para comparar exigência da vaga com experiência do candidato.
ORDEM_SENIORIDADE = {
    "Desconhecida": 0, "Junior": 1, "Pleno": 2,
    "Senior": 3, "Especialista": 4, "Gerente": 5,
}

# ── Modalidade ────────────────────────────────────────────────────────────────
MODALIDADE: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Formas masculina e feminina: anúncio escreve tanto "trabalho remoto" quanto
    # "vaga 100% remota". Só a masculina estava na lista.
    ("Remoto", ("100% remoto", "100% remota", "totalmente remoto", "totalmente remota",
                "remoto", "remota", "remote", "home office", "teletrabalho",
                "anywhere", "work from home")),
    ("Híbrido", ("híbrido", "híbrida", "hibrido", "hibrida", "hybrid",
                 "semipresencial", "semi-presencial")),
    ("Presencial", ("presencial", "on-site", "onsite", "no escritório", "in office")),
)

# ── Setor da empresa ──────────────────────────────────────────────────────────
SETOR: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Fintech", ("fintech", "banco", "bank", "pagamentos", "payments", "crédito",
                 "cartão", "investimento", "corretora", "financeira")),
    ("Saúde", ("healthtech", "saúde", "health", "hospital", "clínica", "medicina",
               "farmacêutic", "medical")),
    ("Varejo", ("varejo", "retail", "e-commerce", "ecommerce", "marketplace", "loja")),
    ("Educação", ("edtech", "educação", "education", "ensino", "universidade", "escola")),
    ("Logística", ("logística", "logistica", "logistics", "transporte", "entrega",
                   "delivery", "supply chain", "frete")),
    ("Agronegócio", ("agro", "agronegócio", "agricultura", "agtech")),
    ("Telecom", ("telecom", "telecomunicações", "operadora")),
    ("Seguros", ("seguros", "insurtech", "insurance", "seguradora")),
    ("Energia", ("energia", "energy", "petróleo", "elétrica", "utilities")),
    ("Indústria", ("indústria", "industria", "manufatura", "manufacturing", "fábrica")),
    ("Consultoria", ("consultoria", "consulting", "consultancy")),
    ("Mídia", ("mídia", "media", "streaming", "entretenimento", "publicidade")),
    ("Jogos", ("games", "gaming", "jogos", "game studio")),
    ("RH", ("recursos humanos", "hrtech", "rh tech", "recrutamento")),
    ("Imobiliário", ("proptech", "imobiliári", "real estate")),
    ("Mobilidade", ("mobilidade", "mobility", "ride", "transporte urbano")),
    ("SaaS", ("saas", "software as a service", "plataforma b2b")),
)

# ── Soft skills ───────────────────────────────────────────────────────────────
SOFT_SKILLS: dict[str, tuple[str, ...]] = {
    "Comunicação": ("comunicação", "comunicacao", "communication"),
    "Trabalho em equipe": ("trabalho em equipe", "team work", "teamwork", "colaboração"),
    "Liderança": ("liderança", "lideranca", "leadership", "liderar"),
    "Proatividade": ("proatividade", "proativo", "proactive"),
    "Resolução de problemas": ("resolução de problemas", "problem solving",
                               "solução de problemas"),
    "Pensamento analítico": ("pensamento analítico", "analytical", "analítico"),
    "Autonomia": ("autonomia", "autônomo", "self-starter", "independente"),
    "Organização": ("organização", "organizado", "organization"),
    "Adaptabilidade": ("adaptabilidade", "flexibilidade", "adaptability"),
}

# ── Idioma ────────────────────────────────────────────────────────────────────
#: Inglês *exigido*, não apenas mencionado. "inglês é um diferencial" não conta —
#: por isso os padrões pedem o nível junto.
INGLES_EXIGIDO: tuple[str, ...] = (
    "inglês avançado", "ingles avancado", "inglês fluente", "ingles fluente",
    "inglês intermediário", "ingles intermediario", "fluent in english",
    "advanced english", "english proficiency", "proficiência em inglês",
    "inglês obrigatório", "english required", "must speak english",
)

#: Sinal de que a vaga é conduzida em inglês.
INGLES_PROVAVEL: tuple[str, ...] = (
    "we are looking for", "you will", "requirements:", "responsibilities:",
    "what you'll do", "about the role", "nice to have",
)

# ── Expressões regulares ──────────────────────────────────────────────────────
_RE_ANOS = (
    re.compile(r"(?:mínimo|minimo|pelo menos|no mínimo|acima de|at least|minimum(?:\s+of)?)\s*"
               r"(?:de\s*)?(\d{1,2})\s*\+?\s*(?:anos?|years?)", re.I),
    re.compile(r"(\d{1,2})\s*\+\s*(?:anos?|years?)", re.I),
    re.compile(r"(\d{1,2})\s*(?:a|to|-)\s*\d{1,2}\s*(?:anos?|years?)", re.I),
    re.compile(r"(\d{1,2})\s*(?:anos?|years?)\s*(?:de\s*)?(?:experiência|experiencia|experience)", re.I),
)

_RE_SALARIO = re.compile(
    r"R\$\s?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?(?:\s*(?:a|até|-|–)\s*R?\$?\s?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?)?",
    re.I,
)


def _fronteira(termo: str) -> re.Pattern:
    """Casa o termo como palavra inteira, tolerando pontuação em torno.

    Substring pura causaria falso positivo grosseiro: 'java' dentro de
    'javascript', 'aws' dentro de 'laws'.
    """
    escapado = re.escape(termo)
    return re.compile(rf"(?<![\w.]){escapado}(?![\w])", re.IGNORECASE)


#: Padrões pré-compilados: a normalização roda sobre milhares de vagas por ciclo.
_PADROES_TEC = {
    canonico: tuple(_fronteira(v) for v in variantes)
    for canonico, variantes in TECNOLOGIAS.items()
}
_PADROES_SOFT = {
    canonico: tuple(_fronteira(v) for v in variantes)
    for canonico, variantes in SOFT_SKILLS.items()
}


def tecnologias_em(texto: str) -> list[str]:
    """Tecnologias reconhecidas no texto, em nome canônico e ordem estável."""
    if not texto:
        return []
    return [
        canonico
        for canonico, padroes in _PADROES_TEC.items()
        if any(p.search(texto) for p in padroes)
    ]


def soft_skills_em(texto: str) -> list[str]:
    if not texto:
        return []
    return [
        canonico
        for canonico, padroes in _PADROES_SOFT.items()
        if any(p.search(texto) for p in padroes)
    ]


#: Canônicos ordenados pela variante mais longa, do maior para o menor. Sem isto
#: `canonizar("Azure Data Factory")` devolvia "Azure", porque a iteração pelo
#: dicionário encontrava a entrada mais curta primeiro — e aí a tecnologia perdia
#: a identidade e não casava mais com nenhuma equivalência.
_CANONICOS_POR_ESPECIFICIDADE = sorted(
    TECNOLOGIAS, key=lambda c: max(len(v) for v in TECNOLOGIAS[c]), reverse=True
)


def canonizar(tecnologia: str) -> str:
    """Mapeia uma tecnologia escrita à mão para o nome canônico do vocabulário.

    Usado no currículo, que é escrito por humano: 'powerbi', 'Power-BI' e
    'POWER BI' têm de virar o mesmo termo que a vaga produz.

    Casa do mais específico para o mais genérico: "Azure Data Factory" tem de
    virar "Azure Data Factory", não "Azure".
    """
    if not tecnologia:
        return ""
    alvo = tecnologia.strip()
    for canonico in _CANONICOS_POR_ESPECIFICIDADE:
        if any(p.search(alvo) for p in _PADROES_TEC[canonico]):
            return canonico
    return alvo


def sao_equivalentes(a: str, b: str) -> bool:
    """True se as duas tecnologias resolvem o mesmo problema."""
    if a == b:
        return True
    return any(a in grupo and b in grupo for grupo in EQUIVALENCIAS)


def anos_exigidos(texto: str) -> int | None:
    """Menor exigência de anos encontrada no texto, ou None.

    Menor, não maior: um anúncio que diz "3 a 5 anos" exige 3. Pegar o maior
    inflaria a barreira e descartaria vaga elegível.
    """
    if not texto:
        return None
    achados: list[int] = []
    for padrao in _RE_ANOS:
        for m in padrao.finditer(texto):
            try:
                n = int(m.group(1))
            except (ValueError, IndexError):
                continue
            # Acima de 20 quase sempre é ano de calendário ou ruído.
            if 0 < n <= 20:
                achados.append(n)
    return min(achados) if achados else None


def salario_em(texto: str) -> str | None:
    if not texto:
        return None
    m = _RE_SALARIO.search(texto)
    return m.group(0).strip() if m else None


def _primeiro_match(texto: str, tabela) -> str | None:
    if not texto:
        return None
    baixo = texto.lower()
    for rotulo, termos in tabela:
        if any(t in baixo for t in termos):
            return rotulo
    return None


def senioridade_em(titulo: str, descricao: str = "") -> str:
    """Senioridade da vaga. O título tem precedência sobre a descrição.

    A descrição costuma citar vários níveis ("vaga para pleno, reportando ao
    sênior"); o título é o que a empresa está de fato contratando.
    """
    return (
        _primeiro_match(titulo, SENIORIDADE)
        or _primeiro_match(descricao, SENIORIDADE)
        or "Desconhecida"
    )


def modalidade_em(*textos: str) -> str:
    for texto in textos:
        achado = _primeiro_match(texto, MODALIDADE)
        if achado:
            return achado
    return "Desconhecida"


def setor_em(*textos: str) -> str | None:
    for texto in textos:
        achado = _primeiro_match(texto, SETOR)
        if achado:
            return achado
    return None


def idioma_em(descricao: str) -> str:
    """Idioma principal exigido pela vaga."""
    if not descricao:
        return "Desconhecida"
    baixo = descricao.lower()
    if any(t in baixo for t in INGLES_EXIGIDO):
        return "Inglês"
    # Descrição inteira em inglês implica processo em inglês.
    if sum(1 for t in INGLES_PROVAVEL if t in baixo) >= 2:
        return "Inglês"
    return "Português"
