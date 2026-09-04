"""Vocabulário de status: fonte única para backend e interface.

A interface ficou para trás do backend em silêncio. Conhecia 8 status de vaga
enquanto o orquestrador produzia 17 — e o mais importante deles,
``pronta_para_revisao``, era justamente onde toda vaga do modo sombra caía. O
ponto do modo sombra é revisão humana, e a tela de revisão não conseguia
mostrá-las.

Status espalhados como strings literais em três camadas não têm como divergir
com aviso. Aqui eles têm rótulo, descrição e agrupamento num lugar só, e há
teste garantindo que a UI cobre tudo que o backend produz.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Status:
    codigo: str
    rotulo: str
    descricao: str
    #: Agrupamento para a interface: o que o usuário faz com isto.
    grupo: str
    #: Cor semântica, não a cor de marca.
    tom: str = "neutro"

    @property
    def exige_acao(self) -> bool:
        return self.grupo == "acao"


# ── Status de VAGA ────────────────────────────────────────────────────────────

VAGA: tuple[Status, ...] = (
    # Em processamento
    Status("nova", "Nova", "Coletada, ainda não avaliada", "processando"),
    Status("em_andamento", "Em andamento", "Sendo processada agora", "processando"),
    # Descartadas pelos filtros
    Status("filtrada_4a", "Filtrada (4A)", "Descartada pelo filtro de texto, sem custo",
           "descartada"),
    Status("filtrada_4b", "Filtrada (4B)", "Descartada após a normalização", "descartada"),
    # Legado: score não rejeita mais (viram 'pendente'). Fica para linhas antigas.
    Status("rejeitada", "Rejeitada (legado)", "Descartada por score, antes da política atual",
           "descartada"),
    Status("inelegivel", "Inelegível", "Exige autorização de trabalho que você não tem",
           "descartada", "aviso"),
    Status("encerrada", "Encerrada", "A vaga saiu do ar", "descartada"),
    # Aguardando você
    # Grupo próprio: possibilidade não é pendência. Contá-la como "esperando
    # por você" inflou o painel de 344 para 455 — lista de afazeres com 195
    # itens de score baixo é o maçante que a Finalidade proíbe.
    Status("pendente", "Possibilidade",
           "Abaixo do corte de aprovação — acessível baixando o filtro da fila",
           "possibilidade"),
    Status("pronta_para_revisao", "Pronta para revisão",
           "Modo sombra: documentos preparados, envio não executado", "acao", "aviso"),
    Status("aguardando_revisao", "Confirmação inconclusiva",
           "Formulário submetido sem prova de recebimento — confira na plataforma",
           "acao", "aviso"),
    Status("aguardando_resposta_manual", "Pergunta sem resposta",
           "O formulário tem campo obrigatório que a automação não sabe preencher",
           "acao", "aviso"),
    Status("aguardando_configuracao", "Falta configuração",
           "Um dado seu está ausente (ex.: CPF)", "acao", "aviso"),
    Status("pronta_envio_manual", "Pronta para você enviar",
           "Currículo e carta prontos; a plataforma não permite envio automático",
           "acao", "aviso"),
    Status("adiada", "Decidir depois",
           "Você viu e preferiu pensar — sai da fila principal, não se perde",
           "acao"),
    Status("aberta", "Aberta por você",
           "Você abriu o link da vaga. Não sabemos se chegou a enviar",
           "acao", "aviso"),
    # Aguardando o sistema
    Status("aprovada", "Aprovada", "Na fila para candidatura", "processando"),
    Status("aguardando_suporte", "Sem suporte ainda",
           "O formulário tem um tipo de campo que a automação não trata", "bloqueada"),
    Status("sem_automacao", "Plataforma sem automação",
           "Não há applicator para esta plataforma", "bloqueada"),
    # Legado: nome anterior de 'aguardando_revisao'. 49 vagas ainda o usam, e
    # sem entrada aqui elas apareciam como "não catalogado" na interface.
    Status("aguardando_resposta", "Confirmação inconclusiva (legado)",
           "Registro anterior à mudança de vocabulário", "acao", "aviso"),
    # Desfechos
    Status("candidatada", "Candidatada", "Envio confirmado pela plataforma",
           "concluida", "bom"),
    Status("enviada_manual", "Enviada por você",
           "Você aplicou pelo site, com o dossiê que o sistema preparou",
           "concluida", "bom"),
    Status("descartada_por_voce", "Descartada por você",
           "Você viu o cartão e decidiu que não vale", "descartada"),
    Status("erro", "Erro", "Falha técnica — pode ser retentada", "problema", "ruim"),
)

# ── Status de CANDIDATURA ─────────────────────────────────────────────────────

CANDIDATURA: tuple[Status, ...] = (
    Status("enviada_confirmada", "Enviada e confirmada",
           "A plataforma confirmou o recebimento", "concluida", "bom"),
    Status("revisao_manual", "Requer revisão",
           "Submetida sem prova, ou com pergunta em branco", "acao", "aviso"),
    Status("falha_automacao", "Falha técnica",
           "Nada foi submetido", "problema", "ruim"),
    # Grupo 'acao' e não 'problema': o trabalho caro já foi feito, e o que falta
    # é você digitar um código. Contá-la como falha esconderia a única categoria
    # que uma sessão assistida resolve.
    Status("aguardando_verificacao", "Aguarda seu código",
           "Formulário pronto; a plataforma pede verificação humana", "acao",
           "aviso"),
    Status("simulada", "Simulada (modo sombra)",
           "Preparada e deliberadamente não enviada", "processando"),
    # Legados: só leitura de linhas antigas do banco.
    Status("enviada", "Enviada (legado)", "Registro anterior à mudança de vocabulário",
           "concluida", "bom"),
    Status("perguntas_pendentes", "Perguntas pendentes (legado)",
           "Registro anterior à mudança de vocabulário", "acao", "aviso"),
    Status("erro", "Erro (legado)", "Registro anterior à mudança de vocabulário",
           "problema", "ruim"),
)

_POR_CODIGO_VAGA = {s.codigo: s for s in VAGA}
_POR_CODIGO_CAND = {s.codigo: s for s in CANDIDATURA}


def de_vaga(codigo: str) -> Status:
    """Status da vaga. Código desconhecido vira um Status genérico, nunca KeyError:
    a interface não pode quebrar porque o backend ganhou um estado novo."""
    return _POR_CODIGO_VAGA.get(
        codigo, Status(codigo, codigo or "?", "Status não catalogado", "processando")
    )


def de_candidatura(codigo: str) -> Status:
    return _POR_CODIGO_CAND.get(
        codigo, Status(codigo, codigo or "?", "Status não catalogado", "processando")
    )


def e_legado(codigo: str) -> bool:
    """O status é do vocabulário antigo?

    Serve para **separar** relatório, nunca para converter. Os dois vocabulários
    foram medidos com réguas diferentes: `enviada` do acervo antigo significava
    "o botão foi clicado", e `enviada_confirmada` exige prova na página. Somar os
    dois produz uma taxa de sucesso que não descreve nem um período nem o outro.

    A fonte é `applicators.base.STATUS_LEGADOS`, que já existia para leitura de
    linha antiga — repetir a lista aqui criaria a segunda cópia de sempre.
    """
    from jobapplier.applicators.base import STATUS_LEGADOS

    return (codigo or "") in STATUS_LEGADOS


def codigos_vaga(*grupos: str) -> list[str]:
    """Códigos de vaga, opcionalmente filtrados por grupo."""
    return [s.codigo for s in VAGA if not grupos or s.grupo in grupos]


def exigem_sua_acao() -> list[str]:
    """Status em que a vaga está esperando por VOCÊ, não pelo sistema."""
    return codigos_vaga("acao")


#: Emoji por tom, para a interface. Semântico, não decorativo: comunica
#: severidade num relance numa lista longa.
TOM_ICONE = {"bom": "✅", "aviso": "⚠️", "ruim": "❌", "neutro": "•"}
