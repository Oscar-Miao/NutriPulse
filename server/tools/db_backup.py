"""Manual backup, verification, and non-overwriting restore for local data.

Run from server/: python tools/db_backup.py create|verify|restore ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.db.backup import BackupError, create_backup, restore_backup, verify_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="NutriPulse 本地 SQLite 备份工具")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="在线一致快照，不必停服")
    create.add_argument("--source", type=Path, help="源数据库；默认 NUTRIPULSE_DB")
    create.add_argument("--directory", type=Path, help="备份目录；默认数据库旁 backups/")
    verify = commands.add_parser("verify", help="检查 SHA-256、完整性、外键和表计数")
    verify.add_argument("backup", type=Path)
    restore = commands.add_parser("restore", help="恢复到不存在的新数据库路径")
    restore.add_argument("backup", type=Path)
    restore.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            print(create_backup(source=args.source, directory=args.directory))
        elif args.command == "verify":
            result = verify_backup(args.backup)
            print(f"校验通过：{result['filename']} · {result['bytes']} bytes · {result['sha256']}")
        else:
            print(restore_backup(args.backup, args.target))
        return 0
    except (BackupError, OSError) as error:
        print(f"操作失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
