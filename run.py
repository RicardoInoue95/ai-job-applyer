"""Launcher de desenvolvimento: sobe o Postgres, a UI e o orquestrador.

Único entry point na raiz. O domínio vive em ``jobapplier/`` e a UI em ``ui/``.
Todos os subprocessos herdam ``cwd=RAIZ``, para que ``ui/app.py`` seja
encontrado e ``data/`` resolva no mesmo lugar de onde quer que este script tenha
sido chamado.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from jobapplier.config import secrets  # noqa: E402  (após ajustar sys.path)


def esperar_postgres(url: str, tentativas: int = 10, espera: float = 2.0) -> bool:
    from sqlalchemy import create_engine, text

    engine = create_engine(url, pool_pre_ping=True)
    for tentativa in range(1, tentativas + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            print(f"  PostgreSQL não disponível (tentativa {tentativa}/{tentativas})...")
            time.sleep(espera)
    return False


def main():
    print("Iniciando AI Job Applier...")

    secrets.carregar_env()
    database_url = secrets.database_url()

    print("\n[1/3] Subindo PostgreSQL...")
    subprocess.run(
        ["docker", "compose", "up", "postgres", "-d"],
        check=True,
        cwd=RAIZ,
    )

    print("[2/3] Aguardando PostgreSQL ficar pronto...")
    if not esperar_postgres(database_url):
        print("ERRO: PostgreSQL não ficou disponível a tempo. Verifique o Docker.")
        sys.exit(1)
    print("  PostgreSQL pronto.")

    env = os.environ.copy()
    # DATABASE_URL sem prefixo é mantido por compatibilidade; database/connection
    # dá precedência a AIJOB_DATABASE_URL.
    env["DATABASE_URL"] = database_url
    env["AIJOB_DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(RAIZ) + os.pathsep + env.get("PYTHONPATH", "")

    print("[3/3] Iniciando processos...\n")

    processos = [
        subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", "ui/app.py",
                "--server.headless", "false",
                "--browser.gatherUsageStats", "false",
            ],
            env=env,
            cwd=RAIZ,
        ),
        subprocess.Popen(
            [sys.executable, "-m", "jobapplier.orchestrator"],
            env=env,
            cwd=RAIZ,
        ),
    ]

    print("App disponível em: http://localhost:8501")
    print("Pressione Ctrl+C para encerrar.\n")

    try:
        for p in processos:
            p.wait()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        for p in processos:
            p.terminate()
        for p in processos:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("Encerrado.")


if __name__ == "__main__":
    main()
