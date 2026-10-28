"""Versioned schema initialisation.

`schema_version` records which migrations have run. Version 1 creates the
initial tables from the ORM metadata; any later schema change must be added
as a new numbered step (explicit DDL), never by editing an applied one. This
keeps existing local databases (experiment history) usable across upgrades
without pulling in Alembic for a single-user tool.
"""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.db.database import Base
from app.models import experiment  # noqa: F401  (registers the models on Base.metadata)


def _v1_initial(conn: Connection) -> None:
    Base.metadata.create_all(conn)


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "initial schema: experiments, variant_results, repetitions, cache_sim_rows, reports", _v1_initial),
]


def current_version(eng: Engine) -> int:
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_version ("
                          "version INTEGER PRIMARY KEY, description TEXT NOT NULL)"))
        return int(conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_version")).scalar_one())


def migrate(eng: Engine) -> int:
    """Apply pending migrations, each in its own transaction. Returns the final version."""
    version = current_version(eng)
    for number, description, step in MIGRATIONS:
        if number <= version:
            continue
        with eng.begin() as conn:
            step(conn)
            conn.execute(text("INSERT INTO schema_version (version, description) VALUES (:v, :d)"),
                         {"v": number, "d": description})
        version = number
    return version
