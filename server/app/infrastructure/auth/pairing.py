"""One-time LAN pairing; tokens live only for this server process."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.shared.errors import ApiError


CODE_TTL_SECONDS = 600
TOKEN_TTL_SECONDS = 24 * 60 * 60
MAX_FAILED_ATTEMPTS = 5
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PairingManager:
    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._lock = Lock()
        self._code = ""
        self._code_expires = 0.0
        self._failed_attempts = 0
        self._tokens: dict[str, float] = {}

    def issue_code(self) -> dict:
        with self._lock:
            self._code = "".join(secrets.choice(_ALPHABET) for _ in range(16))
            self._code_expires = self._clock() + CODE_TTL_SECONDS
            self._failed_attempts = 0
            grouped = "-".join(self._code[i:i + 4] for i in range(0, 16, 4))
        return {"code": grouped, "expires_in_seconds": CODE_TTL_SECONDS}

    def redeem(self, code: str) -> dict:
        if not isinstance(code, str) or len(code) > 32:
            raise ApiError("VALIDATION_ERROR", "配对码格式无效")
        entered = code.replace("-", "").strip().upper()
        with self._lock:
            if not self._code or self._clock() >= self._code_expires:
                raise ApiError("PAIRING_EXPIRED", "配对码已失效，请在电脑上生成新码", 410)
            if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
                raise ApiError("PAIRING_LOCKED", "配对尝试次数过多，请在电脑上生成新码", 429)
            if not secrets.compare_digest(entered, self._code):
                self._failed_attempts += 1
                raise ApiError("PAIRING_INVALID", "配对码不正确", 401)
            self._code = ""  # A successful code cannot authorize a second device.
            token = secrets.token_urlsafe(32)
            self._tokens[hashlib.sha256(token.encode("ascii")).hexdigest()] = self._clock() + TOKEN_TTL_SECONDS
        return {"access_token": token, "token_type": "Bearer",
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS))
                .isoformat(timespec="seconds")}

    def authorizes(self, authorization: str) -> bool:
        if not authorization.startswith("Bearer "):
            return False
        token = authorization[7:]
        if not 20 <= len(token) <= 128:
            return False
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._lock:
            expiry = self._tokens.get(digest)
            if expiry is None:
                return False
            if self._clock() >= expiry:
                del self._tokens[digest]
                return False
            return True

    def revoke_all(self) -> None:
        with self._lock:
            self._tokens.clear()
            self._code = ""
