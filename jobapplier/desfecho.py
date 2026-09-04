"""O que aconteceu depois de candidatar: resposta, entrevista, recusa, oferta.

O funil do projeto morre em `candidatada`. Não há registro de nada depois — e
por isso **o corte de score nunca foi validado contra desfecho real**. Tudo o
que se ajustou até hoje (limiar 85, faixa salarial, currículo em inglês, linha
de equivalência) foi medido contra métrica interna: preenchimento de formulário,
ATS%, tamanho da fila. Nenhuma contra "ele foi chamado?".

Sem isto, otimizar é preciso e cego ao mesmo tempo.

**Por que e-mail e não um botão na tela.** A régua do projeto: "contabilidade que
só serve ao sistema é tédio; procure um sinal que já exista no fluxo dele". O
candidato já lê o e-mail da empresa. O sistema não precisa que ele volte à tela
para registrar o que ele acabou de ler — precisa ler junto.

**O classificador é conservador de propósito.** `None` é uma resposta legítima e
frequente: um e-mail que não dá para classificar vira nada, não vira "resposta".
Inflar o funil com falso positivo destruiria a única coisa que este módulo
existe para produzir — um número em que dá para confiar.
"""
from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


class Desfecho(StrEnum):
    """Ordem importa: do pior para o melhor, e o melhor vence no mesmo e-mail."""

    RECUSA = "recusa"
    #: Confirmação automática de recebimento. Não é resposta humana, mas prova
    #: que a candidatura chegou — que é justamente o que hoje não se sabe.
    RECEBIDA = "recebida"
    #: Alguém leu e respondeu pedindo algo: teste, formulário, disponibilidade.
    RESPOSTA = "resposta"
    ENTREVISTA = "entrevista"
    OFERTA = "oferta"


#: Do mais forte para o mais fraco: um e-mail que marca entrevista e agradece o
#: interesse é entrevista, não recusa. A ordem resolve isso sem heurística de
#: contagem.
_ORDEM = (Desfecho.OFERTA, Desfecho.ENTREVISTA, Desfecho.RESPOSTA,
          Desfecho.RECUSA, Desfecho.RECEBIDA)

_PADROES: dict[Desfecho, tuple[str, ...]] = {
    Desfecho.OFERTA: (
        "carta oferta", "carta proposta", "proposta de trabalho", "job offer",
        "offer letter", "temos uma proposta", "oferta de emprego",
        "pleased to offer", "gostariamos de te contratar",
    ),
    Desfecho.ENTREVISTA: (
        "entrevista", "interview", "bate-papo", "conversa com",
        "agendar uma conversa", "schedule a call", "schedule a chat",
        "convite para", "proxima etapa", "próxima etapa", "next step",
        "next stage", "disponibilidade de agenda", "video call",
    ),
    Desfecho.RESPOSTA: (
        "teste tecnico", "desafio tecnico", "technical challenge", "take-home",
        "case pratico", "precisamos de mais", "poderia enviar",
        "could you provide", "some questions", "algumas perguntas",
        "avaliacao online", "assessment",
    ),
    Desfecho.RECUSA: (
        "nao seguiremos", "não seguiremos", "nao daremos continuidade",
        "não daremos continuidade", "seguimos com outro", "outro candidato",
        "other candidates", "not moving forward", "will not be moving",
        "decided not to", "unfortunately", "infelizmente", "nao foi selecionado",
        "não foi selecionado", "processo encerrado", "no longer under consider",
        "we have decided", "nao prosseguir", "banco de talentos",
    ),
    Desfecho.RECEBIDA: (
        "recebemos sua candidatura", "candidatura recebida",
        "we received your application", "thank you for applying",
        "obrigado por se candidatar", "application received",
        "sua inscricao foi", "your application has been received",
        "thank you for your interest",
    ),
}

#: Ruído que chega da mesma caixa e do mesmo remetente. Sem isto, "vagas que
#: combinam com você" da Gupy viraria "resposta" toda semana.
_RUIDO = (
    "vagas para voce", "vagas que combinam", "novas vagas", "jobs for you",
    "vagas selecionadas", "oportunidades para voce", "recomendadas para voce",
    "job alert", "alerta de vaga", "recomendacoes de vaga", "newsletter",
    "confirme seu e-mail", "verification code", "codigo de verificacao",
    "redefinir senha", "password reset", "unsubscribe preferences",
)


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento).lower()


def e_ruido(assunto: str, corpo: str = "") -> bool:
    """Alerta de vaga, newsletter e código de verificação não são desfecho."""
    texto = _normalizar(f"{assunto} {corpo[:400]}")
    return any(r in texto for r in _RUIDO)


def classificar(assunto: str, corpo: str = "") -> Desfecho | None:
    """O desfecho que este e-mail representa, ou None.

    `None` é resposta legítima e comum. Um e-mail ambíguo classificado como
    "resposta" infla o funil, e o funil inflado é pior que funil vazio: o vazio
    se reconhece, o inflado se acredita.
    """
    if e_ruido(assunto, corpo):
        return None
    # O assunto pesa mais, mas sozinho perde a recusa que só aparece no corpo.
    texto = _normalizar(f"{assunto} {assunto} {corpo[:2000]}")
    for tipo in _ORDEM:
        if any(p in texto for p in _PADROES[tipo]):
            return tipo
    return None


def empresa_do_remetente(remetente: str) -> str:
    """Domínio útil do remetente, sem o que é comum a todo ATS.

    `no-reply@adyen.com` → `adyen`. Serve para casar o e-mail com a vaga: o
    ATS entrega pelo domínio da empresa na maior parte dos casos.
    """
    m = re.search(r"@([\w.-]+)", remetente or "")
    if not m:
        return ""
    partes = [p for p in m.group(1).lower().split(".")
              if p not in ("com", "br", "co", "io", "net", "org", "www",
                           "mail", "email", "greenhouse", "lever", "gupy",
                           "myworkday", "inhire", "us")]
    return partes[-1] if partes else ""
