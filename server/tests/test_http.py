import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app.api.http import Handler
from app.infrastructure.auth.pairing import PairingManager
from app.infrastructure.db.database import connect, migrate
from app.infrastructure.db.seed import seed
from app.application.profile.service import update_profile, add_measurement, set_goal, set_preferences
from app.shared.util import today
from tests.image_fixture import encoded_jpeg


class HttpBlackBoxTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("NUTRIPULSE_DB")
        self.previous_token = os.environ.get("NUTRIPULSE_API_TOKEN")
        os.environ["NUTRIPULSE_DB"] = str(Path(self.temp.name) / "http.sqlite3")
        os.environ["NUTRIPULSE_API_TOKEN"] = "test-token"
        migrate()
        seed()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.previous_db is None:
            os.environ.pop("NUTRIPULSE_DB", None)
        else:
            os.environ["NUTRIPULSE_DB"] = self.previous_db
        if self.previous_token is None:
            os.environ.pop("NUTRIPULSE_API_TOKEN", None)
        else:
            os.environ["NUTRIPULSE_API_TOKEN"] = self.previous_token
        self.temp.cleanup()

    def call(self, method, path, body=None, authenticated=True, extra_headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer test-token"
        if extra_headers:
            headers.update(extra_headers)
        conn.request(method, "/api/v1" + path, json.dumps(body).encode() if body is not None else None, headers)
        response = conn.getresponse()
        status = response.status
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
        return status, payload

    def report(self, body, authenticated=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=15)
        headers = {"Content-Type": "application/json", "Accept": "application/pdf"}
        if authenticated:
            headers["Authorization"] = "Bearer test-token"
        conn.request("POST", "/api/v1/reports", json.dumps(body).encode("utf-8"), headers)
        response = conn.getresponse()
        status, content_type, cache_control = response.status, response.getheader("Content-Type"), response.getheader("Cache-Control")
        payload = response.read()
        conn.close()
        return status, content_type, cache_control, payload

    def test_diagnostic_logs_require_auth_and_exclude_health_inputs(self):
        self.assertEqual(self.call("GET", "/diagnostics/logs", authenticated=False)[0], 401)
        self.assertEqual(self.call("GET", "/meals/private-id?access_token=private-token")[0], 404)
        with patch("app.api.http.profile.get_profile", side_effect=ValueError("private-health-value")):
            status, failure = self.call("GET", "/profile")
        self.assertEqual(status, 500)
        self.assertEqual(failure["code"], "INTERNAL_ERROR")
        status, response = self.call("GET", "/diagnostics/logs?limit=10")
        self.assertEqual(status, 200)
        events = response["data"]["events"]
        self.assertTrue(any(event["request_id"] == failure["request_id"] and
                            event["status"] == 500 and event["module"] == "profile" and
                            event["exception_type"] == "ValueError" for event in events))
        exported = json.dumps(events)
        for secret in ("private-id", "private-token", "private-health-value", "test-token"):
            self.assertNotIn(secret, exported)
        self.assertEqual(self.call("GET", "/diagnostics/logs?limit=0")[0], 400)
        self.assertEqual(self.call("GET", "/diagnostics/logs?limit=nan")[0], 400)

    def test_pairing_issues_short_lived_device_token_without_admin_access(self):
        self.server.pairing = PairingManager()
        code = self.server.pairing.issue_code()["code"]
        status, paired = self.call("POST", "/auth/pair", {"code": code}, authenticated=False)
        self.assertEqual(status, 201)
        device_token = paired["data"]["access_token"]
        headers = {"Authorization": f"Bearer {device_token}"}
        self.assertEqual(self.call("GET", "/profile", authenticated=False,
                                   extra_headers=headers)[0], 200)
        self.assertEqual(self.call("POST", "/auth/pair-code", {}, authenticated=False,
                                   extra_headers=headers)[0], 401)
        self.assertEqual(self.call("POST", "/auth/pair", {"code": code}, authenticated=False)[0], 410)
        new_code = self.call("POST", "/auth/pair-code", {})[1]["data"]["code"]
        self.assertNotEqual(code, new_code)
        status, logs = self.call("GET", "/diagnostics/logs")
        self.assertEqual(status, 200)
        exported = json.dumps(logs["data"])
        self.assertNotIn(code, exported)
        self.assertNotIn(device_token, exported)
        second_token = self.call("POST", "/auth/pair", {"code": new_code},
                                 authenticated=False)[1]["data"]["access_token"]
        self.assertEqual(self.call("POST", "/privacy/delete", {"category": "all",
            "confirmation_phrase": "DELETE_ALL"}, authenticated=False,
            extra_headers={"Authorization": f"Bearer {second_token}"})[0], 200)
        self.assertEqual(self.call("GET", "/profile", authenticated=False,
            extra_headers={"Authorization": f"Bearer {second_token}"})[0], 401)

    def test_training_plan_catalog_http_exposes_versioned_guidance(self):
        status, result = self.call("GET", "/training-plans")
        self.assertEqual(status, 200)
        plans = result["data"]
        self.assertEqual(len(plans), 6)
        for plan in plans:
            self.assertEqual(plan["version"], 2)
            self.assertTrue(plan["warmup"])
            self.assertTrue(plan["cooldown"])
            self.assertTrue(plan["contraindications"])
            self.assertTrue(plan["completion_rule"])
            self.assertGreaterEqual(len(plan["alternatives"]), 3)
        self.assertEqual(len(json.loads(plans[0]["days"][0]["session_template_json"])), 5)

    def test_timed_strength_set_http_keeps_seconds_separate_from_reps(self):
        status, response = self.call("POST", "/workouts", {"workout_type": "strength",
            "minutes": 15, "sets": [{"exercise_name": "平板支撑", "set_no": 1,
                                      "reps": 0, "duration_sec": 25, "weight_kg": None}]})
        self.assertEqual(status, 201)
        self.assertEqual(response["data"]["sets"][0]["duration_sec"], 25)
        self.assertEqual(response["data"]["sets"][0]["reps"], 0)
        self.assertEqual(response["data"]["total_volume"], 0)
        self.assertEqual(self.call("POST", "/workouts", {"workout_type": "strength",
            "minutes": 15, "sets": [{"exercise_name": "平板支撑", "set_no": 1,
                                      "reps": 20, "duration_sec": 25}]})[0], 400)

    def test_food_scan_http_retry_reuses_job_and_rejects_other_photo(self):
        photo = {"image_base64": encoded_jpeg("http-photo"),
                 "mime_type": "image/jpeg"}
        result = {"items": [{"name": "米饭", "estimated_grams": 100,
                             "kcal": 116, "carb_g": 25.9, "protein_g": 2.6,
                             "fat_g": 0.3, "confidence": 0.9}]}
        headers = {"Idempotency-Key": "http-scan-once"}
        with patch("app.application.nutrition.scan.invoke", return_value=result) as agent:
            first_status, first = self.call("POST", "/food-scans", photo, extra_headers=headers)
            retry_status, retry = self.call("POST", "/food-scans", photo, extra_headers=headers)
            self.assertEqual((first_status, retry_status), (201, 201))
            self.assertEqual(first["data"]["id"], retry["data"]["id"])
            self.assertEqual(retry["data"]["status"], "REVIEW_REQUIRED")
            self.assertEqual(agent.call_count, 1)
            another = dict(photo, image_base64=encoded_jpeg("different"))
            self.assertEqual(self.call("POST", "/food-scans", another, extra_headers=headers)[0], 409)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM food_scan_jobs").fetchone()[0], 1)

    def test_food_scan_http_rejects_non_image_payload_before_agent(self):
        fake = {"image_base64": base64.b64encode(b"fake-jpeg" * 200).decode("ascii"),
                "mime_type": "image/jpeg"}
        with patch("app.application.nutrition.scan.invoke") as agent:
            status, response = self.call("POST", "/food-scans", fake)
            self.assertEqual(status, 400)
            self.assertEqual(response["code"], "VALIDATION_ERROR")
            agent.assert_not_called()
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM food_scan_jobs").fetchone()[0], 0)

    def test_food_scan_http_empty_review_never_reverts_to_agent_items(self):
        recognized = {"items": [{"name": "原识别食物", "estimated_grams": 100,
                                  "kcal": 100, "carb_g": 20, "protein_g": 3,
                                  "fat_g": 1, "confidence": 0.9}]}
        with patch("app.application.nutrition.scan.invoke", return_value=recognized):
            _, scan = self.call("POST", "/food-scans", {"image_base64": encoded_jpeg("empty-review"),
                                                       "mime_type": "image/jpeg"})
        scan_id = scan["data"]["id"]
        status, response = self.call("POST", f"/food-scans/{scan_id}/confirm",
                                     {"meal_type": "lunch", "items": []})
        self.assertEqual(status, 400)
        self.assertEqual(response["code"], "VALIDATION_ERROR")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals WHERE source_ref_id=?",
                                        (scan_id,)).fetchone()[0], 0)
        status, confirmed = self.call("POST", f"/food-scans/{scan_id}/confirm",
                                      {"meal_type": "lunch", "items": [
                                          {"display_name": "用户保留食物", "amount": 50,
                                           "unit": "g", "grams": 50, "kcal": 80}]})
        self.assertEqual(status, 201)
        self.assertEqual(confirmed["data"]["items"][0]["display_name"], "用户保留食物")

    def test_chat_http_rejects_unpriced_plan_and_accepts_verified_recipe(self):
        update_profile({"display_name": "HTTP测试", "birth_date": "1998-05-01",
                        "formula_sex": "male", "height_cm": 178, "activity_level": "light"})
        add_measurement({"weight_kg": 72.5})
        set_goal({"goal_type": "fat_loss"})
        set_preferences({"allergies": [], "restrictions": [], "preferences": [],
                         "dining": {"max_cost_cny": 18, "max_cook_minutes": 20,
                                    "flavors": [], "preferred_scenario": "self_cook"}})
        _, session = self.call("POST", "/agent/chats", {})
        chat_id = session["data"]["id"]
        freeform = {"reply": "可以吃米饭", "proposal": {"meal_type": "dinner", "items": [
            {"name": "米饭", "grams": 100, "kcal": 116, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=freeform):
            status, rejected = self.call("POST", f"/agent/chats/{chat_id}/messages", {"content": "晚餐吃什么"})
        self.assertEqual(status, 409)
        self.assertEqual(rejected["code"], "HARD_CONSTRAINT_UNVERIFIED")
        _, recommendation = self.call("POST", "/recommendations/meals", {"meal_type": "dinner"})
        recipe_id = recommendation["data"]["items"][0]["candidate_ref_id"]
        with patch("app.application.recommendation.chat.invoke", return_value={
                "reply": "已选择可核算菜谱", "proposal": {"meal_type": "dinner", "recipe_id": recipe_id}}):
            status, result = self.call("POST", f"/agent/chats/{chat_id}/messages", {"content": "选择安全菜谱"})
        self.assertEqual(status, 201)
        self.assertEqual(result["data"]["proposal"]["recipe_id"], recipe_id)
        self.assertTrue(result["data"]["proposal"]["items"])
        self.assertEqual(self.call("POST", f"/agent/chats/{chat_id}/accept", {})[0], 201)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals WHERE source_type='chat_agent' AND source_ref_id=?",
                                        (chat_id,)).fetchone()[0], 1)

    def test_recommendation_feedback_http_changes_later_score_without_banning_recipe(self):
        _, first = self.call("POST", "/recommendations/meals",
                             {"meal_type": "dinner", "scenario": "takeout"})
        selected = first["data"]["items"][0]
        score_context = json.loads(first["data"]["session"]["context_snapshot_json"])
        self.assertTrue(score_context["ranking_version"].startswith("recommend-v3-weighted-"))
        self.assertEqual(set(score_context["score_components"][selected["candidate_ref_id"]]),
                         set(score_context["scoring_weights"]))
        item_id, recipe_id = selected["id"], selected["candidate_ref_id"]
        self.assertEqual(self.call("POST", f"/recommendations/{item_id}/feedback",
                                   {"feedback_type": "UNKNOWN"})[0], 400)
        status, stored = self.call("POST", f"/recommendations/{item_id}/feedback",
                                   {"feedback_type": "DISLIKE"})
        self.assertEqual(status, 200)
        self.assertEqual(stored["data"]["recipe_id"], recipe_id)
        _, second = self.call("POST", "/recommendations/meals",
                              {"meal_type": "dinner", "scenario": "takeout"})
        changed = next(item for item in second["data"]["items"]
                       if item["candidate_ref_id"] == recipe_id)
        self.assertLess(changed["score"], selected["score"])
        self.assertEqual(changed["feedback_type"], "DISLIKE")
        status, _ = self.call("POST", f"/recommendations/{item_id}/feedback",
                              {"feedback_type": "CLEAR"})
        self.assertEqual(status, 200)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM recommendation_feedback").fetchone()[0], 0)

    def test_blind_box_http_returns_one_draw_and_can_change_to_another(self):
        payload = {"meal_type": "dinner", "scenario": "self_cook", "shuffle": True}
        status, first = self.call("POST", "/recommendations/meals", payload)
        self.assertEqual(status, 201)
        self.assertEqual(len(first["data"]["items"]), 1)
        original = first["data"]["items"][0]["candidate_ref_id"]
        first_pool = json.loads(first["data"]["session"]["context_snapshot_json"])["blind_box"]
        self.assertEqual(first_pool["drawn_recipe_id"], original)
        status, second = self.call("POST", "/recommendations/meals",
                                   dict(payload, avoid_recipe_id=original))
        self.assertEqual(status, 201)
        self.assertEqual(len(second["data"]["items"]), 1)
        self.assertNotEqual(second["data"]["items"][0]["candidate_ref_id"], original)
        second_pool = json.loads(second["data"]["session"]["context_snapshot_json"])["blind_box"]
        self.assertEqual(second_pool["pool_version"], first_pool["pool_version"])

    def test_recipe_http_exposes_preview_only_substitutions(self):
        status, result = self.call("GET", "/recipes/r1")
        self.assertEqual(status, 200)
        options = result["data"]["substitutions"]
        self.assertTrue(options)
        self.assertTrue(all(option["grams_per_serving"] > 0 and
                            option["nutrition_per_serving_if_used"]["kcal"] > 0
                            for option in options))
        self.assertEqual(self.call("GET", "/recipes/unknown")[0], 404)

    def test_recommendation_accept_retry_uses_actual_meal_state(self):
        _, result = self.call("POST", "/recommendations/meals", {"scenario": "self_cook"})
        item_id = result["data"]["items"][0]["id"]
        _, planned = self.call("POST", f"/recommendations/{item_id}/accept", {})
        meal_id = planned["data"]["meal_id"]
        self.assertEqual(self.call("POST", f"/meals/{meal_id}",
                                   {"status": "CONSUMED"})[0], 200)
        _, repeated = self.call("POST", f"/recommendations/{item_id}/accept", {})
        self.assertEqual(repeated["data"], {"meal_id": meal_id, "status": "CONSUMED"})
        self.assertEqual(self.call("DELETE", f"/meals/{meal_id}")[0], 200)
        self.assertEqual(self.call("DELETE", f"/meals/{meal_id}")[0], 200)
        status, removed = self.call("POST", f"/recommendations/{item_id}/accept", {})
        self.assertEqual((status, removed["code"]), (409, "ALREADY_REMOVED"))

    def test_workout_estimate_http_matches_saved_calories(self):
        request = {"workout_type": "cycling", "intensity": "low", "minutes": 30}
        status, preview = self.call("POST", "/workouts/estimate", request)
        self.assertEqual(status, 200)
        self.assertEqual(preview["data"]["weight_source"], "demo_default")
        self.assertEqual(preview["data"]["met_value"], 4.0)
        saved_status, saved = self.call("POST", "/workouts", request)
        self.assertEqual(saved_status, 201)
        self.assertEqual(saved["data"]["kcal"], preview["data"]["kcal"])
        self.assertEqual(saved["data"]["calculation_version"], "met-demo-v1")
        self.assertEqual(self.call("POST", "/workouts/estimate",
                                   dict(request, intensity="extreme"))[0], 400)

    def test_workout_recovery_http_is_grounded_and_authenticated(self):
        status, saved = self.call("POST", "/workouts", {"workout_type": "strength",
            "minutes": 35, "sets": [{"exercise_name": "深蹲", "weight_kg": 30,
                                      "reps": 8, "completed": True}]})
        self.assertEqual(status, 201)
        path = f"/workouts/{saved['data']['id']}/recovery"
        self.assertEqual(self.call("GET", path, authenticated=False)[0], 401)
        status, result = self.call("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["summary"]["training_volume_kg"], 240)
        self.assertEqual(result["data"]["evidence"]["workout_id"], saved["data"]["id"])
        self.assertEqual(result["data"]["source"], "rules-v1")
        self.assertEqual(self.call("GET", "/workouts/" + "0" * 32 + "/recovery")[0], 404)

    def test_bodyweight_workout_http_keeps_null_load(self):
        status, result = self.call("POST", "/workouts", {"workout_type": "strength", "minutes": 20,
            "sets": [{"exercise_name": "俯卧撑", "set_no": 1,
                      "weight_kg": None, "reps": 12, "completed": True}]})
        self.assertEqual(status, 201)
        self.assertIsNone(result["data"]["sets"][0]["weight_kg"])
        self.assertEqual(result["data"]["sets"][0]["volume"], 0)
        self.assertEqual(result["data"]["total_volume"], 0)

    def test_device_conflict_http_can_be_reviewed_and_resolved(self):
        day = today()
        def at(hour: int, minute: int = 0) -> str:
            return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+08:00").astimezone(
                timezone.utc).isoformat(timespec="seconds")
        workout = {"local_date": day, "workout_type": "walking", "minutes": 60,
                   "kcal": 80, "start_at": at(10), "end_at": at(11)}
        self.assertEqual(self.call("POST", "/workouts", workout)[0], 201)
        connected = self.call("POST", "/devices", {"provider": "manual_device_import"})[1]
        device_id = connected["data"]["id"]
        imported = self.call("POST", f"/devices/{device_id}/samples", {"samples": [{
            "external_id": "http-timed", "sample_type": "active_energy", "local_date": day,
            "value": 100, "start_at": at(10, 30), "end_at": at(11, 30)}]})
        self.assertEqual(imported[0], 201)
        self.assertEqual(imported[1]["data"]["pending_conflicts"], 1)
        status, listed = self.call("GET", f"/devices/conflicts?date={day}")
        self.assertEqual(status, 200)
        conflict_id = listed["data"][0]["id"]
        self.assertEqual(self.call("GET", "/devices/conflicts", authenticated=False)[0], 401)
        self.assertEqual(self.call("POST", f"/devices/conflicts/{conflict_id}/resolve",
                                   {"resolution": "KEEP_MANUAL"})[0], 200)
        self.assertEqual(self.call("GET", f"/analytics/days?date={day}")[1]["data"]
                         ["energy"]["activity_kcal"], 130)
        self.assertEqual(self.call("GET", f"/devices/conflicts?date={day}")[1]["data"], [])
        self.assertEqual(self.call("GET", f"/devices/conflicts?date={day}&status=all")[1]
                         ["data"][0]["resolution"], "KEEP_MANUAL")

    def test_device_revoke_http_can_keep_or_delete_history(self):
        day = today()
        status, connected = self.call("POST", "/devices", {"provider": "manual_device_import"})
        self.assertEqual(status, 201)
        device_id = connected["data"]["id"]
        sample = {"external_id": "revoke-http-1", "sample_type": "active_energy",
                  "local_date": day, "value": 135}
        self.assertEqual(self.call("POST", f"/devices/{device_id}/samples",
                                   {"samples": [sample]})[0], 201)
        status, listed = self.call("GET", "/devices")
        self.assertEqual(status, 200)
        self.assertEqual(listed["data"][0]["sample_count"], 1)
        self.assertEqual(self.call("DELETE", f"/devices/{device_id}", authenticated=False)[0], 401)
        self.assertEqual(self.call("DELETE", f"/devices/{device_id}?delete_history=yes")[0], 400)
        status, retained = self.call("DELETE", f"/devices/{device_id}")
        self.assertEqual(status, 200)
        self.assertTrue(retained["data"]["history_retained"])
        self.assertEqual(retained["data"]["removed_samples"], 0)
        self.assertEqual(self.call("GET", "/devices")[1]["data"][0]["sample_count"], 1)
        self.assertEqual(self.call("GET", f"/analytics/days?date={day}")[1]["data"]
                         ["energy"]["activity_kcal"], 135)
        self.assertEqual(self.call("POST", f"/devices/{device_id}/samples",
                                   {"samples": [sample]})[0], 404)
        status, removed = self.call("DELETE", f"/devices/{device_id}?delete_history=true")
        self.assertEqual(status, 200)
        self.assertFalse(removed["data"]["history_retained"])
        self.assertEqual(removed["data"]["removed_samples"], 1)
        self.assertEqual(self.call("GET", "/devices")[1]["data"][0]["sample_count"], 0)
        self.assertEqual(self.call("GET", f"/analytics/days?date={day}")[1]["data"]
                         ["energy"]["activity_kcal"], 0)

    def test_articles_priority_visibility_and_source_filter(self):
        previous_rss = os.environ.get("NUTRIPULSE_RSS_URL")
        os.environ["NUTRIPULSE_RSS_URL"] = "https://feed.example.com/rss.xml"
        try:
            with connect() as db:
                for index, host in enumerate(("feed.example.com", "feed.example.com", "evil.example.org")):
                    db.execute("""INSERT INTO articles(id,source,source_url,title,summary,published_at,
                        expires_at,content_hash) VALUES (?,?,?,?,?,?,?,?)""",
                        (f"{index + 1:032x}", host, f"https://{host}/story-{index}",
                         f"Story {index}", "Summary", f"2026-10-0{index + 1} 00:00:00",
                         "2099-01-01 00:00:00", f"digest-{index}"))
                db.commit()
            status, payload = self.call("GET", "/articles")
            self.assertEqual(status, 200)
            self.assertEqual([row["title"] for row in payload["data"]], ["Story 1", "Story 0"])
            first_id = f"{1:032x}"
            status, payload = self.call("PATCH", f"/articles/{first_id}/moderation",
                                        {"status": "VISIBLE", "priority": 50})
            self.assertEqual(status, 200)
            self.assertEqual(payload["data"]["priority"], 50)
            self.assertEqual(self.call("GET", "/articles")[1]["data"][0]["title"], "Story 0")
            self.assertEqual(self.call("PATCH", f"/articles/{first_id}/moderation",
                                       {"status": "HIDDEN", "priority": 50})[0], 200)
            self.assertEqual([row["title"] for row in self.call("GET", "/articles")[1]["data"]],
                             ["Story 1"])
            self.assertEqual(self.call("PATCH", f"/articles/{first_id}/moderation",
                                       {"status": "VISIBLE", "priority": 101})[0], 400)
        finally:
            if previous_rss is None:
                os.environ.pop("NUTRIPULSE_RSS_URL", None)
            else:
                os.environ["NUTRIPULSE_RSS_URL"] = previous_rss

    def test_diagnosis_http_history_and_metadata(self):
        day = today()
        self.assertEqual(self.call("GET", f"/analytics/diagnostics?start={day}&end={day}")[1]
                         ["data"]["items"], [])
        first_status, first = self.call("POST", "/analytics/diagnostics", {"start": day, "end": day})
        second_status, second = self.call("POST", "/analytics/diagnostics", {"start": day, "end": day})
        self.assertEqual((first_status, second_status), (201, 201))
        self.assertEqual((first["data"]["version"], second["data"]["version"]), (1, 2))
        self.assertEqual(len(first["data"]["input_hash"]), 64)
        history = self.call("GET", f"/analytics/diagnostics?start={day}&end={day}")[1]["data"]["items"]
        self.assertEqual([entry["version"] for entry in history], [2, 1])
        self.assertEqual(history[0]["advice_details"][0]["evidence_refs"][0]["metric"], "target_days")
        self.assertEqual(self.call("GET", f"/analytics/diagnostics?start={day}&end={day}",
                                   authenticated=False)[0], 401)

    def test_http_retry_with_same_idempotency_key_does_not_duplicate_ledger(self):
        day = today()
        meal = {"local_date": day, "meal_type": "breakfast", "items": [
            {"display_name": "幂等早餐", "amount": 1, "unit": "份", "kcal": 180}]}
        key = {"Idempotency-Key": "http-breakfast-once"}
        first = self.call("POST", "/meals", meal, extra_headers=key)
        repeated = self.call("POST", "/meals", meal, extra_headers=key)
        self.assertEqual((first[0], repeated[0]), (201, 201))
        self.assertEqual(first[1]["data"]["id"], repeated[1]["data"]["id"])
        self.assertEqual(self.call("GET", f"/analytics/days?date={day}")[1]["data"]
                         ["energy"]["intake_kcal"], 180)
        workout = {"local_date": day, "workout_type": "walking", "minutes": 20}
        key = {"Idempotency-Key": "http-workout-once"}
        first = self.call("POST", "/workouts", workout, extra_headers=key)
        repeated = self.call("POST", "/workouts", workout, extra_headers=key)
        self.assertEqual((first[0], repeated[0]), (201, 201))
        self.assertEqual(first[1]["data"]["id"], repeated[1]["data"]["id"])
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0], 1)

    def test_pdf_report_period_auth_and_no_cache(self):
        from app.application.analytics.report import period_bounds, report_snapshot
        self.assertEqual(period_bounds("week", "2026-10-03"), ("2026-09-27", "2026-10-03", "day"))
        self.assertEqual(period_bounds("month", "2026-10-03"), ("2026-10-01", "2026-10-03", "week"))
        self.assertEqual(self.report({"period": "day", "end": today()}, False)[0], 401)
        status, content_type, cache_control, payload = self.report({"period": "week", "end": today()})
        self.assertEqual((status, content_type, cache_control), (200, "application/pdf", "no-store"))
        self.assertTrue(payload.startswith(b"%PDF-"))
        self.assertGreater(len(payload), 10_000)
        snapshot = report_snapshot("week", today())
        self.assertIn("habits", snapshot)
        self.assertEqual(snapshot["habits"]["end"], snapshot["end"])
        self.assertEqual(snapshot["habits"]["start"], snapshot["start"])
        self.assertEqual(self.report({"period": "invalid", "end": today()})[0], 400)

    def test_auth_profile_meal_and_summary_contract(self):
        self.assertEqual(self.call("GET", "/profile", authenticated=False)[0], 401)
        self.assertEqual(self.call("GET", "/health", authenticated=False)[1]["data"]["status"], "ok")
        profile = {"display_name": "黑盒用户", "birth_date": "1998-05-01", "formula_sex": "male",
                   "height_cm": 178, "activity_level": "light"}
        self.assertEqual(self.call("PUT", "/profile", profile)[0], 200)
        self.assertEqual(self.call("POST", "/measurements", {"weight_kg": 72.5})[0], 201)
        self.assertEqual(self.call("POST", "/goals", {"goal_type": "maintenance"})[0], 201)
        meal = {"local_date": today(), "meal_type": "lunch", "status": "PLANNED",
                "items": [{"display_name": "米饭", "amount": 100, "unit": "g", "kcal": 116}]}
        status, created = self.call("POST", "/meals", meal)
        self.assertEqual(status, 201)
        meal_id = created["data"]["id"]
        self.assertEqual(self.call("GET", f"/nutrition/days/{today()}")[1]["data"]["summary"]["energy"]["intake_kcal"], 0)
        self.assertEqual(self.call("POST", f"/meals/{meal_id}", {"status": "CONSUMED"})[0], 200)
        self.assertEqual(self.call("GET", f"/nutrition/days/{today()}")[1]["data"]["summary"]["energy"]["intake_kcal"], 116)

    def test_food_catalog_search_contract(self):
        status, payload = self.call("GET", "/foods?q=%E7%B1%B3%E9%A5%AD")
        self.assertEqual(status, 200)
        foods = payload["data"]
        self.assertTrue(any(food["id"] == "rice" and food["kcal"] == 116 for food in foods))
        self.assertLessEqual(len(foods), 30)
        self.assertEqual(self.call("GET", "/foods/frequent")[1]["data"], [])

    def test_habit_summary_http_marks_missing_fiber_and_provisional_today(self):
        day = today()
        self.assertEqual(self.call("GET", f"/analytics/habits?start={day}&end={day}",
                                   authenticated=False)[0], 401)
        self.assertEqual(self.call("POST", "/meals", {"local_date": day,
            "meal_type": "lunch", "items": [{"display_name": "未知纤维午餐",
                "amount": 100, "unit": "g", "kcal": 250}]})[0], 201)
        self.assertEqual(self.call("POST", "/water-logs", {"local_date": day,
            "amount_ml": 300})[0], 201)
        status, response = self.call("GET", f"/analytics/habits?start={day}&end={day}")
        self.assertEqual(status, 200)
        data = response["data"]
        self.assertEqual(data["water"]["recorded_ml"], 300)
        self.assertEqual(data["fiber"]["unknown_items"], 1)
        self.assertIsNone(data["fiber"]["known_g"])
        self.assertEqual(data["closed_days"], 0)
        self.assertIsNone(data["meals"]["three_meal_logging_pct"])
        self.assertIsNone(data["training"]["completion_pct"])
        future = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        self.assertEqual(self.call("GET", f"/analytics/habits?start={future}&end={future}")[1]
                         ["data"]["observed_days"], 0)
        self.assertEqual(self.call("GET", f"/analytics/habits?start={future}&end={day}")[0], 400)

    def test_partial_macro_presence_is_visible_in_day_and_period_contracts(self):
        day = today()
        item = {"display_name": "宏量未知样本", "amount": 1, "unit": "份",
                "kcal": 220, "carb_g": 0, "protein_g": 10}
        status, created = self.call("POST", "/meals", {
            "local_date": day, "meal_type": "lunch", "items": [item]})
        self.assertEqual(status, 201)
        meal_id = created["data"]["id"]
        self.assertEqual(created["data"]["items"][0]["nutrient_known_mask"], 3)
        daily = self.call("GET", f"/nutrition/days/{day}")[1]["data"]["summary"]
        self.assertEqual(daily["incomplete_macro_items"], 1)
        period = self.call("GET", f"/analytics/macros?start={day}&end={day}")[1]["data"]
        self.assertEqual(period["incomplete_items"], 1)
        item["fat_g"] = 0
        status, updated = self.call("POST", f"/meals/{meal_id}", {"items": [item]})
        self.assertEqual(status, 200)
        self.assertEqual(updated["data"]["items"][0]["nutrient_known_mask"], 7)
        self.assertEqual(self.call("GET", f"/nutrition/days/{day}")[1]["data"]
                         ["summary"]["incomplete_macro_items"], 0)

    def test_training_plan_filter_contract(self):
        status, payload = self.call("GET", "/training-plans?level=beginner&goal_type=fat_loss")
        self.assertEqual(status, 200)
        self.assertEqual([plan["code"] for plan in payload["data"]], ["PLAN-02"])
        self.assertEqual(self.call("GET", "/training-plans?level=expert")[0], 400)
        self.assertEqual(self.call("GET", "/training-plans?goal_type=medical_rehab")[0], 400)

    def test_plan_follow_http_updates_fitness_and_analytics(self):
        day = today()
        status, enrolled = self.call("POST", "/training-plans/PLAN-03/enroll", {"start_date": day})
        self.assertEqual(status, 201)
        session = self.call("GET", f"/fitness/days/{day}")[1]["data"]["active_plan"]["today_session"]
        self.assertEqual(session["title"], "上肢 A")
        self.assertEqual(session["scheduled_date"], day)
        status, replaced = self.call("POST", f"/training-plans/active/sessions/{session['id']}/replace",
                                     {"index": 0, "replacement": "哑铃卧推 4×8", "reason": "器械条件调整"})
        self.assertEqual(status, 200)
        self.assertEqual(replaced["data"]["exercises"][0], "哑铃卧推 4×8")
        self.assertEqual(replaced["data"]["original_exercises"][0], "卧推 4×6-8")
        workout = {"local_date": day, "workout_type": "strength", "minutes": 45,
                   "plan_session_id": session["id"],
                   "sets": [{"exercise_name": "哑铃卧推", "set_no": 1, "weight_kg": 40, "reps": 8}]}
        status, created = self.call("POST", "/workouts", workout)
        self.assertEqual(status, 201)
        self.assertEqual(created["data"]["plan_instance_id"], enrolled["data"]["id"])
        self.assertEqual(created["data"]["total_volume"], 320)
        self.assertEqual(self.call("POST", "/workouts", workout)[0], 400)
        fitness = self.call("GET", f"/fitness/days/{day}")[1]["data"]
        self.assertEqual(fitness["active_plan"]["progress"]["completed"], 0)
        self.assertEqual(fitness["active_plan"]["progress"]["partial"], 1)
        self.assertEqual(fitness["active_plan"]["today_session"]["status"], "PARTIAL")
        self.assertEqual(fitness["workouts"][0]["plan_session_title"], "上肢 A")
        self.assertEqual(self.call("GET", f"/analytics/energy?start={day}&end={day}")[1]
                         ["data"]["series"][0]["training_volume"], 320)

    def test_dining_preferences_http_contract(self):
        body = {"allergies": [], "restrictions": [], "preferences": [],
                "dining": {"max_cost_cny": 20, "max_cook_minutes": 10,
                           "flavors": ["清淡"], "preferred_scenario": "self_cook"}}
        self.assertEqual(self.call("PUT", "/preferences", body)[0], 200)
        profile = self.call("GET", "/profile")[1]["data"]
        self.assertEqual(profile["dining"]["max_cook_minutes"], 10)
        status, payload = self.call("POST", "/recommendations/meals", {"meal_type": "dinner"})
        self.assertEqual(status, 201)
        self.assertTrue(payload["data"]["items"])
        for item in payload["data"]["items"]:
            self.assertLessEqual(item["estimated_cost_cny"], 20)
            self.assertLessEqual(item["prep_minutes"] + item["cook_minutes"], 10)
        body["dining"]["flavors"] = ["unknown"]
        self.assertEqual(self.call("PUT", "/preferences", body)[0], 400)

    def test_privacy_export_and_confirmed_category_deletion(self):
        day = today()
        self.assertEqual(self.call("PUT", "/profile", {"display_name": "需要导出的用户",
            "birth_date": "1998-05-01", "formula_sex": "female", "height_cm": 165,
            "activity_level": "light"})[0], 200)
        self.assertEqual(self.call("POST", "/measurements", {"weight_kg": 58})[0], 201)
        trend = self.call("GET", f"/analytics/body-composition?start={day}&end={day}")[1]["data"]["series"]
        self.assertEqual(trend[0]["weight_kg"], 58.0)
        self.assertIsNone(trend[0]["body_fat_pct"])
        self.assertEqual(self.call("POST", "/goals", {"goal_type": "maintenance"})[0], 201)
        self.assertEqual(self.call("POST", "/meals", {"local_date": day, "meal_type": "lunch",
            "items": [{"display_name": "米饭", "amount": 100, "unit": "g", "kcal": 116}]})[0], 201)
        self.assertEqual(self.call("POST", "/workouts", {"local_date": day,
            "workout_type": "walking", "minutes": 30})[0], 201)
        self.assertEqual(self.call("POST", "/recommendations/meals", {"meal_type": "dinner"})[0], 201)
        self.assertEqual(self.call("GET", "/privacy/export", authenticated=False)[0], 401)
        status, exported = self.call("GET", "/privacy/export?category=all")
        self.assertEqual(status, 200)
        tables = exported["data"]["tables"]
        self.assertEqual(tables["users"][0]["display_name"], "需要导出的用户")
        self.assertEqual(len(tables["meals"]), 1)
        self.assertEqual(len(tables["workout_sessions"]), 1)
        self.assertTrue(tables["recommendation_sessions"])
        self.assertNotIn("token_ref", str(exported))
        preview = self.call("GET", "/privacy/delete-preview?category=diet")[1]["data"]
        self.assertEqual(preview["counts"]["meals"], 1)
        self.assertEqual(self.call("POST", "/privacy/delete", {"category": "diet",
            "confirmation_phrase": "wrong"})[0], 400)
        self.assertEqual(len(self.call("GET", "/privacy/export?category=diet")[1]["data"]["tables"]["meals"]), 1)
        self.assertEqual(self.call("POST", "/privacy/delete", {"category": "diet",
            "confirmation_phrase": preview["confirmation_phrase"]})[0], 200)
        after_diet = self.call("GET", "/privacy/export?category=all")[1]["data"]["tables"]
        self.assertEqual(after_diet["meals"], [])
        self.assertEqual(after_diet["recommendation_sessions"], [])
        self.assertEqual(len(after_diet["workout_sessions"]), 1)
        self.assertEqual(self.call("POST", "/privacy/delete", {"category": "all",
            "confirmation_phrase": "DELETE_ALL"})[0], 200)
        after_all = self.call("GET", "/privacy/export?category=all")[1]["data"]["tables"]
        self.assertEqual(after_all["users"][0]["display_name"], "我")
        self.assertEqual(after_all["workout_sessions"], [])
        self.assertEqual(after_all["body_measurements"], [])
        self.assertEqual(after_all["goals"], [])
        self.assertEqual(after_all["outbox_events"], [])

    def test_cross_hub_http_flow(self):
        day = today()
        self.assertEqual(self.call("PUT", "/profile", {"display_name": "联调用户",
            "birth_date": "1998-05-01", "formula_sex": "female", "height_cm": 165,
            "activity_level": "light"})[0], 200)
        self.assertEqual(self.call("POST", "/measurements", {"weight_kg": 58})[0], 201)
        self.assertEqual(self.call("POST", "/goals", {"goal_type": "maintenance"})[0], 201)
        self.assertEqual(self.call("PUT", "/preferences", {"allergies": ["花生"],
            "restrictions": [], "preferences": []})[0], 200)
        plans = self.call("GET", "/training-plans")[1]["data"]
        self.assertGreaterEqual(len(plans), 5)
        self.assertEqual(self.call("POST", f"/training-plans/{plans[0]['id']}/enroll", {})[0], 201)
        self.assertEqual(self.call("POST", "/workouts", {"local_date": day,
            "workout_type": "walking", "minutes": 30})[0], 201)
        status, recommended = self.call("POST", "/recommendations/meals", {
            "local_date": day, "meal_type": "dinner", "scenario": "self_cook"})
        self.assertEqual(status, 201)
        items = recommended["data"]["items"]
        self.assertTrue(items)
        self.assertEqual(self.call("GET", f"/analytics/macros?start={day}&end={day}")[1]
                         ["data"]["intake_kcal"], 0)
        status, accepted = self.call("POST", f"/recommendations/{items[0]['id']}/accept", {"servings": 1})
        self.assertEqual(status, 201)
        meal_id = accepted["data"]["meal_id"]
        self.assertEqual(self.call("GET", f"/nutrition/days/{day}")[1]["data"]["summary"]
                         ["energy"]["intake_kcal"], 0)
        self.assertEqual(self.call("POST", f"/meals/{meal_id}", {"status": "CONSUMED"})[0], 200)
        macros = self.call("GET", f"/analytics/macros?start={day}&end={day}")[1]["data"]
        self.assertGreater(macros["intake_kcal"], 0)
        self.assertGreater(macros["actual"]["protein_g"], 0)
        energy_point = (self.call("GET", f"/analytics/energy?start={day}&end={day}")[1]
                        ["data"]["series"][0])
        self.assertGreater(energy_point["expenditure_kcal"], 0)
        self.assertGreater(energy_point["tdee_kcal"], energy_point["bmr_kcal"])

    def test_goal_preview_http_requires_confirmation_and_preserves_inputs(self):
        self.assertEqual(self.call("POST", "/goals/preview",
                                   {"goal_type": "fat_loss"}, authenticated=False)[0], 401)
        status, incomplete = self.call("POST", "/goals/preview", {"goal_type": "fat_loss"})
        self.assertEqual(status, 200)
        self.assertFalse(incomplete["data"]["ready"])
        self.assertEqual(self.call("PUT", "/profile", {"display_name": "试算用户",
            "birth_date": "1998-05-01", "formula_sex": "female", "height_cm": 165,
            "activity_level": "light"})[0], 200)
        self.assertEqual(self.call("POST", "/measurements", {"weight_kg": 58})[0], 201)
        status, preview = self.call("POST", "/goals/preview", {"goal_type": "maintenance"})
        self.assertEqual(status, 200)
        self.assertTrue(preview["data"]["ready"])
        self.assertEqual(self.call("POST", "/goals", {"goal_type": "maintenance",
            "preview_fingerprint": "outdated"})[0], 409)
        self.assertIsNone(self.call("GET", "/profile")[1]["data"]["goal"])
        confirmed = self.call("POST", "/goals", {"goal_type": "maintenance",
            "preview_fingerprint": preview["data"]["input_fingerprint"]})
        self.assertEqual(confirmed[0], 201)
        target = confirmed[1]["data"]["target"]
        self.assertEqual(target["inputs"]["measurement_id"],
                         confirmed[1]["data"]["measurement"]["id"])
        self.assertEqual(target["kcal"], preview["data"]["proposed_target"]["target_kcal"])


if __name__ == "__main__":
    unittest.main()
