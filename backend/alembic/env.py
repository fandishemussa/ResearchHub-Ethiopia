"""Alembic environment for online and offline migrations."""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from researchhub.core.config import get_settings  # noqa: E402
from researchhub.infrastructure.persistence import models  # noqa: F401,E402
from researchhub.infrastructure.persistence.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
migration_url = settings.sync_database_url
if migration_url.startswith("postgresql://"):
    migration_url = migration_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif migration_url.startswith("postgres://"):
    migration_url = migration_url.replace("postgres://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", migration_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating an engine."""

    context.configure(
        url=migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live database connection."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
