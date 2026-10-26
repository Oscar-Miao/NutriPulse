import unittest
import os
from unittest.mock import patch

from app.api.http import serve
from app.infrastructure.auth.pairing import PairingManager
from app.shared.errors import ApiError


class PairingTest(unittest.TestCase):
    def test_lan_refuses_wildcard_or_public_bind_before_database_work(self):
        for host in ("0.0.0.0", "8.8.8.8", "example.com"):
            with self.subTest(host=host), patch.dict(os.environ,
                    {"NUTRIPULSE_HOST": host, "NUTRIPULSE_API_TOKEN": "admin-secret"}), \
                    patch("app.api.http.migrate") as migrate:
                with self.assertRaises(RuntimeError):
                    serve()
                migrate.assert_not_called()

    def test_lan_rejects_weak_administrator_token(self):
        with patch.dict(os.environ, {"NUTRIPULSE_HOST": "192.168.1.20",
                                  "NUTRIPULSE_API_TOKEN": "short"}), \
                patch("app.api.http.migrate") as migrate:
            with self.assertRaises(RuntimeError):
                serve()
            migrate.assert_not_called()

    def test_code_is_one_time_and_token_expires(self):
        now = [1000.0]
        manager = PairingManager(clock=lambda: now[0])
        issued = manager.issue_code()
        self.assertEqual(len(issued["code"].replace("-", "")), 16)
        token = manager.redeem(issued["code"].lower())["access_token"]
        self.assertTrue(manager.authorizes(f"Bearer {token}"))
        with self.assertRaises(ApiError) as reused:
            manager.redeem(issued["code"])
        self.assertEqual(reused.exception.code, "PAIRING_EXPIRED")
        self.assertNotIn(token, repr(manager._tokens))
        now[0] += 24 * 60 * 60
        self.assertFalse(manager.authorizes(f"Bearer {token}"))

    def test_code_expires_and_failed_attempts_lock_until_rotation(self):
        now = [1000.0]
        manager = PairingManager(clock=lambda: now[0])
        issued = manager.issue_code()
        for _ in range(5):
            with self.assertRaises(ApiError) as wrong:
                manager.redeem("WRONG-CODE")
            self.assertEqual(wrong.exception.code, "PAIRING_INVALID")
        with self.assertRaises(ApiError) as locked:
            manager.redeem(issued["code"])
        self.assertEqual(locked.exception.code, "PAIRING_LOCKED")
        issued = manager.issue_code()
        now[0] += 600
        with self.assertRaises(ApiError) as expired:
            manager.redeem(issued["code"])
        self.assertEqual(expired.exception.code, "PAIRING_EXPIRED")
        issued = manager.issue_code()
        token = manager.redeem(issued["code"])["access_token"]
        manager.revoke_all()
        self.assertFalse(manager.authorizes(f"Bearer {token}"))


if __name__ == "__main__":
    unittest.main()
