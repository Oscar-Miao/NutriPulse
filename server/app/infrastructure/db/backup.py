"""Consistent SQLite snapshots, verified restore, and bounded local retention.

Backups contain sensitive health data. They are intentionally local files and
are never exposed through the HTTP API. Restore refuses an existing target.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.infrastructure.db.database import MIGRATIONS, database_path


FORMAT = "nutripulse-sqlite-backup-v1"
KINDS = {"manual", "daily", "weekly", "pre-migration"}
BACKUP_NAME = re.compile(r"^nutripulse-(manual|daily|weekly|pre-migration)-([A-Za-z0-9_-]+)\.sqlite3$")


class BackupError(RuntimeError):
    pass


def backup_directory() -> Path:
    configured = os.environ.get("NUTRIPULSE_BACKUP_DIR")
    return Path(configured).resolve() if configured else database_path().parent / "backups"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect(path: Path) -> dict:
    if not path.is_file():
        raise BackupError(f"数据库文件不存在：{path}")
    # A published backup is a complete, immutable main database file. Opening
    # it this way does not create -wal/-shm sidecars during verification.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=10)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("SQLite 完整性检查失败")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError("SQLite 外键检查失败")
        names = sorted(row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        counts = {}
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            counts[name] = db.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        versions = [row[0] for row in db.execute("SELECT version FROM schema_migrations ORDER BY version")] \
            if "schema_migrations" in counts else []
    return {"table_counts": counts, "schema_versions": versions}


def verify_backup(path: str | Path) -> dict:
    backup = Path(path).resolve()
    if BACKUP_NAME.fullmatch(backup.name) is None:
        raise BackupError("不是 NutriPulse 备份文件名")
    manifest_path = backup.with_suffix(".json")
    if not backup.is_file() or not manifest_path.is_file():
        raise BackupError("备份或校验清单缺失")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as error:
        raise BackupError("备份清单无法读取") from error
    if manifest.get("format") != FORMAT or manifest.get("filename") != backup.name:
        raise BackupError("备份清单格式或文件名不匹配")
    if manifest.get("bytes") != backup.stat().st_size or manifest.get("sha256") != _hash_file(backup):
        raise BackupError("备份大小或 SHA-256 不匹配")
    inspected = _inspect(backup)
    if inspected != {key: manifest.get(key) for key in ("table_counts", "schema_versions")}:
        raise BackupError("备份表计数或迁移版本与清单不一致")
    return manifest


def create_backup(kind: str = "manual", label: str | None = None,
                  source: str | Path | None = None, directory: str | Path | None = None) -> Path:
    if kind not in KINDS:
        raise BackupError("备份类型无效")
    source_path = Path(source).resolve() if source else database_path()
    if not source_path.is_file():
        raise BackupError("源数据库不存在，不创建空库备份")
    stamp = label or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S%f")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", stamp):
        raise BackupError("备份标签无效")
    folder = Path(directory).resolve() if directory else backup_directory()
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f"nutripulse-{kind}-{stamp}.sqlite3"
    if backup.exists() or backup.with_suffix(".json").exists():
        verify_backup(backup)
        return backup
    fd, temp_name = tempfile.mkstemp(prefix=".nutripulse-backup-", suffix=".tmp", dir=folder)
    os.close(fd)
    temporary = Path(temp_name)
    published_by_this_call = False
    try:
        with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=10)) as original:
            with closing(sqlite3.connect(temporary)) as copy:
                original.backup(copy)
                if copy.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                    raise BackupError("无法将备份转换为独立单文件格式")
        inspected = _inspect(temporary)
        manifest = {"format": FORMAT, "filename": backup.name, "kind": kind,
                    "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                    "bytes": temporary.stat().st_size, "sha256": _hash_file(temporary),
                    **inspected}
        # Exclusive creation: never replace a backup another process published.
        with backup.open("xb") as published, temporary.open("rb") as snapshot:
            published_by_this_call = True
            shutil.copyfileobj(snapshot, published)
            published.flush()
            os.fsync(published.fileno())
        manifest_path = backup.with_suffix(".json")
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        verify_backup(backup)
        return backup
    except Exception:
        if published_by_this_call:
            backup.with_suffix(".json").unlink(missing_ok=True)
            backup.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def restore_backup(path: str | Path, target: str | Path) -> Path:
    backup = Path(path).resolve()
    expected = verify_backup(backup)
    destination = Path(target).resolve()
    if destination == backup or destination.exists() or any(
        Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise BackupError("恢复目标已存在；为保护现有数据，只允许恢复到全新路径")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open("xb") as output, backup.open("rb") as source:
            created = True
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        if _hash_file(destination) != expected["sha256"] or _inspect(destination) != {
            key: expected[key] for key in ("table_counts", "schema_versions")}:
            raise BackupError("恢复后校验失败")
        return destination
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def prune_backups(directory: str | Path | None = None, daily: int = 7, weekly: int = 4) -> list[Path]:
    folder = Path(directory).resolve() if directory else backup_directory()
    removed = []
    if not folder.is_dir():
        return removed
    for kind, keep in (("daily", daily), ("weekly", weekly)):
        if keep < 1:
            raise BackupError("至少保留一份周期备份")
        candidates = sorted((p for p in folder.glob(f"nutripulse-{kind}-*.sqlite3")
                             if BACKUP_NAME.fullmatch(p.name)), reverse=True)
        valid = []
        for backup in candidates:
            try:
                verify_backup(backup)
            except BackupError:
                continue  # Preserve suspicious files, but do not count them as recoverable copies.
            valid.append(backup)
        for backup in valid[keep:]:
            backup.unlink()
            backup.with_suffix(".json").unlink()
            removed.append(backup)
    return removed


def automatic_backup() -> list[Path]:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    # The server may be powered off on Monday; back up the current ISO week
    # whenever it next runs, rather than relying on one weekday.
    created = [create_backup("daily", now.date().isoformat()),
               create_backup("weekly", now.strftime("%G-W%V"))]
    prune_backups()
    return created


def backup_before_migration() -> Path | None:
    source = database_path()
    if not source.is_file() or source.stat().st_size == 0:
        return None
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
            applied = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
        else:
            applied = set()
    if not any(file.stem not in applied for file in MIGRATIONS.glob("*.sql")):
        return None
    return create_backup("pre-migration")
