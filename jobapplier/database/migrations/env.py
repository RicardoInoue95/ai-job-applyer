import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from jobapplier.database.connection import DATABASE_URL  # noqa: E402
from jobapplier.database.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# DATABASE_URL vem de jobapplier.database.connection, que passa por
# config.secrets. Este arquivo tinha a própria resolução, com
# "localhost:5432/jobapplier" hardcoded como default — duas fontes de verdade
# para o mesmo endereço.
#
# Não era teórico: esta máquina tem outro projeto ocupando a 5432. Enquanto a
# aplicação já apontava para a porta correta, o Alembic seguia tentando conectar
# no banco alheio. Só a senha não bater impediu um upgrade na base errada.


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
