"""Startup migration: legacy focal mechanism tables gain schema_version."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.database import run_migrations
from app.models import FocalMechanismInversion, FocalMechanismSolution  # noqa: F401


def _legacy_schema_sqlite(path) -> None:
    """Create the pre-fix focal tables (no schema_version) with one report."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE focal_mechanism_inversions ("
                "id VARCHAR(36) PRIMARY KEY, "
                "request_hash VARCHAR(64) UNIQUE, "
                "request JSON, event_id VARCHAR(36), run_id VARCHAR(36), "
                "frozen JSON, grid_step_deg FLOAT, station_count INTEGER, "
                "solution_count INTEGER, min_misfit_weight FLOAT, "
                "created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE focal_mechanism_solutions ("
                "id VARCHAR(36) PRIMARY KEY, inversion_id VARCHAR(36), "
                "sort_index INTEGER, misfit_weight FLOAT, "
                "misfit_count INTEGER, detail JSON)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO focal_mechanism_inversions "
                "(id, request_hash, grid_step_deg, station_count, "
                "solution_count, min_misfit_weight, created_at) "
                "VALUES ('abc', 'h', 10.0, 6, 3, 1.0, '2026-09-01 00:00:00')"
            )
        )
    engine.dispose()


def test_migration_adds_column_and_backfills_legacy(tmp_path):
    import app.database as database

    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _legacy_schema_sqlite(db_path)

    original = database.engine
    database.engine = engine
    try:
        run_migrations()  # adds column, backfills to legacy version 1
        columns = {
            c["name"]
            for c in inspect(engine).get_columns("focal_mechanism_inversions")
        }
        assert "schema_version" in columns
        with engine.begin() as conn:
            version = conn.execute(
                text(
                    "SELECT schema_version FROM focal_mechanism_inversions "
                    "WHERE id = 'abc'"
                )
            ).scalar()
        assert version == 1

        # idempotent: a second pass neither errors nor rewrites anything
        run_migrations()
        with engine.begin() as conn:
            version = conn.execute(
                text(
                    "SELECT schema_version FROM focal_mechanism_inversions "
                    "WHERE id = 'abc'"
                )
            ).scalar()
        assert version == 1
    finally:
        database.engine = original
        engine.dispose()
