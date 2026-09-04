"""Normalização e scoring sem nenhuma chamada de LLM.

Normalizar uma vaga é **extração**, não julgamento: senioridade está no título,
tecnologias estão num vocabulário fechado, anos de experiência estão numa frase
com número. É também a etapa de maior volume — milhares de vagas por ciclo — e
portanto a que dominava o custo de API.

O scoring aqui é a metade determinística do desenho híbrido: requisito
obrigatório, senioridade, idioma e localização são regra, não opinião de modelo.
Onde um LLM ganharia é em equivalência semântica entre tecnologias, e isso está
coberto por uma tabela curada em `vocabulario.EQUIVALENCIAS`.

Produz exatamente o mesmo formato dos módulos que usam LLM, então nada a jusante
muda — o PDF, os filtros e o orquestrador não sabem qual caminho gerou o dado.
"""
import logging
import re

from jobapplier import vocabulario as vocab
from jobapplier.elegibilidade import extrair_geografia as _geografia
from jobapplier.elegibilidade import pais_de_localizacao as _pais_do_local

logger = logging.getLogger(__name__)

#: Ruído comum em títulos de anúncio, removido para obter o cargo limpo.
_RE_RUIDO_TITULO = (
    re.compile(r"\s*\(.*?\)\s*"),                       # (Remoto), (SP), (PJ)
    re.compile(r"\s*[\[\{].*?[\]\}]\s*"),               # [Urgente]
    re.compile(r"\s*[-–—|]\s*(?:remoto|remote|híbrido|hibrido|presencial|home office)\b.*$", re.I),
    re.compile(r"\s*[-–—|]\s*[A-Z]{2}\s*$"),            # "- SP"
    re.compile(r"\s*#?\d{4,}\s*$"),                     # id de requisição
    re.compile(r"\s*[-–—|]\s*(?:vaga afirmativa|pcd|exclusiva).*$", re.I),
)


def limpar_cargo(titulo: str) -> str:
    """Título sem marcação de local, modalidade e id de requisição."""
    if not titulo:
        return ""
    limpo = titulo
    for padrao in _RE_RUIDO_TITULO:
        limpo = padrao.sub(" ", limpo)
    limpo = re.sub(r"\s{2,}", " ", limpo).strip(" -–—|,")
    return limpo or titulo.strip()


def _geografia_completa(titulo: str, localizacao: str, descricao: str) -> dict:
    """Geografia do texto, corrigida pelo campo estruturado de local.

    O casamento textual só conhecia quatro países (US, CA, GB, BR) porque foi
    escrito quando só havia Greenhouse. Com a Gupy no pipeline apareceram Chile,
    México e Portugal — e "Data Engineer [remote from EU]" com `localizacao`
    igual a "Portugal" passava com score 86, perto do topo da lista, para uma
    vaga que exige autorização de trabalho na União Europeia.

    O campo `localizacao` da API é mais confiável que o texto: é estruturado e
    curto. Quando ele afirma um país estrangeiro, isso prevalece.
    """
    geografia = _geografia("\n".join((titulo, localizacao, descricao)))

    pais = _pais_do_local(localizacao)
    if pais == "XX":
        paises = list(geografia.get("work_location_country") or [])
        if "BR" not in paises:
            geografia["work_location_country"] = [*paises, "XX"]
            geografia["work_authorization_required"] = True
    return geografia


def normalizar(vaga) -> dict:
    """Extrai os campos estruturados de uma vaga. Nunca falha, nunca chama rede.

    Mesmo formato de `agents.normalizer.normalize`, para ser intercambiável.
    """
    titulo = getattr(vaga, "titulo", "") or ""
    empresa = getattr(vaga, "empresa", "") or ""
    localizacao = getattr(vaga, "localizacao", "") or ""
    descricao = getattr(vaga, "descricao", "") or ""

    texto = f"{titulo}\n{descricao}"

    return {
        "cargo": limpar_cargo(titulo),
        "senioridade": vocab.senioridade_em(titulo, descricao),
        "tecnologias": vocab.tecnologias_em(texto),
        "anos_experiencia_minimo": vocab.anos_exigidos(descricao),
        "localizacao": localizacao.strip() or None,
        "modalidade": vocab.modalidade_em(localizacao, titulo, descricao),
        "salario": vocab.salario_em(descricao),
        "soft_skills": vocab.soft_skills_em(descricao),
        "idioma_principal": vocab.idioma_em(descricao),
        "setor_empresa": vocab.setor_em(empresa, descricao),
        # Campos geográficos estruturados, consumidos pelo filtro 4B. Separam
        # quatro dimensões que o sistema antes tratava como uma: onde a vaga
        # está, de onde dá para trabalhar, onde é preciso residir e onde é
        # preciso ter autorização.
        **_geografia_completa(titulo, localizacao, descricao),
        # Marca a origem: sem isto não há como saber depois se um score veio de
        # extração ou de modelo, nem comparar a qualidade dos dois.
        "_origem": "deterministica",
    }



# ── Scoring ───────────────────────────────────────────────────────────────────
# Pesos idênticos aos do scorer por LLM, para os scores serem comparáveis.
PESO_SKILLS = 40
PESO_SENIORIDADE = 20
PESO_SETOR = 15
PESO_IDIOMA = 15
PESO_LOCALIZACAO = 10


def _pontuar_skills(tec_vaga: list[str], tec_curriculo: set[str]) -> tuple[float, list[str], list[str]]:
    """Cobertura das tecnologias da vaga pelo currículo, com crédito parcial.

    Equivalente conta menos que idêntico: quem usou Azure Data Factory sabe
    orquestrar, mas não conhece as particularidades do Airflow.
    """
    if not tec_vaga:
        # Vaga sem tecnologia reconhecida não é evidência de incompatibilidade;
        # é falta de informação. Crédito neutro, não zero.
        return PESO_SKILLS * 0.5, [], []

    creditos = 0.0
    presentes: list[str] = []
    ausentes: list[str] = []

    for tec in tec_vaga:
        if tec in tec_curriculo:
            creditos += 1.0
            presentes.append(tec)
        elif any(vocab.sao_equivalentes(tec, t) for t in tec_curriculo):
            creditos += vocab.PESO_EQUIVALENTE
            presentes.append(f"{tec} (equivalente)")
        else:
            ausentes.append(tec)

    return PESO_SKILLS * (creditos / len(tec_vaga)), presentes, ausentes


def _pontuar_senioridade(exigida: str, anos_candidato: float, anos_min: int | None) -> tuple[float, str | None]:
    nivel = vocab.ORDEM_SENIORIDADE.get(exigida, 0)

    if anos_min is not None and anos_candidato + 0.5 < anos_min:
        falta = anos_min - anos_candidato
        return PESO_SENIORIDADE * 0.3, (
            f"exige {anos_min} anos, candidato tem {anos_candidato:.1f} "
            f"(faltam {falta:.1f})"
        )

    if nivel == 0:
        return PESO_SENIORIDADE * 0.7, None

    # Faixa aproximada de anos por nível no mercado brasileiro de dados.
    faixas = {1: (0, 2), 2: (2, 5), 3: (4, 8), 4: (6, 99), 5: (6, 99)}
    minimo, maximo = faixas.get(nivel, (0, 99))

    if minimo <= anos_candidato <= maximo:
        return float(PESO_SENIORIDADE), None
    if anos_candidato > maximo:
        # Sobrequalificado ainda dá conta do trabalho; só reduz o encaixe.
        return PESO_SENIORIDADE * 0.75, f"candidato acima do nível pedido ({exigida})"
    return PESO_SENIORIDADE * 0.4, f"abaixo do nível pedido ({exigida})"


def _pontuar_idioma(exigido: str, idiomas_curriculo: list[dict]) -> tuple[float, str | None]:
    if exigido != "Inglês":
        return float(PESO_IDIOMA), None

    for idioma in idiomas_curriculo:
        nome = (idioma.get("nome") or "").lower()
        if "inglês" in nome or "ingles" in nome or "english" in nome:
            nivel = (idioma.get("nivel") or "").lower()
            if any(n in nivel for n in ("avançado", "avancado", "fluente", "nativo", "advanced", "fluent")):
                return float(PESO_IDIOMA), None
            if any(n in nivel for n in ("intermediário", "intermediario", "intermediate")):
                return PESO_IDIOMA * 0.6, "inglês intermediário para vaga que exige inglês"
            return PESO_IDIOMA * 0.3, f"inglês {nivel or 'básico'} para vaga em inglês"

    return 0.0, "vaga exige inglês e o currículo não lista o idioma"


def _pontuar_localizacao(modalidade: str, loc_vaga: str | None, loc_candidato: str) -> tuple[float, str | None]:
    if modalidade == "Remoto":
        return float(PESO_LOCALIZACAO), None

    candidato = (loc_candidato or "").lower()
    vaga_loc = (loc_vaga or "").lower()
    if not vaga_loc:
        return PESO_LOCALIZACAO * 0.7, None

    # Compara a cidade, que é o que determina deslocamento.
    cidade_candidato = candidato.split(",")[0].strip()
    if cidade_candidato and cidade_candidato in vaga_loc:
        return float(PESO_LOCALIZACAO), None

    if modalidade == "Presencial":
        return 0.0, f"presencial em {loc_vaga}, candidato em {loc_candidato}"
    return PESO_LOCALIZACAO * 0.4, f"híbrido em {loc_vaga}, candidato em {loc_candidato}"


def _pontuar_setor(setor_vaga: str | None, setores_candidato: set[str]) -> tuple[float, str | None]:
    if not setor_vaga:
        return PESO_SETOR * 0.6, None
    if setor_vaga in setores_candidato:
        return float(PESO_SETOR), None
    return PESO_SETOR * 0.45, f"sem experiência prévia no setor {setor_vaga}"


def pontuar(vaga, resume_json: dict, anos_experiencia: float) -> dict:
    """Score determinístico de 0 a 100. Mesmo formato do scorer por LLM, mais campos.

    Os campos extras — `hard_requirements_met`, `missing_required`, `confidence` —
    existem porque um número sozinho não sustenta a decisão de candidatar. Uma
    vaga pode pontuar bem e ainda assim ter um requisito eliminatório ausente.
    """
    normalizado = getattr(vaga, "normalizado_json", None) or {}

    tec_vaga = normalizado.get("tecnologias") or []
    tec_curriculo = {vocab.canonizar(t) for t in (resume_json.get("tecnologias") or [])}
    tec_curriculo.discard("")

    setores_candidato = {
        s for s in (
            vocab.setor_em(e.get("empresa", ""), " ".join(
                e.get("descricao", []) if isinstance(e.get("descricao"), list)
                else [str(e.get("descricao") or "")]
            ))
            for e in (resume_json.get("experiencias") or [])
        ) if s
    }

    p_skills, presentes, ausentes = _pontuar_skills(tec_vaga, tec_curriculo)
    p_sen, obs_sen = _pontuar_senioridade(
        normalizado.get("senioridade") or "Desconhecida",
        anos_experiencia,
        normalizado.get("anos_experiencia_minimo"),
    )
    p_setor, obs_setor = _pontuar_setor(normalizado.get("setor_empresa"), setores_candidato)
    p_idioma, obs_idioma = _pontuar_idioma(
        normalizado.get("idioma_principal") or "Desconhecida",
        resume_json.get("idiomas") or [],
    )
    p_local, obs_local = _pontuar_localizacao(
        normalizado.get("modalidade") or "Desconhecida",
        normalizado.get("localizacao"),
        resume_json.get("localizacao") or "",
    )

    total = p_skills + p_sen + p_setor + p_idioma + p_local
    gaps = [o for o in (obs_sen, obs_setor, obs_idioma, obs_local) if o]
    if ausentes:
        gaps.append(f"tecnologias da vaga ausentes no currículo: {', '.join(ausentes[:6])}")

    # Confiança NO SCORE — quanto menos a vaga informa, menos o número significa.
    # Deliberadamente NÃO se chama `confidence`: `application_confidence` é outra
    # coisa (se a automação consegue preencher o formulário), vive em
    # `applicators.base` e as duas acabariam no mesmo JSON.
    sinais = sum([
        bool(tec_vaga),
        normalizado.get("senioridade", "Desconhecida") != "Desconhecida",
        normalizado.get("modalidade", "Desconhecida") != "Desconhecida",
        bool(normalizado.get("setor_empresa")),
        normalizado.get("idioma_principal", "Desconhecida") != "Desconhecida",
    ])
    confianca = round(sinais / 5, 2)

    return {
        "score": round(max(0.0, min(100.0, total)), 1),
        "breakdown": {
            "skills_tecnicas": round(p_skills, 1),
            "senioridade": round(p_sen, 1),
            "setor": round(p_setor, 1),
            "idioma": round(p_idioma, 1),
            "localizacao": round(p_local, 1),
        },
        "motivos_positivos": presentes[:8] or ["nenhuma tecnologia da vaga reconhecida"],
        "gaps": gaps,
        "resumo": (
            f"{len(presentes)}/{len(tec_vaga)} tecnologias cobertas"
            if tec_vaga else "vaga sem tecnologias reconhecíveis na descrição"
        ),
        "perfil_base_sugerido": _sugerir_perfil(tec_vaga, normalizado.get("cargo", "")),
        # Campos que o scorer por LLM não produz.
        "hard_requirements_met": not ausentes,
        "missing_required": ausentes,
        "confianca_score": confianca,
        "_origem": "deterministica",
    }


#: Perfil base → tecnologias e termos que o caracterizam.
_PERFIS = (
    ("analytics_engineer", ("dbt", "Modelagem Dimensional", "Snowflake", "BigQuery"),
     ("analytics engineer", "analytics")),
    ("cloud_data_engineer", ("Azure", "AWS", "GCP", "Terraform", "Kubernetes", "Docker"),
     ("cloud", "infraestrutura", "plataforma")),
    ("bi_analyst", ("Power BI", "Tableau", "Looker", "Qlik", "Metabase", "Excel"),
     ("business intelligence", " bi ", "analista de dados", "data analyst")),
    ("data_engineer", ("Airflow", "Spark", "Kafka", "ETL/ELT", "Databricks"),
     ("data engineer", "engenheiro de dados", "engenharia de dados")),
)


def _sugerir_perfil(tec_vaga: list[str], cargo: str) -> str:
    cargo_baixo = (cargo or "").lower()
    melhor, melhor_nota = "data_engineer", -1.0

    for perfil, tecnologias, termos in _PERFIS:
        nota = sum(1 for t in tecnologias if t in tec_vaga)
        # O cargo no título é sinal mais forte que a stack: uma vaga de BI cita
        # SQL e Python como qualquer outra.
        nota += 2.5 * sum(1 for t in termos if t in cargo_baixo)
        if nota > melhor_nota:
            melhor, melhor_nota = perfil, nota

    return melhor
