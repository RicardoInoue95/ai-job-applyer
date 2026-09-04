"""Pretensão salarial: a única resposta que é posição de negociação, não fato.

Perguntas de triagem se respondem olhando o currículo. Esta não: não existe
resposta verdadeira ou falsa para "qual sua pretensão?", existe âncora boa ou
ruim. Por isso mora fora de `agents/respostas.py` — a régua de sustentação não
se aplica aqui.

Três decisões embutidas, todas com custo assimétrico:

**Nunca deixar em branco.** Campo de salário vazio não é neutro em triagem
automática: lê como evasivo, e em muitos ATS é campo obrigatório que trava o
envio.

**Ancorar no topo da faixa quando o campo aceita um número só.** O valor
declarado vira o teto da negociação, nunca o piso — recrutador negocia para
baixo a partir dele. Dizer o mínimo garante receber o mínimo.

**Converter CLT→PJ.** No Brasil a mesma vaga em PJ paga ~30% mais bruto para dar
o mesmo líquido: não há 13º, férias, FGTS nem INSS patronal. Declarar valor CLT
numa vaga PJ é pedir 30% menos sem perceber. A conversão é aritmética de regime,
não aumento de pretensão — o alvo em poder de compra é o mesmo.

A faixa em si é decisão do usuário e vive em `data/config.json`; este módulo não
tem opinião sobre o número, só sobre como apresentá-lo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from jobapplier.vocabulario import ORDEM_SENIORIDADE

#: Quanto o bruto PJ precisa ser maior que o CLT para o líquido empatar.
#: Conservador de propósito: a conta cheia (13º + férias + 1/3 + FGTS + INSS
#: patronal) passa de 1.4, e pedir demais filtra antes de negociar.
FATOR_PJ_PADRAO = 1.30


@dataclass(frozen=True)
class Faixa:
    minimo: float
    alvo: float
    maximo: float
    fator_pj: float = FATOR_PJ_PADRAO

    def __post_init__(self):
        if not (0 < self.minimo <= self.alvo <= self.maximo):
            raise ValueError(
                f"faixa incoerente: mínimo={self.minimo} alvo={self.alvo} "
                f"máximo={self.maximo}"
            )


def carregar_faixa(config: dict | None = None) -> Faixa | None:
    """Lê `pretensao` da config. `None` quando não configurada.

    None significa "não responda", não "responda zero". Chutar a pretensão de
    alguém é o tipo de precisão falsa que faz o sistema parecer confiável quando
    não é.
    """
    if config is None:
        from jobapplier.config.manager import ConfigManager

        config = ConfigManager().load()

    bruto = (config or {}).get("pretensao") or {}
    minimo, maximo = bruto.get("minimo"), bruto.get("maximo")
    if not minimo or not maximo:
        return None

    try:
        minimo, maximo = float(minimo), float(maximo)
        alvo = float(bruto.get("alvo") or (minimo + maximo) / 2)
        return Faixa(
            minimo=minimo,
            alvo=alvo,
            maximo=maximo,
            fator_pj=float(bruto.get("fator_pj", FATOR_PJ_PADRAO)),
        )
    except (TypeError, ValueError):
        # Config editada à mão com valor inválido não pode virar pretensão
        # absurda num formulário — nem derrubar a candidatura inteira.
        return None


# ── Regime de contratação ─────────────────────────────────────────────────────

_PJ = re.compile(
    r"\bpj\b|pessoa jur[ií]dica|contrato pj|regime pj|prestador de servi[cç]o"
    r"|\bcnpj\b|contractor|freelanc",
    re.IGNORECASE,
)
_CLT = re.compile(r"\bclt\b|carteira assinada|regime celetista|efetivo", re.IGNORECASE)


def detectar_regime(texto: str) -> str:
    """'pj', 'clt' ou 'desconhecido'.

    CLT ganha do PJ quando os dois aparecem: anúncio que diz "CLT ou PJ" costuma
    ter a faixa cotada em CLT, e assumir PJ inflaria a pretensão em 30% contra um
    orçamento que não é esse.
    """
    if not texto:
        return "desconhecido"
    tem_clt, tem_pj = bool(_CLT.search(texto)), bool(_PJ.search(texto))
    if tem_clt:
        return "clt"
    if tem_pj:
        return "pj"
    return "desconhecido"


# ── Valor ─────────────────────────────────────────────────────────────────────

def valor_para(faixa: Faixa, senioridade: str = "", regime: str = "desconhecido",
               unico: bool = True) -> float:
    """Valor a declarar, em reais.

    `unico=True` (campo numérico, um valor só) devolve o topo da posição na
    faixa, porque esse número vira o teto da negociação. `unico=False` é usado
    por `formatar` para montar o intervalo.
    """
    base = _por_senioridade(faixa, senioridade)
    if unico:
        base = max(base, faixa.alvo)
    if regime == "pj":
        base *= faixa.fator_pj
    return round(base, -2)  # centena mais próxima: "9.000" lê melhor que "8.967"


def _por_senioridade(faixa: Faixa, senioridade: str) -> float:
    """Move dentro da faixa conforme o nível da vaga, sem nunca sair dela.

    Pedir o topo numa vaga júnior filtra por orçamento; pedir o mínimo numa vaga
    sênior sinaliza que você se vê como júnior. Ambos custam a vaga, por motivos
    opostos.
    """
    nivel = ORDEM_SENIORIDADE.get(senioridade or "Desconhecida", 0)
    if nivel <= 1:                      # Junior / Desconhecida
        return faixa.minimo
    if nivel == 2:                      # Pleno
        return faixa.alvo
    return faixa.maximo                 # Senior, Especialista, Gerente


def formatar(valor: float, tipo_campo: str = "input_text",
             faixa: Faixa | None = None, regime: str = "desconhecido") -> str:
    """Formata para o campo. Numérico recebe só dígitos.

    Muitos ATS validam o campo com regex de número e rejeitam "R$ 9.000" em
    silêncio — o formulário não envia e a causa não aparece em lugar nenhum.
    """
    if tipo_campo in ("number", "numeric", "input_number"):
        return str(int(valor))

    texto = f"R$ {_milhar(valor)}"
    if faixa is not None and valor < faixa.maximo:
        teto = faixa.maximo * (faixa.fator_pj if regime == "pj" else 1)
        texto = f"R$ {_milhar(valor)} a R$ {_milhar(round(teto, -2))}"
    if regime == "pj":
        texto += " (PJ)"
    return texto


def _milhar(valor: float) -> str:
    return f"{int(valor):,}".replace(",", ".")


#: Valores em R$ dentro desta janela são plausivelmente salário mensal. Fora
#: dela é quase sempre outra coisa: R$ 800 de vale-refeição, R$ 500.000 de
#: faturamento citado na descrição da empresa.
PISO_PLAUSIVEL = 2000.0
TETO_PLAUSIVEL = 80_000.0

_VALOR_BRL = re.compile(r"r\$\s?(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?)", re.IGNORECASE)


def extrair_faixa_publicada(texto: str) -> tuple[float, float] | None:
    """(menor, maior) valor em R$ plausível como salário, ou None.

    Raramente encontra algo: medido sobre 310 vagas de dados da Gupy, só 1,9%
    trazem valor em R$, e boa parte desses é benefício, não remuneração — um
    "Engenheiro de Dados Pleno" com R$ 2.400 é vale-refeição. Por isso quem
    consome isto trata `None` como o caso normal, não como erro.
    """
    if not texto:
        return None

    valores = []
    for bruto in _VALOR_BRL.findall(texto):
        try:
            valor = float(bruto.replace(".", "").replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        if PISO_PLAUSIVEL <= valor <= TETO_PLAUSIVEL:
            valores.append(valor)

    if not valores:
        return None
    return min(valores), max(valores)


def compativel_com_faixa(texto: str, faixa: Faixa | None = None,
                         config: dict | None = None) -> bool | None:
    """A faixa publicada alcança a pretensão do usuário? `None` se não há faixa.

    Basta o topo do que a vaga paga chegar ao mínimo dele: uma vaga que anuncia
    "R$ 6.000 a R$ 9.000" é negociável para alguém que quer 7.000, e descartá-la
    por causa do piso do anúncio jogaria fora vaga viável.
    """
    publicada = extrair_faixa_publicada(texto)
    if publicada is None:
        return None

    faixa = faixa or carregar_faixa(config)
    if faixa is None:
        return None

    return publicada[1] >= faixa.minimo


def responder(texto_vaga: str = "", senioridade: str = "",
              tipo_campo: str = "input_text", config: dict | None = None) -> dict | None:
    """Resposta pronta para o campo de pretensão, ou `None` se não configurada.

    Devolve também `regime` e `justificativa` para o log: quando o número sair
    diferente do esperado, a causa tem que estar registrada — quase sempre é a
    conversão PJ.
    """
    faixa = carregar_faixa(config)
    if faixa is None:
        return None

    regime = detectar_regime(texto_vaga)
    valor = valor_para(faixa, senioridade, regime)
    justificativa = f"faixa R$ {_milhar(faixa.minimo)}–{_milhar(faixa.maximo)}"
    if senioridade:
        justificativa += f", vaga {senioridade}"
    if regime == "pj":
        justificativa += f", convertido para PJ (×{faixa.fator_pj:g})"

    return {
        "valor": formatar(valor, tipo_campo, faixa, regime),
        "numero": valor,
        "regime": regime,
        "justificativa": justificativa,
    }
