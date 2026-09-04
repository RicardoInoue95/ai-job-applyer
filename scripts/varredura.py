"""Marca como encerradas as vagas da fila que não existem mais.

    .venv\\Scripts\\python.exe scripts\\varredura.py            # só relata
    .venv\\Scripts\\python.exe scripts\\varredura.py --aplicar  # marca no banco
    .venv\\Scripts\\python.exe scripts\\varredura.py --aplicar --limite 100

Amostra de 40 vagas do Greenhouse na fila: **22% estavam encerradas**. Some as 8
da inhire, todas mortas. O usuário escolhe o cartão, lê o dossiê, decide
candidatar — e leva 404. Fila com uma em cada cinco morta não é fila, é sorteio.

**Relata por padrão, só marca com `--aplicar`.** Encerrar vaga é irreversível na
prática: ela some da fila, e recuperá-la exige saber que existiu. Um erro meu em
massa custaria caro, então o padrão é mostrar antes.
"""
import argparse
import contextlib
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jobapplier import vigencia
from jobapplier.database.connection import get_session
from jobapplier.database.models import Vaga
from jobapplier.vigencia import Vigencia

#: Status que colocam a vaga na frente do usuário. Só eles são varridos: vaga já
#: descartada ou já candidatada não ganha nada em ser reclassificada.
NA_FILA = ("aprovada", "pendente", "pronta_envio_manual", "pronta_para_revisao",
           "aguardando_revisao", "adiada")

#: Pausa entre chamadas. A varredura bate em board de terceiro centenas de
#: vezes seguidas; sem intervalo isso parece ataque e é rude com quem hospeda.
INTERVALO_S = 0.4


def varrer(limite: int | None = None, aplicar: bool = False) -> int:
    with get_session() as sessao:
        vagas = (sessao.query(Vaga)
                 .filter(Vaga.status.in_(NA_FILA))
                 .order_by(Vaga.score.desc()).all())
        for v in vagas:
            sessao.expunge(v)
    if limite:
        vagas = vagas[:limite]

    if not vagas:
        print("\n  Fila vazia — nada a varrer.\n")
        return 0

    print(f"\n  {len(vagas)} vagas na fila"
          f"{' · MODO RELATÓRIO, nada será alterado' if not aplicar else ''}\n")

    contagem = Counter()
    encerradas: list[tuple[int, float, str, str, str]] = []
    inicio = time.monotonic()

    for i, vaga in enumerate(vagas, 1):
        estado, motivo = vigencia.checar(vaga)
        contagem[estado] += 1
        if estado is Vigencia.ENCERRADA:
            encerradas.append((vaga.id, vaga.score or 0, str(vaga.empresa or "")[:16],
                               str(vaga.titulo or "")[:44], motivo))
        if i % 50 == 0:
            print(f"    {i}/{len(vagas)}  ({time.monotonic() - inicio:.0f}s)",
                  flush=True)
        time.sleep(INTERVALO_S)

    total = len(vagas)
    print(f"\n  {'estado':<16}{'n':>6}{'%':>7}")
    for estado in (Vigencia.ABERTA, Vigencia.ENCERRADA, Vigencia.INDETERMINADA):
        n = contagem[estado]
        print(f"  {estado!s:<16}{n:>6}{n / total * 100:>6.0f}%")

    if encerradas:
        print(f"\n  encerradas, por score (as {min(15, len(encerradas))} maiores):")
        for _, score, empresa, titulo, motivo in sorted(
                encerradas, key=lambda x: -x[1])[:15]:
            print(f"    {score:>5.0f}  {empresa:<18}{titulo:<46}{motivo}")

    if not aplicar:
        print(f"\n  Nada foi alterado. Para marcar as {len(encerradas)}: "
              f"--aplicar\n")
        return 0

    with get_session() as sessao:
        for vid, *_ in encerradas:
            vaga = sessao.get(Vaga, vid)
            if vaga is not None:
                vaga.status = "encerrada"
    print(f"\n  {len(encerradas)} vagas marcadas como 'encerrada'.\n")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true",
                   help="marca no banco; sem isto só relata")
    p.add_argument("--limite", type=int, default=None,
                   help="varre apenas as N de maior score")
    args = p.parse_args(argv)
    return varrer(limite=args.limite, aplicar=args.aplicar)


if __name__ == "__main__":
    raise SystemExit(main())
