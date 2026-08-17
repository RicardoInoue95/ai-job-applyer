"""Verificação de que o banco está na revisão esperada do Alembic.

Migrations escritas e não aplicadas criam uma divergência silenciosa entre três
coisas que deveriam concordar: a arquitetura documentada, os models em código e
o banco realmente em uso. O sintoma aparece tarde e no pior lugar — um
`UndefinedColumn` no meio de uma candidatura, com a vaga já marcada como
`em_andamento`.

Regra: **nada de candidatura real com o schema fora de `head`.** A coleta e a UI
continuam funcionando, porque são leitura e não gravam decisão irreversível; o
que para é a esteira que age em nome do usuário.
"""
import logging
from dataclasses import dataclass

from jobapplier import paths

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EstadoSchema:
    """Comparação entre a revisão aplicada no banco e a esperada pelo código."""

    aplicada: str | None
    esperada: str | None
    acessivel: bool
    detalhe: str = ""

    @property
    def em_head(self) -> bool:
        return self.acessivel and self.aplicada is not None and self.aplicada == self.esperada

    def mensagem(self) -> str:
        if not self.acessivel:
            return f"Banco inacessível: {self.detalhe}"
        if self.aplicada is None:
            return (
                "Banco sem nenhuma migration aplicada. Rode: "
                "python -m alembic upgrade head"
            )
        if not self.em_head:
            return (
                f"Schema desatualizado: banco em '{self.aplicada}', código espera "
                f"'{self.esperada}'. Faça backup e rode: "
                f"python scripts/backup.py && python -m alembic upgrade head"
            )
        return f"Schema em head ({self.aplicada})."


def _config_alembic():
    from alembic.config import Config

    cfg = Config(str(paths.RAIZ / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(paths.RAIZ / "jobapplier" / "database" / "migrations")
    )
    return cfg


def revisao_esperada() -> str | None:
    """Revisão `head` segundo os arquivos de migration. Não toca o banco."""
    try:
        from alembic.script import ScriptDirectory

        return ScriptDirectory.from_config(_config_alembic()).get_current_head()
    except Exception as exc:
        logger.warning("Não foi possível ler as migrations: %s", exc)
        return None


def revisao_aplicada() -> tuple[str | None, bool, str]:
    """Revisão gravada no banco. Retorna (revisão, acessível, detalhe)."""
    try:
        from alembic.runtime.migration import MigrationContext

        from jobapplier.database.connection import get_engine

        with get_engine().connect() as conn:
            return MigrationContext.configure(conn).get_current_revision(), True, ""
    except Exception as exc:
        return None, False, str(exc)


def verificar() -> EstadoSchema:
    """Estado do schema. Nunca levanta — quem chama decide o que fazer."""
    aplicada, acessivel, detalhe = revisao_aplicada()
    return EstadoSchema(
        aplicada=aplicada,
        esperada=revisao_esperada(),
        acessivel=acessivel,
        detalhe=detalhe,
    )


def exigir_head() -> EstadoSchema:
    """Verifica e loga. Use o retorno para decidir se pode agir.

    Não levanta exceção de propósito: o orquestrador precisa continuar rodando as
    esteiras de leitura mesmo com o schema atrasado, e só recusar a de escrita.
    """
    estado = verificar()
    if estado.em_head:
        logger.info(estado.mensagem())
    else:
        logger.error("SCHEMA FORA DE HEAD — %s", estado.mensagem())
    return estado
