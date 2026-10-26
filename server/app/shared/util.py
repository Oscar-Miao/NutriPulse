from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.shared.errors import require


USER_ID = "local-user"


def new_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today(tz_name: str = "Asia/Shanghai") -> str:
    return datetime.now(ZoneInfo(tz_name)).date().isoformat()


def valid_date(value: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            "日期格式须为 YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        require(False, "日期格式须为 YYYY-MM-DD")
    return value


def as_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_value(value, default=None):
    return json.loads(value) if value else default


def number(value, field: str, lower: float = 0, upper: float = 1_000_000) -> float:
    try:
        result = float(value)
    except (ValueError, TypeError):
        require(False, f"{field} 必须是数字")
    require(lower <= result <= upper, f"{field} 需在 {lower}-{upper} 之间")
    return result
