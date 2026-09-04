"""Perfis de currículo derivados do mestre, nunca copiados dele.

Antes eram quatro arquivos `data/resumes/resume_base_*.json`, cada um uma cópia
integral do currículo. Cópia diverge, e divergiu: quando `data/resume.json` foi
reescrito, os quatro ficaram para trás carregando **fato errado** —

- FIAP como "em andamento" nos quatro, sendo que o curso está concluído;
- telefone ausente nos quatro, e o gerador de PDF lê `telefone`: todo currículo
  enviado saiu sem número de contato;
- o cliente nomeado em dois deles, quando o mestre diz "ambiente regulado" de
  propósito — o nome do cliente ia para o concorrente dele;
- certificações já podadas no mestre (12 para 3) ainda presentes, 9 num caso.

Nada disso apareceu no score, porque o score lê o mestre. Só o PDF lia as cópias,
e ninguém compara PDF com JSON. É a invariante 9 no caso geral: o artefato que
chega ao recrutador tinha uma fonte de verdade própria, e ela apodreceu.

Aqui o perfil não guarda fato nenhum. Guarda **ênfase**: o resumo profissional e
a ordem das tecnologias. Empresa, cargo, data, formação, certificação e contato
vêm do mestre em toda geração. Um fato errado passa a ser impossível de existir
só num perfil — ou está errado no mestre, para todos, ou está certo.

`tests/unit/test_perfis.py` trava isso: se algum perfil ou algum idioma divergir
do mestre em fato, o teste falha.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from jobapplier import paths

logger = logging.getLogger(__name__)

PADRAO = "data_engineer"

#: Mestre por idioma. O de inglês existe porque metade da fila está em inglês e
#: o ATS casa termo literal — "Engenharia de Dados" não bate com "Data
#: Engineering". Traduzido uma vez, à mão, e não a cada geração: tradução em
#: tempo de execução custaria uma chamada de LLM por vaga e daria texto
#: diferente a cada rodada, impossível de revisar.
MESTRES = {"pt": paths.RESUME_JSON, "en": paths.DATA / "resume_en.json"}

#: Termos descritivos que mudam de idioma. Nome próprio (Snowflake, Terraform,
#: Power BI) não entra: é igual nos dois e mapeá-lo só criaria manutenção.
_EQUIV_EN = {
    "Modelagem Dimensional": "Dimensional Modeling",
    "Arquitetura Medallion": "Medallion Architecture",
    "Governança de Dados": "Data Governance",
    "APIs REST": "REST APIs",
}


@dataclass(frozen=True)
class Perfil:
    """Ênfase de um perfil. Nenhum fato mora aqui — só resumo e ordem."""

    chave: str
    rotulo: str
    resumo: dict[str, str]
    #: Tecnologias que sobem para o topo da lista, na ordem declarada. Declaradas
    #: em português e traduzidas por `_EQUIV_EN`; o resto da lista do mestre
    #: segue depois, na ordem original. Nada é removido — o ATS lê a lista
    #: inteira, e esconder tecnologia real só perde casamento de palavra-chave.
    enfase: tuple[str, ...] = field(default_factory=tuple)


PERFIS: dict[str, Perfil] = {
    "data_engineer": Perfil(
        chave="data_engineer",
        rotulo="Engenheiro de Dados",
        resumo={
            "pt": "Engenheiro de Dados com dois anos de atuação em pipelines de "
                  "ingestão e transformação em Snowflake, Azure Data Factory e "
                  "Databricks, com progressão de analista pleno a coordenação. "
                  "Modelagem em camadas medallion, otimização de custo e "
                  "performance de processamento, infraestrutura como código em "
                  "Terraform e CI/CD em GitHub Actions. Também entrego a camada "
                  "de consumo: definição de métricas e dashboards em Power BI.",
            "en": "Data Engineer with two years building ingestion and "
                  "transformation pipelines on Snowflake, Azure Data Factory and "
                  "Databricks, progressing from mid-level analyst to "
                  "coordination. Medallion-layer modeling, processing cost and "
                  "performance optimization, infrastructure as code with "
                  "Terraform and CI/CD with GitHub Actions. Also delivering the "
                  "consumption layer: metric definition and Power BI dashboards.",
        },
        enfase=("Python", "SQL", "Snowflake", "Azure Data Factory", "Databricks",
                "ETL/ELT", "Arquitetura Medallion", "Azure", "Terraform"),
    ),
    "analytics_engineer": Perfil(
        chave="analytics_engineer",
        rotulo="Analytics Engineer",
        resumo={
            "pt": "Analytics Engineer com dois anos entre a camada de "
                  "transformação e a de consumo: modelagem em camadas medallion "
                  "no Snowflake, padronização de métricas e entrega de "
                  "dashboards em Power BI. Otimização de queries e custo de "
                  "processamento, governança de tabelas e esquemas com "
                  "documentação de modelo, com progressão de analista pleno a "
                  "coordenação.",
            "en": "Analytics Engineer with two years spanning the transformation "
                  "and consumption layers: medallion-layer modeling on "
                  "Snowflake, metric standardization and Power BI dashboard "
                  "delivery. Query and processing cost optimization, table and "
                  "schema governance with data model documentation, progressing "
                  "from mid-level analyst to coordination.",
        },
        enfase=("SQL", "Snowflake", "Modelagem Dimensional",
                "Arquitetura Medallion", "Python", "ETL/ELT", "Power BI",
                "Databricks", "Governança de Dados"),
    ),
    "bi_analyst": Perfil(
        chave="bi_analyst",
        rotulo="Analista de Business Intelligence",
        resumo={
            "pt": "Profissional de Business Intelligence com dois anos entre a "
                  "definição de métricas e a engenharia que as sustenta: "
                  "dashboards em Power BI, modelagem dimensional e pipelines em "
                  "Snowflake e Azure Data Factory. Tuning de queries de "
                  "relatórios críticos e governança de tabelas e esquemas, com "
                  "progressão de analista pleno a coordenação.",
            "en": "Business Intelligence professional with two years spanning "
                  "metric definition and the engineering behind it: Power BI "
                  "dashboards, dimensional modeling and pipelines on Snowflake "
                  "and Azure Data Factory. Query tuning for critical reports and "
                  "table and schema governance, progressing from mid-level "
                  "analyst to coordination.",
        },
        enfase=("Power BI", "SQL", "Modelagem Dimensional", "Snowflake",
                "ETL/ELT", "Python", "Governança de Dados"),
    ),
    "cloud_data_engineer": Perfil(
        chave="cloud_data_engineer",
        rotulo="Engenheiro de Dados Cloud",
        resumo={
            "pt": "Engenheiro de Dados com dois anos em plataforma de dados no "
                  "Azure: provisionamento com Terraform, com VNet, private "
                  "endpoints e Key Vault versionados por ambiente, e CI/CD em "
                  "GitHub Actions validando pull request. Pipelines em "
                  "Snowflake, Azure Data Factory e Databricks, com modelagem em "
                  "camadas medallion e otimização de custo de processamento.",
            "en": "Data Engineer with two years on Azure data platforms: "
                  "Terraform provisioning, with VNet, private endpoints and Key "
                  "Vault versioned per environment, and CI/CD with GitHub "
                  "Actions validating pull requests. Pipelines on Snowflake, "
                  "Azure Data Factory and Databricks, with medallion-layer "
                  "modeling and processing cost optimization.",
        },
        enfase=("Azure", "Terraform", "IaC", "VNet", "Private Endpoints",
                "Key Vault", "Microsoft Sentinel", "SIEM", "CI/CD",
                "GitHub Actions", "Azure Data Factory", "Snowflake",
                "Databricks", "Python", "SQL"),
    ),
}


def resolver(sugerido: object) -> str:
    """Normaliza o perfil sugerido pelo normalizador para uma chave conhecida.

    O scorer pode devolver o enum inteiro (`"data_engineer|analytics_engineer|
    ..."`) quando o modelo ecoa o formato do prompt em vez de escolher — daí o
    corte no primeiro `|`. Sugestão desconhecida cai no padrão: um perfil novo
    inventado pelo modelo não pode derrubar a geração inteira.
    """
    chave = str(sugerido or "").split("|")[0].strip().lower()
    if chave in PERFIS:
        return chave
    if chave:
        logger.debug("Perfil '%s' desconhecido — usando '%s'.", chave, PADRAO)
    return PADRAO


def carregar_mestre(idioma: str, padrao: dict | None = None) -> dict:
    """Currículo mestre no idioma pedido, com queda para o padrão recebido.

    Idioma indefinido não é inglês: sem certeza, fica o currículo em português,
    que é o do arquivo base. Chutar inglês numa vaga bilíngue mandaria currículo
    em inglês para recrutador brasileiro sem nenhum sinal de que isso ocorreu.
    """
    # Vazio é tratado como ausente, não como "o candidato não tem nada": um dict
    # sem chave nenhuma vira PDF em branco, e em branco não levanta erro.
    portugues = padrao if padrao else _ler(MESTRES["pt"], {})
    if idioma != "en":
        return portugues
    return _ler(MESTRES["en"], portugues)


def _ler(caminho, alternativa: dict) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Currículo mestre '%s' ilegível (%s) — usando o padrão.",
                       caminho.name, exc)
        return alternativa
    return dados if isinstance(dados, dict) else alternativa


def _ordenar(tecnologias: list, enfase: tuple[str, ...], idioma: str) -> list:
    """Sobe as tecnologias do perfil para o topo, preservando o resto.

    Compara em minúsculas porque o mestre e a ênfase são escritos à mão em
    momentos diferentes, e "power bi" não pode deixar de casar com "Power BI".
    """
    restantes = [t for t in tecnologias if isinstance(t, str)]
    indice = {t.lower(): t for t in restantes}

    topo = []
    for termo in enfase:
        alvo = _EQUIV_EN.get(termo, termo) if idioma == "en" else termo
        real = indice.get(alvo.lower())
        if real is not None and real not in topo:
            topo.append(real)

    return topo + [t for t in restantes if t not in topo]


def montar(perfil: str, idioma: str = "pt", mestre: dict | None = None) -> dict:
    """Currículo base para um perfil: fatos do mestre, ênfase do perfil.

    O mestre é copiado em nível raso e só duas chaves são trocadas. Experiências,
    formação, certificações e contato são referenciados como estão — é isso que
    torna impossível um perfil afirmar algo que o mestre não afirma.
    """
    chave = resolver(perfil)
    spec = PERFIS[chave]
    base = dict(carregar_mestre(idioma, mestre))

    # `_nota` e afins documentam o arquivo, não o candidato.
    for interna in [k for k in base if k.startswith("_")]:
        base.pop(interna)

    resumo = spec.resumo.get(idioma) or spec.resumo["pt"]
    base["perfil"] = chave
    base["resumo_profissional"] = resumo

    tecnologias = base.get("tecnologias")
    if isinstance(tecnologias, list):
        base["tecnologias"] = _ordenar(tecnologias, spec.enfase, idioma)

    return base
