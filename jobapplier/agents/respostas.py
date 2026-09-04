"""Política de resposta a perguntas de triagem.

O problema real, medido no histórico: 152 das 293 tentativas morreram em pergunta
de triagem, e a maioria delas era **respondível com verdade**. `_auto_answer`
devolvia `None` para "Which BI tools do you have experience with?" com "Power BI"
escrito no currículo. Campo em branco não é neutro — é o mesmo que responder
"não" numa triagem automática, com o agravante de parecer candidatura abandonada.

Então a primeira coisa que este módulo faz não é mentir melhor: é **parar de
deixar em branco o que já é verdade**. Equivalência generosa cobre a maior parte
do buraco. Quem tem Snowflake, Databricks, ADF e Airbyte responde "sim" com
verdade a data warehouse, lakehouse, ETL, orquestração, cloud e modelagem.

Onde a verdade literal não cobre, a postura é graduada por **classe de pergunta**,
não uniforme. A régua não é moral, é sustentação: uma afirmação que você não
consegue defender na entrevista seguinte não te aproxima da vaga, te queima o
contato. Ampliar ênfase é advocacia; afirmar experiência inexistente no assunto
central da vaga é comprar uma entrevista que você perde.

Toda resposta carrega a evidência que a sustenta e um nível de sustentação. As
esticadas ficam registradas para virar o briefing do que você precisa estar
pronto para defender — ver `briefing()`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


class Classe(StrEnum):
    """Classe da pergunta. Determina a postura permitida."""

    #: Nome de empresa, cargo, datas, formação, certificação, salário atual,
    #: autorização de trabalho. Conferível em background check.
    FATO = "fato"
    #: Consentimento, LGPD, política de privacidade, uso de dados.
    CONSENTIMENTO = "consentimento"
    #: Ferramenta ou tecnologia nomeada: "experiência com Airflow?".
    FERRAMENTA = "ferramenta"
    #: Domínio ou área: "experiência com pagamentos?", "com varejo?".
    DOMINIO = "dominio"
    #: "Quantos anos de experiência com X?"
    TEMPO = "tempo"
    #: Disponibilidade, modalidade, localidade, pretensão, notice period.
    PREFERENCIA = "preferencia"
    #: Gênero, raça, deficiência, orientação, veterano.
    SENSIVEL = "sensivel"
    #: Texto aberto sem categoria clara.
    ABERTA = "aberta"


class Sustentacao(StrEnum):
    """Quão bem o currículo sustenta a resposta dada."""

    #: Está escrito no currículo. Defensável citando a linha.
    DOCUMENTADA = "documentada"
    #: Deriva do que está escrito por equivalência ou adjacência real.
    #: Defensável, mas exige que ele saiba fazer a ponte em voz alta.
    DERIVADA = "derivada"
    #: Vai além do currículo. Permitida só onde a política deixa, e sempre
    #: registrada no briefing.
    ESTENDIDA = "estendida"


@dataclass
class Resposta:
    valor: str | list[str] | None
    classe: Classe
    sustentacao: Sustentacao
    #: Trecho do currículo que embasa. Vazio só quando ESTENDIDA.
    evidencia: str = ""
    #: Por que esta resposta, em uma linha. Vai para o log e o briefing.
    justificativa: str = ""
    #: O que ele precisa conseguir dizer se perguntarem. Só para ESTENDIDA/DERIVADA.
    preparar: str = ""

    @property
    def responder(self) -> bool:
        return self.valor is not None


@dataclass
class Contexto:
    """O que a política precisa saber sobre a vaga para calibrar a postura."""

    titulo: str = ""
    senioridade: str = ""
    #: Termos centrais da vaga: título + requisitos obrigatórios. Afirmar
    #: experiência inexistente NESTES é o que produz entrevista perdida.
    termos_centrais: set[str] = field(default_factory=set)

    def e_central(self, termo: str) -> bool:
        t = _normalizar(termo)
        if not t:
            return False
        if t in _normalizar(self.titulo):
            return True
        return any(t in _normalizar(c) or _normalizar(c) in t
                   for c in self.termos_centrais)


# ── Política por classe ───────────────────────────────────────────────────────
#
# Máxima sustentação permitida por classe. Ler como: "até onde pode ir".

POLITICA: dict[Classe, Sustentacao] = {
    # Conferível. Mentir aqui não custa a entrevista, custa a oferta — rescisão
    # por falsidade em processo seletivo é causa justa.
    Classe.FATO: Sustentacao.DOCUMENTADA,
    # Consentir com o que se pede é a condição de participar. Nunca é mentira.
    Classe.CONSENTIMENTO: Sustentacao.DOCUMENTADA,
    # Ferramenta nomeada é verificável em 30 segundos de entrevista técnica. O
    # próprio usuário reconheceu: "em perguntas muito específicas, como
    # ferramentas, já fica mais difícil de mentir".
    Classe.FERRAMENTA: Sustentacao.DERIVADA,
    # Domínio é onde a esticada compensa — e onde ela é limitada pela
    # centralidade: ver `_politica_dominio`.
    Classe.DOMINIO: Sustentacao.ESTENDIDA,
    # Faixa de tempo em pergunta composta admite leitura favorável.
    Classe.TEMPO: Sustentacao.ESTENDIDA,
    Classe.PREFERENCIA: Sustentacao.DERIVADA,
    # Dado sensível não se responde por inferência, nem para "otimizar". Ele
    # decide, sempre, manualmente.
    Classe.SENSIVEL: Sustentacao.DOCUMENTADA,
    Classe.ABERTA: Sustentacao.DERIVADA,
}


def politica_para(classe: Classe, contexto: Contexto, termo: str = "",
                  pergunta: str = "") -> Sustentacao:
    """Teto de sustentação para esta pergunta, já considerando a vaga.

    A regra que faz o trabalho pesado: domínio que é o **assunto central da vaga**
    cai para DERIVADA. Dizer "sim, tenho experiência com pagamentos" numa vaga de
    Payments Analyst na Adyen não te leva à entrevista — te leva à tela técnica
    sobre pagamentos. Numa vaga de Data Engineer que menciona pagamentos de
    passagem, a mesma resposta é barata e provavelmente irrelevante.
    """
    teto = POLITICA[classe]
    if classe is Classe.DOMINIO and termo and contexto.e_central(termo):
        return Sustentacao.DERIVADA
    if classe is Classe.TEMPO and pergunta:
        return politica_tempo(pergunta)
    return teto


def politica_tempo(pergunta: str) -> Sustentacao:
    """Teto para pergunta de tempo, que depende de a pergunta ser composta.

    "Quantos anos com Risco, Payment Performance **e** Dados" bundla três áreas:
    2,2 anos em dados torna "2-4 years" verdadeiro para um dos termos, e não há
    leitura única correta. Já "How many years with Python?" tem resposta exata,
    e as datas estão no LinkedIn dele — esticar aqui é barato de checar e caro
    quando checam.

    Antes as duas tinham o mesmo teto, e a segunda é que fazia o dano.
    """
    if _e_composta(pergunta):
        return Sustentacao.ESTENDIDA
    return Sustentacao.DERIVADA


#: Conectivos que indicam pergunta sobre mais de uma área ao mesmo tempo.
_CONECTIVOS = (" and ", " e ", " ou ", " or ", ", ", "/", "&")


def _e_composta(pergunta: str) -> bool:
    """Pergunta que agrupa áreas distintas admite leitura favorável.

    Precisa do sujeito depois do "com/with": "How many years of experience do you
    have with Risk, Payments and Data?" é composta; "How many years of experience
    do you have with Python?" não é, apesar de a frase inteira ter vírgulas.
    """
    texto = _normalizar(pergunta)
    for marcador in (" with ", " com ", " em ", " in "):
        if marcador in texto:
            sujeito = texto.split(marcador, 1)[1]
            return any(c in sujeito for c in _CONECTIVOS)
    return False


_ORDEM = {Sustentacao.DOCUMENTADA: 0, Sustentacao.DERIVADA: 1, Sustentacao.ESTENDIDA: 2}


def permitida(resposta: Resposta, contexto: Contexto, termo: str = "",
              pergunta: str = "") -> bool:
    teto = politica_para(resposta.classe, contexto, termo, pergunta)
    return _ORDEM[resposta.sustentacao] <= _ORDEM[teto]


# ── Classificação da pergunta ─────────────────────────────────────────────────

_PADROES: tuple[tuple[Classe, tuple[str, ...]], ...] = (
    (Classe.SENSIVEL, (
        "gender", "genero", "identidade de genero", "race", "raca", "etnic", "etnic",
        "lgbt", "orientacao sexual", "sexual orientation", "disability", "deficiencia",
        "neurodiver", "veteran", "pronoun", "pessoa com deficiencia", "pcd",
    )),
    (Classe.CONSENTIMENTO, (
        "acknowledge", "consent", "consinto", "concordo", "privacy", "privacidade",
        "lgpd", "gdpr", "data transfer", "tratamento de dados", "i confirm",
        "i have read", "termo de", "autorizo",
    )),
    (Classe.FATO, (
        "current employer", "empresa atual", "current company", "current title",
        "cargo atual", "current salary", "salario atual", "graduat", "formacao",
        "degree", "diploma", "certificat", "cpf", "linkedin", "website", "github",
        "work authorization", "autorizacao de trabalho", "visa", "visto",
        "sponsorship", "previously worked", "ja trabalhou", "referenc",
        # Documentos e filiação. A etapa de perguntas da empresa na Gupy pede
        # isto, e `cpf` estava sozinho aqui: os irmãos dele caíam em ABERTA, que
        # é escopo por empresa — o banco de respostas guardaria "nome da mãe"
        # uma vez por empresa e ele redigitaria em quase todas as 230 vagas,
        # que é exatamente o tédio que o banco existe para matar.
        "registro geral", "orgao emissor", "orgao expedidor", "emissao do rg",
        "nome da mae", "nome do pai", "filiacao", "naturalidade",
        "data de nascimento", "date of birth", "estado civil",
        "carteira de trabalho", "titulo de eleitor",
        "reservista", "passaporte", "passport",
        # "Você trabalha na empresa X?" e "alguém daqui indicou você?" são fatos
        # sobre ele, não sobre a empresa: com a neutralização do nome, uma
        # resposta serve em todas.
        "trabalha na empresa", "trabalha nesta empresa", "indicou voce",
        "indicacao de colaborador", "employee referral",
    )),
    (Classe.TEMPO, (
        "how many years", "quantos anos", "years of experience", "anos de experiencia",
        "tempo de experiencia", "how long have you",
    )),
    (Classe.PREFERENCIA, (
        "salary expectation", "pretensao", "expectativa salarial", "available",
        "disponibilidade", "notice period", "aviso previo", "willing to",
        "able to work", "disposto a", "relocat", "mudanca de cidade", "start date",
        "data de inicio", "hybrid", "remote", "presencial", "how did you hear",
        "como voce soube", "como conheceu",
    )),
)

#: Siglas curtas demais para casar por substring, testadas por palavra inteira
#: DEPOIS de `_PADROES`. "rg" vive dentro de "energia", "urgente" e — pior — de
#: "orgao": como substring, classificaria pergunta de domínio como documento.
_TERMOS_CURTOS: tuple[tuple[Classe, tuple[str, ...]], ...] = (
    (Classe.FATO, ("rg", "pis", "pasep", "ctps", "cnh")),
)


def classificar(label: str, opcoes: list | None = None) -> Classe:
    """Classe da pergunta a partir do enunciado.

    Ordem importa: SENSIVEL e CONSENTIMENTO primeiro, porque um enunciado de
    consentimento sobre deficiência tem que cair em SENSIVEL, não no genérico.
    """
    texto = _normalizar(label)
    for classe, termos in _PADROES:
        if any(t in texto for t in termos):
            return classe

    for classe, termos in _TERMOS_CURTOS:
        if any(re.search(rf"\b{t}\b", texto) for t in termos):
            return classe

    # Sem padrão explícito: ferramenta se cita tecnologia conhecida, senão
    # domínio se pergunta sobre experiência, senão aberta.
    if _tecnologias_citadas(label):
        return Classe.FERRAMENTA
    if any(t in texto for t in ("experience with", "experiencia com", "experiencia em",
                                "familiar", "worked with", "ja trabalhou com",
                                "knowledge of", "conhecimento em")):
        return Classe.DOMINIO
    return Classe.ABERTA


# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT = """\
Você preenche formulários de candidatura a vagas de dados no Brasil, em nome do
candidato abaixo. Seu objetivo é maximizar a chance de ele chegar à ENTREVISTA.

## Currículo do candidato
{curriculo}

## Vaga
Título: {titulo}
Senioridade: {senioridade}
Termos centrais da vaga (o assunto de que a entrevista vai tratar):
{termos_centrais}

## Pergunta do formulário
Enunciado: {pergunta}
Tipo: {tipo}
Classe: {classe}
Opções disponíveis: {opcoes}

## Como responder

Campo em branco não é neutro: numa triagem automática vale o mesmo que "não",
e ainda parece candidatura abandonada. Responda sempre que houver base.

Antes de considerar esticar, esgote a VERDADE. A maior parte das perguntas é
respondível com o que já está no currículo, desde que você seja generoso com
equivalência. Exemplos de equivalência legítima:

- Snowflake, Databricks, Redshift, BigQuery  → "data warehouse", "lakehouse"
- Azure Data Factory, Airbyte, Fivetran      → "ETL/ELT", "ingestão", "pipelines"
- Airflow, ADF, Databricks Workflows         → "orquestração"
- Power BI, Looker, Tableau, Metabase        → "BI", "visualização", "dashboards"
- Terraform, IaC                             → "infraestrutura como código", "DevOps"
- Azure, AWS, GCP                            → "cloud", "nuvem"
- dbt, SQL, modelagem dimensional            → "modelagem de dados", "transformação"

Um candidato com Snowflake e Azure Data Factory responde SIM, com verdade, a
"experiência com data warehouse?" e a "experiência com ETL?" — mesmo que essas
palavras não apareçam literalmente no currículo.

Classifique sua própria resposta em um destes níveis de sustentação:

- `documentada`: está escrito no currículo. Cite a linha.
- `derivada`:    deriva do que está escrito por equivalência ou adjacência real.
                 Defensável, mas ele precisa saber fazer a ponte em voz alta.
- `estendida`:   vai além do currículo.

Teto permitido para esta pergunta: **{teto}**.
Não ultrapasse. Se só conseguir responder acima do teto, devolva `valor: null`.

## Regras que não se dobram

1. Nunca invente empregador, cargo, data, formação, certificação ou salário.
   Isso é conferido em background check e custa a oferta, não a entrevista.
2. Nunca responda pergunta sensível (gênero, raça, deficiência, orientação) por
   inferência. Devolva `valor: null`.
3. Nunca afirme experiência inexistente num termo CENTRAL da vaga. Comprar uma
   entrevista que ele perde nos primeiros 10 minutos é pior que não ter a
   entrevista: gasta o contato com a empresa.
4. Em pergunta de tempo composta ("anos com Risco, Pagamentos E Dados"), use a
   leitura mais favorável que ainda seja verdadeira para ao menos um dos termos.
5. Se houver lista de opções, o `valor` tem que ser EXATAMENTE um dos rótulos.

## Saída

JSON, e nada além dele:

{{
  "valor": "<rótulo exato da opção, ou texto curto, ou null>",
  "sustentacao": "documentada" | "derivada" | "estendida",
  "evidencia": "<trecho do currículo que embasa; vazio se estendida>",
  "justificativa": "<uma linha: por que esta resposta>",
  "preparar": "<o que ele precisa conseguir dizer se perguntarem na entrevista;
                vazio se documentada>"
}}
"""


def montar_prompt(pergunta: str, tipo: str, opcoes: list | None,
                  curriculo: dict, contexto: Contexto) -> str:
    """Monta o prompt já com o teto de sustentação resolvido pela política."""
    import json

    classe = classificar(pergunta, opcoes)
    termo = _termo_da_pergunta(pergunta)
    teto = politica_para(classe, contexto, termo, pergunta)

    rotulos = [o.get("label", "") for o in (opcoes or []) if isinstance(o, dict)]
    return PROMPT.format(
        curriculo=json.dumps(curriculo, ensure_ascii=False, indent=2)[:6000],
        titulo=contexto.titulo or "(não informado)",
        senioridade=contexto.senioridade or "(não informada)",
        termos_centrais=", ".join(sorted(contexto.termos_centrais)) or "(nenhum)",
        pergunta=pergunta,
        tipo=tipo,
        classe=classe.value,
        opcoes=", ".join(rotulos) if rotulos else "(campo livre)",
        teto=teto.value,
    )


def validar(bruto: dict, pergunta: str, opcoes: list | None,
            contexto: Contexto) -> Resposta | None:
    """Converte a saída do modelo em `Resposta`, recusando o que a política veta.

    Invariante 9 do projeto: saída de LLM nunca vira artefato entregável sem
    normalização. Aqui o artefato é um formulário enviado a um empregador — o
    modelo pode devolver rótulo que não existe, ou se autoclassificar abaixo do
    que de fato fez. Nada disso pode chegar ao browser.
    """
    if not isinstance(bruto, dict):
        return None
    valor = bruto.get("valor")
    if valor in (None, "", "null"):
        return None

    try:
        sustentacao = Sustentacao(str(bruto.get("sustentacao", "")).strip().lower())
    except ValueError:
        # Sem autoclassificação confiável, trate como o pior caso.
        sustentacao = Sustentacao.ESTENDIDA

    # Rótulo tem que existir. Modelo alucinando opção é a forma mais fácil de o
    # formulário ser submetido com campo vazio sem ninguém perceber.
    rotulos = [o.get("label", "") for o in (opcoes or []) if isinstance(o, dict)]
    if rotulos:
        exato = next((r for r in rotulos if _normalizar(r) == _normalizar(str(valor))), None)
        if exato is None:
            exato = next(
                (r for r in rotulos if _normalizar(str(valor)) in _normalizar(r)), None
            )
        if exato is None:
            return None
        valor = exato

    # Sem evidência não existe resposta documentada, diga o modelo o que disser.
    evidencia = str(bruto.get("evidencia", "")).strip()
    if sustentacao is Sustentacao.DOCUMENTADA and not evidencia:
        sustentacao = Sustentacao.DERIVADA

    resposta = Resposta(
        valor=valor,
        classe=classificar(pergunta, opcoes),
        sustentacao=sustentacao,
        evidencia=evidencia,
        justificativa=str(bruto.get("justificativa", "")).strip(),
        preparar=str(bruto.get("preparar", "")).strip(),
    )
    if not permitida(resposta, contexto, _termo_da_pergunta(pergunta), pergunta):
        return None
    return resposta


def briefing(respostas: dict[str, Resposta]) -> list[dict]:
    """O que foi afirmado além do currículo, para ele revisar ANTES da entrevista.

    Esta é a contrapartida de permitir esticar. Uma afirmação esticada que ele
    não lembra de ter feito é uma armadilha marcada com o nome dele. Ordenado por
    risco: estendidas primeiro.
    """
    itens = [
        {
            "pergunta": pergunta,
            "resposta": r.valor,
            "sustentacao": r.sustentacao.value,
            "evidencia": r.evidencia,
            "preparar": r.preparar or r.justificativa,
        }
        for pergunta, r in respostas.items()
        if r.sustentacao is not Sustentacao.DOCUMENTADA
    ]
    return sorted(itens, key=lambda i: i["sustentacao"] != "estendida")


# ── Auxiliares ────────────────────────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto).lower())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip()


def _tecnologias_citadas(label: str) -> list[str]:
    from jobapplier.vocabulario import TECNOLOGIAS

    texto = _normalizar(label)
    achadas = []
    for canonico, variantes in TECNOLOGIAS.items():
        for v in variantes:
            if re.search(rf"\b{re.escape(_normalizar(v))}\b", texto):
                achadas.append(canonico)
                break
    return achadas


#: Domínios de negócio que aparecem em pergunta de triagem. Não são tecnologias,
#: então não estão no vocabulário — mas são exatamente o que define se uma
#: esticada é barata ou cara.
DOMINIOS: tuple[str, ...] = (
    "pagamentos", "payments", "risco", "risk", "fraude", "fraud", "credito",
    "credit", "seguros", "insurance", "varejo", "retail", "ecommerce", "logistica",
    "logistics", "saude", "health", "educacao", "education", "marketing",
    "supply chain", "banking", "bancario", "fintech", "telecom", "energia",
)


def _termo_da_pergunta(label: str) -> str:
    """O assunto da pergunta, para checar centralidade contra a vaga."""
    texto = _normalizar(label)
    for d in DOMINIOS:
        if re.search(rf"\b{re.escape(d)}\b", texto):
            return d
    citadas = _tecnologias_citadas(label)
    return citadas[0] if citadas else ""
