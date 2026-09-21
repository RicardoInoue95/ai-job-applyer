"""O que o score quer dizer, em uma frase — e o que ele esconde.

"97% de aderência" é um número chamativo que não diz por quê. O breakdown do
scorer tem a resposta (`motivos_positivos`, `gaps`, `missing_required`, nota
por eixo), mas ficava atrás de um expander ou nem aparecia. Aqui ele vira três
níveis, e cada tela mostra só o nível que lhe cabe:

- **Nível 1 — conclusão.** `97% · Excelente`, uma frase de por quê, e o ponto
  de atenção. É o que o cartão da lista mostra. Só isso.
- **Nível 2 — evidência.** Nota por eixo, tecnologias cobertas, o que falta.
  Aparece ao abrir a vaga.
- **Nível 3 — técnico.** Pesos, origem do score, confiança. Só se pedido.

O ponto de atenção é a parte que mais importa e a que menos aparecia. A regra
do projeto é dizer o que a candidatura tem *contra* ela, não só a favor — vaga
marginal enviada queima a empresa para a vaga certa depois.

Serviço, não tela: cartão do webapp e painel da extensão leem daqui, e a
mesma vaga tem a mesma conclusão nos dois.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from jobapplier.agents.extracao import (
    PESO_IDIOMA,
    PESO_LOCALIZACAO,
    PESO_SENIORIDADE,
    PESO_SETOR,
    PESO_SKILLS,
)

#: Faixas do rótulo. Alinhadas aos cortes do projeto: `threshold_auto` (85) é
#: onde o envio automático confia; `threshold_bom` (65) é onde a vaga entra na
#: fila. Abaixo disso é possibilidade, e o rótulo diz.
FAIXAS = (
    (85, "Excelente"),
    (75, "Boa"),
    (65, "Razoável"),
    (0, "Fraca"),
)

#: Eixo → (peso máximo, rótulo humano). A ordem é a de exibição.
EIXOS = (
    ("skills_tecnicas", PESO_SKILLS, "Tecnologias"),
    ("senioridade", PESO_SENIORIDADE, "Senioridade"),
    ("setor", PESO_SETOR, "Setor"),
    ("idioma", PESO_IDIOMA, "Idioma"),
    ("localizacao", PESO_LOCALIZACAO, "Localização"),
)


@dataclass
class Eixo:
    nome: str
    nota: float
    maximo: float

    @property
    def fracao(self) -> float:
        return min(1.0, self.nota / self.maximo) if self.maximo else 0.0


@dataclass
class Aderencia:
    score: float
    rotulo: str
    #: Nível 1: por que combina, numa frase.
    porque: str
    #: Nível 1: o que pesa contra. Vazio quando não há nada a apontar.
    atencao: str
    #: Nível 2.
    eixos: list[Eixo] = field(default_factory=list)
    cobertas: list[str] = field(default_factory=list)
    faltam: list[str] = field(default_factory=list)
    #: Requisito eliminatório ausente — a vaga PEDE e o currículo não tem.
    eliminatorios: list[str] = field(default_factory=list)

    @property
    def titulo(self) -> str:
        """`97% · Excelente` — a única coisa que a lista mostra."""
        return f"{self.score:.0f}% · {self.rotulo}"

    def como_dict(self) -> dict:
        d = asdict(self)
        d["titulo"] = self.titulo
        # `fracao` é property e `asdict` não a leva; é o que a barra desenha.
        for e, eixo in zip(d["eixos"], self.eixos, strict=True):
            e["fracao"] = eixo.fracao
        return d


def _como_dict(valor) -> dict:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return {}
    return valor if isinstance(valor, dict) else {}


def rotulo_de(score: float) -> str:
    for corte, nome in FAIXAS:
        if score >= corte:
            return nome
    return FAIXAS[-1][1]


def _agrupar(tecnologias: list[str]) -> str:
    """`Python, SQL, Databricks` → "Python, SQL e Databricks"; corta em três.

    Três e não oito: a frase é conclusão, não inventário. A lista inteira fica
    no nível 2.
    """
    limpas = [t.replace(" (equivalente)", "") for t in tecnologias if t]
    if not limpas:
        return ""
    if len(limpas) == 1:
        return limpas[0]
    tres = limpas[:3]
    return ", ".join(tres[:-1]) + " e " + tres[-1]


def _e_frase(motivo: str) -> bool:
    """"Python" é tecnologia; "Forte alinhamento tecnológico com…" é frase."""
    m = motivo.strip()
    return len(m) > 32 or m.endswith(".") or m.count(" ") >= 4


def _resumir(frase: str, limite: int = 140) -> str:
    f = frase.strip().rstrip(".")
    if len(f) > limite:
        f = f[:limite].rsplit(" ", 1)[0] + "…"
    return f[0].upper() + f[1:] + ("" if f.endswith("…") else ".")


def _ponto_de_atencao(breakdown: dict, eixos: list[Eixo]) -> str:
    """A coisa mais grave que o número esconde, em uma frase. Só uma.

    Ordem de gravidade: requisito eliminatório ausente > eixo zerado ou quase
    (senioridade, localização, idioma) > tecnologias ausentes > setor. Uma vaga
    pode ter vários; o cartão mostra o pior, e o detalhe mostra todos.
    """
    faltam = [t for t in (breakdown.get("missing_required") or []) if t]
    if faltam:
        verbo = "estão" if len(faltam) > 1 else "está"
        return f"Pede {_agrupar(faltam)}, que não {verbo} no seu currículo."

    por_nome = {e.nome: e for e in eixos}
    local = por_nome.get("Localização")
    if local and local.fracao == 0:
        return "Presencial numa cidade que você não declarou aceitar."
    sen = por_nome.get("Senioridade")
    if sen and sen.fracao < 0.5:
        return "Senioridade acima do que dois anos sustentam."
    idi = por_nome.get("Idioma")
    if idi and idi.fracao < 0.5:
        return "Exige idioma que o currículo não declara."

    gaps = [g for g in (breakdown.get("gaps") or []) if g]
    for g in gaps:
        if g.startswith("tecnologias da vaga ausentes"):
            lista = g.split(":", 1)[-1].strip()
            return f"Não cita {lista} no currículo."
    setor = por_nome.get("Setor")
    if setor and setor.fracao < 0.6:
        for g in gaps:
            if "setor" in g:
                return g[0].upper() + g[1:].rstrip(".") + "."
    return ""


def analisar(vaga) -> Aderencia:
    """Conclusão a partir de `score` e `score_breakdown_json`. Nunca levanta."""
    score = float(getattr(vaga, "score", None) or 0)
    dados = _como_dict(getattr(vaga, "score_breakdown_json", None))
    brk = dados.get("breakdown") or {}

    # Só os eixos que o breakdown TEM. Ausente não é zero: score antigo, de
    # outra versão do scorer, não pode virar "presencial em cidade não aceita"
    # só porque a chave não existia na época.
    eixos = [Eixo(rotulo, float(brk[chave]), float(peso))
             for chave, peso, rotulo in EIXOS if chave in brk and brk[chave] is not None]
    # O scorer escreve "nenhuma tecnologia da vaga reconhecida" DENTRO de
    # `motivos_positivos` quando não há nenhuma. Não é motivo positivo.
    motivos = [t for t in (dados.get("motivos_positivos") or [])
               if t and not t.lower().startswith("nenhuma")]
    # Scorer antigo (com LLM) escrevia motivos em frase — "Forte alinhamento
    # tecnológico com Databricks, SQL…". Frase não é tecnologia: virava chip
    # de 869px e "Forte aderência em Forte alinhamento…". Medido: 21 vagas.
    cobertas = [t for t in motivos if not _e_frase(t)]
    frases = [t for t in motivos if _e_frase(t)]
    faltam: list[str] = []
    for g in dados.get("gaps") or []:
        if isinstance(g, str) and g.startswith("tecnologias da vaga ausentes"):
            faltam = [t.strip() for t in g.split(":", 1)[-1].split(",") if t.strip()]
    eliminatorios = [t for t in (dados.get("missing_required") or []) if t]

    fortes = _agrupar(cobertas)
    if fortes and score >= 75:
        porque = f"Forte aderência em {fortes}."
    elif fortes:
        porque = f"Cobre {fortes}."
    elif frases:
        porque = _resumir(frases[0])
    else:
        porque = "Pouca sobreposição com o seu currículo."

    return Aderencia(
        score=score,
        # Pelo arredondado: 84,8 aparece como "85%", e "85% · Boa" contradiz a
        # faixa que começa em 85.
        rotulo=rotulo_de(round(score)),
        porque=porque,
        atencao=_ponto_de_atencao(dados, eixos),
        eixos=eixos,
        cobertas=cobertas,
        faltam=faltam,
        eliminatorios=eliminatorios,
    )
