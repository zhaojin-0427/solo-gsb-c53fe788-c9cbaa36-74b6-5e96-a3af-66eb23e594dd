"""Database engine / session management."""
from __future__ import annotations

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config

_is_sqlite = config.DATABASE_URL.startswith("sqlite")
connect_args = (
    {"check_same_thread": False, "timeout": 30.0} if _is_sqlite else {}
)
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # WAL + busy_timeout let concurrent creators/activators block on the
        # unique constraints instead of failing with "database is locked".
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


class Base(DeclarativeBase):
    pass


def run_migrations() -> None:
    """Idempotent lightweight migrations for columns added after first release.

    ``Base.metadata.create_all`` only creates missing tables, so columns added
    to existing tables are brought in here with portable DDL; rows created
    before a column existed are backfilled to the legacy value and never
    touched again.
    """
    inspector = inspect(engine)
    if "focal_mechanism_inversions" not in inspector.get_table_names():
        return  # fresh database: create_all builds the table with the new column
    columns = {c["name"] for c in inspector.get_columns("focal_mechanism_inversions")}
    with engine.begin() as conn:
        if "schema_version" not in columns:
            # Reports already stored were produced under the sign-merging
            # dedup rule, so they start at schema version 1; the service
            # repairs them lazily to 2 on their next request/query.
            conn.execute(
                text(
                    "ALTER TABLE focal_mechanism_inversions "
                    "ADD COLUMN schema_version INTEGER"
                )
            )
            conn.execute(
                text(
                    "UPDATE focal_mechanism_inversions SET schema_version = 1 "
                    "WHERE schema_version IS NULL"
                )
            )


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
