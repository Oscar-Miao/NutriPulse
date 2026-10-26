"""Bounded, redacted request diagnostics for the single-user local server."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock


_MAX_EVENTS = 500
_events: deque[dict] = deque(maxlen=_MAX_EVENTS)
_lock = Lock()
_modules = {
    "profile": "profile", "training-profile": "profile", "measurements": "profile",
    "goals": "profile", "preferences": "profile", "privacy": "privacy",
    "foods": "nutrition", "meals": "nutrition", "water-logs": "nutrition",
    "food-scans": "nutrition", "nutrition": "nutrition",
    "exercises": "fitness", "training-plans": "fitness", "workouts": "fitness",
    "fitness": "fitness", "devices": "devices",
    "recommendations": "recommendation", "recipes": "recommendation",
    "agent": "agent", "analytics": "analytics", "reports": "analytics",
    "articles": "content", "diagnostics": "diagnostics", "health": "health",
    "auth": "auth",
}


def module_for_path(path: str) -> str:
    """Classify paths without retaining identifiers, query strings or user text."""
    if path.startswith("/api/v1/"):
        path = path[len("/api/v1/"):]
    return _modules.get(path.strip("/").split("/", 1)[0], "unknown")


def record_request(request_id: str, method: str, path: str, status: int,
                   duration_ms: float, error_code: str | None = None,
                   exception_type: str | None = None) -> None:
    event = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "request_id": request_id,
        "method": method,
        "module": module_for_path(path),
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "error_code": error_code,
        "exception_type": exception_type,
    }
    with _lock:
        _events.append(event)


def recent_requests(limit: int = 100) -> dict:
    if type(limit) is not int or not 1 <= limit <= _MAX_EVENTS:
        raise ValueError("limit must be between 1 and 500")
    with _lock:
        entries = [event.copy() for event in list(_events)[-limit:]]
        retained = len(_events)
    entries.reverse()
    return {"events": entries, "retained": retained, "capacity": _MAX_EVENTS,
            "scope": "current_process_only"}
