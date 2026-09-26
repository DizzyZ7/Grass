"""Synchronous ORM: one process, thread-pool handlers and PostgreSQL row locks."""
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    return create_engine(url, pool_pre_ping=True, pool_size=5 if not url.startswith('sqlite') else None)


# Deferred until dependency call: tests can override without real PostgreSQL.
_engine = None
_factory = None


def get_db() -> Generator[Session, None, None]:
    global _engine, _factory
    if _factory is None:
        _engine = make_engine(get_settings().database_url)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    with _factory() as db:
        yield db
