"""Phase 19: database session management.

SQLite for local development/testing (zero extra services to install or
run - this environment has no Docker and installing PostgreSQL needs sudo
this session doesn't have standing access to). Swappable to PostgreSQL in
production via the AT_DATABASE_URL environment variable - this is the
"start simple, scale later" the master spec itself asks for
("For initial development, don't overengineer it... FastAPI, PostgreSQL,
Redis, Docker and scale later"), not a permanent architectural choice.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("AT_DATABASE_URL", "sqlite:///./at_backend.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
