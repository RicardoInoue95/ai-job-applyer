"""Ficha de respostas: o que preencher no formulário desta vaga.

Fecha o circuito entre três peças que já existiam sem se falarem — a descoberta
de perguntas de cada plataforma, o `_auto_answer` que sabe respondê-las, e o
módulo de salário. A saída é para **olhos humanos**, não para um browser: o
usuário abre a vaga, olha a ficha e copia.

Isso muda o que conta como sucesso. Um applicator precisa de resposta para todo
campo obrigatório, senão o envio falha. Uma ficha não: pergunta sem resposta
automática vira uma linha marcada "responda você", que é informação útil — ele
já sabe o que vai ter que pensar antes de abrir o formulário.

Por isso nada aqui inventa. Resposta ausente é ausente (invariante 3), e a
pergunta **eliminatória** — que a Gupy declara explicitamente — é destacada,
porque errar uma dessas não é resposta fraca, é descarte imediato.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Item:
    """Uma pergunta do formulário e o que temos para ela."""

    pergunta: str
    resposta: str = ""
    obrigatoria: bool = False
    eliminatoria: bool = False
    opcoes: list[str] = field(default_factory=list)
    origem: str = ""

    @property
    def respondida(self) -> bool:
        return bool(self.resposta)

    @property
    def exige_confirmacao(self) -> bool:
        """Eliminatória nunca é resposta pronta, mesmo quando temos uma.

        A vaga de Guarulhos mostrou por quê: "Aceita trabalhar presencialmente?"
        vinha respondida "Sim" enquanto a pergunta irmã — "reside em Guarulhos ou
        tem fácil acesso?" — ficava em branco. Inconsistente, e numa pergunta que
        descarta o candidato na hora. Sugerir é útil; afirmar por ele, não.
        """
        return self.eliminatoria


@dataclass
class Ficha:
    itens: list[Item] = field(default_factory=list)
    #: Por que a ficha está vazia, quando está. Distingue "vaga sem perguntas"
    #: de "não consegui ler o formulário" — desfechos opostos que pareceriam
    #: iguais numa lista vazia.
    situacao: str = "ok"
    detalhe: str = ""

    @property
    def total(self) -> int:
        return len(self.itens)

    @property
    def respondidas(self) -> int:
        return sum(1 for i in self.itens if i.respondida)

    @property
    def pendentes(self) -> list[Item]:
        """O que ele vai ter que pensar antes de abrir o formulário."""
        return [i for i in self.itens if not i.respondida]

    @property
    def sem_perguntas(self) -> bool:
        return self.situacao == "ok" and not self.itens

    @property
    def legivel(self) -> bool:
        return self.situacao == "ok"


def montar(vaga, resume: dict, config: dict | None = None) -> Ficha:
    """Ficha da vaga. Nunca levanta — o cartão precisa renderizar de qualquer jeito."""
    config = config or {}
    plataforma = (getattr(vaga, "plataforma", "") or "").lower()

    try:
        descoberta, eliminatorias = _descobrir(vaga, plataforma)
    except Exception as exc:
        logger.warning("Ficha da vaga %s: descoberta falhou (%s)",
                       getattr(vaga, "id", "?"), exc)
        return Ficha(situacao="erro", detalhe=f"{type(exc).__name__}: {exc}")

    if descoberta is None:
        return Ficha(situacao="sem_suporte",
                     detalhe=f"sem leitura de formulário para '{plataforma}'")
    if not descoberta.ok:
        return Ficha(situacao="ilegivel",
                     detalhe=f"{descoberta.status}: {descoberta.detalhe}")

    itens = [
        _responder(p, vaga, resume, config, eliminatorias)
        for p in descoberta.perguntas
        if not _e_campo_padrao(p)
    ]
    # Obrigatórias primeiro, eliminatórias antes de tudo: é onde a atenção dele
    # rende mais.
    itens.sort(key=lambda i: (not i.eliminatoria, not i.obrigatoria, i.respondida))
    return Ficha(itens=itens)


#: Campos que todo formulário tem e que saem do currículo sem pensar. Numa ficha
#: para olhos humanos eles são ruído: ele sabe o próprio nome, e vê-los listados
#: como "responda você" faz a ficha parecer cheia de pendência quando não está.
_CAMPOS_PADRAO = (
    "first name", "last name", "preferred first name", "full name", "nome",
    "sobrenome", "email", "e-mail", "phone", "telefone", "celular",
    "resume", "resume/cv", "cv", "curriculo", "currículo", "cover letter",
    "carta de apresentação", "linkedin", "location", "candidate location",
)


def _e_campo_padrao(pergunta) -> bool:
    """Campo padrão é o que o dossiê já resolve: nome, contato, currículo, carta.

    Comparação por rótulo inteiro, não por prefixo: "Resume/CV" tinha que casar,
    mas "Resume of your most relevant project" — que é pergunta de verdade — não
    pode. Prefixo casaria as duas.
    """
    rotulo = (pergunta.label or "").strip().lower().strip("*: ")
    return rotulo in _CAMPOS_PADRAO


def _descobrir(vaga, plataforma: str):
    """(Descoberta, rótulos eliminatórios) ou (None, []) se não há suporte."""
    link = getattr(vaga, "link", "") or ""

    if plataforma == "gupy":
        import requests

        from jobapplier.applicators import gupy_perguntas

        descoberta = gupy_perguntas.descobrir_perguntas(link)
        elim: list[str] = []
        if descoberta.ok and descoberta.perguntas:
            # Segunda leitura só quando há o que marcar. A flag `disqualifying`
            # não cabe no contrato compartilhado de `Pergunta`, que é o mesmo do
            # Greenhouse — e mudá-lo por causa de uma plataforma seria pior.
            try:
                html = requests.get(
                    link, headers=gupy_perguntas.CABECALHOS, timeout=15,
                ).text
                elim = gupy_perguntas.eliminatorias(descoberta, html)
            except Exception as exc:
                logger.debug("Eliminatórias não lidas: %s", exc)
        return descoberta, elim

    if plataforma == "greenhouse":
        from jobapplier.applicators import greenhouse, identidade

        resolvida = identidade.resolver(vaga)
        if not resolvida:
            return None, []
        return greenhouse.descobrir_perguntas(resolvida.slug, resolvida.job_id), []

    return None, []


def _responder(pergunta, vaga, resume: dict, config: dict,
               eliminatorias: list[str]) -> Item:
    """Resposta para uma pergunta, ou vazio quando não sabemos."""
    item = Item(
        pergunta=pergunta.label,
        obrigatoria=pergunta.obrigatoria,
        eliminatoria=pergunta.label in eliminatorias,
        opcoes=[o.get("label", "") for o in (pergunta.opcoes or [])],
    )

    # Pretensão salarial tem módulo próprio: não é fato sobre o passado, é
    # posição de negociação, e depende do regime de contratação da vaga.
    if _e_pretensao(pergunta.label):
        from jobapplier import salario

        texto_vaga = " ".join(filter(None, (
            getattr(vaga, "titulo", ""), getattr(vaga, "descricao", ""),
        )))
        resposta = salario.responder(
            texto_vaga, _senioridade(vaga), pergunta.tipo, config,
        )
        if resposta:
            item.resposta = resposta["valor"]
            item.origem = resposta["justificativa"]
        return item

    try:
        from jobapplier.applicators.greenhouse import _auto_answer

        bruta = _auto_answer(
            pergunta.label, pergunta.tipo, pergunta.opcoes or [],
            resume, _normalizado(vaga), config.get("dados_pessoais"),
        )
    except Exception as exc:
        logger.debug("Auto-resposta falhou para '%s': %s", pergunta.label[:40], exc)
        return item

    if bruta is None:
        return item

    valores = bruta if isinstance(bruta, list) else [bruta]
    item.resposta = ", ".join(
        _rotulo_da_opcao(pergunta, v) for v in valores
    )
    item.origem = "do seu currículo"
    return item


def _rotulo_da_opcao(pergunta, valor) -> str:
    """Converte o id da opção no texto que o humano vê no formulário.

    `_auto_answer` devolve o *value* porque é o que o Playwright usa para
    selecionar. Numa ficha isso é inútil: "How did you hear about Twilio?"
    aparecia respondida `728714888`, que não diz nada para quem vai copiar.
    """
    texto = str(valor)
    for opcao in (pergunta.opcoes or []):
        if str(opcao.get("value", "")) == texto and opcao.get("label"):
            return str(opcao["label"])
    # Yes/No chegam como 1/0 em alguns formulários, sem opção correspondente.
    return {"1": "Sim", "0": "Não", "yes": "Sim", "no": "Não"}.get(
        texto.lower(), texto
    )


def _e_pretensao(label: str) -> bool:
    texto = (label or "").lower()
    return any(t in texto for t in (
        "pretensão salarial", "pretensao salarial", "salary expectation",
        "expectativa salarial", "pretensão de salário", "remuneração pretendida",
    ))


def _senioridade(vaga) -> str:
    dados = _normalizado(vaga)
    return str(dados.get("senioridade") or "")


def _normalizado(vaga) -> dict:
    import json

    bruto = getattr(vaga, "normalizado_json", None) or {}
    if isinstance(bruto, str):
        try:
            bruto = json.loads(bruto)
        except json.JSONDecodeError:
            return {}
    return bruto if isinstance(bruto, dict) else {}
