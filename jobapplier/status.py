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
    Status("rejeitada", "Rejeitada", "Score abaixo do mínimo", "descartada"),
    Status("inelegivel", "Inelegível", "Exige autorização de trabalho que você não tem",
           "descartada", "aviso"),
    Status("encerrada", "Encerrada", "A vaga saiu do ar", "descartada"),
    # Aguardando você
    Status("pendente", "Aguardando aprovação",
           "Score intermediário: você decide se vale candidatar", "acao", "aviso"),
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
    # Aguardando o sistema
    Status("aprovada", "Aprovada", "Na fila para candidatura", "processando"),
    Status("aguardando_suporte", "Sem suporte ainda",
           "O formulário tem um tipo de campo que a automação não trata", "bloqueada"),
    Status("sem_automacao", "Plataforma sem automação",
           "Não há applicator para esta plataforma", "bloqueada"),
    # Desfechos
    Status("candidatada", "Candidatada", "Envio confirmado pela plataforma",
           "concluida", "bom"),
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


def codigos_vaga(*grupos: str) -> list[str]:
    """Códigos de vaga, opcionalmente filtrados por grupo."""
    return [s.codigo for s in VAGA if not grupos or s.grupo in grupos]


def exigem_sua_acao() -> list[str]:
    """Status em que a vaga está esperando por VOCÊ, não pelo sistema."""
    return codigos_vaga("acao")


#: Emoji por tom, para a interface. Semântico, não decorativo: comunica
#: severidade num relance numa lista longa.
TOM_ICONE = {"bom": "✅", "aviso": "⚠️", "ruim": "❌", "neutro": "•"}
