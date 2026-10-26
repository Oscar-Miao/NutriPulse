from __future__ import annotations

import threading
import time

from app.infrastructure.content.feed import refresh_feed
from app.infrastructure.db.backup import automatic_backup


def start_feed_worker() -> None:
    def loop():
        while True:
            try:
                refresh_feed()
            except Exception as error:
                print(f"Feed refresh failed: {type(error).__name__}", flush=True)
            time.sleep(6 * 60 * 60)
    threading.Thread(target=loop, name="feed-refresh", daemon=True).start()


def start_backup_worker() -> None:
    def loop():
        while True:
            try:
                automatic_backup()
            except Exception as error:
                # Never print exception text; it may contain a private path.
                print(f"Backup failed: {type(error).__name__}", flush=True)
            time.sleep(60 * 60)
    threading.Thread(target=loop, name="database-backup", daemon=True).start()
