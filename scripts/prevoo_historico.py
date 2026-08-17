"""Pré-voo somente-leitura sobre as vagas já tentadas, para comparar os funis.

O histórico mostrou 293 tentativas e 10 envios. Mas "tentativa" incluía
retentativa do mesmo erro, e o denominador estava inflado. Este script reexecuta
o pré-voo — parser, descoberta do formulário, avaliação de preenchimento — sobre
as vagas **distintas**, sem submeter nada e sem gastar LLM, e mostra onde cada
uma pararia hoje.

O objetivo não é prever quantas seriam enviadas: é separar os dois funis.

    Seleção: a vaga merece candidatura?
    Execução: o sistema consegue candidatar com segurança?

    python scripts/prevoo_historico.py
    python scripts/prevoo_historico.py --limite 30 --csv data/reports/prevoo.csv
"""
import argparse
import contextlib
import csv
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

for fluxo in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        fluxo.reconfigure(encoding="utf-8", errors="replace")

#: Pausa entre consultas à API pública. Não é limite de candidatura — é
#: cortesia com um board que não pediu para ser varrido.
PAUSA_SEGUNDOS = 0.4


def _metricas_historicas(sessao) -> dict:
    from sqlalchemy import text

    tentativas = sessao.execute(text("SELECT count(*) FROM candidaturas")).scalar()
    distintas = sessao.execute(
        text("SELECT count(DISTINCT vaga_id) FROM candidaturas")
    ).scalar()
    enviadas = sessao.execute(text(
        "SELECT count(*) FROM candidaturas "
        "WHERE status IN ('enviada','enviada_confirmada')"
    )).scalar()
    vagas_enviadas = sessao.execute(text(
        "SELECT count(DISTINCT vaga_id) FROM candidaturas "
        "WHERE status IN ('enviada','enviada_confirmada')"
    )).scalar()

    return {
        "tentativas": tentativas,
        "vagas_distintas": distintas,
        "envios_confirmados": enviadas,
        "vagas_enviadas": vagas_enviadas,
        # Duas taxas, com nomes distintos: a primeira mistura confiabilidade com
        # o bug de retentativa; a segunda mede cobertura funcional por vaga.
        "success_rate_per_attempt": round(enviadas / tentativas, 3) if tentativas else 0,
        "success_rate_per_distinct_job": round(enviadas / distintas, 3) if distintas else 0,
        "retry_amplification": round(tentativas / distintas, 2) if distintas else 0,
        "duplicidades_externas": enviadas - vagas_enviadas,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limite", type=int, default=0, help="processa só N vagas")
    ap.add_argument("--csv", metavar="ARQUIVO")
    args = ap.parse_args()

    from sqlalchemy import text

    from jobapplier.applicators import base as applicators
    from jobapplier.applicators.identidade import resolver as resolver_identidade
    from jobapplier.config.manager import ConfigManager
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    resume_path = RAIZ / "data" / "resume.json"
    if not resume_path.exists():
        sys.exit("data/resume.json não encontrado.")
    import json

    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    dados = ConfigManager().get("dados_pessoais") or {}

    with get_session() as sessao:
        historico = _metricas_historicas(sessao)
        ids = sessao.execute(text(
            "SELECT DISTINCT vaga_id FROM candidaturas ORDER BY vaga_id"
        )).scalars().all()
        if args.limite:
            ids = ids[: args.limite]
        vagas = sessao.query(Vaga).filter(Vaga.id.in_(ids)).all()
        sessao.expunge_all()

    print("FUNIL ANTIGO (histórico real)")
    print("-" * 74)
    print(f"  tentativas de candidatura:      {historico['tentativas']}")
    print(f"  vagas distintas tentadas:       {historico['vagas_distintas']}")
    print(f"  envios confirmados:             {historico['envios_confirmados']}")
    print(f"  vagas distintas enviadas:       {historico['vagas_enviadas']}")
    print(f"  duplicidades EXTERNAS:          {historico['duplicidades_externas']}")
    print(f"  success_rate_per_attempt:       {historico['success_rate_per_attempt']:.1%}")
    print(f"  success_rate_per_distinct_job:  {historico['success_rate_per_distinct_job']:.1%}")
    print(f"  retry_amplification:            {historico['retry_amplification']}x")

    print(f"\nPRÉ-VOO DE HOJE sobre {len(vagas)} vaga(s) distinta(s)")
    print("-" * 74)

    etapas = Counter()
    prontidoes = Counter()
    bloqueios = Counter()
    linhas = []

    for i, vaga in enumerate(vagas, 1):
        identidade = resolver_identidade(vaga)
        if identidade is None:
            etapas["1_link_nao_reconhecido"] += 1
            linhas.append({"vaga_id": vaga.id, "empresa": vaga.empresa,
                           "etapa": "link_nao_reconhecido", "readiness": "-",
                           "confianca": "", "motivo": "parser não resolveu"})
            continue
        etapas["1_link_ok"] += 1

        if (vaga.plataforma or "").lower() != "greenhouse":
            etapas["2_sem_prevoo_na_plataforma"] += 1
            linhas.append({"vaga_id": vaga.id, "empresa": vaga.empresa,
                           "etapa": "sem_prevoo", "readiness": "-",
                           "confianca": "", "motivo": vaga.plataforma})
            continue

        avaliacao = applicators.avaliar_preenchimento(vaga, resume, dados)
        time.sleep(PAUSA_SEGUNDOS)

        prontidao = avaliacao["application_readiness"]
        prontidoes[prontidao] += 1
        etapas[f"3_{avaliacao['discovery_status']}"] += 1
        for b in avaliacao["blockers"]:
            bloqueios[b["codigo"]] += 1

        linhas.append({
            "vaga_id": vaga.id,
            "empresa": vaga.empresa,
            "etapa": avaliacao["discovery_status"],
            "readiness": prontidao,
            "confianca": avaliacao["application_confidence"],
            "motivo": avaliacao.get("blocking_reason") or "",
        })

        if i % 20 == 0:
            print(f"  ... {i}/{len(vagas)}")

    print("\n  onde cada vaga para hoje:")
    for etapa, n in sorted(etapas.items()):
        print(f"    {etapa:<32} {n:>4}")

    print("\n  prontidão para automação:")
    for p, n in prontidoes.most_common():
        print(f"    {p:<32} {n:>4}")

    if bloqueios:
        print("\n  bloqueadores:")
        for b, n in bloqueios.most_common():
            print(f"    {b:<32} {n:>4}")

    elegiveis = prontidoes.get("pronta", 0)
    total = len(vagas)
    print("\nBASELINE NOVO")
    print("-" * 74)
    print(f"  vagas avaliadas:                    {total}")
    print(f"  chegariam ao browser (pronta):      {elegiveis} "
          f"({elegiveis / total * 100:.0f}%)")
    print(f"  parariam antes, sem gastar LLM:     {total - elegiveis} "
          f"({(total - elegiveis) / total * 100:.0f}%)")
    print("\n  No funil antigo, todas essas gastariam otimização de currículo,")
    print("  PDF, cover letter e browser antes de descobrir que não dava.")

    if args.csv and linhas:
        destino = Path(args.csv)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)
        print(f"\nCSV: {destino}")


if __name__ == "__main__":
    main()
