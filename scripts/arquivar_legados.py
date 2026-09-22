r"""Fecha em lote os registros de candidatura de uma época anterior do produto.

Decisão do usuário (auditoria de UX, 22/09/2026): 165 "Perguntas pendentes" e
118 "Erro" de junho/agosto apareciam no histórico misturados aos envios
reais, e ninguém ia resolvê-los. Viram `arquivada` — status catalogado em
`jobapplier/status.py`, fora do filtro "Envios e atenção".

Reversível: o status anterior de cada linha vai para
`data/arquivamento_<data>.json`. Nada é apagado; `--desfazer <arquivo>`
devolve os status.

    .venv\Scripts\python.exe scripts\arquivar_legados.py            # mostra o que faria
    .venv\Scripts\python.exe scripts\arquivar_legados.py --aplicar
    .venv\Scripts\python.exe scripts\arquivar_legados.py --desfazer data/arquivamento_20260922.json
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobapplier import paths
from jobapplier.database.connection import get_session
from jobapplier.database.models import Candidatura
from jobapplier.tempo import hoje

STATUS_ANTIGOS = ("perguntas_pendentes", "erro")
#: Tudo anterior a esta data é de antes do vocabulário atual.
CORTE = datetime(2026, 9, 1)  # noqa: DTZ001 — colunas naive-UTC (jobapplier.tempo)


def candidatas():
    with get_session() as s:
        return [(c.id, c.status) for c in s.query(Candidatura)
                .filter(Candidatura.status.in_(STATUS_ANTIGOS),
                        Candidatura.criado_em < CORTE).all()]


def aplicar() -> Path:
    linhas = candidatas()
    saida = paths.DATA / f"arquivamento_{hoje():%Y%m%d}.json"
    saida.write_text(json.dumps({"corte": CORTE.isoformat(), "linhas": linhas},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    with get_session() as s:
        for ident, _ in linhas:
            s.query(Candidatura).filter(Candidatura.id == ident).update({"status": "arquivada"})
    return saida


def desfazer(arquivo: Path) -> int:
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    with get_session() as s:
        for ident, anterior in dados["linhas"]:
            s.query(Candidatura).filter(Candidatura.id == ident).update({"status": anterior})
    return len(dados["linhas"])


if __name__ == "__main__":
    if "--desfazer" in sys.argv:
        n = desfazer(Path(sys.argv[sys.argv.index("--desfazer") + 1]))
        print(f"{n} registros devolvidos ao status anterior.")
    elif "--aplicar" in sys.argv:
        saida = aplicar()
        print(f"arquivados; status anteriores em {saida}")
    else:
        linhas = candidatas()
        from collections import Counter
        print(f"{len(linhas)} registros seriam arquivados:", dict(Counter(st for _, st in linhas)))
        print("use --aplicar para executar")
