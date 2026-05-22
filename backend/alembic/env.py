"""
Alembic env.py para migraciones asíncronas con SQLAlchemy + PostGIS.
"""
import asyncio
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine
from alembic import context
import sys
from pathlib import Path

# Agregar directorio app al path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.models.persistence import Base
from app.core.config import settings

# Configuración de logging
if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

# Modelos para autogenerate
target_metadata = Base.metadata

def run_migrations_offline():
    """Ejecuta migraciones en modo 'offline'."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    """Ejecuta migraciones en modo 'online' con AsyncEngine."""
    connectable = AsyncEngine(
        engine_from_config(
            {"sqlalchemy.url": settings.DATABASE_URL},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: context.configure(
                connection=conn,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )
        )

        await connection.run_sync(lambda _: context.run_migrations())

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
