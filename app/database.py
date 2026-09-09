"""Database engine and session helpers."""

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

# check_same_thread is a SQLite-only quirk; harmless to guard on the URL.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Create tables that don't exist yet. Called on app startup."""
    # Importing models registers them on SQLModel.metadata.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session
