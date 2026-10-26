import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.infrastructure.db.backup import (BackupError, automatic_backup, create_backup, prune_backups,
                                          restore_backup, verify_backup)
from app.infrastructure.db.database import MIGRATIONS, connect, migrate
from app.infrastructure.db.seed import seed


class BackupRestoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous_db = os.environ.get("NUTRIPULSE_DB")
        self.previous_backups = os.environ.get("NUTRIPULSE_BACKUP_DIR")
        os.environ["NUTRIPULSE_DB"] = str(self.root / "live.sqlite3")
        os.environ["NUTRIPULSE_BACKUP_DIR"] = str(self.root / "backups")
        migrate()
        seed()

    def tearDown(self):
        for name, old in (("NUTRIPULSE_DB", self.previous_db),
                          ("NUTRIPULSE_BACKUP_DIR", self.previous_backups)):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        self.temp.cleanup()

    def test_online_wal_snapshot_restore_and_no_overwrite(self):
        writer = connect()
        try:
            writer.execute("UPDATE users SET display_name='WAL中已提交' WHERE id='local-user'")
            writer.commit()
            self.assertGreater(Path(os.environ["NUTRIPULSE_DB"] + "-wal").stat().st_size, 0)
            backup = create_backup("manual", "wal-test")
            manifest = verify_backup(backup)
            self.assertEqual(manifest["table_counts"]["users"], 1)
            self.assertEqual(len(manifest["schema_versions"]), len(list(MIGRATIONS.glob("*.sql"))))
            self.assertFalse(Path(str(backup) + "-wal").exists())
            self.assertFalse(Path(str(backup) + "-shm").exists())
            self.assertEqual(list((self.root / "backups").glob(".nutripulse-backup-*")), [])
            restored = restore_backup(backup, self.root / "restored.sqlite3")
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute("SELECT display_name FROM users").fetchone()[0], "WAL中已提交")
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            writer.execute("UPDATE users SET display_name='后续新值' WHERE id='local-user'")
            writer.commit()
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute("SELECT display_name FROM users").fetchone()[0], "WAL中已提交")
            with self.assertRaises(BackupError):
                restore_backup(backup, restored)
        finally:
            writer.close()

    def test_tamper_is_rejected_before_restore(self):
        backup = create_backup("manual", "tamper-test")
        with backup.open("r+b") as stream:
            stream.seek(120)
            byte = stream.read(1)
            stream.seek(120)
            stream.write(bytes([byte[0] ^ 1]))
        with self.assertRaises(BackupError):
            verify_backup(backup)
        target = self.root / "must_not_exist.sqlite3"
        with self.assertRaises(BackupError):
            restore_backup(backup, target)
        self.assertFalse(target.exists())

    def test_automatic_backup_is_idempotent_for_day_and_week(self):
        first = automatic_backup()
        second = automatic_backup()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertTrue(all(verify_backup(path) for path in first))

    def test_command_line_create_verify_restore(self):
        tool = Path(__file__).resolve().parents[1] / "tools" / "db_backup.py"
        environment = os.environ.copy()
        created = subprocess.run([sys.executable, str(tool), "create"], env=environment,
                                 capture_output=True, text=True, check=True)
        backup = Path(created.stdout.strip())
        self.assertTrue(backup.is_file())
        verified = subprocess.run([sys.executable, str(tool), "verify", str(backup)], env=environment,
                                  capture_output=True, text=True, check=True)
        self.assertIn(verify_backup(backup)["sha256"], verified.stdout)
        target = self.root / "cli_restored.sqlite3"
        subprocess.run([sys.executable, str(tool), "restore", str(backup), str(target)],
                       env=environment, capture_output=True, text=True, check=True)
        self.assertTrue(target.is_file())
        rejected = subprocess.run([sys.executable, str(tool), "restore", str(backup), str(target)],
                                  env=environment, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(verify_backup(backup)["sha256"], hashlib.sha256(target.read_bytes()).hexdigest())

    def test_retention_only_prunes_verified_periodic_files(self):
        for day in range(1, 10):
            create_backup("daily", f"2026-09-{day:02d}")
        for week in range(1, 6):
            create_backup("weekly", f"2026-W{week:02d}")
        protected = create_backup("manual", "keep-me")
        removed = prune_backups()
        self.assertEqual(len(removed), 3)
        self.assertTrue(protected.exists())
        folder = self.root / "backups"
        self.assertEqual(len(list(folder.glob("nutripulse-daily-*.sqlite3"))), 7)
        self.assertEqual(len(list(folder.glob("nutripulse-weekly-*.sqlite3"))), 4)
        self.assertTrue(all(verify_backup(path) for path in folder.glob("*.sqlite3")))

    def test_corrupt_backup_is_preserved_but_not_counted_as_valid_retention(self):
        for day in range(1, 10):
            create_backup("daily", f"2026-09-{day:02d}")
        newest = self.root / "backups" / "nutripulse-daily-2026-09-09.sqlite3"
        with newest.open("r+b") as stream:
            stream.seek(120)
            byte = stream.read(1)
            stream.seek(120)
            stream.write(bytes([byte[0] ^ 1]))
        removed = prune_backups()
        self.assertEqual(len(removed), 1)
        self.assertTrue(newest.exists())
        valid = [path for path in (self.root / "backups").glob("*.sqlite3") if path != newest]
        self.assertEqual(len(valid), 7)
        self.assertTrue(all(verify_backup(path) for path in valid))
