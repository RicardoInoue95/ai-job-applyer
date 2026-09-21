"""Tudo que o sistema já gerou para você, num lugar só.

São 593 currículos e 566 cartas em `data/`, e até aqui só dava para chegar a
eles por dentro do cartão da vaga correspondente — um por vez, e só enquanto a
vaga estivesse na fila. Documento de vaga encerrada ficava inalcançável pela
interface, embora seja justamente o que se quer reaproveitar: o currículo que
você mandou para a vaga parecida do mês passado.

**A fonte é o disco, não a tabela `candidaturas`.** São 593 arquivos para 351
linhas com `curriculo_path`: o dossiê é gerado para o baralho sem que exista
candidatura, e registrar só o que virou candidatura esconderia 40% do acervo.
O `vaga_id` está no nome do arquivo (`resume_<perfil>_<id>.pdf`), e é por ele
que se liga cada arquivo à vaga.

Serviço, não página: a interface e o painel da extensão renderizam a mesma
lista, e a regra de quais documentos existem mora aqui.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jobapplier import paths, tempo

#: `resume_data_engineer_14692.pdf` → perfil `data_engineer`, vaga 14692.
_RE_CURRICULO = re.compile(r"^resume_(?P<perfil>.+)_(?P<vaga>\d+)\.pdf$")
#: `cover_letter_14692.txt` → vaga 14692.
_RE_CARTA = re.compile(r"^cover_letter_(?P<vaga>\d+)\.txt$")

#: Arquivo sem data legível vai para o fim da lista. Naive de propósito, para
#: comparar com o que `tempo.de_timestamp` devolve — as datas do projeto são
#: naive-UTC por decisão registrada em `jobapplier/tempo.py`. Por isso `noqa`:
#: a regra DTZ901 pede tz-aware, e aqui tz-aware é que quebraria a comparação.
_SEM_DATA = datetime.min  # noqa: DTZ901


@dataclass
class Documento:
    vaga_id: int
    #: Caminhos podem faltar um ao outro: a carta é opcional no dossiê, e um PDF
    #: pode existir sem ela sem que nada esteja errado.
    curriculo: Path | None = None
    carta: Path | None = None
    perfil: str = ""
    gerado_em: datetime | None = None
    #: Preenchidos por `com_vagas`, que é quem toca o banco.
    empresa: str = ""
    titulo: str = ""
    plataforma: str = ""
    status_vaga: str = ""
    score: float | None = None

    @property
    def tem_carta(self) -> bool:
        return self.carta is not None and self.carta.exists()

    @property
    def manuscrito(self) -> bool:
        """Escrito à mão para esta vaga (ver `jobapplier/manuscrito.py`)."""
        return (paths.DOSSIES / str(self.vaga_id)).exists()


def _mtime(caminho: Path | None) -> datetime | None:
    if caminho is None:
        return None
    try:
        # Por `tempo`, não por `datetime` direto: as datas do projeto são
        # naive-UTC por decisão registrada, e essa decisão mora num lugar só.
        return tempo.de_timestamp(caminho.stat().st_mtime)
    # Arquivo removido entre o glob e o stat. Raro, e não é motivo para a
    # página inteira falhar.
    except OSError:
        return None


def listar() -> list[Documento]:
    """Todo currículo e carta em disco, agrupados por vaga. Não toca o banco."""
    por_vaga: dict[int, Documento] = {}

    for arquivo in paths.RESUMES.glob("resume_*.pdf"):
        m = _RE_CURRICULO.match(arquivo.name)
        if not m:
            continue
        vaga_id = int(m.group("vaga"))
        doc = por_vaga.setdefault(vaga_id, Documento(vaga_id))
        # Mais de um perfil pode ter sido gerado para a mesma vaga ao longo do
        # tempo; fica o mais recente, que é o que corresponde ao que foi enviado.
        quando = _mtime(arquivo)
        if doc.curriculo is None or (quando and doc.gerado_em and quando > doc.gerado_em):
            doc.curriculo = arquivo
            doc.perfil = m.group("perfil")
            doc.gerado_em = quando

    for arquivo in paths.COVER_LETTERS.glob("cover_letter_*.txt"):
        m = _RE_CARTA.match(arquivo.name)
        if not m:
            continue
        vaga_id = int(m.group("vaga"))
        doc = por_vaga.setdefault(vaga_id, Documento(vaga_id))
        doc.carta = arquivo
        if doc.gerado_em is None:
            doc.gerado_em = _mtime(arquivo)

    return sorted(por_vaga.values(),
                  key=lambda d: d.gerado_em or _SEM_DATA, reverse=True)


def com_vagas(docs: list[Documento] | None = None) -> list[Documento]:
    """A mesma lista, com empresa, título e status vindos do banco.

    Uma consulta só para todos os ids. Buscar vaga por vaga eram 593 idas ao
    banco para montar uma página — o mesmo erro que `bulk_create_if_not_exists`
    comete na coleta e que está anotado como dívida.
    """
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    docs = listar() if docs is None else docs
    if not docs:
        return docs

    ids = [d.vaga_id for d in docs]
    with get_session() as sessao:
        linhas = (sessao.query(Vaga.id, Vaga.empresa, Vaga.titulo, Vaga.plataforma,
                               Vaga.status, Vaga.score)
                  .filter(Vaga.id.in_(ids)).all())
    por_id = {linha[0]: linha for linha in linhas}
    for doc in docs:
        linha = por_id.get(doc.vaga_id)
        if linha is None:
            # Vaga apagada do banco com o arquivo ainda em disco. O documento
            # continua servindo — é currículo seu —, e some da lista se
            # exigíssemos a vaga.
            doc.empresa, doc.titulo, doc.status_vaga = "—", "(vaga fora do acervo)", ""
            continue
        _, doc.empresa, doc.titulo, doc.plataforma, doc.status_vaga, doc.score = linha
    return docs


def filtrar(docs: list[Documento], termo: str = "", plataforma: str = "",
            so_com_carta: bool = False) -> list[Documento]:
    """Busca por empresa, título ou id. Sem acento e sem caixa."""
    import unicodedata

    def normal(t: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                       if unicodedata.category(c) != "Mn")

    alvo = normal(termo).strip()
    saida = []
    for d in docs:
        if plataforma and d.plataforma != plataforma:
            continue
        if so_com_carta and not d.tem_carta:
            continue
        if alvo and alvo not in normal(f"{d.empresa} {d.titulo} {d.vaga_id}"):
            continue
        saida.append(d)
    return saida
