"""A fila de candidatura: quais vagas, em que ordem, e o que fazer com uma.

Serviço, não tela. A regra vivia dentro de `ui/pages/5_Aplicar.py`, e o painel
da extensão precisa exatamente da mesma — duas implementações da mesma decisão
divergem, e este projeto já pagou esse preço com os quatro `resume_base_*.json`
que eram cópias do mestre e apodreceram em silêncio. Aqui a regra é uma; webapp
e painel renderizam.

**Fila do dia, não acervo.** `do_dia()` devolve poucas vagas de propósito. São
412 na fila, com mediana alta e cartões que se parecem: uma lista com 412 itens
não é escolha, é carimbo — e é a fonte real do cansaço que o projeto existe para
atacar. O acervo continua acessível por `listar()`, com filtro; o que muda é o
padrão.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

#: Status que estão esperando por VOCÊ. `pendente` entra porque é possibilidade
#: acessível baixando o corte — o score nunca rejeita (ver CLAUDE.md). `aberta`
#: também: você abriu o link e não disse se enviou, então ela continua sua.
NA_FILA = ("pronta_envio_manual", "aprovada", "pronta_para_revisao", "pendente",
           "aberta")

#: Quantas vagas o dia oferece por padrão. Cinco porque é quanto cabe numa
#: sessão sem virar tarefa: o histórico do projeto é de 293 tentativas para 10
#: envios, e o gargalo nunca foi a quantidade oferecida.
DO_DIA = 5

#: Decisões possíveis sobre uma vaga da fila, e o status que cada uma grava.
#: Mapa explícito para a API não aceitar status arbitrário vindo de fora — sem
#: isto, um POST poderia escrever "enviada_confirmada" e furar a invariante 2.
DECISOES = {
    "enviada": "enviada_manual",
    "descartar": "descartada_por_voce",
    "adiar": "adiada",
    # "Abrir e candidatar": o painel abre o link E registra que você abriu. A
    # vaga NÃO sai da fila — o que se sabe é que o link foi aberto, não que a
    # candidatura saiu. Sair só com "enviei" ou "não é para mim".
    "abrir": "aberta",
}


@dataclass
class ItemFila:
    id: int
    titulo: str
    empresa: str
    empresa_exibicao: str
    plataforma: str
    link: str
    score: float
    localizacao: str
    modalidade: str
    status: str
    #: Documentos prontos, para o painel saber o que oferecer sem outra chamada.
    tem_curriculo: bool = False
    tem_carta: bool = False
    #: Nível 1 da aderência (`jobapplier.aderencia`): título, por quê, atenção.
    #: Vai junto para o cartão não precisar de uma segunda chamada por vaga.
    aderencia: dict | None = None

    def como_dict(self) -> dict:
        return asdict(self)


def titulo_exibicao(titulo: str | None) -> str:
    """`12393045 - Engenheiro de Dados Pleno` → `Engenheiro de Dados Pleno`.

    Código de requisição no começo do título é identificador do ATS da
    empresa, não cargo — e é o primeiro campo que o olho lê. Aqui e não na UI:
    o painel da extensão e o webapp mostram o mesmo título.
    """
    import re

    t = (titulo or "").strip()
    # Só numeral de 4+ dígitos seguido de separador: "3 Analistas" não é
    # código; "0731 - Analista" (Sicredi) e "12393045 - Engenheiro" são.
    return re.sub(r"^\d{4,}\s*[-|:·]\s*", "", t) or t


def _item(vaga, curriculos: set[int], cartas: set[int]) -> ItemFila:
    from jobapplier import aderencia, empresas

    nivel1 = aderencia.analisar(vaga)
    return ItemFila(
        id=vaga.id,
        titulo=titulo_exibicao(vaga.titulo),
        empresa=vaga.empresa or "",
        empresa_exibicao=empresas.nome_exibicao(vaga.empresa) or (vaga.empresa or ""),
        plataforma=(vaga.plataforma or "").lower(),
        link=vaga.link or "",
        score=round(vaga.score or 0, 1),
        localizacao=vaga.localizacao or "",
        modalidade=vaga.modalidade or "",
        status=vaga.status or "",
        tem_curriculo=vaga.id in curriculos,
        tem_carta=vaga.id in cartas,
        aderencia={"titulo": nivel1.titulo, "rotulo": nivel1.rotulo,
                   "porque": nivel1.porque, "atencao": nivel1.atencao},
    )


def _ids_com_documento() -> tuple[set[int], set[int]]:
    """Quais vagas já têm currículo e carta em disco.

    Lido de uma vez, não por vaga: montar a fila com um `glob` por item eram
    centenas de idas ao disco para desenhar cinco cartões.
    """
    from jobapplier import documentos

    curriculos, cartas = set(), set()
    for doc in documentos.listar():
        if doc.curriculo is not None:
            curriculos.add(doc.vaga_id)
        if doc.carta is not None:
            cartas.add(doc.vaga_id)
    return curriculos, cartas


def listar(score_min: int = 0, plataformas: tuple[str, ...] = (),
           limite: int | None = None) -> list[ItemFila]:
    """A fila inteira, da melhor para a pior. Filtro opcional."""
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    with get_session() as sessao:
        consulta = (sessao.query(Vaga)
                    .filter(Vaga.status.in_(NA_FILA))
                    .order_by(Vaga.score.desc().nullslast()))
        if plataformas:
            consulta = consulta.filter(Vaga.plataforma.in_(plataformas))
        if score_min:
            consulta = consulta.filter(Vaga.score >= score_min)
        if limite:
            consulta = consulta.limit(limite)
        vagas = consulta.all()
        for v in vagas:
            sessao.expunge(v)

    curriculos, cartas = _ids_com_documento()
    return [_item(v, curriculos, cartas) for v in vagas]


def corte_de_atencao() -> int:
    """A partir de que score uma vaga "precisa de você": `scoring.threshold_auto`.

    É o corte em que o sistema confiaria para enviar sozinho — então é o corte
    em que vale a sua decisão. Abaixo dele a vaga continua em Vagas, com
    dossiê, acessível; só não entra na conta de "precisam de você", que senão
    volta a ser 275.
    """
    from jobapplier.config.manager import ConfigManager

    return int((ConfigManager().get("scoring") or {}).get("threshold_auto", 85))


def precisam_de_voce() -> list[ItemFila]:
    """As que a IA achou excelentes E já preparou. É o número da barra lateral
    e a frase do Início. `pendente` fica fora: possibilidade não é fila."""
    corte = corte_de_atencao()
    return [i for i in listar(score_min=corte)
            if i.status != "pendente" and i.tem_curriculo]


def do_dia(quantas: int = DO_DIA) -> list[ItemFila]:
    """As melhores da fila, poucas de propósito.

    Só as que já têm currículo pronto: oferecer uma vaga cujo dossiê ainda não
    saiu é oferecer trabalho, não oportunidade — o usuário clica, não encontra o
    PDF e volta. Se nenhuma tiver, devolve as melhores mesmo assim, porque uma
    fila vazia esconderia que há vaga esperando.
    """
    candidatas = listar(limite=quantas * 6)
    prontas = [i for i in candidatas if i.tem_curriculo]
    return (prontas or candidatas)[:quantas]


def decidir(vaga_id: int, decisao: str) -> dict:
    """Grava a decisão do candidato sobre uma vaga.

    `enviada` NÃO marca como confirmada: quem afirma é ele, e o sistema não viu
    a página de confirmação. Falso "enviada" é pior que erro, porque
    `guard.ja_candidatado` bloqueia a vaga para sempre.
    """
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    if decisao not in DECISOES:
        raise ValueError(f"decisão desconhecida: {decisao!r}")

    novo = DECISOES[decisao]
    with get_session() as sessao:
        vaga = sessao.get(Vaga, vaga_id)
        if vaga is None:
            return {"ok": False}
        anterior = vaga.status
        vaga.status = novo

        if decisao == "enviada":
            # Pela porta oficial: é o repositório que grava candidatura, e sem
            # isto o envio pela extensão ficaria invisível para o limite diário
            # e para o funil — foi o bug que `scripts/finalizar.py` teve.
            from jobapplier.applicators.base import REVISAO_MANUAL
            from jobapplier.database.repository import CandidaturaRepository

            CandidaturaRepository(sessao).registrar(
                vaga_id=vaga_id, status=REVISAO_MANUAL,
                erro="enviada por você; sem prova na página")

    return {"ok": True, "vaga_id": vaga_id, "de": anterior, "para": novo}


def dossie(vaga_id: int) -> dict:
    """O que o painel mostra ao lado do formulário: carta, perguntas, links."""
    import json

    from jobapplier import documentos, ficha, paths
    from jobapplier.config.manager import ConfigManager
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    with get_session() as sessao:
        vaga = sessao.get(Vaga, vaga_id)
        if vaga is None:
            return {}
        sessao.expunge(vaga)

    curriculos, cartas = _ids_com_documento()
    item = _item(vaga, curriculos, cartas)

    texto_carta = ""
    for doc in documentos.listar():
        if doc.vaga_id == vaga_id and doc.carta is not None and doc.carta.exists():
            texto_carta = doc.carta.read_text(encoding="utf-8")
            break

    # A ficha lê o formulário real da plataforma e pode demorar ou falhar; ela
    # nunca levanta, e o painel renderiza sem perguntas em vez de não renderizar.
    perguntas: list[dict] = []
    situacao = "erro"
    try:
        resume = json.loads(paths.RESUME_JSON.read_text(encoding="utf-8"))
        montada = ficha.montar(vaga, resume, ConfigManager().load())
        perguntas = [
            {"pergunta": i.pergunta, "resposta": i.resposta or "",
             "respondida": bool(i.respondida), "obrigatoria": bool(i.obrigatoria),
             "eliminatoria": bool(i.eliminatoria), "origem": i.origem}
            for i in (montada.itens or [])
        ]
        situacao = montada.situacao
    except Exception:
        # Cego de propósito: sem currículo, sem rede ou com formulário ilegível a
        # ficha não sai, e nenhum dos três impede o resto do painel.
        perguntas = []

    from jobapplier import aderencia

    return {
        "vaga": item.como_dict(),
        "aderencia": aderencia.analisar(vaga).como_dict(),
        "carta": texto_carta,
        "perguntas": perguntas,
        "situacao_ficha": situacao,
        "manuscrito": (paths.DOSSIES / str(vaga_id)).exists(),
    }
