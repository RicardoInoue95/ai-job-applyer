import os
import subprocess
import sys
import time

DATABASE_URL = "postgresql://jobapplier:jobapplier@localhost:5432/jobapplier"


def wait_for_postgres(retries: int = 10, delay: float = 2.0) -> bool:
    from sqlalchemy import create_engine, text

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            print(f"  PostgreSQL não disponível (tentativa {attempt}/{retries})...")
            time.sleep(delay)
    return False


def main():
    print("Iniciando AI Job Applier...")

    print("\n[1/3] Subindo PostgreSQL...")
    subprocess.run(
        ["docker", "compose", "up", "postgres", "-d"],
        check=True,
    )

    print("[2/3] Aguardando PostgreSQL ficar pronto...")
    if not wait_for_postgres():
        print("ERRO: PostgreSQL não ficou disponível a tempo. Verifique o Docker.")
        sys.exit(1)
    print("  PostgreSQL pronto.")

    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL

    print("[3/3] Iniciando processos...\n")

    processes = [
        subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", "app.py",
                "--server.headless", "false",
                "--browser.gatherUsageStats", "false",
            ],
            env=env,
        ),
        subprocess.Popen(
            [sys.executable, "orchestrator.py"],
            env=env,
        ),
    ]

    print("App disponível em: http://localhost:8501")
    print("Pressione Ctrl+C para encerrar.\n")

    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("Encerrado.")


if __name__ == "__main__":
    main()
