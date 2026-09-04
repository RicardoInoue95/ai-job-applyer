"""Banco de respostas aprendidas: o que você digitou uma vez, o sistema repete.

**Por que existe.** A etapa de perguntas da empresa na Gupy pede RG, nome da mãe
e naturalidade. São 230 vagas da Gupy na fila. Sem memória, isso é redigitar o
nome da própria mãe 230 vezes — exatamente o tédio que o projeto existe para
matar ("configuração recorrente é tédio", CLAUDE.md).

**Por que não fere a invariante 3.** A invariante proíbe o *sistema* afirmar o
que o currículo não sustenta. Aqui não há afirmação do sistema: a resposta é sua,
dada por você, repetida literalmente. É o oposto de um chute — é a única fonte
que não precisa de sustentação, porque veio da pessoa.

O que ainda é chute, e continua proibido, é reaproveitar resposta **específica de
contexto** em outro contexto. Por isso a classe da pergunta governa o escopo:

    FATO, PREFERENCIA, FERRAMENTA, DOMINIO, TEMPO, CONSENTIMENTO, SENSIVEL
        → global. São sobre VOCÊ, e não mudam de empresa para empresa.
    ABERTA
        → por empresa. "Por que a PagBank?" não responde "por que o Nubank?", e
          resposta genérica reaproveitada é o que faz recrutador descartar.

**Neutralização da empresa.** "Você trabalha na empresa PagBank?" aparece em toda
Gupy mudando só o nome. Guardado com o nome trocado por `{empresa}`, uma resposta
serve nas 230 — a resposta é sobre você, não sobre a empresa. Só vale para as
classes globais; em pergunta ABERTA o nome da empresa é justamente o assunto.
"""
from __future__ import annotations

import logging
import re

from jobapplier.agents import respostas
from jobapplier.agents.respostas import Classe

logger = logging.getLogger(__name__)

#: Classes cuja resposta é sobre o candidato, não sobre a vaga: valem em
#: qualquer empresa. `ABERTA` fica de fora de propósito — ver o cabeçalho.
CLASSES_GLOBAIS = frozenset({
    Classe.FATO, Classe.PREFERENCIA, Classe.FERRAMENTA,
    Classe.DOMINIO, Classe.TEMPO, Classe.CONSENTIMENTO, Classe.SENSIVEL,
})

#: Marcador que substitui o nome da empresa na chave.
MARCADOR_EMPRESA = "{empresa}"


def normalizar(pergunta: str, empresa: str = "") -> str:
    """Chave de casamento da pergunta.

    Casamento **exato** sobre esta forma, nunca aproximado: "tem experiência com
    Python?" e "tem experiência com Python 3?" são perguntas diferentes, e um
    casamento frouxo responderia uma com a outra.
    """
    texto = respostas._normalizar(pergunta)          # minúscula, sem acento
    texto = re.sub(r"^\s*\d+\s*[.)-]\s*", "", texto)  # "6. " da numeração da Gupy
    texto = texto.replace("*", " ")                   # marca de obrigatório
    if empresa:
        alvo = respostas._normalizar(empresa)
        if alvo:
            texto = re.sub(rf"\b{re.escape(alvo)}\b", MARCADOR_EMPRESA, texto)
    return re.sub(r"[^\w{}]+", " ", texto).strip()


def escopo_de(classe: Classe) -> str:
    """`global` ou `empresa`. Ver a tabela no cabeçalho."""
    return "global" if classe in CLASSES_GLOBAIS else "empresa"


def chave(pergunta: str, empresa: str, classe: Classe) -> tuple[str, str, str]:
    """(chave, escopo, empresa_da_chave).

    Em pergunta ABERTA o nome da empresa **não** é neutralizado: ele é o assunto.
    """
    escopo = escopo_de(classe)
    if escopo == "global":
        return normalizar(pergunta, empresa), escopo, ""
    return normalizar(pergunta), escopo, (empresa or "").strip().lower()


def _limpar(resposta: str | None) -> str:
    return re.sub(r"\s+", " ", str(resposta or "")).strip()


def registrar(sessao, pergunta: str, resposta: str, empresa: str = "",
              opcoes: list | None = None) -> bool:
    """Guarda a resposta que você deu. Devolve se algo foi gravado.

    Resposta vazia apaga a entrada em vez de gravar vazio: você limpar um campo
    é a forma natural de dizer "não era isso", e gravar "" faria o banco
    responder nada em todo formulário seguinte, silenciosamente.
    """
    from jobapplier.database.models import RespostaAprendida
    from jobapplier.tempo import agora_utc

    pergunta = (pergunta or "").strip()
    valor = _limpar(resposta)
    if not pergunta:
        return False

    classe = respostas.classificar(pergunta, opcoes)
    ch, escopo, emp = chave(pergunta, empresa, classe)
    if not ch:
        return False

    existente = (sessao.query(RespostaAprendida)
                 .filter_by(chave=ch, escopo=escopo, empresa=emp).one_or_none())

    if not valor:
        if existente is not None:
            sessao.delete(existente)
            logger.info("Resposta aprendida apagada (%s).", classe)
            return True
        return False

    if existente is not None:
        existente.resposta = valor
        existente.pergunta = pergunta
        existente.atualizado_em = agora_utc()
        return True

    sessao.add(RespostaAprendida(
        chave=ch, escopo=escopo, empresa=emp, pergunta=pergunta,
        resposta=valor, classe=str(classe)))
    # A pergunta vai no log, a resposta NUNCA: "nome da mãe" é PII e o log vive
    # em disco (invariante 12).
    logger.info("Resposta aprendida (%s, %s): %s", classe, escopo, pergunta[:70])
    return True


def consultar(sessao, pergunta: str, empresa: str = "",
              opcoes: list | None = None) -> str | None:
    """A resposta que você já deu para esta pergunta, ou None."""
    from jobapplier.database.models import RespostaAprendida
    from jobapplier.tempo import agora_utc

    pergunta = (pergunta or "").strip()
    if not pergunta:
        return None

    classe = respostas.classificar(pergunta, opcoes)
    ch, escopo, emp = chave(pergunta, empresa, classe)
    if not ch:
        return None

    achado = (sessao.query(RespostaAprendida)
              .filter_by(chave=ch, escopo=escopo, empresa=emp).one_or_none())
    if achado is None:
        return None

    achado.vezes_usada = (achado.vezes_usada or 0) + 1
    achado.usada_em = agora_utc()
    return achado.resposta
