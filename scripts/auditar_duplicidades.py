"""Auditoria das vagas com mais de uma candidatura.

A migration 004 renumerou duplicatas em ciclos para poder criar a constraint de
unicidade. O número máximo foi 5 — mas `ciclo` é só uma renumeração mecânica, e
até se entender o que ele representa nos dados reais, ele não deve virar
mecanismo operacional de recandidatura.

Cinco candidaturas para a mesma vaga podem significar coisas muito diferentes:

- cinco submissões reais (dano reputacional com o recrutador)
- retentativas de uma falha técnica (nada chegou, e o problema é outro)
- vaga republicada (recandidatura legítima)
- URLs distintas dedupadas só depois (falha da identidade antiga)
- falso negativo de confirmação: enviou, não reconheceu, tentou de novo

Este script não conclui por você — ele separa os casos e mostra a evidência.

    python scripts/auditar_duplicidades.py
    python scripts/auditar_duplicidades.py --csv data/reports/duplicidades.csv
"""
import argparse
import contextlib
import csv
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

for fluxo in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        fluxo.reconfigure(encoding="utf-8", errors="replace")

#: Status que indicam que algo chegou à plataforma. O resto é tentativa que
#: não saiu — e repetir depois de uma dessas é retry, não recandidatura.
CHEGOU = {"enviada_confirmada", "revisao_manual", "enviada", "perguntas_pendentes"}

#: Abaixo disto, duas candidaturas são a mesma tentativa repetida, não uma
#: decisão nova de se candidatar.
MINUTOS_RETRY = 60


def _classificar(tentativas: list[dict]) -> tuple[str, str]:
    """Diagnostica o padrão de um grupo de candidaturas à mesma vaga."""
    chegaram = [t for t in tentativas if t["status"] in CHEGOU]
    confirmadas = [t for t in tentativas if t["status"] in ("enviada_confirmada", "enviada")]

    intervalos = [
        (tentativas[i + 1]["criado_em"] - tentativas[i]["criado_em"]).total_seconds() / 60
        for i in range(len(tentativas) - 1)
        if tentativas[i + 1]["criado_em"] and tentativas[i]["criado_em"]
    ]
    proximas = [m for m in intervalos if m <= MINUTOS_RETRY]

    if len(confirmadas) > 1:
        return "envio_multiplo_confirmado", (
            f"{len(confirmadas)} envios confirmados — o recrutador recebeu mais de uma vez"
        )
    if len(chegaram) > 1:
        return "chegou_mais_de_uma_vez", (
            f"{len(chegaram)} tentativas alcançaram a plataforma, "
            f"{len(confirmadas)} confirmada(s)"
        )
    if not chegaram:
        return "so_falhas", (
            f"{len(tentativas)} tentativas, nenhuma chegou — retry de falha técnica"
        )
    if proximas and len(proximas) == len(intervalos):
        return "retry_imediato", (
            f"todas as repetições em até {MINUTOS_RETRY}min — mesma tentativa"
        )
    return "uma_chegou_resto_falhou", (
        f"1 chegou, {len(tentativas) - 1} falharam antes ou depois"
    )


def _fmt(dt) -> str:
    return dt.strftime("%d/%m %H:%M") if dt else "-"


def auditar() -> list[dict]:
    from sqlalchemy import text

    from jobapplier.database.connection import get_session

    with get_session() as sessao:
        duplicadas = sessao.execute(text("""
            SELECT vaga_id FROM candidaturas
            GROUP BY vaga_id HAVING count(*) > 1
            ORDER BY count(*) DESC, vaga_id
        """)).scalars().all()

        linhas = []
        for vaga_id in duplicadas:
            vaga = sessao.execute(text("""
                SELECT id, plataforma, fonte_vaga_id, empresa, titulo, link, status
                FROM vagas WHERE id = :id
            """), {"id": vaga_id}).mappings().first()

            tentativas = [dict(r) for r in sessao.execute(text("""
                SELECT id, ciclo, status, criado_em, curriculo_path, erro
                FROM candidaturas WHERE vaga_id = :id ORDER BY criado_em, id
            """), {"id": vaga_id}).mappings().all()]

            padrao, explicacao = _classificar(tentativas)
            curriculos = {
                Path(t["curriculo_path"]).name
                for t in tentativas if t["curriculo_path"]
            }
            datas = [t["criado_em"] for t in tentativas if t["criado_em"]]
            janela = (
                (max(datas) - min(datas)).total_seconds() / 3600 if len(datas) > 1 else 0
            )

            linhas.append({
                "vaga_id": vaga_id,
                "plataforma": vaga["plataforma"] if vaga else "?",
                "fonte_vaga_id": (vaga["fonte_vaga_id"] if vaga else None) or "-",
                "empresa": (vaga["empresa"] if vaga else "?")[:28],
                "titulo": (vaga["titulo"] if vaga else "?")[:44],
                "status_vaga": vaga["status"] if vaga else "?",
                "n_candidaturas": len(tentativas),
                "ciclo_max": max(t["ciclo"] for t in tentativas),
                "statuses": ", ".join(t["status"] for t in tentativas),
                "primeira": _fmt(min(datas)) if datas else "-",
                "ultima": _fmt(max(datas)) if datas else "-",
                "janela_horas": round(janela, 1),
                "curriculos_distintos": len(curriculos),
                "padrao": padrao,
                "explicacao": explicacao,
            })
    return linhas


def _classificar_erro(status: str, erro: str) -> str:
    erro = (erro or "").strip()
    if not erro:
        return "(sem detalhe)"
    if erro.startswith("["):
        return "perguntas de triagem sem resposta automática"
    if "Link inválido" in erro:
        return "link não reconhecido pelo parser"
    if "submit não encontrado" in erro:
        return "botão de submit não encontrado"
    if "EUA" in erro or "United States" in erro:
        return "vaga exclusiva dos EUA"
    if "CPF" in erro:
        return "CPF não configurado"
    if "imeout" in erro:
        return "timeout"
    if "Easy Apply não encontrado" in erro:
        return "sem Easy Apply no LinkedIn"
    return "outro"


def panorama() -> None:
    """Taxa real de sucesso do histórico e por que as tentativas falharam.

    A pergunta que ninguém tinha feito: das candidaturas que o sistema tentou,
    quantas de fato saíram? Sem isto, contar cover letters geradas dá a impressão
    de que houve candidatura — quando a maioria parou antes de submeter.
    """
    from sqlalchemy import text

    from jobapplier.database.connection import get_session

    with get_session() as sessao:
        total = sessao.execute(text("SELECT count(*) FROM candidaturas")).scalar()
        if not total:
            return
        enviadas = sessao.execute(text(
            "SELECT count(*) FROM candidaturas "
            "WHERE status IN ('enviada','enviada_confirmada')"
        )).scalar()
        vagas = sessao.execute(
            text("SELECT count(DISTINCT vaga_id) FROM candidaturas")
        ).scalar()

        print("PANORAMA DO HISTÓRICO")
        print("-" * 78)
        print(f"  tentativas de candidatura: {total}")
        print(f"  vagas distintas tentadas:  {vagas}")
        print(f"  ENVIADAS de fato:          {enviadas}  "
              f"({enviadas / total * 100:.1f}% das tentativas)")

        falhas = sessao.execute(text(
            "SELECT status, erro FROM candidaturas "
            "WHERE status NOT IN ('enviada','enviada_confirmada')"
        )).all()

    motivos = Counter(_classificar_erro(st, e) for st, e in falhas)
    print(f"\n  por que as outras {len(falhas)} não saíram:")
    for motivo, n in motivos.most_common(6):
        print(f"    {n:>4}  {motivo}  ({n / len(falhas) * 100:.0f}%)")

    # Falhas que a avaliação de preenchimento agora detecta ANTES de gastar
    # token de LLM e abrir browser.
    evitaveis = (
        motivos["perguntas de triagem sem resposta automática"]
        + motivos["link não reconhecido pelo parser"]
        + motivos["vaga exclusiva dos EUA"]
        + motivos["CPF não configurado"]
    )
    print(f"\n  detectáveis em pré-voo pela avaliação de preenchimento: "
          f"{evitaveis} de {len(falhas)} ({evitaveis / len(falhas) * 100:.0f}%)")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", metavar="ARQUIVO", help="também grava um CSV")
    ap.add_argument("--detalhe", metavar="PADRAO",
                    help="lista as vagas de um padrão específico")
    args = ap.parse_args()

    panorama()
    linhas = auditar()
    if not linhas:
        print("Nenhuma vaga com mais de uma candidatura.")
        return

    print(f"{len(linhas)} vaga(s) com mais de uma candidatura\n")

    padroes = Counter(x["padrao"] for x in linhas)
    print("PADRÃO DAS DUPLICIDADES")
    print("-" * 78)
    for padrao, n in padroes.most_common():
        exemplo = next(x for x in linhas if x["padrao"] == padrao)
        print(f"  {padrao:<28} {n:>4} vaga(s)   {exemplo['explicacao'][:36]}")

    confirmados = [x for x in linhas if x["padrao"] == "envio_multiplo_confirmado"]
    print("\nO QUE IMPORTA PARA A DECISÃO SOBRE 'ciclo'")
    print("-" * 78)
    print(f"  candidaturas realmente duplicadas ao recrutador: {len(confirmados)}")
    print(f"  duplicidade que foi só retry de falha técnica:   "
          f"{padroes['so_falhas'] + padroes['retry_imediato']}")
    print(f"  vagas com currículos diferentes entre tentativas: "
          f"{sum(1 for x in linhas if x['curriculos_distintos'] > 1)}")
    curtas = sum(1 for x in linhas if x["janela_horas"] <= 1)
    print(f"  repetições dentro de 1 hora:                     {curtas}")

    if args.detalhe:
        alvo = [x for x in linhas if x["padrao"] == args.detalhe]
        print(f"\nDETALHE — {args.detalhe} ({len(alvo)} vagas)")
        print("-" * 78)
        for x in alvo[:25]:
            print(f"  vaga {x['vaga_id']:<6} {x['empresa']:<28} {x['titulo'][:36]}")
            print(f"       {x['n_candidaturas']}x · {x['primeira']} → {x['ultima']} "
                  f"({x['janela_horas']}h) · {x['statuses'][:60]}")
    else:
        print("\nPIORES CASOS (mais candidaturas)")
        print("-" * 78)
        for x in sorted(linhas, key=lambda z: -z["n_candidaturas"])[:10]:
            print(f"  vaga {x['vaga_id']:<6} {x['n_candidaturas']}x  {x['empresa']:<26} "
                  f"{x['titulo'][:34]}")
            print(f"       {x['padrao']} · {x['primeira']} → {x['ultima']} "
                  f"({x['janela_horas']}h)")

    if args.csv:
        destino = Path(args.csv)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=list(linhas[0]))
            escritor.writeheader()
            escritor.writerows(linhas)
        print(f"\nCSV: {destino}")

    print("\nEnquanto os padrões não forem interpretados, 'ciclo' permanece")
    print("descritivo. Recandidatura automática segue desabilitada.")


if __name__ == "__main__":
    main()
