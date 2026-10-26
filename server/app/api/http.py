from __future__ import annotations

import json
import ipaddress
import os
import re
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app.application.analytics import service as analytics
from app.application.analytics import report as analytics_report
from app.application.fitness import service as fitness
from app.application.fitness import recovery as fitness_recovery
from app.application.fitness import device as devices
from app.application.fitness import conflicts as fitness_conflicts
from app.application.nutrition import service as nutrition
from app.application.nutrition import scan as food_scan
from app.application.profile import service as profile
from app.application.profile import privacy
from app.application.recommendation import service as recommendation
from app.application.recommendation import chat as food_chat
from app.infrastructure.db.database import connect, migrate, transaction
from app.infrastructure.db.seed import seed
from app.infrastructure.content.feed import refresh_feed, public_articles
from app.infrastructure.auth.pairing import PairingManager
from app.workers.scheduler import start_backup_worker, start_feed_worker
from app.shared.errors import ApiError
from app.shared.observability import record_request, recent_requests
from app.shared.util import new_id, today


MAX_BODY = 5 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "NutriPulse/0.1"

    def log_message(self, format, *args):
        # The default format includes URL query strings, which can contain
        # health data. Keep the transport log limited to method and status.
        pass

    def _send(self, status: int, data: dict | list, request_id: str):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", request_id)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_pdf(self, body: bytes, request_id: str, period: str, end: str):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="NutriPulse_{period}_{end}.pdf"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", request_id)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ApiError("PAYLOAD_TOO_LARGE", "请求体过大", 413)
        if not length:
            return {}
        try:
            obj = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, ValueError):
            raise ApiError("VALIDATION_ERROR", "请求体必须是 UTF-8 JSON")
        if not isinstance(obj, dict):
            raise ApiError("VALIDATION_ERROR", "请求体必须是 JSON 对象")
        return obj

    def _authorized(self, admin_only: bool = False):
        # The environment token remains a server-side admin credential. Paired
        # devices use short-lived per-process tokens instead.
        token = os.environ.get("NUTRIPULSE_API_TOKEN", "")
        authorization = self.headers.get("Authorization", "")
        if not token:
            return  # Unauthenticated access is allowed only on loopback.
        if secrets.compare_digest(authorization, f"Bearer {token}"):
            return
        pairing = getattr(self.server, "pairing", None)
        if not admin_only and pairing is not None and pairing.authorizes(authorization):
            return
        raise ApiError("UNAUTHORIZED", "访问凭据无效或已过期，请重新配对", 401)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str):
        request_id = new_id()
        started = time.perf_counter()
        path = ""
        status = 500
        error_code = None
        exception_type = None
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            if path not in ("/health", "/api/v1/health") and not (
                    method == "POST" and path == "/api/v1/auth/pair"):
                self._authorized(admin_only=path == "/api/v1/auth/pair-code")
            body = self._body() if method in ("POST", "PUT", "PATCH") else {}
            if method == "POST" and path == "/api/v1/reports":
                pdf = analytics_report.build_report(body)
                self._send_pdf(pdf, request_id, body.get("period", "week"), body.get("end") or today())
                status = 200
                return
            data, status = self._route(method, path, query, body)
            self._send(status, {"data": data, "request_id": request_id}, request_id)
        except ApiError as exc:
            status = exc.status
            error_code = exc.code
            self._send(exc.status, {"code": exc.code, "message": exc.message,
                                    "request_id": request_id, "retryable": exc.status >= 500}, request_id)
        except Exception as exc:
            status = 500
            error_code = "INTERNAL_ERROR"
            exception_type = type(exc).__name__
            self._send(500, {"code": "INTERNAL_ERROR", "message": "服务暂不可用",
                             "request_id": request_id, "retryable": True}, request_id)
        finally:
            record_request(request_id, method, path, status,
                           (time.perf_counter() - started) * 1000,
                           error_code, exception_type)

    def _route(self, method: str, path: str, query: dict, body: dict):
        if method == "GET" and path in ("/health", "/api/v1/health"):
            with connect() as db:
                db.execute("SELECT 1").fetchone()
            return {"status": "ok", "database": "ok"}, 200
        if not path.startswith("/api/v1/"):
            raise ApiError("NOT_FOUND", "接口不存在", 404)
        path = path[len("/api/v1"):]
        if method == "POST" and path == "/auth/pair":
            if not ipaddress.ip_address(self.client_address[0]).is_private:
                raise ApiError("PAIRING_FORBIDDEN", "仅允许私有网络设备配对", 403)
            pairing = getattr(self.server, "pairing", None)
            if pairing is None:
                raise ApiError("PAIRING_UNAVAILABLE", "此服务未启用配对", 503)
            return pairing.redeem(body.get("code")), 201
        if method == "POST" and path == "/auth/pair-code":
            pairing = getattr(self.server, "pairing", None)
            if pairing is None:
                raise ApiError("PAIRING_UNAVAILABLE", "此服务未启用配对", 503)
            return pairing.issue_code(), 201
        if method == "GET" and path == "/diagnostics/logs":
            try:
                limit = int(query.get("limit", "100"))
            except ValueError:
                raise ApiError("VALIDATION_ERROR", "limit 必须是 1-500 的整数")
            try:
                return recent_requests(limit), 200
            except ValueError:
                raise ApiError("VALIDATION_ERROR", "limit 必须是 1-500 的整数")
        if method == "GET" and path == "/profile":
            return profile.get_profile(), 200
        if method == "PUT" and path == "/profile":
            return profile.update_profile(body), 200
        if method == "PUT" and path == "/training-profile":
            return profile.set_training_profile(body), 200
        if method == "POST" and path == "/measurements":
            return profile.add_measurement(body), 201
        if method == "POST" and path == "/goals":
            return profile.set_goal(body), 201
        if method == "POST" and path == "/goals/preview":
            return profile.preview_goal(body), 200
        if method == "PUT" and path == "/preferences":
            return profile.set_preferences(body), 200
        if method == "GET" and path == "/privacy/export":
            return privacy.export_data(query.get("category", "all")), 200
        if method == "GET" and path == "/privacy/delete-preview":
            return privacy.deletion_preview(query.get("category", "all")), 200
        if method == "POST" and path == "/privacy/delete":
            result = privacy.delete_data(body.get("category"), body.get("confirmation_phrase"))
            if body.get("category") == "all":
                pairing = getattr(self.server, "pairing", None)
                if pairing is not None:
                    pairing.revoke_all()
            return result, 200
        if method == "GET" and path == "/foods":
            return nutrition.list_foods(query.get("q", "")), 200
        if method == "GET" and path == "/foods/frequent":
            return nutrition.frequent_foods(), 200
        if method == "POST" and path == "/meals":
            return nutrition.create_meal(body, self.headers.get("Idempotency-Key")), 201
        if method == "GET" and path == "/meals":
            return nutrition.list_meals(query.get("date", today())), 200
        match = re.fullmatch(r"/meals/([0-9a-f]{32})", path)
        if match and method == "GET":
            return nutrition.get_meal(match[1]), 200
        if match and method == "PATCH":
            return nutrition.update_meal(match[1], body), 200
        if match and method == "POST":
            # HttpURLConnection on Android does not reliably support PATCH.
            return nutrition.update_meal(match[1], body), 200
        if match and method == "DELETE":
            return nutrition.delete_meal(match[1]), 200
        match = re.fullmatch(r"/meals/([0-9a-f]{32})/restore", path)
        if match and method == "POST":
            return nutrition.restore_meal(match[1]), 200
        if method == "POST" and path == "/water-logs":
            return nutrition.add_water(body, self.headers.get("Idempotency-Key")), 201
        match = re.fullmatch(r"/water-logs/days/(\d{4}-\d{2}-\d{2})", path)
        if match and method == "PUT":
            return nutrition.set_water_total(match[1], body), 200
        if method == "POST" and path == "/food-scans":
            return food_scan.create_scan(body, self.headers.get("Idempotency-Key")), 201
        match = re.fullmatch(r"/food-scans/([0-9a-f]{32})", path)
        if match and method == "GET":
            return food_scan.get_scan(match[1]), 200
        match = re.fullmatch(r"/food-scans/([0-9a-f]{32})/confirm", path)
        if match and method == "POST":
            return food_scan.confirm_scan(match[1], body), 201
        if method == "GET" and path.startswith("/nutrition/days/"):
            day = path.rsplit("/", 1)[-1]
            return {"summary": analytics.day_summary(day), "meals": nutrition.list_meals(day)}, 200
        if method == "GET" and path == "/exercises":
            return fitness.list_exercises(), 200
        if method == "GET" and path == "/training-plans":
            return fitness.list_plans(query.get("level"), query.get("goal_type")), 200
        if method == "GET" and path == "/devices":
            return devices.connections(), 200
        if method == "POST" and path == "/devices":
            return devices.connect_device(body), 201
        if method == "GET" and path == "/devices/conflicts":
            return fitness_conflicts.list_conflicts(query.get("date"),
                query.get("status") == "all"), 200
        match = re.fullmatch(r"/devices/conflicts/([0-9a-f]{32})/resolve", path)
        if match and method == "POST":
            return fitness_conflicts.resolve_conflict(match[1], body.get("resolution")), 200
        match = re.fullmatch(r"/devices/([0-9a-f]{32})/samples", path)
        if match and method == "POST":
            return devices.import_samples(match[1], body), 201
        match = re.fullmatch(r"/devices/([0-9a-f]{32})", path)
        if match and method == "DELETE":
            delete_history = query.get("delete_history", "false")
            if delete_history not in ("true", "false"):
                raise ApiError("VALIDATION_ERROR", "delete_history 必须为 true 或 false")
            return devices.disconnect(match[1], delete_history == "true"), 200
        if method == "GET" and path == "/training-plans/active":
            return fitness.active_plan(query.get("date")), 200
        if method == "POST" and path == "/training-plans/active/stop":
            return fitness.stop_active_plan(), 200
        match = re.fullmatch(r"/training-plans/active/sessions/([0-9a-f]{32})/replace", path)
        if match and method == "POST":
            return fitness.replace_plan_exercise(match[1], body), 200
        match = re.fullmatch(r"/training-plans/([A-Z0-9-]+)/enroll", path)
        if match and method == "POST":
            return fitness.enroll(match[1], body.get("start_date")), 201
        if method == "POST" and path == "/workouts":
            return fitness.create_workout(body, self.headers.get("Idempotency-Key")), 201
        if method == "POST" and path == "/workouts/estimate":
            return fitness.estimate_workout(body), 200
        match = re.fullmatch(r"/workouts/([0-9a-f]{32})/recovery", path)
        if match and method == "GET":
            return fitness_recovery.recovery_advice(match[1]), 200
        if method == "GET" and path == "/workouts":
            return fitness.list_workouts(query.get("date", today())), 200
        if method == "GET" and path.startswith("/fitness/days/"):
            day = path.rsplit("/", 1)[-1]
            return {"summary": analytics.day_summary(day), "workouts": fitness.list_workouts(day),
                    "active_plan": fitness.active_plan(day)}, 200
        if method == "POST" and path == "/recommendations/meals":
            return recommendation.recommend(body), 201
        if method == "POST" and path == "/agent/chats":
            return food_chat.new_chat(), 201
        match = re.fullmatch(r"/agent/chats/([0-9a-f]{32})", path)
        if match and method == "GET":
            return food_chat.get_chat(match[1]), 200
        match = re.fullmatch(r"/agent/chats/([0-9a-f]{32})/messages", path)
        if match and method == "POST":
            return food_chat.send_message(match[1], body.get("content", "")), 201
        match = re.fullmatch(r"/agent/chats/([0-9a-f]{32})/accept", path)
        if match and method == "POST":
            return food_chat.accept_proposal(match[1], self.headers.get("Idempotency-Key")), 201
        match = re.fullmatch(r"/recommendations/([0-9a-f]{32})/accept", path)
        if match and method == "POST":
            return recommendation.accept(match[1], self.headers.get("Idempotency-Key"), body.get("servings", 1)), 201
        match = re.fullmatch(r"/recommendations/([0-9a-f]{32})/feedback", path)
        if match and method == "POST":
            return recommendation.submit_feedback(match[1], body.get("feedback_type")), 200
        if method == "GET" and path.startswith("/recipes/"):
            return recommendation.recipe_detail(path.rsplit("/", 1)[-1]), 200
        if method == "GET" and path == "/analytics/energy":
            return analytics.energy_series(query.get("start", today()), query.get("end", today()),
                                           query.get("granularity", "day")), 200
        if method == "GET" and path == "/analytics/macros":
            return analytics.macro_summary(query.get("start", today()), query.get("end", today())), 200
        if method == "GET" and path == "/analytics/habits":
            return analytics.habit_summary(query.get("start", today()), query.get("end", today())), 200
        if method == "GET" and path == "/analytics/body-composition":
            return analytics.body_composition_series(query.get("start", today()), query.get("end", today())), 200
        if method == "GET" and path == "/analytics/days":
            return analytics.day_summary(query.get("date", today())), 200
        if method == "POST" and path == "/analytics/diagnostics":
            return analytics.generate_diagnosis(body.get("start", today()), body.get("end", today())), 201
        if method == "GET" and path == "/analytics/diagnostics":
            return analytics.diagnosis_history(query.get("start", today()), query.get("end", today())), 200
        if method == "GET" and path == "/articles":
            with connect() as db:
                return public_articles([dict(r) for r in db.execute("""SELECT id,source,source_url,title,summary,cover_url,published_at
                    FROM articles WHERE status='VISIBLE' AND (expires_at IS NULL OR datetime(expires_at)>CURRENT_TIMESTAMP)
                    ORDER BY priority DESC, published_at DESC LIMIT 30""")])[:10], 200
        if method == "POST" and path == "/articles/refresh":
            return refresh_feed(), 200
        match = re.fullmatch(r"/articles/([0-9a-f]{32})/moderation", path)
        if method == "PATCH" and match:
            status = body.get("status")
            priority = body.get("priority")
            if status not in ("VISIBLE", "HIDDEN") or type(priority) is not int or not 0 <= priority <= 100:
                raise ApiError("VALIDATION_ERROR", "可见状态或优先级无效")
            with transaction() as db:
                updated = db.execute("UPDATE articles SET status=?,priority=? WHERE id=?",
                                     (status, priority, match[1]))
                if updated.rowcount == 0:
                    raise ApiError("NOT_FOUND", "文章不存在", 404)
                return dict(db.execute("SELECT id,status,priority FROM articles WHERE id=?", (match[1],)).fetchone()), 200
        raise ApiError("NOT_FOUND", "接口不存在", 404)


def serve():
    host = os.environ.get("NUTRIPULSE_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise RuntimeError("LAN mode requires an explicit private interface address")
        trusted = (address.version == 4 and any(address in ipaddress.ip_network(network) for network in
                   ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))) or (
                   address.version == 6 and address in ipaddress.ip_network("fc00::/7"))
        if not trusted:
            raise RuntimeError("LAN mode requires an explicit private interface address")
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("NUTRIPULSE_API_TOKEN"):
        raise RuntimeError("LAN mode requires NUTRIPULSE_API_TOKEN")
    if host not in ("127.0.0.1", "localhost", "::1") and len(os.environ["NUTRIPULSE_API_TOKEN"]) < 24:
        raise RuntimeError("LAN mode requires a random administrator token of at least 24 characters")
    migrate()
    seed()
    port = int(os.environ.get("NUTRIPULSE_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    server.pairing = PairingManager()
    pair_code = server.pairing.issue_code()
    start_feed_worker()
    start_backup_worker()
    print(f"NutriPulse listening on http://{host}:{port}", flush=True)
    print(f"One-time pairing code (10 minutes): {pair_code['code']}", flush=True)
    server.serve_forever()
