"""Alembic autogeneration reads the same metadata as the application."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from backend.app.config import get_settings
from backend.app.db import Base
from backend.app import models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
url = get_settings().database_url
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
config.set_main_option('sqlalchemy.url', url.replace('%', '%%'))
target_metadata = Base.metadata


def offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={'paramstyle': 'named'}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def online():
    engine = engine_from_config(config.get_section(config.config_ini_section),
                                prefix='sqlalchemy.', poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    offline()
else:
    online()
