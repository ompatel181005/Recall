"""SQLite engine and session helpers (SQLModel)."""

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False}
)


def init_db() -> None:
    from . import models  # noqa: F401  — register tables

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
