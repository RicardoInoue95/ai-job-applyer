"""Sequência de migração do banco, com evidência em cada passo.

Migration aplicada sem verificação é como candidatura sem confirmação: parece
que deu certo. Este script executa a sequência acordada e imprime, ao final, o
quadro de evidências que atesta a conclusão — ou para no primeiro passo que
falhar, sem seguir adiante.

    python scripts/migrar.py            # executa a sequência
    python scripts/migrar.py --seco     # só diagnostica, não altera nada

Ordem: diagnóstico → backup validado → contagens antes → upgrade → confirmação
de head → contagens depois → recuperação de lease.
"""
import argparse
import contextlib
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# O console do Windows usa cp1252 por padrão, que não representa os caracteres de
# caixa nem os acentos deste relatório — e um UnicodeEncodeError no print faria
# a sequência parecer ter falhado depois de a migration já ter sido aplicada.
for fluxo in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        fluxo.reconfigure(encoding="utf-8", errors="replace")

TABELAS = ("vagas", "candidaturas", "empresas", "aprovacoes_historico",
           "cache_gemini", "execucoes")

#: Tabelas que a migration 003+ cria. Não existem antes, e a ausência delas
#: numa contagem "antes" é esperada, não perda de dado.
TABELAS_NOVAS = {"execucoes"}


class Passo:
    """Um passo com evidência. Falha interrompe a sequência."""

    def __init__(self, numero, titulo: str):
        self.numero, self.titulo = numero, titulo

    def __enter__(self):
        print(f"\n[{self.numero}] {self.titulo}")
        return self

    def __exit__(self, *_):
        return False

    def ok(self, msg: str) -> None:
        print(f"    ok: {msg}")

    def falhar(self, msg: str) -> None:
        print(f"    FALHOU: {msg}")
        print("\nSequência interrompida. Nada além deste ponto foi executado.")
        sys.exit(1)


def _rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=RAIZ, capture_output=True, text=True, check=False)


def _contagens() -> dict[str, int | None]:
    """Linhas por tabela. None quando a tabela ainda não existe."""
    from sqlalchemy import text

    from jobapplier.database.connection import get_engine

    resultado: dict[str, int | None] = {}
    for tabela in TABELAS:
        try:
            with get_engine().connect() as conn:
                resultado[tabela] = conn.execute(
                    text(f"SELECT count(*) FROM {tabela}")
                ).scalar()
        except Exception:
            resultado[tabela] = None
    return resultado


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seco", action="store_true",
                    help="apenas diagnostica; não faz backup nem upgrade")
    args = ap.parse_args()

    from jobapplier.database import schema

    # ── 1. Diagnóstico ───────────────────────────────────────────────────────
    with Passo(1, "Diagnóstico do banco") as p:
        estado = schema.verificar()
        if not estado.acessivel:
            p.falhar(
                f"{estado.mensagem()}\n"
                "    Suba o banco com: docker compose up postgres -d"
            )
        p.ok(f"acessível · revisão aplicada: {estado.aplicada or '(nenhuma)'} "
             f"· head esperado: {estado.esperada}")

    # ── 1b. Identidade do banco ──────────────────────────────────────────────
    # Antes de QUALQUER escrita: confirmar que este é o banco deste projeto.
    # Esta máquina já teve outro projeto ocupando a 5432, e um upgrade ali
    # teria migrado a base de outro sistema.
    with Passo("1b", "Identidade do banco") as p:
        certo, detalhe = schema.confirmar_identidade()
        if not certo:
            p.falhar(detalhe)
        p.ok(detalhe)

    revisao_antes = estado.aplicada

    if estado.em_head:
        print("\nBanco já está em head. Nada a migrar.")
        _relatorio(revisao_antes, estado.esperada, None, None, backup=None)
        return

    if args.seco:
        print(f"\n[seco] Migraria de {revisao_antes or '(vazio)'} para {estado.esperada}.")
        return

    # ── 2. Backup validado ───────────────────────────────────────────────────
    with Passo(2, "Backup, com validação do dump") as p:
        r = _rodar(sys.executable, str(RAIZ / "scripts" / "backup.py"))
        if r.returncode != 0:
            p.falhar(f"backup falhou:\n{(r.stderr or r.stdout)[-800:]}")
        linha = [x for x in r.stdout.splitlines() if "validação:" in x]
        p.ok(linha[0].strip() if linha else "dump criado")

    backups = sorted((RAIZ / "data" / "backups").glob("*.sql.gz"), reverse=True)
    backup = backups[0] if backups else None

    # ── 3. Contagens antes ───────────────────────────────────────────────────
    with Passo(3, "Contagens antes da migration") as p:
        antes = _contagens()
        p.ok(", ".join(f"{t}={v if v is not None else '-'}" for t, v in antes.items()))

    # ── 4. Upgrade ───────────────────────────────────────────────────────────
    with Passo(4, "alembic upgrade head") as p:
        r = _rodar(sys.executable, "-m", "alembic", "upgrade", "head")
        if r.returncode != 0:
            p.falhar(
                f"{(r.stderr or r.stdout)[-1500:]}\n"
                f"    Restaure com: python scripts/backup.py --restaurar {backup}"
            )
        p.ok("aplicado")

    # ── 5. Confirmação de head ───────────────────────────────────────────────
    with Passo(5, "Confirmação da revisão") as p:
        depois_estado = schema.verificar()
        if not depois_estado.em_head:
            p.falhar(f"ainda fora de head: {depois_estado.mensagem()}")
        p.ok(f"revisão aplicada = {depois_estado.aplicada} (head)")

    # ── 6. Contagens depois ──────────────────────────────────────────────────
    with Passo(6, "Contagens depois, comparadas") as p:
        depois = _contagens()
        perdas = [
            f"{t}: {antes[t]} → {depois[t]}"
            for t in TABELAS
            if antes.get(t) is not None
            and depois.get(t) is not None
            and depois[t] < antes[t]
        ]
        if perdas:
            p.falhar(
                "PERDA DE DADOS: " + "; ".join(perdas)
                + f"\n    Restaure com: python scripts/backup.py --restaurar {backup}"
            )
        novas = [t for t in TABELAS_NOVAS if antes.get(t) is None and depois.get(t) is not None]
        p.ok(", ".join(f"{t}={v if v is not None else '-'}" for t, v in depois.items())
             + (f" · tabelas criadas: {novas}" if novas else ""))

    # ── 7. Recuperação de lease ──────────────────────────────────────────────
    with Passo(7, "Recuperação de leases órfãos") as p:
        from jobapplier.safety import guard

        liberadas = guard.liberar_orfaos()
        p.ok(f"{liberadas} vaga(s) com lease expirado devolvida(s) à fila")

    # ── 8. Pipeline liberado? ────────────────────────────────────────────────
    with Passo(8, "run_applications deixou de bloquear?") as p:
        estado_final = schema.verificar()
        if not estado_final.em_head:
            p.falhar("schema ainda fora de head")
        p.ok("candidaturas liberadas do bloqueio de schema")

    _relatorio(revisao_antes, depois_estado.aplicada, antes, depois, backup)


def _relatorio(antes_rev, depois_rev, antes, depois, backup) -> None:
    print("\n" + "─" * 62)
    print("EVIDÊNCIA DA MIGRAÇÃO")
    print("-" * 62)
    print(f"  revision antes:        {antes_rev or '(nenhuma)'}")
    print(f"  revision depois:       {depois_rev}")
    print(f"  schema em head:        {'sim' if depois_rev else 'não'}")
    print(f"  backup validado:       {backup.name if backup else '(não necessário)'}")
    if antes and depois:
        preservadas = all(
            depois.get(t) is None or antes.get(t) is None or depois[t] >= antes[t]
            for t in TABELAS
        )
        print(f"  contagens preservadas: {'sim' if preservadas else 'NÃO'}")
    print("\nPróximo: python -m pytest -m db   (testes de integração)")


if __name__ == "__main__":
    main()
