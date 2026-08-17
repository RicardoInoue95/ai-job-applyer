"""Backup e restore do PostgreSQL.

O projeto não tinha nenhuma rotina de backup. O banco guarda o histórico de
candidaturas — para onde você se candidatou, com que score, com qual currículo.
O cache de LLM é recriável; esse histórico não é. E ele vive num bind mount
dentro da pasta do projeto, exatamente onde uma reinstalação ou um `git clean`
mal dado apaga tudo.

    python scripts/backup.py                    # cria dump, aplica retenção
    python scripts/backup.py --listar
    python scripts/backup.py --restaurar data/backups/jobapplier_20260817.sql.gz

O dump sai por `docker compose exec`, então não exige pg_dump instalado no host —
apenas o contêiner de pé. Formato SQL puro comprimido: legível, versão-tolerante
e restaurável com psql, ao contrário do formato custom.

O restore é destrutivo e pede confirmação explícita.
"""
import argparse
import gzip
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "backups"
SERVICO = "postgres"
BANCO = "jobapplier"
USUARIO = "jobapplier"

#: Quantos dumps manter. Diário por ~2 semanas é suficiente para o caso de uso:
#: perdas aqui são acidentes recentes, não corrupção silenciosa de meses.
RETENCAO = 14


def _compose(*args: str, entrada: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "exec", "-T", SERVICO, *args],
        cwd=RAIZ, capture_output=True, input=entrada, check=False,
    )


def _container_ativo() -> bool:
    r = _compose("pg_isready", "-U", USUARIO, "-q")
    return r.returncode == 0


def criar() -> Path:
    if not _container_ativo():
        sys.exit(
            "PostgreSQL não responde. Suba com: docker compose up postgres -d"
        )

    DESTINO.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    saida = DESTINO / f"{BANCO}_{marca}.sql.gz"

    print(f"Gerando dump de '{BANCO}'...")
    r = _compose("pg_dump", "-U", USUARIO, "--clean", "--if-exists", BANCO)
    if r.returncode != 0:
        sys.exit(f"pg_dump falhou:\n{r.stderr.decode('utf-8', 'replace')}")

    if len(r.stdout) < 1000:
        sys.exit(
            f"Dump suspeito de estar vazio ({len(r.stdout)} bytes). "
            "Abortando para não sobrescrever um backup bom por um ruim."
        )

    with gzip.open(saida, "wb") as f:
        f.write(r.stdout)

    mb = saida.stat().st_size / 1024 / 1024
    print(f"  {saida.name}  ({mb:.2f} MB, {len(r.stdout) / 1024 / 1024:.2f} MB sem compressão)")

    _aplicar_retencao()
    return saida


def _aplicar_retencao() -> None:
    dumps = sorted(DESTINO.glob(f"{BANCO}_*.sql.gz"), reverse=True)
    for antigo in dumps[RETENCAO:]:
        antigo.unlink()
        print(f"  retenção: removido {antigo.name}")


def listar() -> None:
    dumps = sorted(DESTINO.glob(f"{BANCO}_*.sql.gz"), reverse=True)
    if not dumps:
        print(f"Nenhum backup em {DESTINO}")
        return
    print(f"{len(dumps)} backup(s) em {DESTINO}:")
    for d in dumps:
        mb = d.stat().st_size / 1024 / 1024
        quando = datetime.fromtimestamp(d.stat().st_mtime, tz=UTC)
        print(f"  {d.name:<40} {mb:>7.2f} MB   {quando:%Y-%m-%d %H:%M} UTC")


def restaurar(caminho: Path, confirmado: bool = False) -> None:
    caminho = Path(caminho)
    if not caminho.exists():
        sys.exit(f"Backup não encontrado: {caminho}")
    if not _container_ativo():
        sys.exit("PostgreSQL não responde. Suba com: docker compose up postgres -d")

    if not confirmado:
        print(f"\nATENÇÃO: restaurar '{caminho.name}' SOBRESCREVE o banco atual.")
        print("Todo dado posterior a este dump será perdido.")
        if input("Digite 'restaurar' para confirmar: ").strip() != "restaurar":
            sys.exit("Cancelado.")

    print("Restaurando...")
    with gzip.open(caminho, "rb") as f:
        sql = f.read()

    r = _compose("psql", "-U", USUARIO, "-d", BANCO, "-v", "ON_ERROR_STOP=1", entrada=sql)
    if r.returncode != 0:
        sys.exit(f"Restore falhou:\n{r.stderr.decode('utf-8', 'replace')[-3000:]}")

    print("Restore concluído. Confira as contagens:")
    r = _compose(
        "psql", "-U", USUARIO, "-d", BANCO, "-c",
        "SELECT 'vagas' t, count(*) FROM vagas "
        "UNION ALL SELECT 'candidaturas', count(*) FROM candidaturas;",
    )
    print(r.stdout.decode("utf-8", "replace"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--listar", action="store_true", help="lista backups existentes")
    ap.add_argument("--restaurar", metavar="ARQUIVO", help="restaura um dump (destrutivo)")
    ap.add_argument("--sim", action="store_true", help="pula a confirmação do restore")
    args = ap.parse_args()

    if args.listar:
        listar()
    elif args.restaurar:
        restaurar(Path(args.restaurar), confirmado=args.sim)
    else:
        criar()


if __name__ == "__main__":
    main()
