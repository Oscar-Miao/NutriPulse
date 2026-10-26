from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = SERVER_ROOT / "data" / "nutripulse.sqlite3"
MIGRATIONS = SERVER_ROOT / "migrations"


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def database_path() -> Path:
    return Path(os.environ.get("NUTRIPULSE_DB", str(DEFAULT_DB))).resolve()


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10, factory=ManagedConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def migrate() -> None:
    # A live-WAL-safe snapshot is required before any forward schema change.
    from app.infrastructure.db.backup import backup_before_migration
    backup_before_migration()
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        applied = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            if migration.stem in applied:
                continue
            script = migration.read_text(encoding="utf-8")
            # sqlite3.executescript commits implicitly, so wrap the entire
            # migration text in one explicit SQLite transaction.
            db.executescript("BEGIN IMMEDIATE;\n" + script +
                             f"\nINSERT INTO schema_migrations(version) VALUES ('{migration.stem}');\nCOMMIT;")


@contextmanager
def transaction():
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
