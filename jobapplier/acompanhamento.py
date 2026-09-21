"""O que aconteceu depois de enviar: você marca, o sistema conta.

`desfecho.py` foi desenhado para ler a resposta no e-mail, e o argumento segue
válido — "contabilidade que só serve ao sistema é tédio". Mas a leitura de
e-mail ainda não existe, e enquanto não existe o funil morre em "enviada" e
"aguardando retorno" é igual a "enviadas". Marcar à mão é o caminho provisório:
um seletor por candidatura, cinco opções, e o número que o projeto nunca teve —
*de quantas eu fui chamado?* — passa a existir.

O registro é o mesmo que o e-mail vai produzir (`Evento`, `fonte='manual'`),
de propósito: quando a leitura chegar, as duas fontes contam na mesma tabela,
e o que você marcou à mão não se perde nem duplica.

Um evento por (vaga, tipo). Marcar "entrevista" depois de "resposta" acrescenta
o evento mais forte; o resumo considera o mais forte de cada vaga. Marcar
"sem resposta" apaga os manuais daquela vaga — é o único jeito de desfazer.
"""
from __future__ import annotations

from dataclasses import dataclass

from jobapplier.desfecho import Desfecho
from jobapplier.tempo import agora_utc

#: Do mais fraco para o mais forte. O resumo de uma vaga é o maior índice.
FORCA = {d: i for i, d in enumerate((Desfecho.RECEBIDA, Desfecho.RECUSA,
                                      Desfecho.RESPOSTA, Desfecho.ENTREVISTA,
                                      Desfecho.OFERTA))}

#: O que o seletor mostra, na voz do candidato — não do sistema.
ROTULOS = {
    None: "Sem resposta ainda",
    Desfecho.RECEBIDA: "Só a confirmação automática",
    Desfecho.RESPOSTA: "Responderam (teste, formulário, contato)",
    Desfecho.ENTREVISTA: "Entrevista marcada",
    Desfecho.OFERTA: "Oferta",
    Desfecho.RECUSA: "Recusa",
}

#: Marcar "sem resposta" no seletor é desfazer.
SEM_RESPOSTA = "sem_resposta"


@dataclass
class Resumo:
    enviadas: int = 0
    com_resposta: int = 0      # qualquer evento humano (resposta+)
    entrevistas: int = 0
    ofertas: int = 0
    recusas: int = 0

    @property
    def aguardando(self) -> int:
        return max(0, self.enviadas - self.com_resposta - self.recusas)


def registrar(vaga_id: int, desfecho: str | None) -> dict:
    """Grava o que você marcou. `None`/`sem_resposta` apaga os manuais da vaga.

    Nunca apaga evento de fonte `email`: o que o sistema leu na caixa é
    evidência; o que você marcou é declaração, e uma não sobrescreve a outra.
    """
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Evento

    if desfecho in (None, "", SEM_RESPOSTA):
        with get_session() as s:
            n = (s.query(Evento)
                 .filter(Evento.vaga_id == vaga_id, Evento.fonte == "manual")
                 .delete(synchronize_session=False))
        return {"ok": True, "vaga_id": vaga_id, "desfecho": None, "apagados": n}

    tipo = Desfecho(desfecho)
    with get_session() as s:
        existente = (s.query(Evento)
                     .filter(Evento.vaga_id == vaga_id, Evento.tipo == tipo.value)
                     .one_or_none())
        if existente is None:
            s.add(Evento(vaga_id=vaga_id, tipo=tipo.value, fonte="manual",
                         referencia="marcado por você", ocorrido_em=agora_utc()))
        elif existente.fonte == "manual":
            existente.ocorrido_em = agora_utc()
    return {"ok": True, "vaga_id": vaga_id, "desfecho": tipo.value}


def _mais_forte(tipos: list[str]) -> Desfecho | None:
    validos = [Desfecho(t) for t in tipos if t in Desfecho.__members__.values()]
    return max(validos, key=lambda d: FORCA[d]) if validos else None


def por_vaga(vaga_ids: list[int]) -> dict[int, Desfecho | None]:
    """O desfecho mais forte de cada vaga, numa consulta."""
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Evento

    if not vaga_ids:
        return {}
    with get_session() as s:
        linhas = (s.query(Evento.vaga_id, Evento.tipo)
                  .filter(Evento.vaga_id.in_(vaga_ids)).all())
    tipos: dict[int, list[str]] = {}
    for vaga_id, tipo in linhas:
        tipos.setdefault(vaga_id, []).append(tipo)
    return {vid: _mais_forte(tipos.get(vid, [])) for vid in vaga_ids}


#: Status de vaga que contam como "enviada" para o funil.
ENVIADAS = ("candidatada", "enviada_manual")


def resumo() -> Resumo:
    """Os números do funil. `aguardando` é o que sobra depois de descontar
    quem respondeu e quem recusou — não mais igual a "enviadas"."""
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    with get_session() as s:
        ids = [i for (i,) in s.query(Vaga.id).filter(Vaga.status.in_(ENVIADAS)).all()]
    desfechos = por_vaga(ids)
    r = Resumo(enviadas=len(ids))
    for d in desfechos.values():
        if d is None or d is Desfecho.RECEBIDA:
            continue
        if d is Desfecho.RECUSA:
            r.recusas += 1
            continue
        r.com_resposta += 1
        if d is Desfecho.ENTREVISTA:
            r.entrevistas += 1
        elif d is Desfecho.OFERTA:
            r.ofertas += 1
            r.entrevistas += 1   # oferta implica ter passado por entrevista
    return r
