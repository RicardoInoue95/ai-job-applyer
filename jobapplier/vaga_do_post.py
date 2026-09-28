"""Vaga anunciada em post: do texto colado ao dossiê e às mensagens prontas.

Boa parte das vagas de dados no Brasil não chega por ATS nenhum — é um post de
recrutador no LinkedIn com "envie o currículo para contato@empresa.com.br com o
assunto X". Para essas, o acervo não serve: não há link de formulário, não há
`jobId`, não há coletor. Mas o trabalho que o sistema sabe fazer (pontuar
contra o currículo, montar o dossiê, escrever o que dizer) é exatamente o
mesmo.

Este módulo recebe o texto do post e devolve **a candidatura pronta**:

    texto  →  o que é a vaga (cargo, empresa, salário, modalidade)
           →  por onde responder (e-mail, WhatsApp, perfil de LinkedIn)
           →  vaga no banco (plataforma `post`), normalizada e pontuada
           →  dossiê: currículo em PDF + carta
           →  e-mail, mensagem de LinkedIn e de WhatsApp (`jobapplier.abordagem`)

**O que não é extraído fica vazio, nunca é inventado** (invariante 3): sem
empresa no texto, a saudação é neutra; sem cargo reconhecido, o título é a
primeira linha do post e `incertezas` diz isso a quem chamou. Um post não é
formulário: a heurística acerta o comum e declara o que não sabe.

Idempotente pelo hash do texto: colar o mesmo post duas vezes devolve a mesma
vaga, com o dossiê já montado — e não cria duplicata na fila.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from jobapplier import paths, tempo

logger = logging.getLogger(__name__)

PLATAFORMA = "post"

# ── O que se procura no texto ────────────────────────────────────────────────
# Regex e não parser: post não tem estrutura. O que existe é convenção de
# recrutador — rótulo com dois-pontos, e-mail no fim, "assunto" entre aspas.

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PERFIL_LINKEDIN = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+", re.I)
#: `wa.me/5511999999999` e `api.whatsapp.com/send?phone=...`.
_WHATSAPP_LINK = re.compile(
    r"(?:https?://)?(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\+?\d{10,15})", re.I)
#: Telefone brasileiro escrito à mão. Exige DDD entre parênteses **ou** o
#: contexto da palavra (whatsapp, zap, telefone) — ver `_telefones`. Sem essa
#: âncora, "R$ 12.000,00" e "2 anos de experiência" viravam telefone.
_TELEFONE = re.compile(r"\(\d{2}\)\s?9?\d{4}[-.\s]?\d{4}|\b\d{2}\s9\d{4}[-.\s]?\d{4}\b")
_CONTEXTO_TELEFONE = re.compile(r"(whats|wpp|zap|telefone|celular|\btel\b|fone)", re.I)
#: `com o assunto "Cientista de Dados Junior - Sebrae-NA"`.
_ASSUNTO = re.compile(
    r"assunto\s*[:\-]?\s*[\"“']([^\"”'\n]{3,140})|"
    r"assunto\s*[:\-]\s*([^\n]{3,140})", re.I)

#: Rótulos que o recrutador usa. A ordem importa: "Local de trabalho" casa com
#: `modalidade` antes de `localizacao` porque é onde ele costuma escrever
#: "100% home office".
_ROTULOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("salario", ("remunera", "salario", "salário", "faixa salarial", "pacote")),
    ("modalidade", ("modelo", "modalidade", "regime de trabalho", "local de trabalho")),
    ("contratacao", ("contratacao", "contratação", "tipo de contrato", "regime de contrata")),
    ("localizacao", ("localizacao", "localização", "cidade", "local")),
    ("empresa", ("empresa", "cliente", "consultoria")),
    ("senioridade", ("nivel", "nível", "senioridade")),
)

#: Uma linha que começa com estas palavras depois de "Vaga" não é cargo:
#: "Vaga para quem quer trabalhar em iniciativas estratégicas" é chamada, não
#: título. Sem isto o cargo do post da imagem sairia como "para quem quer…".
#: Um cargo cabe numa linha curta. Acima disto é frase.
LIMITE_CARGO = 70

_NAO_E_CARGO = ("para ", "de emprego", "em aberto", "aberta", "disponível", "que ")

_ABERTURAS = re.compile(
    r"^(?:vaga|oportunidade|estamos contratando|contratando|hiring|we are hiring)"
    r"\s*[:\-–]?\s*(?:de\s+|para\s+(?!quem)|of\s+)?", re.I)


@dataclass
class Contato:
    """Por onde responder ao anúncio. Vazio é vazio — não se deduz."""

    emails: list[str] = field(default_factory=list)
    telefones: list[str] = field(default_factory=list)
    perfis_linkedin: list[str] = field(default_factory=list)
    #: O assunto que o anúncio pede. Recrutador filtra a caixa por ele.
    assunto: str = ""
    #: Nome de quem publicou, quando informado por quem chamou. Não se adivinha
    #: pelo texto: a primeira linha de um post colado tanto é o autor quanto o
    #: título da vaga.
    autor: str = ""

    @property
    def tem_canal(self) -> bool:
        return bool(self.emails or self.telefones or self.perfis_linkedin)

    def whatsapp_link(self) -> str:
        """`wa.me` do primeiro telefone, com DDI 55 quando ele não vier."""
        if not self.telefones:
            return ""
        digitos = re.sub(r"\D", "", self.telefones[0])
        if not digitos.startswith("55") and len(digitos) in (10, 11):
            digitos = "55" + digitos
        return f"https://wa.me/{digitos}"


@dataclass
class PostVaga:
    """O que o post diz — e o que ele não diz."""

    titulo: str = ""
    empresa: str = ""
    #: Quando a vaga é de consultoria: "THS Tecnologia - Cliente Sebrae
    #: Nacional" tem contratante E cliente final. São coisas diferentes — o
    #: e-mail vai para a primeira, o trabalho acontece na segunda — e juntas
    #: num campo só viravam um nome de 51 caracteres que comia a mensagem do
    #: LinkedIn inteira.
    cliente: str = ""
    salario: str = ""
    modalidade: str = ""
    contratacao: str = ""
    localizacao: str = ""
    senioridade: str = ""
    descricao: str = ""
    link: str = ""
    contato: Contato = field(default_factory=Contato)
    #: Campos que o texto não trouxe. Vai para a resposta da API em vez de
    #: virar palpite: quem lê decide se completa à mão.
    incertezas: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        d = asdict(self)
        d["contato"]["whatsapp_link"] = self.contato.whatsapp_link()
        return d


def _sem_emoji(texto: str) -> str:
    """Tira emoji e símbolo decorativo, mantendo acento e pontuação.

    Recrutador enfeita: "🚀 Vaga Cientista de Dados Júnior". O emoji não é
    cargo e atrapalharia o casamento de vocabulário mais adiante.
    """
    limpo = "".join(
        c for c in texto
        if unicodedata.category(c) not in ("So", "Sk", "Cf")
    )
    return re.sub(r"\s{2,}", " ", limpo).strip(" -–—•*·\t")


def _linhas(texto: str) -> list[str]:
    return [x for x in (_sem_emoji(ln) for ln in (texto or "").splitlines()) if x]


def _valor_rotulado(linhas: list[str], termos: tuple[str, ...]) -> str:
    """`Remuneração: R$ 12.000,00` → `R$ 12.000,00`."""
    for linha in linhas:
        if ":" not in linha:
            continue
        rotulo, _, valor = linha.partition(":")
        rotulo = _sem_acento(rotulo).lower().strip()
        # Rótulo é o começo da linha, não qualquer menção: "Envie para o e-mail
        # da empresa: x@y" não é o nome da empresa.
        if len(rotulo) > 40:
            continue
        if any(_sem_acento(t) in rotulo for t in termos):
            limpo = _sem_emoji(valor)
            if limpo:
                return limpo
    return ""


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn")


def _cargo(linhas: list[str]) -> str:
    """O cargo anunciado, ou a primeira linha se o post não o marcar."""
    for linha in linhas[:12]:
        m = _ABERTURAS.match(linha)
        if not m:
            continue
        resto = linha[m.end():].strip(" :-–—")
        if not resto or resto.lower().startswith(_NAO_E_CARGO):
            continue
        cargo = resto.split("|")[0].strip()
        if len(cargo) <= LIMITE_CARGO:
            return cargo
    rotulado = _valor_rotulado(linhas, ("vaga", "cargo", "posicao", "posição", "role"))
    if rotulado:
        return rotulado
    # Desistência honesta: a primeira linha serve de título **se parecer um
    # cargo**. Um parágrafo de 180 caracteres ("Hoje o mercado de dados está
    # aquecido…") é conversa, não vaga, e viraria o título de uma vaga órfã na
    # fila e o assunto de um e-mail sem sentido.
    primeira = linhas[0] if linhas else ""
    if primeira and len(primeira) <= LIMITE_CARGO and len(primeira.split()) <= 10:
        return primeira
    return ""


def _telefones(texto: str, linhas: list[str]) -> list[str]:
    achados: list[str] = []
    for bruto in _WHATSAPP_LINK.findall(texto):
        achados.append(bruto)
    for linha in linhas:
        for bruto in _TELEFONE.findall(linha):
            # `(11) 99999-9999` traz o próprio DDD entre parênteses e dispensa
            # contexto; `11 99999-9999` solto, não — pode ser qualquer número.
            if bruto.strip().startswith("(") or _CONTEXTO_TELEFONE.search(linha):
                achados.append(bruto.strip())
    vistos, saida = set(), []
    for t in achados:
        chave = re.sub(r"\D", "", t)
        if chave and chave not in vistos:
            vistos.add(chave)
            saida.append(t)
    return saida


def _assunto(texto: str) -> str:
    m = _ASSUNTO.search(texto or "")
    if not m:
        return ""
    return _sem_emoji(m.group(1) or m.group(2) or "").strip(" .;")


def extrair(texto: str, autor: str = "", link: str = "") -> PostVaga:
    """Lê o post. Nunca levanta, nunca inventa: o que falta vai em `incertezas`."""
    linhas = _linhas(texto)
    contato = Contato(
        emails=list(dict.fromkeys(_EMAIL.findall(texto or ""))),
        telefones=_telefones(texto or "", linhas),
        perfis_linkedin=list(dict.fromkeys(
            m.rstrip("/.,") for m in _PERFIL_LINKEDIN.findall(texto or ""))),
        assunto=_assunto(texto),
        autor=_sem_emoji(autor),
    )

    post = PostVaga(
        titulo=_cargo(linhas),
        empresa=_valor_rotulado(linhas, _ROTULOS[4][1]),
        salario=_valor_rotulado(linhas, _ROTULOS[0][1]),
        modalidade=_valor_rotulado(linhas, _ROTULOS[1][1]),
        contratacao=_valor_rotulado(linhas, _ROTULOS[2][1]),
        localizacao=_valor_rotulado(linhas, _ROTULOS[3][1]),
        senioridade=_valor_rotulado(linhas, _ROTULOS[5][1]),
        descricao=(texto or "").strip(),
        link=(link or "").strip(),
        contato=contato,
    )
    # A empresa costuma vir sem rótulo, numa linha do tipo
    # "THS Tecnologia - Cliente Sebrae Nacional". Só aceito quando a palavra
    # "cliente" aparece: sem ela, qualquer linha viraria nome de empresa.
    if not post.empresa:
        for linha in linhas[:14]:
            if re.search(r"\bcliente\b", linha, re.I) and len(linha) < 120:
                post.empresa = linha
                break
    post.empresa, post.cliente = _contratante_e_cliente(post.empresa)
    if not post.empresa and contato.emails:
        # Último recurso, e é uma leitura do domínio, não um palpite sobre o
        # nome: `contatorh@ths.inf.br` → `ths`.
        dominio = contato.emails[0].split("@")[-1].split(".")[0]
        if dominio and dominio not in ("gmail", "hotmail", "outlook", "yahoo"):
            post.empresa = dominio

    for campo, rotulo in (("titulo", "cargo"), ("empresa", "empresa"),
                          ("salario", "remuneração"), ("modalidade", "modalidade")):
        if not getattr(post, campo):
            post.incertezas.append(rotulo)
    if not contato.tem_canal:
        post.incertezas.append("canal de resposta (e-mail, WhatsApp ou perfil)")
    return post


def _contratante_e_cliente(bruto: str) -> tuple[str, str]:
    """`THS Tecnologia - Cliente Sebrae Nacional (Sebrae-NA)` → os dois nomes.

    Quem contrata e para quem se trabalha são informações diferentes, e o
    recrutador as escreve na mesma linha.
    """
    texto = (bruto or "").strip()
    if not texto:
        return "", ""
    partes = re.split(r"\s*[-\u2013\u2014|\u00b7]\s*|\s+para\s+o?\s*", texto, maxsplit=1)
    if len(partes) == 2 and re.search(r"\bcliente\b", partes[1], re.I):
        contratante = partes[0].strip(" .:-")
        cliente = re.sub(r"^\s*cliente\s*[:\-]?\s*", "", partes[1], flags=re.I).strip(" .:-")
        return contratante, cliente
    if re.match(r"^\s*cliente\b", texto, re.I):
        return "", re.sub(r"^\s*cliente\s*[:\-]?\s*", "", texto, flags=re.I).strip(" .:-")
    return texto.strip(" .:-"), ""


def hash_do_post(texto: str) -> str:
    """Identidade da vaga avulsa: o próprio texto.

    Não há `fonte_vaga_id` para um post. Colar duas vezes o mesmo anúncio tem de
    devolver a mesma vaga — senão a fila enche de cópias e `ja_candidatado`
    deixa de proteger.
    """
    normalizado = re.sub(r"\s+", " ", (texto or "").strip()).lower()
    return "post-" + hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:40]


def registrar(post: PostVaga, texto: str):
    """Grava (ou reencontra) a vaga do post, normalizada e pontuada.

    Devolve `(vaga_id, ja_existia)`. A vaga entra como qualquer outra: mesmo
    normalizador, mesmo scorer, mesma tabela — é o que faz o resto do produto
    (aderência, fila, Documentos, funil) funcionar sem saber que ela veio de um
    post.
    """
    import json

    from jobapplier.agents import normalizer, scorer
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    chave = hash_do_post(texto)
    resume = json.loads(paths.RESUME_JSON.read_text(encoding="utf-8"))

    with get_session() as sessao:
        vaga = sessao.query(Vaga).filter(Vaga.hash == chave).first()
        ja_existia = vaga is not None
        if vaga is None:
            vaga = Vaga(hash=chave, plataforma=PLATAFORMA, status="nova",
                        primeira_coleta_em=tempo.agora_utc())
            sessao.add(vaga)

        vaga.titulo = post.titulo or "(vaga sem título no post)"
        vaga.empresa = post.empresa or post.cliente or "(empresa não informada)"
        vaga.descricao = post.descricao
        vaga.link = post.link
        vaga.localizacao = post.localizacao or None
        vaga.salario = (post.salario or None) and post.salario[:100]
        vaga.ultima_coleta_em = tempo.agora_utc()
        sessao.flush()

        normalizado = normalizer.normalize(vaga) or {}
        # O que o post declarou com todas as letras vence a inferência do
        # texto: "Modelo: 100% Home Office" é mais confiável que adivinhar
        # modalidade no meio da descrição.
        if post.modalidade:
            normalizado["modalidade"] = _modalidade_canonica(post.modalidade)
        if post.senioridade:
            normalizado.setdefault("senioridade", post.senioridade.lower())
        vaga.normalizado_json = normalizado
        vaga.modalidade = normalizado.get("modalidade")
        vaga.senioridade = normalizado.get("senioridade")

        breakdown = scorer.score(vaga, resume) or {}
        vaga.score = float(breakdown.get("score") or 0)
        vaga.score_breakdown_json = breakdown
        vaga_id = vaga.id

    logger.info("Vaga de post %s: %s — %s (score %.0f)", vaga_id,
                post.titulo or "?", post.empresa or "?", float(breakdown.get("score") or 0))
    return vaga_id, ja_existia


def _modalidade_canonica(texto: str) -> str:
    baixo = _sem_acento(texto).lower()
    if "home office" in baixo or "remot" in baixo or "anywhere" in baixo:
        return "remoto"
    if "hibrid" in baixo:
        return "híbrido"
    if "presencial" in baixo or "on-site" in baixo or "onsite" in baixo:
        return "presencial"
    return texto.strip().lower()[:50]


def preparar(texto: str, autor: str = "", link: str = "") -> dict:
    """Do post à candidatura pronta. É o que o endpoint `POST /post` devolve.

    Ordem deliberada: registrar e pontuar **antes** de montar o dossiê, porque o
    currículo é derivado do perfil e do idioma que o score escolheu. E o dossiê
    passa pela trava do PDF (invariante 8): currículo quebrado não vira anexo.
    """
    import json

    from jobapplier import abordagem, aderencia
    from jobapplier import dossie as mod_dossie
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    post = extrair(texto, autor=autor, link=link)
    vaga_id, ja_existia = registrar(post, texto)
    resume = json.loads(paths.RESUME_JSON.read_text(encoding="utf-8"))

    with get_session() as sessao:
        vaga = sessao.get(Vaga, vaga_id)
        sessao.expunge(vaga)

    dossie = mod_dossie.montar(vaga, resume)
    _, base = mod_dossie.perfil_base(vaga, resume)

    if dossie.pronto:
        with get_session() as sessao:
            alvo = sessao.get(Vaga, vaga_id)
            # `pronta_envio_manual` e não `aprovada`: aqui não existe formulário
            # para automatizar — a candidatura sai por e-mail ou mensagem, que
            # é você quem manda.
            if alvo is not None and alvo.status in ("nova", "pendente", "aprovada"):
                alvo.status = "pronta_envio_manual"

    conclusao = aderencia.analisar(vaga).como_dict()
    mensagens = abordagem.montar(post, vaga, base, dossie)

    return {
        "vaga_id": vaga_id,
        "ja_existia": ja_existia,
        "vaga": post.como_dict(),
        "aderencia": conclusao,
        "atencao": abordagem.pontos_de_atencao(post, conclusao),
        "curriculo": dossie.pdf_path.name if dossie.pronto else None,
        "curriculo_url": f"/vaga/{vaga_id}/curriculo" if dossie.pronto else None,
        "carta": dossie.cover_letter_texto or "",
        "erro_dossie": dossie.erro or "",
        "mensagens": mensagens,
    }
