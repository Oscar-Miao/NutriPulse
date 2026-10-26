import os
import base64
import json
import sqlite3
import tempfile
import unittest
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PIL import Image

from app.application.analytics.service import (day_summary, energy_series, body_composition_series,
                                               macro_summary, habit_summary, rule_diagnosis, generate_diagnosis,
                                               diagnosis_history)
from app.application.fitness.service import (create_workout, estimate_workout, list_workouts, list_plans, enroll,
                                             active_plan, replace_plan_exercise, stop_active_plan)
from app.application.fitness.recovery import recovery_advice
from app.application.fitness.device import connect_device, import_samples, disconnect, connections
from app.application.fitness.conflicts import list_conflicts, resolve_conflict
from app.application.nutrition.service import create_meal, get_meal, update_meal, delete_meal, restore_meal, add_water, set_water_total, frequent_foods
from app.application.nutrition.scan import create_scan, get_scan, confirm_scan
from app.application.profile.service import (add_measurement, get_profile, set_goal, set_preferences,
                                             set_training_profile, update_profile, preview_goal)
from app.application.profile.privacy import delete_data, deletion_preview, export_data
from app.application.recommendation.service import accept, recommend, recipe_detail, submit_feedback, get_recommendations
from app.application.recommendation.scoring import DEFAULT_WEIGHTS, scoring_config
from app.application.recommendation.chat import new_chat, send_message, accept_proposal
from app.domain.metabolism import calculate_targets, met_kcal, training_volume
from app.domain.exercise import estimate_activity
from app.domain.activity import reconcile_activity
from app.domain.energy import calculate_day
from app.infrastructure.db.database import MIGRATIONS, connect, migrate, transaction
from app.infrastructure.db.backup import restore_backup, verify_backup
from app.infrastructure.db.seed import seed
from app.infrastructure.files.image_upload import clean_upload_image
from app.shared.util import new_id, today, valid_date
from app.shared.errors import ApiError
from tests.image_fixture import encoded_jpeg, image_bytes


class DomainTest(unittest.TestCase):
    def test_recommendation_weights_are_complete_versioned_and_validated(self):
        weights, base_version = scoring_config()
        self.assertEqual(weights, DEFAULT_WEIGHTS)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        adjusted = {**weights, "macro": 0.30, "calorie": 0.25}
        with patch.dict(os.environ, {"NUTRIPULSE_RECOMMENDATION_WEIGHTS": json.dumps(adjusted)}):
            actual, version = scoring_config()
            self.assertEqual(actual, adjusted)
            self.assertNotEqual(version, base_version)
        with patch.dict(os.environ, {"NUTRIPULSE_RECOMMENDATION_WEIGHTS": '{"macro": 1}'}):
            self.assertEqual(scoring_config(), (DEFAULT_WEIGHTS, base_version))

    def test_mifflin_and_met(self):
        result = calculate_targets(28, 178, 72.5, "male", "light", "fat_loss")
        self.assertEqual(result.bmr_kcal, 1703.0)
        self.assertEqual(result.tdee_kcal, 2341.0)
        self.assertGreater(met_kcal(8.3, 72.5, 30), 300)
        self.assertEqual(training_volume([{"weight_kg": 50, "reps": 8},
                                          {"weight_kg": 50, "reps": 8, "completed": False}]), 400)
        with self.assertRaises(ApiError):
            valid_date("20261002")

    def test_energy_net_uses_raw_expenditure_before_display_rounding(self):
        result = calculate_day(200, 100.06, 0, 100.04, 0)
        self.assertEqual(result.total_expenditure_kcal, 100.0)
        self.assertEqual(result.net_kcal, 0.0)

    def test_remaining_budget_only_credits_activity_beyond_tdee_baseline(self):
        routine = calculate_day(2000, 1200, 1500, 2200, 300)
        self.assertEqual(routine.activity_adjustment_kcal, 0)
        self.assertEqual(routine.remaining_kcal, 800)
        extra = calculate_day(2000, 1200, 1500, 2200, 1000)
        self.assertEqual(extra.total_expenditure_kcal, 2500)
        self.assertEqual(extra.activity_adjustment_kcal, 300)
        self.assertEqual(extra.remaining_kcal, 1100)
        self.assertEqual(extra.net_kcal, -1300)

    def test_met_intensity_reference_is_monotonic_and_versioned(self):
        estimates = [estimate_activity("cycling", intensity, 70, 30)
                     for intensity in ("low", "moderate", "high")]
        self.assertEqual([item["met_value"] for item in estimates], [4.0, 7.0, 10.0])
        self.assertEqual(estimates[1]["kcal"], met_kcal(7.0, 70, 30))
        self.assertTrue(estimates[0]["kcal"] < estimates[1]["kcal"] < estimates[2]["kcal"])
        self.assertEqual(estimates[1]["calculation_version"], "met-demo-v1")
        with self.assertRaises(ApiError):
            estimate_activity("walking", "extreme", 70, 30)

    def test_time_window_activity_reconciliation_and_coarse_fallback(self):
        sample = {"id": "device", "start_at": "2026-10-04T01:00:00+00:00",
                  "end_at": "2026-10-04T02:00:00+00:00", "value": 100}
        workout = {"id": "manual", "start_at": "2026-10-04T01:30:00+00:00",
                   "end_at": "2026-10-04T02:30:00+00:00", "kcal": 80}
        self.assertEqual(reconcile_activity([sample], [workout])["kcal"], 140)
        self.assertEqual(reconcile_activity([sample], [workout],
            {("device", "manual"): "KEEP_DEVICE"})["kcal"], 100)
        self.assertEqual(reconcile_activity([sample], [workout],
            {("device", "manual"): "KEEP_MANUAL"})["kcal"], 130)
        self.assertEqual(reconcile_activity([sample], [workout],
            {("device", "manual"): "MERGE_NON_OVERLAPPING"})["kcal"], 140)
        coarse = dict(sample, end_at=None)
        self.assertEqual(reconcile_activity([coarse], [workout])["kcal"], 100)
        self.assertEqual(reconcile_activity([coarse], [workout])["quality"], "daily_fallback")


class MigrationUpgradeTest(unittest.TestCase):
    def test_upgrade_from_001_preserves_profile_and_refreshes_old_energy_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "upgrade.sqlite3"
            old_db = os.environ.get("NUTRIPULSE_DB")
            os.environ["NUTRIPULSE_DB"] = str(path)
            try:
                with closing(sqlite3.connect(path)) as db:
                    db.executescript((Path(__file__).resolve().parents[1] /
                                      "migrations" / "001_initial.sql").read_text(encoding="utf-8"))
                    db.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                    db.execute("INSERT INTO schema_migrations(version) VALUES ('001_initial')")
                    db.execute("UPDATE users SET display_name='原有用户' WHERE id='local-user'")
                    db.execute("INSERT INTO recipes(id,name,scenario) VALUES ('r1','鸡胸肉西兰花饭','self_cook')")
                    db.execute("""INSERT INTO meals(id,user_id,local_date,meal_type,status)
                        VALUES ('legacy-meal','local-user','2026-10-01','lunch','CONSUMED')""")
                    db.execute("""INSERT INTO meal_items(id,meal_id,display_name,amount,unit,
                        kcal,carb_g,protein_g,fat_g) VALUES
                        ('legacy-item','legacy-meal','旧版米饭',100,'g',116,25.9,2.6,0.3)""")
                    db.execute("INSERT INTO daily_energy_snapshots(user_id,local_date,intake_kcal) "
                               "VALUES ('local-user','2026-10-01',999)")
                    db.commit()
                migrate()
                pre_migration = list((Path(directory) / "backups").glob("nutripulse-pre-migration-*.sqlite3"))
                self.assertEqual(len(pre_migration), 1)
                self.assertEqual(verify_backup(pre_migration[0])["schema_versions"], ["001_initial"])
                recovered = restore_backup(pre_migration[0], Path(directory) / "before_upgrade.sqlite3")
                with closing(sqlite3.connect(recovered)) as before:
                    self.assertEqual(before.execute("SELECT display_name FROM users").fetchone()[0], "原有用户")
                seed()
                self.assertEqual(get_profile()["profile"]["display_name"], "原有用户")
                self.assertEqual(get_profile()["dining"]["preferred_scenario"], "self_cook")
                with connect() as db:
                    recipe = db.execute("SELECT estimated_cost_cny,flavors_json FROM recipes WHERE id='r1'").fetchone()
                    self.assertEqual(recipe["estimated_cost_cny"], 18)
                    self.assertIn("清淡", recipe["flavors_json"])
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],
                                     len(list(MIGRATIONS.glob("*.sql"))))
                    self.assertIsNotNone(db.execute("""SELECT name FROM sqlite_master
                        WHERE type='index' AND name='idx_device_samples_external_type'""").fetchone())
                    old_cache = db.execute("""SELECT intake_kcal,calc_version FROM daily_energy_snapshots
                        WHERE local_date='2026-10-01'""").fetchone()
                    self.assertEqual((old_cache["intake_kcal"], old_cache["calc_version"]),
                                     (999, "energy-v1"))
                    self.assertEqual(db.execute("SELECT nutrient_known_mask FROM meal_items WHERE id='legacy-item'")
                                     .fetchone()[0], 0)
                    self.assertIn("stopped_on", {column[1] for column in
                        db.execute("PRAGMA table_info(user_plan_enrollments)")})
                    self.assertGreater(db.execute("SELECT COUNT(*) FROM food_substitutions").fetchone()[0], 0)
                self.assertEqual(energy_series("2026-10-01", "2026-10-01")["series"][0]
                                 ["intake_kcal"], 116)
                self.assertEqual(macro_summary("2026-10-01", "2026-10-01")["incomplete_items"], 1)
                with connect() as db:
                    self.assertEqual(db.execute("""SELECT calc_version FROM daily_energy_snapshots
                        WHERE local_date='2026-10-01'""").fetchone()[0], "energy-v6-nutrient-presence")
            finally:
                if old_db is None:
                    os.environ.pop("NUTRIPULSE_DB", None)
                else:
                    os.environ["NUTRIPULSE_DB"] = old_db


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("NUTRIPULSE_DB")
        os.environ["NUTRIPULSE_DB"] = str(Path(self.temp.name) / "test.sqlite3")
        migrate()
        seed()

    def tearDown(self):
        if self.old_db is None:
            os.environ.pop("NUTRIPULSE_DB", None)
        else:
            os.environ["NUTRIPULSE_DB"] = self.old_db
        self.temp.cleanup()

    def _onboard(self):
        update_profile({"display_name": "测试", "birth_date": "1998-05-01",
                        "formula_sex": "male", "height_cm": 178, "activity_level": "light"})
        add_measurement({"weight_kg": 72.5})
        set_goal({"goal_type": "fat_loss"})

    def test_habit_summary_preserves_unknown_fiber_and_excludes_unfinished_day_from_rates(self):
        self._onboard()
        today_date = date.fromisoformat(today())
        start = (today_date - timedelta(days=4)).isoformat()
        middle = (today_date - timedelta(days=3)).isoformat()
        later = (today_date - timedelta(days=2)).isoformat()
        with transaction() as db:
            db.execute("UPDATE nutrition_targets SET effective_from=? WHERE user_id='local-user'",
                       (start,))
        add_water({"local_date": start, "amount_ml": 2500})
        add_water({"local_date": middle, "amount_ml": 500})
        add_water({"local_date": today(), "amount_ml": 300})
        def meal(day: str, kind: str, fiber_known: bool = True, status: str = "CONSUMED"):
            item = {"display_name": "测试餐食", "amount": 100, "unit": "g", "kcal": 100}
            if fiber_known:
                item["fiber_g"] = 2
            create_meal({"local_date": day, "meal_type": kind, "status": status,
                         "items": [item]})
        for kind in ("breakfast", "lunch", "dinner"):
            meal(start, kind)
            meal(later, kind)
        meal(middle, "lunch", fiber_known=False)
        meal(today(), "snack", status="PLANNED")
        result = habit_summary(start, today())
        self.assertEqual((result["observed_days"], result["closed_days"]), (5, 4))
        self.assertTrue(result["today_is_partial"])
        self.assertEqual(result["water"], {"recorded_ml": 3300, "recorded_days": 3,
                                           "evaluated_goal_days": 2, "met_goal_days": 1})
        self.assertEqual(result["fiber"], {"known_g": 12.0, "known_items": 6,
                                           "unknown_items": 1, "consumed_items": 7})
        self.assertEqual(result["meals"], {"logged_closed_days": 3,
                                           "three_main_meals_logged_days": 2,
                                           "three_meal_logging_pct": 66.7})
        self.assertIsNone(result["training"]["completion_pct"])
        future = (today_date + timedelta(days=1)).isoformat()
        self.assertEqual(habit_summary(future, future)["observed_days"], 0)
        self.assertIsNone(habit_summary(future, future)["fiber"]["known_g"])

    def test_habit_training_rate_excludes_sessions_after_stop_and_unknown_legacy_stop(self):
        start = (date.fromisoformat(today()) - timedelta(days=14)).isoformat()
        joined = enroll("PLAN-01", start)
        stopped = stop_active_plan()
        self.assertEqual(stopped["stopped_on"], today())
        stop_day = (date.fromisoformat(start) + timedelta(days=3)).isoformat()
        with transaction() as db:
            rows = db.execute("""SELECT id FROM plan_session_instances WHERE enrollment_id=?
                ORDER BY scheduled_date LIMIT 2""", (joined["id"],)).fetchall()
            db.execute("UPDATE plan_session_instances SET status='COMPLETED' WHERE id=?",
                       (rows[0]["id"],))
            db.execute("UPDATE plan_session_instances SET status='PARTIAL' WHERE id=?",
                       (rows[1]["id"],))
            db.execute("UPDATE user_plan_enrollments SET stopped_on=? WHERE id=?",
                       (stop_day, joined["id"]))
        result = habit_summary(start, today())["training"]
        self.assertEqual((result["scheduled_closed_sessions"], result["completed_sessions"],
                          result["partial_sessions"]), (2, 1, 1))
        self.assertIsNone(result["completion_pct"])
        with transaction() as db:
            db.execute("UPDATE user_plan_enrollments SET stopped_on=NULL WHERE id=?", (joined["id"],))
        legacy = habit_summary(start, today())["training"]
        self.assertEqual(legacy["scheduled_closed_sessions"], 0)
        self.assertGreater(legacy["legacy_stop_unknown_sessions"], 0)

    def test_reenrolling_stamps_previous_plan_stop_date(self):
        prior = enroll("PLAN-01", (date.fromisoformat(today()) - timedelta(days=7)).isoformat())
        enroll("PLAN-02", today())
        with connect() as db:
            status, stopped_on = db.execute(
                "SELECT status,stopped_on FROM user_plan_enrollments WHERE id=?",
                (prior["id"],)).fetchone()
        self.assertEqual((status, stopped_on), ("STOPPED", today()))

    def test_habit_training_completion_rate_counts_only_full_sessions(self):
        start = (date.fromisoformat(today()) - timedelta(days=14)).isoformat()
        joined = enroll("PLAN-01", start)
        with transaction() as db:
            rows = db.execute("""SELECT id FROM plan_session_instances WHERE enrollment_id=?
                AND scheduled_date<? ORDER BY scheduled_date LIMIT 3""",
                (joined["id"], today())).fetchall()
            self.assertEqual(len(rows), 3)
            db.execute("UPDATE plan_session_instances SET status='COMPLETED' WHERE id=?",
                       (rows[0]["id"],))
            db.execute("UPDATE plan_session_instances SET status='PARTIAL' WHERE id=?",
                       (rows[1]["id"],))
        result = habit_summary(start, today())["training"]
        self.assertEqual((result["completed_sessions"], result["partial_sessions"]), (1, 1))
        self.assertGreaterEqual(result["scheduled_closed_sessions"], 3)
        self.assertEqual(result["completion_pct"],
                         round(100 / result["scheduled_closed_sessions"], 1))

    def test_body_composition_preserves_weight_gaps_and_last_known_weekly_fat(self):
        monday = date.fromisoformat(today()) - timedelta(days=date.fromisoformat(today()).weekday())
        first = monday - timedelta(days=14)
        second = monday - timedelta(days=7)
        with transaction() as db:
            for day, weight, fat in ((first, 70.0, 20.0), (second, 69.0, 19.5),
                                     (second + timedelta(days=1), 68.8, None)):
                db.execute("""INSERT INTO body_measurements
                    (id,user_id,measured_at,weight_kg,body_fat_pct,source_type)
                    VALUES (?,'local-user',?,?,?,'manual')""",
                    (new_id(), f"{day.isoformat()}T01:00:00+00:00", weight, fat))
        series = body_composition_series(first.isoformat(), today())["series"]
        self.assertEqual([point["weight_kg"] for point in series], [70.0, 68.8, None])
        self.assertEqual([point["body_fat_pct"] for point in series], [20.0, 19.5, None])
        self.assertEqual([point["training_volume_kg"] for point in series], [0.0, 0.0, 0.0])

    def test_device_revoke_can_retain_then_delete_only_its_imported_history(self):
        self._onboard()
        day = today()
        device = connect_device({"provider": "health_connect", "scopes": ["read_steps"]})
        import_samples(device["id"], {"samples": [
            {"external_id": "revoke-energy", "sample_type": "active_energy",
             "local_date": day, "value": 1000},
            {"external_id": "revoke-weight", "sample_type": "body_weight",
             "local_date": day, "value": 70},
        ]})
        imported_measurement = get_profile()["measurement"]["id"]
        self.assertEqual(get_profile()["target"]["measurement_id"], imported_measurement)
        self.assertEqual(connections()[0]["sample_count"], 2)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 1000)

        retained = disconnect(device["id"])
        self.assertTrue(retained["history_retained"])
        self.assertEqual(connections()[0]["sample_count"], 2)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 1000)
        self.assertEqual(energy_series(day, day)["series"][0]["expenditure_kcal"],
                         day_summary(day)["energy"]["total_expenditure_kcal"])
        with self.assertRaises(ApiError):
            import_samples(device["id"], {"samples": []})
        self.assertEqual(get_profile()["measurement"]["id"], imported_measurement)

        purged = disconnect(device["id"], delete_history=True)
        self.assertFalse(purged["history_retained"])
        self.assertEqual((purged["removed_samples"], purged["removed_measurements"],
                          purged["removed_targets"]), (2, 1, 1))
        self.assertTrue(purged["target_recalculated"])
        self.assertEqual(connections()[0]["sample_count"], 0)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 0)
        self.assertEqual(energy_series(day, day)["series"][0]["expenditure_kcal"],
                         day_summary(day)["energy"]["total_expenditure_kcal"])
        self.assertEqual(get_profile()["measurement"]["weight_kg"], 72.5)
        self.assertNotEqual(get_profile()["target"]["measurement_id"], imported_measurement)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM device_samples").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM body_measurements WHERE device_sample_id IS NOT NULL").fetchone()[0], 0)

    def test_device_history_deletion_without_other_weight_clears_active_target(self):
        update_profile({"birth_date": "1998-05-01", "formula_sex": "male",
                        "height_cm": 178, "activity_level": "light"})
        set_goal({"goal_type": "maintenance"})
        device = connect_device({"provider": "health_connect"})
        import_samples(device["id"], {"samples": [{
            "external_id": "only-weight", "sample_type": "body_weight",
            "local_date": today(), "value": 70}]})
        self.assertIsNotNone(get_profile()["target"])
        result = disconnect(device["id"], delete_history=True)
        self.assertFalse(result["target_recalculated"])
        self.assertIsNone(get_profile()["measurement"])
        self.assertIsNone(get_profile()["target"])
        self.assertFalse(day_summary(today())["has_target"])

    def test_reconnect_reuses_retained_device_samples_without_double_counting(self):
        self._onboard()
        day = today()
        first = connect_device({"provider": "health_connect"})
        sample = {"external_id": "stable-hc-record", "sample_type": "active_energy",
                  "local_date": day, "value": 120}
        import_samples(first["id"], {"samples": [sample]})
        disconnect(first["id"])
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 120)
        resumed = connect_device({"provider": "health_connect", "scopes": ["read_energy"]})
        self.assertEqual(resumed["id"], first["id"])
        self.assertEqual(import_samples(resumed["id"], {"samples": [sample]})["duplicates"], 1)
        self.assertEqual(connections()[0]["sample_count"], 1)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 120)
        import_samples(resumed["id"], {"samples": [dict(sample, value=140)]})
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 140)

    def test_retained_device_conflict_can_still_be_resolved_after_revoke(self):
        self._onboard()
        day = today()
        def at(hour: int, minute: int = 0) -> str:
            return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+08:00").astimezone(
                timezone.utc).isoformat(timespec="seconds")
        create_workout({"local_date": day, "workout_type": "walking", "minutes": 60,
                        "kcal": 80, "start_at": at(10), "end_at": at(11)})
        device = connect_device({"provider": "manual_device_import"})
        import_samples(device["id"], {"samples": [{
            "external_id": "revoked-conflict", "sample_type": "active_energy",
            "local_date": day, "value": 100, "start_at": at(10, 30), "end_at": at(11, 30)}]})
        disconnect(device["id"])
        pending = list_conflicts(day)
        self.assertEqual(len(pending), 1)
        resolve_conflict(pending[0]["id"], "KEEP_MANUAL")
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 130)
        disconnect(device["id"], delete_history=True)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 80)
        self.assertEqual(list_conflicts(day), [])

    def test_legacy_same_provider_connections_do_not_double_count_stable_sample_ids(self):
        self._onboard()
        day = today()
        def at(hour: int, minute: int = 0) -> str:
            return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+08:00").astimezone(
                timezone.utc).isoformat(timespec="seconds")
        create_workout({"local_date": day, "workout_type": "walking", "minutes": 60,
                        "kcal": 80, "start_at": at(10), "end_at": at(11)})
        old = connect_device({"provider": "manual_device_import"})
        def samples(energy: int, steps: int, heart: int) -> list[dict]:
            return [
                {"external_id": "same-energy", "sample_type": "active_energy",
                 "local_date": day, "value": energy, "start_at": at(10, 30), "end_at": at(11, 30)},
                {"external_id": "same-steps", "sample_type": "steps",
                 "local_date": day, "value": steps, "start_at": at(11)},
                {"external_id": "same-heart", "sample_type": "heart_rate",
                 "local_date": day, "value": heart, "start_at": at(11)},
            ]
        import_samples(old["id"], {"samples": samples(100, 1000, 75)})
        disconnect(old["id"])
        newer_id = new_id()
        with transaction() as db:
            db.execute("""INSERT INTO device_connections(id,user_id,provider,status)
                VALUES (?,'local-user','manual_device_import','ACTIVE')""", (newer_id,))
        import_samples(newer_id, {"samples": samples(120, 1100, 80)})
        summary = day_summary(day)
        self.assertEqual(summary["device_activity_kcal"], 120)
        self.assertEqual(summary["steps"], 1100)
        self.assertEqual(summary["heart_rate_bpm"], 80)
        self.assertEqual(len(list_conflicts(day)), 1)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM device_samples").fetchone()[0], 6)
        disconnect(newer_id, delete_history=True)
        summary = day_summary(day)
        self.assertEqual(summary["device_activity_kcal"], 100)
        self.assertEqual(summary["steps"], 1000)
        self.assertEqual(summary["heart_rate_bpm"], 75)
        self.assertEqual(len(list_conflicts(day)), 1)

    def test_legacy_sample_date_correction_does_not_leave_old_day_copy(self):
        self._onboard()
        old_day = (date.fromisoformat(today()) - timedelta(days=1)).isoformat()
        new_day = today()
        with transaction() as db:
            db.execute("UPDATE nutrition_targets SET effective_from=? WHERE user_id='local-user'",
                       (old_day,))
        old = connect_device({"provider": "manual_device_import"})
        import_samples(old["id"], {"samples": [{
            "external_id": "moved-source-id", "sample_type": "active_energy",
            "local_date": old_day, "value": 1000}]})
        disconnect(old["id"])
        original_expenditure = energy_series(old_day, old_day)["series"][0]["expenditure_kcal"]
        newer_id = new_id()
        with transaction() as db:
            db.execute("""INSERT INTO device_connections(id,user_id,provider,status)
                VALUES (?,'local-user','manual_device_import','ACTIVE')""", (newer_id,))
        import_samples(newer_id, {"samples": [{
            "external_id": "moved-source-id", "sample_type": "active_energy",
            "local_date": new_day, "value": 1200}]})
        self.assertEqual(day_summary(old_day)["device_activity_kcal"], 0)
        self.assertEqual(day_summary(new_day)["device_activity_kcal"], 1200)
        self.assertLess(energy_series(old_day, old_day)["series"][0]["expenditure_kcal"],
                        original_expenditure)
        disconnect(newer_id, delete_history=True)
        self.assertEqual(day_summary(old_day)["device_activity_kcal"], 1000)
        self.assertEqual(energy_series(old_day, old_day)["series"][0]["expenditure_kcal"],
                         original_expenditure)

    def test_official_plan_v2_details_and_advanced_training_phases(self):
        plans = list_plans()
        self.assertEqual(len(plans), 6)
        for plan in plans:
            self.assertEqual(plan["version"], 2)
            for field in ("suitability", "contraindications", "warmup", "cooldown",
                          "progression_rule", "completion_rule"):
                self.assertTrue(plan[field], (plan["code"], field))
            self.assertGreaterEqual(plan["estimated_minutes"], 25)
            self.assertGreaterEqual(len(plan["alternatives"]), 3)
            self.assertEqual(len(plan["days"]), plan["days_per_week"])
        self.assertEqual(len(json.loads(plans[0]["days"][0]["session_template_json"])), 5)
        with connect() as db:
            rows = db.execute("""SELECT week_no,title,session_template_json FROM plan_days
                WHERE plan_id='PLAN-05' AND day_no=1 ORDER BY week_no""").fetchall()
        self.assertEqual(len(rows), 9)
        self.assertTrue(rows[0]["title"].startswith("积累"))
        self.assertIn("深蹲 4×5", rows[0]["session_template_json"])
        self.assertTrue(rows[4]["title"].startswith("强化"))
        self.assertIn("深蹲 4×3", rows[4]["session_template_json"])
        self.assertTrue(rows[7]["title"].startswith("减量"))
        self.assertIn("深蹲 2×5", rows[7]["session_template_json"])
        self.assertTrue(rows[8]["title"].startswith("技术测试"))
        self.assertIn("深蹲 3×1", rows[8]["session_template_json"])

    def test_plan_catalog_upgrade_preserves_existing_enrollment_snapshot(self):
        enrollment = enroll("PLAN-03", today())
        session = active_plan(today())["today_session"]
        old_template = '["卧推 4×6-8","划船 4×8-10","侧平举 3×15"]'
        with transaction() as db:
            db.execute("UPDATE training_plans SET version=1 WHERE id='PLAN-03'")
            db.execute("UPDATE plan_days SET session_template_json=? WHERE id='PLAN-03-1-1'",
                       (old_template,))
            db.execute("UPDATE user_plan_enrollments SET plan_version=1 WHERE id=?", (enrollment["id"],))
            db.execute("UPDATE plan_session_instances SET template_json=? WHERE id=?",
                       (old_template, session["id"]))
        seed()
        self.assertEqual(next(p for p in list_plans() if p["code"] == "PLAN-03")["version"], 2)
        with connect() as db:
            self.assertNotEqual(db.execute("SELECT session_template_json FROM plan_days WHERE id='PLAN-03-1-1'")
                                .fetchone()[0], old_template)
            self.assertEqual(db.execute("SELECT plan_version FROM user_plan_enrollments WHERE id=?",
                                        (enrollment["id"],)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT template_json FROM plan_session_instances WHERE id=?",
                                        (session["id"],)).fetchone()[0], old_template)
        with transaction() as db:
            db.execute("DELETE FROM plan_session_instances WHERE enrollment_id=?", (enrollment["id"],))
        regenerated = active_plan(today())
        self.assertEqual(regenerated["today_session"]["original_exercises"], json.loads(old_template))
        self.assertEqual(regenerated["plan_version"], 1)

    def test_post_workout_recovery_uses_saved_volume_and_live_nutrition_gaps(self):
        self._onboard()
        workout = create_workout({"workout_type": "strength", "minutes": 45,
            "sets": [{"exercise_name": "卧推", "weight_kg": 20, "reps": 6}]})
        before = day_summary(today())
        result = recovery_advice(workout["id"])
        self.assertEqual(result["source"], "rules-v1")
        self.assertEqual(result["summary"]["training_volume_kg"], 120)
        self.assertEqual(result["summary"]["minutes"], 45)
        self.assertEqual(result["evidence"]["protein_gap_g"],
                         round(before["target"]["protein_g"] - before["macros"]["protein_g"], 1))
        self.assertIn("protein", {entry["id"] for entry in result["advice"]})
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals").fetchone()[0], 0)
        create_meal({"meal_type": "lunch", "items": [
            {"display_name": "已吃餐", "amount": 1, "unit": "份", "kcal": 300,
             "protein_g": 30, "carb_g": 30, "fat_g": 5}]})
        revised = recovery_advice(workout["id"])
        self.assertAlmostEqual(revised["evidence"]["protein_gap_g"],
                               result["evidence"]["protein_gap_g"] - 30, delta=0.1)
        with patch("app.application.fitness.recovery.configured", return_value=True), \
             patch("app.application.fitness.recovery.invoke",
                   return_value={"advice_ids": ["water"]}):
            selected = recovery_advice(workout["id"])
        self.assertEqual(selected["source"], "agent-selected-v1")
        self.assertEqual([entry["id"] for entry in selected["advice"]], ["water"])
        with patch("app.application.fitness.recovery.configured", return_value=True), \
             patch("app.application.fitness.recovery.invoke",
                   return_value={"advice_ids": ["invented_dose"]}):
            rejected = recovery_advice(workout["id"])
        self.assertEqual(rejected["source"], "rules-v1")
        self.assertNotIn("invented_dose", {entry["id"] for entry in rejected["advice"]})

    def test_recovery_without_target_is_explicitly_not_personalized(self):
        workout = create_workout({"workout_type": "walking", "minutes": 20})
        result = recovery_advice(workout["id"])
        self.assertFalse(result["evidence"]["has_target"])
        self.assertIsNone(result["evidence"]["protein_gap_g"])
        self.assertEqual(result["advice"][0]["id"], "complete_profile")
        with self.assertRaises(ApiError) as missing:
            recovery_advice("0" * 32)
        self.assertEqual(missing.exception.status, 404)

    def test_goal_preview_is_read_only_and_confirmed_target_has_input_provenance(self):
        self._onboard()
        before = get_profile()
        with connect() as db:
            count = db.execute("SELECT COUNT(*) FROM nutrition_targets").fetchone()[0]
        preview = preview_goal({"goal_type": "muscle_gain"})
        self.assertTrue(preview["ready"])
        self.assertGreater(preview["proposed_target"]["target_kcal"],
                           before["target"]["kcal"])
        self.assertEqual(preview["current_target"]["id"], before["target"]["id"])
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM nutrition_targets").fetchone()[0], count)
        with self.assertRaises(ApiError) as conflict:
            set_goal({"goal_type": "muscle_gain", "preview_fingerprint": "stale"})
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(get_profile()["goal"]["goal_type"], "fat_loss")
        changed = set_goal({"goal_type": "muscle_gain",
                            "preview_fingerprint": preview["input_fingerprint"]})
        self.assertEqual(changed["target"]["kcal"],
                         preview["proposed_target"]["target_kcal"])
        self.assertEqual(changed["target"]["inputs"]["goal_type"], "muscle_gain")
        self.assertEqual(changed["target"]["inputs"]["weight_kg"], 72.5)
        self.assertEqual(changed["target"]["measurement_id"], before["measurement"]["id"])
        self.assertEqual(changed["target"]["profile_version"], before["profile"]["profile_version"])
        self.assertEqual(changed["target"]["goal_id"], changed["goal"]["id"])

    def test_goal_preview_expires_when_current_goal_changes(self):
        self._onboard()
        preview = preview_goal({"goal_type": "muscle_gain"})
        set_goal({"goal_type": "maintenance"})
        with self.assertRaises(ApiError) as stale:
            set_goal({"goal_type": "muscle_gain",
                      "preview_fingerprint": preview["input_fingerprint"]})
        self.assertEqual(stale.exception.status, 409)
        self.assertEqual(get_profile()["goal"]["goal_type"], "maintenance")

    def test_goal_and_target_change_roll_back_together_if_target_write_fails(self):
        self._onboard()
        before = get_profile()
        with patch("app.application.profile.service._persist_target", side_effect=RuntimeError("disk failure")):
            with self.assertRaises(RuntimeError):
                set_goal({"goal_type": "muscle_gain"})
        after = get_profile()
        self.assertEqual(after["goal"]["id"], before["goal"]["id"])
        self.assertEqual(after["target"]["id"], before["target"]["id"])

    def test_goal_preview_blocks_switch_when_profile_incomplete_but_old_target_exists(self):
        self._onboard()
        old_goal = get_profile()["goal"]["id"]
        with self.assertRaises(ApiError):
            update_profile({"birth_date": None})
        with connect() as db:
            db.execute("UPDATE profiles SET birth_date=NULL WHERE user_id='local-user'")
            db.commit()
        preview = preview_goal({"goal_type": "muscle_gain"})
        self.assertFalse(preview["can_activate"])
        with self.assertRaises(ApiError):
            set_goal({"goal_type": "muscle_gain",
                      "preview_fingerprint": preview["input_fingerprint"]})
        self.assertEqual(get_profile()["goal"]["id"], old_goal)

    def test_workout_preview_matches_saved_ledger_and_training_goal(self):
        self._onboard()
        set_training_profile({"level": "beginner", "days_per_week": 3,
                              "session_minutes": 45, "active_kcal_goal": 450})
        request = {"workout_type": "walking", "intensity": "high", "minutes": 30}
        preview = estimate_workout(request)
        self.assertEqual(preview["weight_kg"], 72.5)
        self.assertEqual(preview["weight_source"], "measurement")
        self.assertEqual(preview["met_value"], 5.0)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0], 0)
        workout = create_workout(request)
        self.assertEqual(workout["kcal"], preview["kcal"])
        self.assertEqual(workout["calculation_version"], preview["calculation_version"])
        self.assertEqual(workout["intensity"], "high")
        self.assertEqual(day_summary(today())["activity_goal_kcal"], 450)
        self.assertEqual(day_summary(today())["workout_minutes"], 30)
        custom = create_workout({"workout_type": "custom", "custom_name": "搬箱子",
                                 "minutes": 20, "kcal": 125})
        self.assertEqual((custom["kcal_source"], custom["calculation_version"]),
                         ("MANUAL", "manual-v1"))
        with self.assertRaises(ApiError):
            estimate_workout({"workout_type": "walking", "intensity": "unknown", "minutes": 30})

    def test_device_manual_overlap_conflict_resolution_and_cache_invalidation(self):
        self._onboard()
        day = today()
        def at(hour: int, minute: int = 0) -> str:
            return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+08:00").astimezone(
                timezone.utc).isoformat(timespec="seconds")
        workout = create_workout({"local_date": day, "workout_type": "walking", "minutes": 60,
                                  "kcal": 80, "start_at": at(10), "end_at": at(11)})
        device = connect_device({"provider": "manual_device_import"})
        sample = {"external_id": "timed-activity-1", "sample_type": "active_energy",
                  "local_date": day, "value": 100, "start_at": at(10, 30), "end_at": at(11, 30)}
        imported = import_samples(device["id"], {"samples": [sample]})
        self.assertEqual((imported["imported"], imported["pending_conflicts"]), (1, 1))
        self.assertEqual(import_samples(device["id"], {"samples": [sample]})["duplicates"], 1)
        summary = day_summary(day)
        self.assertEqual(summary["energy"]["activity_kcal"], 140)
        self.assertEqual((summary["activity_source"], summary["activity_quality"]),
                         ("mixed", "time_window"))
        self.assertEqual(summary["pending_activity_conflicts"], 1)
        self.assertEqual(energy_series(day, day)["series"][0]["expenditure_kcal"],
                         summary["energy"]["total_expenditure_kcal"])
        conflict = list_conflicts(day)[0]
        self.assertEqual(conflict["domain_record_id"], workout["id"])
        self.assertEqual(conflict["overlap_seconds"], 1800)
        resolve_conflict(conflict["id"], "KEEP_MANUAL")
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 130)
        resolve_conflict(conflict["id"], "KEEP_DEVICE")
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 100)
        resolve_conflict(conflict["id"], "MERGE_NON_OVERLAPPING")
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 140)
        self.assertEqual(list_conflicts(day), [])
        moved = dict(sample, start_at=at(12), end_at=at(13))
        self.assertEqual(import_samples(device["id"], {"samples": [moved]})["updated"], 1)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 180)
        self.assertEqual(list_conflicts(day), [])
        self.assertEqual(list_conflicts(day, include_resolved=True)[0]["resolution"], "NO_LONGER_OVERLAPS")
        from app.application.fitness.device import disconnect
        disconnect(device["id"])
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 180)
        disconnect(device["id"], delete_history=True)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 80)

    def test_health_connect_stages_granular_energy_until_final_batch(self):
        self._onboard()
        day = today()
        def at(hour: int, minute: int = 0) -> str:
            return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+08:00").astimezone(
                timezone.utc).isoformat(timespec="seconds")
        create_workout({"local_date": day, "workout_type": "walking", "minutes": 60,
                        "kcal": 80, "start_at": at(10), "end_at": at(11)})
        device = connect_device({"provider": "health_connect"})
        coarse = {"external_id": f"hc-active-{day}", "sample_type": "active_energy",
                  "local_date": day, "start_at": at(0), "value": 300}
        import_samples(device["id"], {"samples": [coarse]})
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 300)
        self.assertEqual(day_summary(day)["activity_quality"], "daily_fallback")
        granular = {"external_id": f"hc-energy-one-{day}", "sample_type": "active_energy",
                    "local_date": day, "start_at": at(10, 30), "end_at": at(11, 30), "value": 100}
        staged = import_samples(device["id"], {"samples": [granular],
            "sync_batch_id": "batch-one", "stage_active_energy": True})
        self.assertEqual(staged["pending_conflicts"], 0)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 300)
        import_samples(device["id"], {"samples": [], "sync_batch_id": "batch-one",
                                      "activate_active_dates": [day]})
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 140)
        self.assertEqual(len(list_conflicts(day)), 1)
        with connect() as db:
            rows = {row["external_id"]: row["pending_activation"] for row in db.execute(
                "SELECT external_id,pending_activation FROM device_samples")}
        self.assertEqual((rows[coarse["external_id"]], rows[granular["external_id"]]), (2, 0))
        # A later full sync without this record must remove the stale device energy.
        import_samples(device["id"], {"samples": [], "sync_batch_id": "batch-two",
                                      "activate_active_dates": [day]})
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 80)
        self.assertEqual(list_conflicts(day), [])

    def test_conflicts_follow_selected_provider_and_coarse_quality(self):
        self._onboard()
        day = today()
        def at(hour: int, minute: int = 0) -> str:
            return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+08:00").astimezone(
                timezone.utc).isoformat(timespec="seconds")
        create_workout({"local_date": day, "workout_type": "walking", "minutes": 60,
                        "kcal": 80, "start_at": at(10), "end_at": at(11)})
        granular_provider = connect_device({"provider": "manual_device_import"})
        import_samples(granular_provider["id"], {"samples": [{
            "external_id": "granular", "sample_type": "active_energy", "local_date": day,
            "value": 100, "start_at": at(10, 30), "end_at": at(11, 30)}]})
        self.assertEqual(len(list_conflicts(day)), 1)
        coarse_provider = connect_device({"provider": "apple_health"})
        import_samples(coarse_provider["id"], {"samples": [{
            "external_id": "coarse", "sample_type": "active_energy", "local_date": day,
            "value": 200, "start_at": at(0)}]})
        self.assertEqual(list_conflicts(day), [])
        self.assertEqual(day_summary(day)["activity_quality"], "daily_fallback")
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 200)
        from app.application.fitness.device import disconnect
        disconnect(coarse_provider["id"])
        self.assertEqual(len(list_conflicts(day)), 0)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 200)
        disconnect(coarse_provider["id"], delete_history=True)
        self.assertEqual(len(list_conflicts(day)), 1)
        self.assertEqual(day_summary(day)["energy"]["activity_kcal"], 140)

    def test_no_profile_does_not_fabricate_energy_balance(self):
        point = energy_series(today(), today())["series"][0]
        self.assertEqual(point["target_days"], 0)
        self.assertIsNone(point["net_kcal"])
        self.assertIsNone(point["expenditure_kcal"])

    def test_batched_energy_series_matches_daily_ledger_across_sources(self):
        self._onboard()
        start, middle, end = "2026-09-30", "2026-10-01", "2026-10-02"
        with connect() as db:
            db.execute("UPDATE nutrition_targets SET effective_from=? WHERE user_id='local-user'", (start,))
            db.execute("""INSERT INTO nutrition_targets(id,user_id,effective_from,kcal,bmr_kcal,
                tdee_kcal,carb_g,protein_g,fat_g,algorithm_version)
                SELECT ?,user_id,?,kcal,bmr_kcal+50,tdee_kcal+50,carb_g,protein_g,fat_g,
                algorithm_version FROM nutrition_targets WHERE user_id='local-user' LIMIT 1""",
                (new_id(), end))
            db.commit()
        create_meal({"local_date": start, "meal_type": "breakfast", "status": "CONSUMED",
                     "items": [{"display_name": "早餐", "amount": 100, "unit": "g", "kcal": 120.04}]}, None)
        create_meal({"local_date": middle, "meal_type": "lunch", "status": "PLANNED",
                     "items": [{"display_name": "未吃午餐", "amount": 1, "unit": "份", "kcal": 900}]}, None)
        removed = create_meal({"local_date": middle, "meal_type": "dinner", "status": "CONSUMED",
                               "items": [{"display_name": "已删除", "amount": 1, "unit": "份", "kcal": 300}]}, None)
        delete_meal(removed["id"])
        add_water({"local_date": middle, "amount_ml": 250})
        create_workout({"local_date": middle, "workout_type": "strength", "minutes": 30,
                        "sets": [{"exercise_name": "深蹲", "set_no": 1, "weight_kg": 40, "reps": 10}]})
        for provider, kcal in (("health_connect", 350), ("manual_device_import", 220)):
            connection = connect_device({"provider": provider})
            import_samples(connection["id"], {"samples": [{"external_id": new_id(),
                "sample_type": "active_energy", "local_date": end, "value": kcal}]})
        series = energy_series(start, end)["series"]
        self.assertEqual(len(series), 3)
        for point in series:
            day = day_summary(point["period"])
            self.assertEqual(point["intake_kcal"], day["energy"]["intake_kcal"])
            self.assertEqual(point["expenditure_kcal"], day["energy"]["total_expenditure_kcal"])
            self.assertEqual(point["net_kcal"], day["energy"]["net_kcal"])
            self.assertEqual(point["bmr_kcal"], day["target"]["bmr_kcal"])
            self.assertEqual(point["tdee_kcal"], day["target"]["tdee_kcal"])
            self.assertEqual(point["training_volume"], day["training_volume"])
            self.assertEqual(point["water_ml"], day["water_ml"])
        self.assertEqual(series[0]["intake_kcal"], 120.0)
        self.assertEqual(series[1]["intake_kcal"], 0)
        self.assertEqual(series[1]["training_volume"], 400)
        self.assertEqual(series[2]["target_days"], 1)
        months = energy_series(start, end, "month")["series"]
        self.assertEqual([point["period"] for point in months], ["2026-09", "2026-10"])
        self.assertEqual(sum(point["intake_kcal"] for point in months), 120.0)

    def test_energy_cache_evicts_only_affected_days_and_refreshes(self):
        self._onboard()
        current = date.fromisoformat(today())
        previous, day, following = ((current - timedelta(days=1)).isoformat(),
                                    current.isoformat(), (current + timedelta(days=1)).isoformat())
        def cached_days():
            with connect() as db:
                return [row[0] for row in db.execute("""SELECT local_date FROM daily_energy_snapshots
                    WHERE user_id='local-user' ORDER BY local_date""")]
        all_days = [previous, day, following]
        energy_series(previous, following)
        self.assertEqual(cached_days(), all_days)
        meal = create_meal({"local_date": previous, "meal_type": "breakfast", "status": "CONSUMED",
                            "items": [{"display_name": "测试早餐", "amount": 1, "unit": "份", "kcal": 100}]})
        self.assertEqual(cached_days(), [day, following])
        self.assertEqual(energy_series(previous, following)["series"][0]["intake_kcal"], 100)
        with connect() as db:
            db.execute("UPDATE meal_items SET kcal=150 WHERE meal_id=?", (meal["id"],))
            db.commit()
        self.assertEqual(cached_days(), [day, following])
        self.assertEqual(energy_series(previous, following)["series"][0]["intake_kcal"], 150)
        add_water({"local_date": following, "amount_ml": 250})
        self.assertEqual(cached_days(), [previous, day])
        energy_series(previous, following)
        workout = create_workout({"local_date": day, "workout_type": "strength", "minutes": 30,
                                  "sets": [{"exercise_name": "深蹲", "set_no": 1,
                                            "weight_kg": 30, "reps": 10}]})
        self.assertEqual(cached_days(), [previous, following])
        energy_series(previous, following)
        with connect() as db:
            db.execute("UPDATE exercise_sets SET volume=500 WHERE session_id=?", (workout["id"],))
            db.commit()
        self.assertEqual(cached_days(), [previous, following])
        self.assertEqual(energy_series(previous, following)["series"][1]["training_volume"], 500)
        connection = connect_device({"provider": "health_connect"})
        import_samples(connection["id"], {"sync_cursor": "cursor-1", "samples": [
            {"external_id": "cache-device-1", "sample_type": "active_energy",
             "local_date": previous, "value": 280}]})
        self.assertEqual(cached_days(), [day, following])
        energy_series(previous, following)
        with connect() as db:
            db.execute("UPDATE device_samples SET local_date=? WHERE external_id='cache-device-1'",
                       (following,))
            db.commit()
        self.assertEqual(cached_days(), [day])
        energy_series(previous, following)
        with self.assertRaises(RuntimeError):
            with transaction() as db:
                db.execute("UPDATE device_samples SET value=999 WHERE external_id='cache-device-1'")
                raise RuntimeError("rollback test")
        self.assertEqual(cached_days(), all_days)
        with connect() as db:
            db.execute("UPDATE nutrition_targets SET effective_from=? WHERE user_id='local-user'", (previous,))
            db.commit()
        self.assertEqual(cached_days(), [])
        self.assertEqual(energy_series(previous, following)["series"][0]["target_days"], 1)
        with connect() as db:
            db.execute("UPDATE device_connections SET status='REVOKED' WHERE id=?", (connection["id"],))
            db.commit()
        self.assertEqual(cached_days(), [])
        energy_series(previous, following)
        with connect() as db:
            db.execute("DELETE FROM nutrition_targets WHERE user_id='local-user'")
            db.commit()
        self.assertEqual(cached_days(), [])
        self.assertEqual(energy_series(previous, following)["series"][0]["target_days"], 0)

    def test_meal_plan_and_energy(self):
        self._onboard()
        day = today()
        planned = create_meal({"local_date": day, "meal_type": "lunch", "status": "PLANNED",
                               "items": [{"display_name": "测试餐", "amount": 100, "unit": "g", "kcal": 300}]},
                              "same-key")
        repeated = create_meal({"local_date": day, "meal_type": "lunch", "items": [
            {"display_name": "不同餐", "amount": 100, "unit": "g", "kcal": 900}]}, "same-key")
        self.assertEqual(planned["id"], repeated["id"])
        self.assertEqual(day_summary(day)["energy"]["intake_kcal"], 0)
        update_meal(planned["id"], {"status": "CONSUMED"})
        self.assertEqual(day_summary(day)["energy"]["intake_kcal"], 300)
        self.assertEqual(energy_series(day, day)["series"][0]["intake_kcal"], 300)
        self.assertGreater(energy_series(day, day)["series"][0]["bmr_kcal"], 0)
        delete_meal(planned["id"])
        self.assertEqual(day_summary(day)["energy"]["intake_kcal"], 0)
        restore_meal(planned["id"])
        self.assertEqual(day_summary(day)["energy"]["intake_kcal"], 300)
        add_water({"local_date": day, "amount_ml": 500})
        self.assertEqual(set_water_total(day, {"total_ml": 250})["total_ml"], 250)
        self.assertEqual(day_summary(day)["water_ml"], 250)
        set_water_total(day, {"total_ml": 0})
        self.assertEqual(day_summary(day)["water_ml"], 0)

    def test_frequent_foods_use_only_consumed_latest_portions(self):
        day = today()
        for kcal in (116, 174):
            create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                         "items": [{"food_id": "rice", "display_name": "米饭", "amount": kcal / 1.16,
                                    "unit": "g", "grams": kcal / 1.16, "kcal": kcal}]})
        create_meal({"local_date": day, "meal_type": "dinner", "status": "PLANNED",
                     "items": [{"display_name": "未吃套餐", "amount": 1, "unit": "份", "kcal": 999}]})
        removed = create_meal({"local_date": day, "meal_type": "snack", "status": "CONSUMED",
                               "items": [{"display_name": "已删除食物", "amount": 1, "unit": "个", "kcal": 80}]})
        delete_meal(removed["id"])
        portion = create_meal({"local_date": day, "meal_type": "dinner", "status": "CONSUMED",
                               "items": [{"display_name": "自制汤", "amount": 1, "unit": "份", "kcal": 180}]})
        self.assertIsNone(portion["items"][0]["grams"])
        result = frequent_foods()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["display_name"], "米饭")
        self.assertEqual(result[0]["use_count"], 2)
        self.assertEqual(result[0]["kcal"], 174)
        self.assertEqual(result[1]["unit"], "份")
        self.assertIsNone(result[1]["grams"])

    def test_macro_summary_uses_only_consumed_items_and_effective_target(self):
        self._onboard()
        day = today()
        create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                     "items": [{"display_name": "米饭", "amount": 100, "unit": "g",
                                "kcal": 116, "carb_g": 25.9, "protein_g": 2.6, "fat_g": 0.3}]}, None)
        create_meal({"local_date": day, "meal_type": "dinner", "status": "PLANNED",
                     "items": [{"display_name": "未吃套餐", "amount": 1, "unit": "份", "kcal": 900}]}, None)
        result = macro_summary(day, day)
        self.assertEqual(result["actual"]["carb_g"], 25.9)
        self.assertEqual(result["intake_kcal"], 116)
        self.assertEqual(result["incomplete_items"], 0)
        self.assertEqual(result["target_days"], 1)
        self.assertGreater(result["target"]["protein_g"], 0)

    def test_missing_macro_fields_remain_unknown_across_edit_and_frequent_foods(self):
        self._onboard()
        day = today()
        meal = create_meal({"local_date": day, "meal_type": "lunch", "items": [
            {"display_name": "部分已知餐", "amount": 1, "unit": "份", "kcal": 250,
             "carb_g": 0, "protein_g": 20}]})
        self.assertEqual(meal["items"][0]["nutrient_known_mask"], 3)
        self.assertEqual(day_summary(day)["incomplete_macro_items"], 1)
        self.assertEqual(macro_summary(day, day)["incomplete_items"], 1)
        self.assertEqual(frequent_foods()[0]["nutrient_known_mask"], 3)
        round_trip = update_meal(meal["id"], {"items": meal["items"]})
        self.assertEqual(round_trip["items"][0]["nutrient_known_mask"], 3)
        updated = update_meal(meal["id"], {"items": [
            {"display_name": "部分已知餐", "amount": 1, "unit": "份", "kcal": 250,
             "carb_g": 0, "protein_g": 20, "fat_g": 0, "fiber_g": None}]})
        self.assertEqual(updated["items"][0]["nutrient_known_mask"], 7)
        self.assertEqual(day_summary(day)["incomplete_macro_items"], 0)
        self.assertEqual(macro_summary(day, day)["incomplete_items"], 0)
        self.assertEqual(updated["items"][0]["fiber_g"], 0)

    def test_macro_snapshot_keeps_raw_precision_until_period_sum(self):
        days = ["2026-09-30", "2026-10-01", "2026-10-02"]
        meals = [create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                              "items": [{"display_name": "微量样本", "amount": 1, "unit": "g",
                                         "kcal": 0.04, "carb_g": 0.04,
                                         "protein_g": 0.04, "fat_g": 0.04}]}) for day in days]
        result = macro_summary(days[0], days[-1])
        self.assertEqual(result["intake_kcal"], 0.1)
        self.assertEqual(energy_series(days[0], days[-1], "year")["series"][0]["intake_kcal"], 0.1)
        self.assertEqual(result["actual"], {"carb_g": 0.1, "protein_g": 0.1, "fat_g": 0.1})
        with connect() as db:
            raw = db.execute("SELECT macro_json FROM daily_energy_snapshots WHERE local_date=?",
                             (days[0],)).fetchone()[0]
            self.assertIn('"carb_g":0.04', raw)
            db.execute("UPDATE meal_items SET carb_g=0.24 WHERE meal_id=?", (meals[0]["id"],))
            db.commit()
        self.assertEqual(macro_summary(days[0], days[-1])["actual"]["carb_g"], 0.3)

    def test_energy_period_sum_uses_raw_daily_net(self):
        days = ["2026-10-01", "2026-10-02"]
        with connect() as db:
            db.execute("""INSERT INTO nutrition_targets(id,user_id,effective_from,kcal,bmr_kcal,
                tdee_kcal,carb_g,protein_g,fat_g,algorithm_version)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (new_id(), "local-user", days[0], 200, 80, 100.04, 20, 10, 10, "precision-test"))
            db.commit()
        for day in days:
            create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                         "items": [{"display_name": "精度样本", "amount": 1, "unit": "份",
                                    "kcal": 100.08}]})
            self.assertEqual(day_summary(day)["energy"]["net_kcal"], 0.0)
        period = energy_series(days[0], days[-1], "year")["series"][0]
        self.assertEqual(period["intake_kcal"], 200.2)
        self.assertEqual(period["net_kcal"], 0.1)

    def test_today_only_diagnosis_does_not_treat_partial_day_as_final_deficit(self):
        self._onboard()
        result = rule_diagnosis(today(), today())
        self.assertTrue(any("尚未结束" in text for text in result["observations"]))
        self.assertTrue(any("暂不" in text for text in result["advice"]))
        self.assertFalse(any("估算赤字较大" in text for text in result["advice"]))

    def test_diagnosis_versions_preserve_snapshot_and_citations(self):
        self._onboard()
        day = today()
        first = generate_diagnosis(day, day)
        create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                     "items": [{"display_name": "午餐", "amount": 1, "unit": "份", "kcal": 420}]}, None)
        second = generate_diagnosis(day, day)
        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertNotEqual(first["input_hash"], second["input_hash"])
        history = diagnosis_history(day, day)["items"]
        self.assertEqual([item["version"] for item in history], [2, 1])
        self.assertEqual(history[0]["input_hash"], second["input_hash"])
        self.assertTrue(history[0]["advice_details"][0]["evidence_refs"])
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM diagnostic_reports").fetchone()[0], 2)

    def test_agent_advice_requires_real_period_metric_references(self):
        self._onboard()
        day = today()
        invalid = {"observations": ["测试观察"], "advice": [
            {"text": "不受支持的建议", "evidence_refs": [{"period": day, "metric": "invented"}]}]}
        valid = {"observations": ["测试观察"], "advice": [
            {"text": "检查今日饮水记录", "evidence_refs": [{"period": day, "metric": "water_ml"}]}],
            "confidence": 0.8, "model": "demo-model-v2"}
        with patch("app.application.analytics.service.configured", return_value=True):
            with patch("app.application.analytics.service.invoke", return_value=invalid):
                self.assertEqual(generate_diagnosis(day, day)["source"], "rules-v1")
            with patch("app.application.analytics.service.invoke", return_value=valid):
                result = generate_diagnosis(day, day)
        self.assertEqual(result["source"], "agent-v1")
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["model_name"], "demo-model-v2")
        self.assertEqual(result["advice_details"][0]["evidence_refs"][0]["value"], 0)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 1)

    def test_allergy_recommendation_and_six_plans(self):
        self._onboard()
        for scenario in ("self_cook", "takeout", "dine_in", "convenience"):
            self.assertGreaterEqual(len(recommend({"meal_type": "dinner", "scenario": scenario})["items"]), 3)
        set_preferences({"allergies": ["milk", "egg", "fish", "soy"],
                         "restrictions": [], "preferences": []})
        result = recommend({"meal_type": "dinner"})
        self.assertGreaterEqual(len(result["items"]), 1)
        forbidden = {"r2", "r3", "r4", "r5"}
        self.assertFalse({x["candidate_ref_id"] for x in result["items"]} & forbidden)
        accepted = accept(result["items"][0]["id"], servings=1.5)
        self.assertEqual(accepted["status"], "PLANNED")
        planned = get_meal(accepted["meal_id"])
        self.assertAlmostEqual(sum(item["kcal"] for item in planned["items"]),
                               result["items"][0]["nutrition"]["kcal"] * 1.5, delta=1)
        self.assertEqual(len(list_plans()), 6)
        enroll("PLAN-01")
        self.assertEqual(active_plan()["plan_id"], "PLAN-01")
        self.assertEqual(stop_active_plan()["status"], "STOPPED")
        self.assertIsNone(active_plan())

    def test_official_plan_filters_match_training_level_and_goal(self):
        self.assertEqual(len(list_plans()), 6)
        self.assertEqual([plan["code"] for plan in list_plans("beginner", "fat_loss")], ["PLAN-02"])
        self.assertEqual([plan["code"] for plan in list_plans("advanced", "muscle_gain")], ["PLAN-05"])
        self.assertEqual([plan["code"] for plan in list_plans(goal_type="recovery")], ["PLAN-06"])
        self.assertEqual(list_plans("advanced", "recovery"), [])
        with self.assertRaises(ApiError):
            list_plans("expert")
        with self.assertRaises(ApiError):
            list_plans(goal_type="medical_rehab")

    def test_recipe_detail_nutrition_matches_recommendation_and_scaled_meal(self):
        self._onboard()
        item = recommend({"meal_type": "dinner", "scenario": "self_cook"})["items"][0]
        detail = recipe_detail(item["candidate_ref_id"])
        self.assertEqual(detail["nutrition_per_serving"], item["nutrition"])
        self.assertGreater(detail["nutrition_per_serving"]["fiber_g"], 0)
        self.assertAlmostEqual(sum(part["kcal"] * part["grams"] / 100
                                   for part in detail["ingredients"]),
                               detail["nutrition_per_serving"]["kcal"], delta=0.1)
        planned = get_meal(accept(item["id"], servings=1.5)["meal_id"])
        self.assertAlmostEqual(sum(part["kcal"] for part in planned["items"]),
                               detail["nutrition_per_serving"]["kcal"] * 1.5, delta=1)

    def test_self_cook_substitutions_are_verified_filtered_and_preview_only(self):
        self._onboard()
        detail = recipe_detail("r1")
        tofu = next(option for option in detail["substitutions"]
                    if option["original_food_id"] == "chicken" and
                    option["replacement_food_id"] == "tofu")
        self.assertGreater(tofu["grams_per_serving"], 0)
        self.assertAlmostEqual(tofu["nutrition_per_serving_if_used"]["kcal"],
                               detail["nutrition_per_serving"]["kcal"], delta=0.2)
        self.assertNotEqual(tofu["nutrition_per_serving_if_used"]["protein_g"],
                            detail["nutrition_per_serving"]["protein_g"])
        self.assertEqual(recipe_detail("r7")["substitutions"], [])
        with connect() as db:
            db.execute("""INSERT INTO food_items(id,name,kcal,verified)
                VALUES ('unverified_alt','未核验替代品',120,0)""")
            db.execute("""INSERT INTO food_substitutions(from_food_id,to_food_id,rank)
                VALUES ('chicken','unverified_alt',99)""")
            db.commit()
        self.assertNotIn("unverified_alt", {option["replacement_food_id"] for option in
                                            recipe_detail("r1")["substitutions"]})

        set_preferences({"allergies": ["soy"], "restrictions": [], "preferences": []})
        self.assertTrue(recipe_detail("r1")["matches_current_restrictions"])
        self.assertFalse(recipe_detail("r4")["matches_current_restrictions"])
        self.assertNotIn("tofu", {option["replacement_food_id"] for option in
                                   recipe_detail("r1")["substitutions"]})
        item = recommend({"scenario": "self_cook"})["items"][0]
        saved = get_meal(accept(item["id"])["meal_id"])
        recipe = recipe_detail(item["candidate_ref_id"])
        self.assertEqual({part["food_id"] for part in saved["items"]},
                         {part["food_id"] for part in recipe["ingredients"]})

    def test_allergen_aliases_are_canonical_and_unknowns_fail_closed(self):
        set_preferences({"allergies": ["花生", "milk", "牛奶"],
                         "restrictions": [], "preferences": []})
        self.assertEqual(set(get_profile()["allergies"]), {"peanut", "milk"})
        with self.assertRaises(ApiError):
            set_preferences({"allergies": ["未知过敏原"],
                             "restrictions": [], "preferences": []})
        self.assertEqual(set(get_profile()["allergies"]), {"peanut", "milk"})

    def test_ingredient_allergen_metadata_is_enforced_even_if_recipe_tag_is_missing(self):
        self._onboard()
        with connect() as db:
            db.execute("""INSERT INTO food_items(id,name,kcal,allergens_json,verified)
                VALUES ('test_sauce','测试花生酱',100,'[\"peanut\"]',1)""")
            db.execute("""INSERT INTO recipes(id,name,scenario,estimated_cost_cny,allergens_json)
                VALUES ('test_recipe','便利店测试蘸酱','convenience',10,'[]')""")
            db.execute("""INSERT INTO recipe_ingredients(recipe_id,food_id,amount,grams)
                VALUES ('test_recipe','test_sauce',100,100)""")
            db.commit()
        visible = recommend({"scenario": "convenience"})
        self.assertIn("test_recipe", {x["candidate_ref_id"] for x in visible["items"]})
        set_preferences({"allergies": ["花生"], "restrictions": [], "preferences": []})
        safe = recommend({"scenario": "convenience"})
        self.assertNotIn("test_recipe", {x["candidate_ref_id"] for x in safe["items"]})

    def test_dining_preferences_filter_cost_and_cooking_time(self):
        self._onboard()
        base = recommend({"meal_type": "dinner", "scenario": "self_cook"})
        self.assertGreaterEqual(len(base["items"]), 3)
        set_preferences({"allergies": [], "restrictions": [], "preferences": [],
                         "dining": {"max_cost_cny": 18, "max_cook_minutes": 20,
                                    "flavors": ["清淡"], "preferred_scenario": "self_cook"}})
        self.assertEqual(get_profile()["dining"]["max_cook_minutes"], 20)
        result = recommend({"meal_type": "dinner"})
        self.assertTrue(result["items"])
        self.assertTrue(all(x["estimated_cost_cny"] <= 18 and
                            x["prep_minutes"] + x["cook_minutes"] <= 20
                            for x in result["items"]))
        self.assertEqual(result["session"]["constraint_version"], "rules-v1")
        with self.assertRaises(ApiError):
            accept(result["items"][0]["id"], servings=2)
        set_preferences({"allergies": [], "restrictions": [], "preferences": [],
                         "dining": {"max_cost_cny": 1, "max_cook_minutes": 5,
                                    "flavors": [], "preferred_scenario": "self_cook"}})
        self.assertEqual(recommend({"meal_type": "dinner"})["items"], [])
        with self.assertRaises(ApiError):
            set_preferences({"allergies": [], "restrictions": [], "preferences": [],
                             "dining": {"max_cost_cny": 30, "flavors": ["未知口味"]}})
        self.assertEqual(get_profile()["dining"]["max_cost_cny"], 1)

    def test_recommendation_feedback_changes_future_rank_only_and_can_be_erased(self):
        self._onboard()
        initial = recommend({"meal_type": "dinner", "scenario": "takeout"})
        chosen = initial["items"][0]
        recipe_id = chosen["candidate_ref_id"]
        saved_score = chosen["score"]
        initial_context = json.loads(initial["session"]["context_snapshot_json"])
        self.assertTrue(initial_context["ranking_version"].startswith("recommend-v3-weighted-"))
        self.assertEqual(set(initial_context["scoring_weights"]), set(DEFAULT_WEIGHTS))
        self.assertEqual(set(initial_context["score_components"][recipe_id]), set(DEFAULT_WEIGHTS))
        self.assertEqual(submit_feedback(chosen["id"], "DISLIKE")["feedback_type"], "DISLIKE")
        changed = recommend({"meal_type": "dinner", "scenario": "takeout"})
        after = next(item for item in changed["items"] if item["candidate_ref_id"] == recipe_id)
        self.assertAlmostEqual(after["score"], saved_score - 5, delta=0.1)
        self.assertEqual(after["feedback_type"], "DISLIKE")
        self.assertEqual(get_recommendations(initial["session"]["id"])["items"][0]["score"], saved_score)
        self.assertNotIn(recipe_id, get_profile()["restrictions"])
        self.assertNotIn(recipe_id, get_profile()["allergies"])
        with patch("app.application.recommendation.service.configured", return_value=True), \
             patch("app.application.recommendation.service.invoke",
                   return_value={"recipe_ids": [recipe_id]}):
            agent_ordered = recommend({"meal_type": "dinner", "scenario": "takeout"})
        self.assertEqual(agent_ordered["session"]["constraint_version"], "agent-v1")
        self.assertNotEqual(agent_ordered["items"][0]["candidate_ref_id"], recipe_id)
        submit_feedback(chosen["id"], "REPEATED")
        repeated = recommend({"meal_type": "dinner", "scenario": "takeout"})
        self.assertEqual(next(item for item in repeated["items"] if item["candidate_ref_id"] == recipe_id)
                         ["score"], round(saved_score - 4, 1))
        submit_feedback(chosen["id"], "CLEAR")
        restored = recommend({"meal_type": "dinner", "scenario": "takeout"})
        self.assertEqual(next(item for item in restored["items"] if item["candidate_ref_id"] == recipe_id)
                         ["score"], saved_score)
        submit_feedback(chosen["id"], "UNSUITABLE")
        self.assertEqual(len(export_data("agent")["tables"]["recommendation_feedback"]), 1)
        self.assertEqual(deletion_preview("agent")["counts"]["recommendation_feedback"], 1)
        delete_data("agent", "DELETE_AGENT")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM recommendation_feedback").fetchone()[0], 0)

    def test_recommendation_retry_reports_live_status_and_delete_is_idempotent(self):
        self._onboard()
        item = recommend({"meal_type": "dinner", "scenario": "self_cook"})["items"][0]
        planned = accept(item["id"])
        self.assertEqual(planned["status"], "PLANNED")
        update_meal(planned["meal_id"], {"status": "CONSUMED"})
        self.assertEqual(accept(item["id"]), {"meal_id": planned["meal_id"], "status": "CONSUMED"})
        self.assertEqual(delete_meal(planned["meal_id"]),
                         {"id": planned["meal_id"], "deleted": True})
        self.assertEqual(delete_meal(planned["meal_id"]),
                         {"id": planned["meal_id"], "deleted": True})
        with connect() as db:
            self.assertEqual(db.execute("""SELECT COUNT(*) FROM outbox_events
                WHERE aggregate_id=? AND event_type='MealStatusChanged'""",
                (planned["meal_id"],)).fetchone()[0], 2)
        with self.assertRaises(ApiError) as removed:
            accept(item["id"])
        self.assertEqual((removed.exception.code, removed.exception.status),
                         ("ALREADY_REMOVED", 409))
        restore_meal(planned["meal_id"])
        self.assertEqual(accept(item["id"])["status"], "CONSUMED")

    def test_recently_planned_recipe_loses_diversity_points_without_changing_intake(self):
        self._onboard()
        first = recommend({"meal_type": "dinner", "scenario": "takeout"})
        chosen = first["items"][0]
        day = first["session"]["local_date"]
        before_intake = day_summary(day)["energy"]["intake_kcal"]
        accept(chosen["id"])
        second = recommend({"meal_type": "dinner", "scenario": "takeout"})
        revised = next(item for item in second["items"]
                       if item["candidate_ref_id"] == chosen["candidate_ref_id"])
        context = json.loads(second["session"]["context_snapshot_json"])
        self.assertEqual(context["recent_recipe_counts"][chosen["candidate_ref_id"]], 1)
        self.assertEqual(context["score_components"][chosen["candidate_ref_id"]]["diversity"], 70)
        self.assertAlmostEqual(revised["score"], chosen["score"] - 1.5, delta=0.1)
        self.assertEqual(day_summary(day)["energy"]["intake_kcal"], before_intake)

    def test_blind_box_draws_one_safe_recipe_and_records_pool_version(self):
        self._onboard()
        set_preferences({"allergies": ["fish"], "restrictions": [], "preferences": []})
        first = recommend({"meal_type": "dinner", "scenario": "self_cook", "shuffle": True})
        self.assertEqual(len(first["items"]), 1)
        initial_id = first["items"][0]["candidate_ref_id"]
        self.assertNotEqual(initial_id, "r2")
        first_context = json.loads(first["session"]["context_snapshot_json"])["blind_box"]
        self.assertEqual(first_context["drawn_recipe_id"], initial_id)
        self.assertGreater(first_context["candidate_count"], 1)
        self.assertEqual(len(first_context["candidate_pool"]), first_context["candidate_count"])
        self.assertNotIn("r2", {item["recipe_id"] for item in first_context["candidate_pool"]})
        self.assertEqual(len(first_context["pool_version"]), 16)
        second = recommend({"meal_type": "dinner", "scenario": "self_cook", "shuffle": True,
                            "avoid_recipe_id": initial_id})
        self.assertEqual(len(second["items"]), 1)
        self.assertNotEqual(second["items"][0]["candidate_ref_id"], initial_id)
        second_context = json.loads(second["session"]["context_snapshot_json"])["blind_box"]
        self.assertEqual(second_context["pool_version"], first_context["pool_version"])
        self.assertEqual(second_context["previous_recipe_id"], initial_id)
        self.assertEqual(get_recommendations(first["session"]["id"])["items"][0]["candidate_ref_id"],
                         initial_id)

    def test_recommendation_accept_rechecks_portion_and_current_day_budget(self):
        self._onboard()
        day = today()
        target = day_summary(day)["energy"]["target_kcal"]
        create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                     "items": [{"display_name": "已摄入", "amount": 1, "unit": "份",
                                "kcal": target - 600}]})
        recommendations = recommend({"local_date": day, "meal_type": "dinner",
                                     "scenario": "self_cook"})
        chicken = next(item for item in recommendations["items"]
                       if item["candidate_ref_id"] == "r1")
        self.assertLess(chicken["nutrition"]["kcal"], 700)
        with self.assertRaises(ApiError) as oversized:
            accept(chicken["id"], servings=2)
        self.assertEqual(oversized.exception.code, "HARD_CONSTRAINT_VIOLATION")
        create_meal({"local_date": day, "meal_type": "snack", "status": "CONSUMED",
                     "items": [{"display_name": "稍后摄入", "amount": 1, "unit": "份",
                                "kcal": 300}]})
        with self.assertRaises(ApiError) as stale:
            accept(chicken["id"], servings=1)
        self.assertEqual(stale.exception.code, "HARD_CONSTRAINT_VIOLATION")
        self.assertEqual(accept(chicken["id"], servings=0.5)["status"], "PLANNED")

    def test_workout_idempotency_and_energy(self):
        self._onboard()
        workout = create_workout({"workout_type": "strength", "minutes": 45,
                                  "sets": [{"exercise_name": "卧推", "set_no": 1,
                                            "weight_kg": 50, "reps": 8, "rpe": 8},
                                           {"exercise_name": "卧推", "set_no": 2,
                                            "weight_kg": 50, "reps": 8, "completed": False}]}, "workout-key")
        repeated = create_workout({"workout_type": "strength", "minutes": 45}, "workout-key")
        self.assertEqual(workout["id"], repeated["id"])
        self.assertEqual(workout["total_volume"], 400)
        self.assertIsNone(workout["sets"][1]["completed_at"])
        self.assertGreater(day_summary(today())["energy"]["activity_kcal"], 0)
        add_measurement({"weight_kg": 72.4, "body_fat_pct": 21.5})
        trend = body_composition_series(today(), today())["series"]
        self.assertEqual(trend[0]["weight_kg"], 72.4)
        self.assertEqual(trend[0]["body_fat_pct"], 21.5)
        self.assertEqual(trend[0]["training_volume_kg"], 400)

    def test_bodyweight_sets_keep_unknown_load_without_inventing_volume(self):
        self._onboard()
        workout = create_workout({"workout_type": "strength", "minutes": 30,
                                  "sets": [{"exercise_name": "俯卧撑", "set_no": 1,
                                            "weight_kg": None, "reps": 12, "rpe": 7},
                                           {"exercise_name": "哑铃卧推", "set_no": 1,
                                            "weight_kg": 10, "reps": 8}]})
        self.assertIsNone(workout["sets"][0]["weight_kg"])
        self.assertIsNotNone(workout["sets"][0]["completed_at"])
        self.assertEqual(workout["sets"][0]["volume"], 0)
        self.assertEqual(workout["total_volume"], 80)
        self.assertEqual(day_summary(today())["training_volume"], 80)
        enroll("PLAN-06", today())
        session = active_plan(today())["today_session"]
        followed = create_workout({"workout_type": "strength", "minutes": 30,
                                   "plan_session_id": session["id"],
                                   "sets": [{"exercise_name": name.rsplit(" ", 1)[0], "set_no": set_no,
                                             "weight_kg": None, "reps": int(name.rsplit("×", 1)[1])}
                                            for name in session["exercises"]
                                            for set_no in range(1, int(name.rsplit(" ", 1)[1].split("×")[0]) + 1)]})
        self.assertEqual(followed["total_volume"], 0)
        self.assertEqual(active_plan(today())["today_session"]["status"], "COMPLETED")
        with self.assertRaises(ApiError):
            create_workout({"workout_type": "strength", "minutes": 10,
                            "sets": [{"exercise_name": "俯卧撑", "reps": 0,
                                      "weight_kg": None, "completed": True}]})

    def test_plan_schedule_follow_progress_and_duplicate_guard(self):
        from datetime import date, timedelta
        start = today()
        joined = enroll("PLAN-03", start)
        plan = active_plan(start)
        self.assertEqual(plan["id"], joined["id"])
        self.assertEqual(plan["progress"], {"total": 32, "completed": 0, "partial": 0,
                                            "current_week": 1})
        first = plan["today_session"]
        self.assertEqual(first["title"], "上肢 A")
        self.assertEqual(first["exercises"][0], "卧推 4×6-8")
        self.assertEqual(plan["next_session"]["id"], first["id"])
        self.assertEqual(active_plan((date.fromisoformat(start) + timedelta(days=1)).isoformat())
                         ["today_session"]["title"], "下肢 A")
        self.assertIsNone(active_plan((date.fromisoformat(start) + timedelta(days=2)).isoformat())
                          ["today_session"])
        with self.assertRaises(ApiError):
            replace_plan_exercise(first["id"], {"index": 2, "replacement": "哑铃侧平举 3×12", "reason": ""})
        updated = replace_plan_exercise(first["id"], {"index": 2,
            "replacement": "哑铃侧平举 3×12", "reason": "家中只有哑铃"})
        self.assertEqual(updated["exercises"][2], "哑铃侧平举 3×12")
        self.assertEqual(updated["original_exercises"][2], "上斜哑铃推 3×10")
        self.assertEqual(updated["replacements"][0]["reason"], "家中只有哑铃")
        exported = export_data("fitness")["tables"]["plan_session_instances"]
        self.assertEqual(len(exported), 32)
        self.assertEqual(next(item for item in exported if item["id"] == first["id"])
                         ["overrides"][0]["reason"], "家中只有哑铃")
        with self.assertRaises(ApiError):
            create_workout({"local_date": start, "workout_type": "strength", "minutes": 20,
                "plan_session_id": first["id"],
                "sets": [{"exercise_name": "未说明的替代动作", "set_no": 1, "weight_kg": 5, "reps": 8}]})
        payload = {"local_date": start, "workout_type": "strength", "minutes": 45,
                   "plan_session_id": first["id"],
                   "sets": [{"exercise_name": "卧推", "set_no": 1, "weight_kg": 40, "reps": 8},
                            {"exercise_name": "划船", "set_no": 1, "weight_kg": 30, "reps": 10},
                            {"exercise_name": "哑铃侧平举", "set_no": 1, "weight_kg": 5, "reps": 12}]}
        workout = create_workout(payload, "plan-unique-key")
        self.assertEqual(workout["plan_instance_id"], joined["id"])
        self.assertEqual(workout["plan_session_title"], "上肢 A")
        self.assertEqual(workout["total_volume"], 680)
        self.assertEqual(create_workout(payload, "plan-unique-key")["id"], workout["id"])
        self.assertEqual(active_plan(start)["progress"]["completed"], 0)
        self.assertEqual(active_plan(start)["progress"]["partial"], 1)
        self.assertEqual(active_plan(start)["today_session"]["status"], "PARTIAL")
        with self.assertRaises(ApiError):
            replace_plan_exercise(first["id"], {"index": 0, "replacement": "器械推胸", "reason": "临时调整"})
        with self.assertRaises(ApiError):
            create_workout(payload, "different-key")
        with self.assertRaises(ApiError):
            create_workout({"workout_type": "walking", "minutes": 20,
                            "plan_instance_id": joined["id"]})
        self.assertEqual(list_plans()[2]["days"][0]["session_template_json"],
                         '["卧推 4×6-8","划船 4×8-10","上斜哑铃推 3×10","高位下拉 3×10","侧平举 3×15","臂屈伸 2×12"]')
        tomorrow = (date.fromisoformat(start) + timedelta(days=1)).isoformat()
        second = active_plan(tomorrow)["today_session"]
        complete_sets = []
        for name, count, reps in (("深蹲", 4, 8), ("罗马尼亚硬拉", 3, 8),
                                  ("腿举", 3, 12), ("腿弯举", 3, 12), ("提踵", 4, 12)):
            complete_sets += [{"exercise_name": name, "set_no": number,
                               "weight_kg": 20, "reps": reps} for number in range(1, count + 1)]
        complete = create_workout({"local_date": tomorrow, "workout_type": "strength",
                                   "minutes": 60, "plan_session_id": second["id"], "sets": complete_sets})
        self.assertEqual(complete["plan_session_id"], second["id"])
        self.assertEqual(active_plan(tomorrow)["today_session"]["status"], "COMPLETED")
        self.assertEqual(active_plan(tomorrow)["progress"]["completed"], 1)
        self.assertEqual(active_plan(tomorrow)["progress"]["partial"], 1)
        stop_active_plan()
        with self.assertRaises(ApiError):
            create_workout({"local_date": (date.fromisoformat(start) + timedelta(days=3)).isoformat(),
                            "workout_type": "strength", "minutes": 30,
                            "plan_session_id": plan["week_sessions"][2]["id"]})
        self.assertEqual(workout["id"], list_workouts(start)[0]["id"])
        self.assertEqual(deletion_preview("fitness")["counts"]["plan_session_instances"], 32)
        delete_data("fitness", "DELETE_FITNESS")
        self.assertEqual(export_data("fitness")["tables"]["plan_session_instances"], [])

    def test_all_six_official_plans_have_completable_first_day_and_cardio(self):
        import re
        from datetime import date, timedelta
        for plan in list_plans():
            enroll(plan["id"], today())
            first = active_plan(today())["today_session"]
            self.assertIsNotNone(first, plan["code"])
            sets = []
            for prescription in first["exercises"]:
                match = re.match(r"^(.*?)\s+(\d+)[×xX](\d+)(?:[-–]\d+)?.*$", prescription)
                name = match.group(1).strip() if match else prescription
                count = int(match.group(2)) if match else 1
                timed = prescription.rstrip().endswith("秒")
                for set_no in range(1, count + 1):
                    sets.append({"exercise_name": name, "set_no": set_no,
                                 "weight_kg": 10, "reps": 0 if timed else int(match.group(3)) if match else 8,
                                 **({"duration_sec": int(match.group(3))} if timed and match else {})})
            create_workout({"local_date": today(), "workout_type": "strength", "minutes": 45,
                            "plan_session_id": first["id"], "sets": sets})
            self.assertEqual(active_plan(today())["today_session"]["status"], "COMPLETED",
                             plan["code"])
        yesterday = (date.fromisoformat(today()) - timedelta(days=1)).isoformat()
        enroll("PLAN-02", yesterday)
        cardio = active_plan(today())["today_session"]
        self.assertEqual(cardio["title"], "有氧")
        self.assertEqual(cardio["minimum_duration_minutes"], 35)
        create_workout({"local_date": today(), "workout_type": "cycling", "minutes": 40,
                        "plan_session_id": cardio["id"]})
        self.assertEqual(active_plan(today())["today_session"]["status"], "COMPLETED")
        enroll("PLAN-02", yesterday)
        short_cardio = active_plan(today())["today_session"]
        create_workout({"local_date": today(), "workout_type": "cycling", "minutes": 10,
                        "plan_session_id": short_cardio["id"]})
        self.assertEqual(active_plan(today())["today_session"]["status"], "PARTIAL")
        interval_start = (date.fromisoformat(today()) - timedelta(days=5)).isoformat()
        enroll("PLAN-02", interval_start)
        interval = active_plan(today())["today_session"]
        self.assertEqual(interval["title"], "间歇")
        self.assertEqual(interval["minimum_duration_minutes"], 36)
        create_workout({"local_date": today(), "workout_type": "cycling", "minutes": 35,
                        "plan_session_id": interval["id"]})
        self.assertEqual(active_plan(today())["today_session"]["status"], "PARTIAL")
        enroll("PLAN-03", today())
        under_reps = active_plan(today())["today_session"]
        all_sets_but_one_rep = []
        for name, count in (("卧推", 4), ("划船", 4), ("侧平举", 3)):
            all_sets_but_one_rep += [{"exercise_name": name, "set_no": number,
                                      "weight_kg": 10, "reps": 1}
                                     for number in range(1, count + 1)]
        create_workout({"local_date": today(), "workout_type": "strength", "minutes": 40,
                        "plan_session_id": under_reps["id"], "sets": all_sets_but_one_rep})
        self.assertEqual(active_plan(today())["today_session"]["status"], "PARTIAL")

    def test_timed_sets_record_seconds_and_plan_completion_uses_seconds(self):
        timed = create_workout({"workout_type": "strength", "minutes": 15,
            "sets": [{"exercise_name": "平板支撑", "set_no": 1,
                      "weight_kg": 5, "reps": 0, "duration_sec": 30}]})
        self.assertEqual(timed["sets"][0]["duration_sec"], 30)
        self.assertEqual(timed["sets"][0]["reps"], 0)
        self.assertEqual(timed["total_volume"], 0)
        for bad in ({"reps": 0}, {"reps": 8, "duration_sec": 30},
                    {"reps": 0, "duration_sec": 12.5}):
            with self.assertRaises(ApiError):
                create_workout({"workout_type": "strength", "minutes": 15,
                    "sets": [{"exercise_name": "计时组", "set_no": 1, **bad}]})

        def planned_sets(plank_seconds):
            entries = []
            for name, count, amount in (("杯式深蹲", 3, 10), ("跪姿俯卧撑", 3, 8),
                                        ("坐姿划船", 3, 10), ("臀桥", 3, 12)):
                entries += [{"exercise_name": name, "set_no": number, "reps": amount}
                            for number in range(1, count + 1)]
            entries += [{"exercise_name": "平板支撑", "set_no": number, "reps": 0,
                         "duration_sec": plank_seconds} for number in range(1, 4)]
            return entries

        enroll("PLAN-01", today())
        first = active_plan(today())["today_session"]
        create_workout({"workout_type": "strength", "minutes": 40,
                        "plan_session_id": first["id"], "sets": planned_sets(10)})
        self.assertEqual(active_plan(today())["today_session"]["status"], "PARTIAL")
        enroll("PLAN-01", today())
        second = active_plan(today())["today_session"]
        create_workout({"workout_type": "strength", "minutes": 40,
                        "plan_session_id": second["id"], "sets": planned_sets(20)})
        self.assertEqual(active_plan(today())["today_session"]["status"], "COMPLETED")

    def test_photo_scan_requires_review_before_counting(self):
        self._onboard()
        image = encoded_jpeg("test-image-bytes")
        recognized = {"items": [{"name": "米饭", "estimated_grams": 150, "kcal": 174,
                                 "carb_g": 38, "protein_g": 4, "fat_g": 0.5,
                                 "confidence": 0.82}], "warnings": []}
        with patch("app.application.nutrition.scan.invoke", return_value=recognized):
            scan = create_scan({"image_base64": image, "mime_type": "image/jpeg"})
        self.assertEqual(scan["status"], "REVIEW_REQUIRED")
        self.assertEqual(day_summary(today())["energy"]["intake_kcal"], 0)
        with self.assertRaises(ApiError):
            confirm_scan(scan["id"], {"meal_type": "dinner", "items": []})
        self.assertEqual(get_scan(scan["id"])["status"], "REVIEW_REQUIRED")
        self.assertEqual(day_summary(today())["energy"]["intake_kcal"], 0)
        meal = confirm_scan(scan["id"], {"meal_type": "dinner"})
        self.assertEqual(meal["meal_type"], "dinner")
        self.assertEqual(day_summary(today())["energy"]["intake_kcal"], 174)
        self.assertEqual(confirm_scan(scan["id"], {"meal_type": "dinner"})["id"], meal["id"])
        with self.assertRaises(ApiError):
            create_scan({"image_base64": "not-base64!", "mime_type": "image/jpeg"})

    def test_photo_upload_decodes_real_image_and_never_forwards_original_metadata(self):
        source = image_bytes("metadata-photo")
        with Image.open(BytesIO(source)) as picture:
            exif = Image.Exif()
            exif[271] = "QA-camera"
            exif[274] = 6
            tagged = BytesIO()
            picture.save(tagged, format="JPEG", exif=exif)
        clean = clean_upload_image(tagged.getvalue(), "image/jpeg")
        self.assertNotEqual(clean, tagged.getvalue())
        with Image.open(BytesIO(clean)) as decoded:
            self.assertEqual(decoded.format, "JPEG")
            self.assertEqual(decoded.getexif().get(271), None)
            self.assertEqual(decoded.getexif().get(274), None)
        png = image_bytes("png-photo", "PNG")
        recognized = {"items": [{"name": "米饭", "estimated_grams": 100,
                                  "kcal": 116, "carb_g": 25.9, "protein_g": 2.6,
                                  "fat_g": 0.3, "confidence": 0.9}]}
        with patch("app.application.nutrition.scan.invoke", return_value=recognized) as agent:
            create_scan({"image_base64": base64.b64encode(png).decode("ascii"),
                         "mime_type": "image/png"})
        sent = agent.call_args.args[1]
        self.assertEqual(sent["mime_type"], "image/jpeg")
        with Image.open(BytesIO(base64.b64decode(sent["image_base64"]))) as decoded:
            self.assertEqual(decoded.format, "JPEG")

    def test_scan_review_uses_edited_items_and_marks_manual_macro_gaps(self):
        recognized = {"items": [{"name": "原识别食物", "estimated_grams": 100,
                                  "kcal": 100, "carb_g": 20, "protein_g": 3,
                                  "fat_g": 1, "confidence": 0.9}]}
        with patch("app.application.nutrition.scan.invoke", return_value=recognized):
            scan = create_scan({"image_base64": encoded_jpeg("edited-review"),
                                "mime_type": "image/jpeg"})
        meal = confirm_scan(scan["id"], {"meal_type": "lunch", "items": [
            {"display_name": "实际米饭", "amount": 200, "unit": "g", "grams": 200,
             "kcal": 232, "carb_g": 51.8, "protein_g": 5.2, "fat_g": 0.6},
            {"display_name": "补充食材", "amount": 5, "unit": "g", "grams": 5,
             "kcal": 45}]})
        self.assertEqual([item["display_name"] for item in meal["items"]],
                         ["实际米饭", "补充食材"])
        self.assertEqual(sum(item["kcal"] for item in meal["items"]), 277)
        self.assertEqual(meal["items"][1]["nutrient_known_mask"], 0)
        summary = day_summary(today())
        self.assertEqual(summary["energy"]["intake_kcal"], 277)
        self.assertEqual(summary["incomplete_macro_items"], 1)

    def test_photo_upload_rejects_fake_mismatched_and_oversized_images_before_agent(self):
        with patch("app.application.nutrition.scan.invoke") as agent:
            for raw, mime in ((b"not-a-photo" * 200, "image/jpeg"),
                              (image_bytes("wrong-mime", "PNG"), "image/jpeg")):
                with self.assertRaises(ApiError) as rejected:
                    create_scan({"image_base64": base64.b64encode(raw).decode("ascii"),
                                 "mime_type": mime})
                self.assertEqual(rejected.exception.code, "VALIDATION_ERROR")
            agent.assert_not_called()
        with Image.new("RGB", (5000, 10), "white") as large:
            output = BytesIO()
            large.save(output, format="JPEG")
        with self.assertRaises(ApiError) as oversized:
            clean_upload_image(output.getvalue(), "image/jpeg")
        self.assertEqual(oversized.exception.code, "VALIDATION_ERROR")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM food_scan_jobs").fetchone()[0], 0)

    def test_photo_scan_retry_reuses_processing_job_and_rejects_changed_photo(self):
        image = encoded_jpeg("same-photo")
        body = {"image_base64": image, "mime_type": "image/jpeg"}
        recognized = {"items": [{"name": "米饭", "estimated_grams": 150, "kcal": 174,
                                  "carb_g": 38, "protein_g": 4, "fat_g": 0.5,
                                  "confidence": 0.82}], "warnings": []}
        started, release = Event(), Event()

        def slow_agent(*_):
            started.set()
            if not release.wait(5):
                raise AssertionError("识餐测试等待超时")
            return recognized

        with patch("app.application.nutrition.scan.invoke", side_effect=slow_agent) as agent:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(create_scan, body, "one-photo-operation")
                self.assertTrue(started.wait(5))
                processing = create_scan(body, "one-photo-operation")
                self.assertEqual(processing["status"], "PROCESSING")
                release.set()
                complete = first.result(timeout=5)
            repeated = create_scan(body, "one-photo-operation")
            self.assertEqual(agent.call_count, 1)
        self.assertEqual((processing["id"], repeated["id"]), (complete["id"], complete["id"]))
        self.assertEqual(repeated["status"], "REVIEW_REQUIRED")
        confirm_scan(complete["id"], {"meal_type": "lunch"})
        self.assertEqual(create_scan(body, "one-photo-operation")["status"], "CONFIRMED")
        changed = dict(body, image_base64=encoded_jpeg("other-photo"))
        with self.assertRaises(ApiError) as conflict:
            create_scan(changed, "one-photo-operation")
        self.assertEqual(conflict.exception.status, 409)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM food_scan_jobs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM agent_runs WHERE agent_type='food_vision'").fetchone()[0], 1)

    def test_photo_scan_failed_attempt_retries_in_same_job(self):
        body = {"image_base64": encoded_jpeg("retry-photo"),
                "mime_type": "image/jpeg"}
        recognized = {"items": [{"name": "米饭", "estimated_grams": 100, "kcal": 116,
                                  "carb_g": 25.9, "protein_g": 2.6, "fat_g": 0.3,
                                  "confidence": 0.9}]}
        malformed = dict(recognized, warnings="不能把一段字符串当警告列表")
        with patch("app.application.nutrition.scan.invoke", side_effect=[
                ApiError("AGENT_UNAVAILABLE", "网关离线", 503), malformed, recognized]) as agent:
            with self.assertRaises(ApiError):
                create_scan(body, "retry-after-failure")
            with self.assertRaises(ApiError) as invalid:
                create_scan(body, "retry-after-failure")
            self.assertEqual(invalid.exception.code, "AGENT_INVALID_RESPONSE")
            scan = create_scan(body, "retry-after-failure")
            self.assertEqual(agent.call_count, 3)
        self.assertEqual(scan["status"], "REVIEW_REQUIRED")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM food_scan_jobs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM agent_runs WHERE agent_type='food_vision'").fetchone()[0], 3)

    def test_food_vision_missing_macro_fields_is_not_silently_saved_as_zero(self):
        body = {"image_base64": encoded_jpeg("missing-macros"),
                "mime_type": "image/jpeg"}
        incomplete = {"items": [{"name": "米饭", "estimated_grams": 100,
                                  "kcal": 116, "confidence": 0.9}]}
        with patch("app.application.nutrition.scan.invoke", return_value=incomplete):
            with self.assertRaises(ApiError) as rejected:
                create_scan(body, "missing-macros")
        self.assertEqual(rejected.exception.code, "AGENT_INVALID_RESPONSE")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals").fetchone()[0], 0)

    def test_photo_scan_stale_attempt_cannot_overwrite_new_result(self):
        body = {"image_base64": encoded_jpeg("stale-photo"),
                "mime_type": "image/jpeg"}
        started, release = Event(), Event()
        calls = 0

        def vision(*_):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                if not release.wait(5):
                    raise AssertionError("旧识餐调用未释放")
                name = "过期结果"
            else:
                name = "新结果"
            return {"items": [{"name": name, "estimated_grams": 100,
                               "kcal": 100, "carb_g": 20, "protein_g": 2, "fat_g": 1,
                               "confidence": 0.9}]}

        with patch("app.application.nutrition.scan.invoke", side_effect=vision):
            with ThreadPoolExecutor(max_workers=2) as pool:
                old = pool.submit(create_scan, body, "stale-operation")
                self.assertTrue(started.wait(5))
                with transaction() as db:
                    db.execute("UPDATE food_scan_jobs SET processing_started_at=? WHERE idempotency_key=?",
                               ("2000-01-01T00:00:00+00:00", "stale-operation"))
                newer = create_scan(body, "stale-operation")
                release.set()
                prior = old.result(timeout=5)
        self.assertEqual(calls, 2)
        self.assertEqual(prior["id"], newer["id"])
        self.assertEqual(get_scan(newer["id"])["result"]["items"][0]["name"], "新结果")
        with connect() as db:
            statuses = {row[0] for row in db.execute("SELECT status FROM agent_runs WHERE agent_type='food_vision'")}
        self.assertEqual(statuses, {"REVIEW_REQUIRED", "SUPERSEDED"})

    def test_concurrent_confirmation_and_retry_create_one_record(self):
        self._onboard()
        def parallel(call):
            with ThreadPoolExecutor(max_workers=5) as pool:
                return list(pool.map(call, range(5)))

        meal_body = {"meal_type": "breakfast", "items": [
            {"display_name": "并发早餐", "amount": 1, "unit": "份", "kcal": 100}]}
        meals = parallel(lambda _: create_meal(meal_body, "stable-breakfast-key"))
        self.assertEqual(len({row["id"] for row in meals}), 1)

        workout_body = {"workout_type": "walking", "minutes": 20}
        workouts = parallel(lambda _: create_workout(workout_body, "stable-workout-key"))
        self.assertEqual(len({row["id"] for row in workouts}), 1)

        waters = parallel(lambda _: add_water({"amount_ml": 250}, "stable-water-key"))
        self.assertEqual(len({row["id"] for row in waters}), 1)

        item = recommend({"meal_type": "dinner"})["items"][0]
        accepted = parallel(lambda _: accept(item["id"], idempotency_key=new_id()))
        self.assertEqual(len({row["meal_id"] for row in accepted}), 1)

        chat = new_chat()
        proposal = {"reply": "可选米饭。", "proposal": {"meal_type": "lunch", "items": [
            {"name": "米饭", "grams": 150, "kcal": 174, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=proposal):
            send_message(chat["id"], "午餐吃什么？")
        chat_meals = parallel(lambda _: accept_proposal(chat["id"], idempotency_key=new_id()))
        self.assertEqual(len({row["meal_id"] for row in chat_meals}), 1)

        image = encoded_jpeg("concurrent-image")
        recognized = {"items": [{"name": "米饭", "estimated_grams": 150, "kcal": 174,
                                 "carb_g": 38, "protein_g": 4, "fat_g": 0.5,
                                 "confidence": 0.82}], "warnings": []}
        with patch("app.application.nutrition.scan.invoke", return_value=recognized):
            scan = create_scan({"image_base64": image, "mime_type": "image/jpeg"})
        scanned = parallel(lambda _: confirm_scan(scan["id"], {"meal_type": "dinner"}))
        self.assertEqual(len({row["id"] for row in scanned}), 1)
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM water_logs").fetchone()[0], 1)
        self.assertEqual(day_summary(today())["water_ml"], 250)

    def test_agent_recommendation_cannot_insert_unsafe_recipe(self):
        self._onboard()
        set_preferences({"allergies": ["milk"], "restrictions": [], "preferences": []})
        with patch("app.application.recommendation.service.configured", return_value=True), \
             patch("app.application.recommendation.service.invoke", return_value={"recipe_ids": ["r3"]}):
            result = recommend({"meal_type": "dinner"})
        self.assertEqual(result["session"]["constraint_version"], "rules-v1")
        self.assertNotIn("r3", {x["candidate_ref_id"] for x in result["items"]})
        set_preferences({"allergies": [], "restrictions": ["vegetarian"], "preferences": []})
        vegetarian = recommend({"meal_type": "dinner"})
        self.assertFalse({x["candidate_ref_id"] for x in vegetarian["items"]} & {"r1", "r2", "r4", "r6"})

    def test_chat_blocks_unverified_food_for_allergic_user(self):
        self._onboard()
        set_preferences({"allergies": ["milk"], "restrictions": [], "preferences": []})
        chat = new_chat()
        response = {"reply": "喝奶茶", "proposal": {"meal_type": "snack", "items": [
            {"name": "奶茶", "grams": 250, "kcal": 180, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=response):
            with self.assertRaises(ApiError) as raised:
                send_message(chat["id"], "想喝点东西")
        self.assertEqual(raised.exception.code, "HARD_CONSTRAINT_UNVERIFIED")

    def test_chat_rejects_invalid_numbers_and_over_budget_proposals(self):
        self._onboard()
        chat = new_chat()
        proposal = {"reply": "可以考虑这份餐食。", "proposal": {"meal_type": "lunch", "items": [
            {"name": "米饭", "grams": 150, "kcal": "NaN", "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=proposal):
            with self.assertRaises(ApiError) as invalid:
                send_message(chat["id"], "午餐吃什么？")
        self.assertEqual(invalid.exception.code, "AGENT_INVALID_RESPONSE")
        proposal["proposal"]["items"] = [
            {"name": "米饭", "grams": 100, "kcal": 1200, "allergens": []},
            {"name": "鸡胸肉", "grams": 100, "kcal": 1200, "allergens": []}]
        with patch("app.application.recommendation.chat.invoke", return_value=proposal):
            with self.assertRaises(ApiError) as oversized:
                send_message(chat["id"], "午餐吃什么？")
        self.assertEqual(oversized.exception.code, "HARD_CONSTRAINT_VIOLATION")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id=?",
                                        (chat["id"],)).fetchone()[0], 0)

    def test_chat_accept_rechecks_live_budget_and_retry_returns_existing_meal(self):
        self._onboard()
        chat = new_chat()
        proposal = {"reply": "建议清淡米饭。", "proposal": {"meal_type": "lunch", "items": [
            {"name": "米饭", "grams": 150, "kcal": 174, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=proposal):
            send_message(chat["id"], "午餐吃什么？")
        target = day_summary(today())["energy"]["target_kcal"]
        eaten = create_meal({"meal_type": "breakfast", "items": [
            {"display_name": "已吃早餐", "amount": 1, "unit": "份", "kcal": target - 50}]})
        with self.assertRaises(ApiError) as stale:
            accept_proposal(chat["id"])
        self.assertEqual(stale.exception.code, "HARD_CONSTRAINT_VIOLATION")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals WHERE source_ref_id=?",
                                        (chat["id"],)).fetchone()[0], 0)
        delete_meal(eaten["id"])
        accepted = accept_proposal(chat["id"])
        set_preferences({"allergies": [], "restrictions": ["rice"], "preferences": []})
        self.assertEqual(accept_proposal(chat["id"]), accepted)
        update_meal(accepted["meal_id"], {"status": "CONSUMED"})
        self.assertEqual(accept_proposal(chat["id"])["status"], "CONSUMED")
        delete_meal(accepted["meal_id"])
        with self.assertRaises(ApiError) as removed:
            accept_proposal(chat["id"])
        self.assertEqual((removed.exception.code, removed.exception.status),
                         ("ALREADY_REMOVED", 409))

    def test_chat_price_ceiling_requires_verified_recipe_and_rechecks_on_accept(self):
        self._onboard()
        set_preferences({"allergies": [], "restrictions": [], "preferences": [],
                         "dining": {"max_cost_cny": 18, "max_cook_minutes": 20,
                                    "flavors": [], "preferred_scenario": "self_cook"}})
        selected = recommend({"meal_type": "dinner"})["items"][0]
        recipe_id = selected["candidate_ref_id"]
        chat = new_chat()
        freeform = {"reply": "随便做。", "proposal": {"meal_type": "dinner", "items": [
            {"name": "米饭", "grams": 100, "kcal": 100, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=freeform):
            with self.assertRaises(ApiError) as unverified:
                send_message(chat["id"], "预算 18 元内吃什么？")
        self.assertEqual(unverified.exception.code, "HARD_CONSTRAINT_UNVERIFIED")
        forged = {"reply": "选已登记菜谱。", "proposal": {"meal_type": "dinner",
                  "recipe_id": recipe_id, "items": [{"name": "伪造菜", "grams": 1,
                                                   "kcal": 0, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=forged):
            answer = send_message(chat["id"], "选一个可核算的菜谱")
        self.assertEqual(answer["proposal"]["recipe_id"], recipe_id)
        self.assertNotIn("伪造菜", {item["name"] for item in answer["proposal"]["items"]})
        self.assertLessEqual(answer["proposal"]["estimated_cost_cny"], 18)
        with connect() as db:
            saved = db.execute("SELECT structured_payload_json FROM chat_messages WHERE session_id=? AND role='assistant'",
                               (chat["id"],)).fetchone()[0]
        self.assertIn(recipe_id, saved)
        accepted = accept_proposal(chat["id"])
        self.assertEqual(accepted["status"], "PLANNED")
        meal = get_meal(accepted["meal_id"])
        self.assertEqual(meal["source_type"], "chat_agent")
        self.assertNotIn("伪造菜", {item["display_name"] for item in meal["items"]})
        stale_chat = new_chat()
        with patch("app.application.recommendation.chat.invoke", return_value=forged):
            send_message(stale_chat["id"], "仍选这个可核算菜谱")
        set_preferences({"allergies": [], "restrictions": [], "preferences": [],
                         "dining": {"max_cost_cny": 1, "max_cook_minutes": 5,
                                    "flavors": [], "preferred_scenario": "self_cook"}})
        with self.assertRaises(ApiError) as stale:
            accept_proposal(stale_chat["id"])
        self.assertEqual(stale.exception.code, "HARD_CONSTRAINT_VIOLATION")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meals WHERE source_ref_id=?",
                                        (stale_chat["id"],)).fetchone()[0], 0)

    def test_chat_plan_and_device_sample_deduplication(self):
        self._onboard()
        chat = new_chat()
        response = {"reply": "建议清淡米饭。", "proposal": {"meal_type": "lunch", "items": [
            {"name": "米饭", "grams": 150, "kcal": 174, "allergens": []}]}}
        with patch("app.application.recommendation.chat.invoke", return_value=response):
            answer = send_message(chat["id"], "午餐吃什么？")
        self.assertEqual(answer["proposal"]["meal_type"], "lunch")
        self.assertEqual(accept_proposal(chat["id"])["status"], "PLANNED")
        self.assertEqual(day_summary(today())["energy"]["intake_kcal"], 0)
        device = connect_device({"provider": "manual_device_import"})
        payload = {"samples": [{"external_id": "watch-001", "sample_type": "active_energy",
                                "local_date": today(), "value": 340}]}
        self.assertEqual(import_samples(device["id"], payload)["imported"], 1)
        self.assertEqual(import_samples(device["id"], payload)["duplicates"], 1)
        self.assertEqual(day_summary(today())["energy"]["activity_kcal"], 340)
        payload["samples"][0]["value"] = 350
        self.assertEqual(import_samples(device["id"], payload)["updated"], 1)
        self.assertEqual(day_summary(today())["energy"]["activity_kcal"], 350)
        import_samples(device["id"], {"samples": [{"external_id": "watch-steps-001",
            "sample_type": "steps", "local_date": today(), "value": 6200}]})
        steps = day_summary(today())
        self.assertEqual(steps["steps"], 6200)
        self.assertEqual(steps["steps_source"], "manual_device_import")
        self.assertIsNotNone(steps["steps_synced_at"])
        import_samples(device["id"], {"samples": [{"external_id": "watch-heart-001",
            "sample_type": "heart_rate", "local_date": today(), "value": 112}]})
        heart = day_summary(today())
        self.assertEqual(heart["heart_rate_bpm"], 112)
        self.assertEqual(heart["heart_rate_source"], "manual_device_import")
        self.assertIsNotNone(heart["heart_rate_sampled_at"])
        body = {"samples": [{"external_id": "scale-w-001", "sample_type": "body_weight",
                             "local_date": today(), "value": 72.1},
                            {"external_id": "scale-f-001", "sample_type": "body_fat",
                             "local_date": today(), "value": 20.8}]}
        import_samples(device["id"], body)
        self.assertEqual(get_profile()["measurement"]["weight_kg"], 72.1)
        self.assertEqual(get_profile()["measurement"]["body_fat_pct"], 20.8)

    def test_fitness_and_profile_erasure_resolve_device_dependencies(self):
        self._onboard()
        day = today()
        create_meal({"local_date": day, "meal_type": "lunch", "items": [
            {"display_name": "米饭", "amount": 100, "unit": "g", "kcal": 116}]})
        create_workout({"local_date": day, "workout_type": "walking", "minutes": 30})
        device = connect_device({"provider": "manual_device_import"})
        import_samples(device["id"], {"samples": [
            {"external_id": "scale", "sample_type": "body_weight", "local_date": day, "value": 71.5},
            {"external_id": "watch", "sample_type": "active_energy", "local_date": day, "value": 200}]})
        self.assertEqual(get_profile()["measurement"]["weight_kg"], 71.5)
        self.assertGreater(deletion_preview("fitness")["counts"]["imported_body_measurements"], 0)
        delete_data("fitness", "DELETE_FITNESS")
        snapshot = export_data("all")["tables"]
        self.assertEqual(snapshot["device_samples"], [])
        self.assertEqual(snapshot["workout_sessions"], [])
        self.assertEqual(snapshot["body_measurements"][-1]["weight_kg"], 72.5)
        self.assertEqual(len(snapshot["meals"]), 1)
        self.assertIsNotNone(get_profile()["target"])
        delete_data("profile", "DELETE_PROFILE")
        self.assertIsNone(get_profile()["profile"]["birth_date"])
        self.assertIsNone(get_profile()["target"])
        self.assertEqual(len(export_data("diet")["tables"]["meals"]), 1)


if __name__ == "__main__":
    unittest.main()
