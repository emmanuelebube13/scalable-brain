"""FastAPI dependencies — shared resources and DB connections."""

from typing import Generator
import sqlalchemy as sa
from layer5.api.config import DB_SERVER, DB_USER, DB_PASS, DB_NAME
from layer5.services.db_client import get_engine


def get_db() -> Generator[sa.engine.Connection, None, None]:
    """Yield a SQLAlchemy connection for FastAPI dependency injection."""
    engine = get_engine(DB_SERVER, DB_USER, DB_PASS, DB_NAME)
    with engine.connect() as conn:
        yield conn
