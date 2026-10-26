from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from app.domain.activity import reconcile_activity
from app.domain.energy import calculate_day
from app.infrastructure.agent.gateway import configured, invoke
from app.infrastructure.db.database import connect, transaction
from app.infrastructure.devices.samples import effective_samples
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, new_id, today, utc_now, valid_date


def _activity_by_day(db, start: str, end: str) -> dict[str, dict]:
    providers: dict[str, dict[str, dict]] = {}
    samples = effective_samples(db, USER_ID, "active_energy", start, end)
    sample_ids = {row["id"] for row in samples}
    for row in samples:
        day_sources = providers.setdefault(row["local_date"], {})
        source = day_sources.setdefault(row["provider"], {"samples": [], "total": 0.0,
                                                           "synced_at": None})
        source["samples"].append(row)
        source["total"] += float(row["value"])
        if row["last_synced_at"] and (source["synced_at"] is None or
                                      row["last_synced_at"] > source["synced_at"]):
            source["synced_at"] = row["last_synced_at"]
    workouts: dict[str, list[dict]] = {}
    for row in db.execute("""SELECT id,local_date,start_at,end_at,kcal FROM workout_sessions
        WHERE user_id=? AND status='COMPLETED' AND local_date BETWEEN ? AND ?""",
        (USER_ID, start, end)):
        workouts.setdefault(row["local_date"], []).append(dict(row))
    resolutions: dict[str, dict[tuple[str, str], str]] = {}
    pending: dict[str, int] = {}
    for row in db.execute("""SELECT s.local_date,sc.sample_id,sc.domain_record_id,sc.resolution
        FROM sync_conflicts sc JOIN device_samples s ON s.id=sc.sample_id
        JOIN device_connections c ON c.id=s.connection_id
        WHERE sc.user_id=? AND c.status IN ('ACTIVE','REVOKED') AND s.pending_activation=0
          AND sc.reason='TIME_OVERLAP'
          AND s.local_date BETWEEN ? AND ?""",
        (USER_ID, start, end)):
        if row["sample_id"] not in sample_ids:
            continue
        day = row["local_date"]
        if row["resolution"] is None:
            pending[day] = pending.get(day, 0) + 1
        else:
            resolutions.setdefault(day, {})[(row["sample_id"], row["domain_record_id"])] = row["resolution"]
    result = {}
    for day in providers.keys() | workouts.keys():
        source_rows = providers.get(day, {})
        chosen = min(source_rows, key=lambda name: (-source_rows[name]["total"], name)) if source_rows else None
        source = source_rows.get(chosen) if chosen else None
        reconciled = reconcile_activity(source["samples"] if source else [],
                                        workouts.get(day, []), resolutions.get(day, {}))
        result[day] = {**reconciled, "provider": chosen,
                       "synced_at": source["synced_at"] if source else None,
                       "raw_device_kcal": source["total"] if source else 0.0,
                       "raw_manual_kcal": sum(float(w["kcal"]) for w in workouts.get(day, [])),
                       "pending_conflicts": pending.get(day, 0)}
    return result


def day_summary(day: str | None = None) -> dict:
    day = valid_date(day or today())
    with connect() as db:
        target = db.execute("""SELECT * FROM nutrition_targets WHERE user_id=? AND effective_from<=?
            AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC, rowid DESC LIMIT 1""",
            (USER_ID, day, day)).fetchone()
        # A day without a target is an onboarding state; values must not be
        # presented as personalized calculations.
        target_data = dict(target) if target else None
        intake = db.execute("""SELECT COALESCE(SUM(i.kcal),0),COALESCE(SUM(i.carb_g),0),
            COALESCE(SUM(i.protein_g),0),COALESCE(SUM(i.fat_g),0),
            COALESCE(SUM(CASE WHEN (i.nutrient_known_mask & 7) != 7 THEN 1 ELSE 0 END),0)
            FROM meal_items i JOIN meals m ON m.id=i.meal_id WHERE m.user_id=? AND m.local_date=?
            AND m.status='CONSUMED' AND m.deleted_at IS NULL""", (USER_ID, day)).fetchone()
        activity = _activity_by_day(db, day, day).get(day, {})
        active = float(activity.get("kcal", 0.0))
        workout_breakdown = db.execute("""SELECT COALESCE(SUM(minutes),0) AS minutes,
            COALESCE(SUM(CASE WHEN workout_type='strength' THEN kcal ELSE 0 END),0) AS strength_kcal
            FROM workout_sessions WHERE user_id=? AND local_date=? AND status='COMPLETED'""",
            (USER_ID, day)).fetchone()
        training_goal = db.execute("SELECT active_kcal_goal FROM training_profiles WHERE user_id=?",
                                   (USER_ID,)).fetchone()
        water = db.execute("SELECT COALESCE(SUM(amount_ml),0) FROM water_logs WHERE user_id=? AND local_date=?",
                           (USER_ID, day)).fetchone()[0]
        workouts = db.execute("SELECT COUNT(*) FROM workout_sessions WHERE user_id=? AND local_date=?",
                              (USER_ID, day)).fetchone()[0]
        volume = db.execute("""SELECT COALESCE(SUM(s.volume),0) FROM exercise_sets s JOIN workout_sessions w
            ON w.id=s.session_id WHERE w.user_id=? AND w.local_date=? AND w.status='COMPLETED'""",
            (USER_ID, day)).fetchone()[0]
        step_sources: dict[str, dict] = {}
        for sample in effective_samples(db, USER_ID, "steps", day, day):
            source = step_sources.setdefault(sample["provider"], {"provider": sample["provider"],
                "total": 0.0, "last_synced_at": None})
            source["total"] += float(sample["value"])
            synced = sample["last_synced_at"]
            if synced and (source["last_synced_at"] is None or synced > source["last_synced_at"]):
                source["last_synced_at"] = synced
        steps_row = min(step_sources.values(), key=lambda row: (-row["total"], row["provider"])) \
            if step_sources else None
        heart_samples = effective_samples(db, USER_ID, "heart_rate", day, day)
        heart_rate = max(heart_samples, key=lambda row: (row["start_at"], row["id"])) \
            if heart_samples else None
    energy = calculate_day(float(target_data["kcal"]) if target_data else 0,
                           float(intake[0]), float(target_data["bmr_kcal"]) if target_data else 0,
                           float(target_data["tdee_kcal"]) if target_data else 0, active)
    return {"local_date": day, "has_target": target_data is not None,
            "target": target_data, "energy": vars(energy),
            "macros": {"carb_g": round(float(intake[1]), 1),
                       "protein_g": round(float(intake[2]), 1),
                       "fat_g": round(float(intake[3]), 1)},
            "incomplete_macro_items": int(intake[4]),
            "water_ml": int(water), "workout_count": int(workouts),
            "training_volume": round(float(volume), 1),
            "workout_minutes": round(float(workout_breakdown["minutes"]), 1),
            "strength_kcal": round(float(workout_breakdown["strength_kcal"]), 1),
            "activity_goal_kcal": int(training_goal[0]) if training_goal else 300,
            "manual_activity_kcal": round(float(activity.get("raw_manual_kcal", 0.0)), 1),
            "device_activity_kcal": round(float(activity.get("raw_device_kcal", 0.0)), 1),
            "activity_provider": activity.get("provider"),
            "activity_synced_at": activity.get("synced_at"),
            "activity_quality": activity.get("quality", "none"),
            "pending_activity_conflicts": activity.get("pending_conflicts", 0),
            "steps": int(steps_row["total"]) if steps_row else 0,
            "steps_source": steps_row["provider"] if steps_row else None,
            "steps_synced_at": steps_row["last_synced_at"] if steps_row else None,
            "heart_rate_bpm": round(float(heart_rate["value"])) if heart_rate else None,
            "heart_rate_source": heart_rate["provider"] if heart_rate else None,
            "heart_rate_sampled_at": heart_rate["start_at"] if heart_rate else None,
            "activity_source": activity.get("source", "none")}


def _calculate_series_day_records(db, start: str, end: str) -> dict[str, dict]:
    """Read each ledger in one range query, then apply the same daily energy rule."""
    targets = [dict(row) for row in db.execute("""SELECT * FROM nutrition_targets
        WHERE user_id=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)
        ORDER BY effective_from DESC,rowid DESC""", (USER_ID, end, start))]
    intake = {row["local_date"]: row for row in db.execute("""SELECT
        m.local_date,SUM(i.kcal) AS kcal,SUM(i.carb_g) AS carb_g,
        SUM(i.protein_g) AS protein_g,SUM(i.fat_g) AS fat_g,
        SUM(CASE WHEN (i.nutrient_known_mask & 7) != 7 THEN 1 ELSE 0 END) AS incomplete_items
        FROM meals m JOIN meal_items i ON i.meal_id=m.id
        WHERE m.user_id=? AND m.local_date BETWEEN ? AND ? AND m.status='CONSUMED'
          AND m.deleted_at IS NULL GROUP BY m.local_date""", (USER_ID, start, end))}
    activities = _activity_by_day(db, start, end)
    workouts = {row["local_date"]: row for row in db.execute("""SELECT local_date,
        COALESCE(SUM(CASE WHEN status='COMPLETED' THEN kcal ELSE 0 END),0) AS kcal,
        COUNT(*) AS workout_count FROM workout_sessions WHERE user_id=?
        AND local_date BETWEEN ? AND ? GROUP BY local_date""", (USER_ID, start, end))}
    volumes = {row["local_date"]: float(row["volume"]) for row in db.execute("""SELECT
        w.local_date,SUM(s.volume) AS volume FROM workout_sessions w JOIN exercise_sets s
          ON s.session_id=w.id WHERE w.user_id=? AND w.local_date BETWEEN ? AND ?
          AND w.status='COMPLETED' GROUP BY w.local_date""", (USER_ID, start, end))}
    water = {row["local_date"]: int(row["amount_ml"]) for row in db.execute("""SELECT
        local_date,SUM(amount_ml) AS amount_ml FROM water_logs WHERE user_id=?
        AND local_date BETWEEN ? AND ? GROUP BY local_date""", (USER_ID, start, end))}
    records = {}
    cursor, final = date.fromisoformat(start), date.fromisoformat(end)
    while cursor <= final:
        day = cursor.isoformat()
        target = next((row for row in targets if row["effective_from"] <= day
                       and (row["effective_to"] is None or row["effective_to"] >= day)), None)
        eaten = intake.get(day)
        actual = {key: float(eaten[key]) if eaten else 0.0 for key in
                  ("kcal", "carb_g", "protein_g", "fat_g")}
        target_macro = {key: float(target[key]) for key in ("carb_g", "protein_g", "fat_g")} if target else None
        workout = workouts.get(day)
        active = float(activities.get(day, {}).get("kcal", 0.0))
        raw_bmr = float(target["bmr_kcal"]) if target else 0.0
        raw_tdee = float(target["tdee_kcal"]) if target else 0.0
        raw_expenditure = max(raw_tdee, raw_bmr + active)
        raw_volume = volumes.get(day, 0.0)
        records[day] = {"has_target": target is not None, "target": target,
                        "energy": vars(calculate_day(float(target["kcal"]) if target else 0,
                                                     actual["kcal"],
                                                     raw_bmr,
                                                     raw_tdee,
                                                     active)),
                        "raw": {"intake_kcal": actual["kcal"], "bmr_kcal": raw_bmr,
                                "tdee_kcal": raw_tdee,
                                "expenditure_kcal": raw_expenditure,
                                "net_kcal": actual["kcal"] - raw_expenditure,
                                "training_volume": raw_volume},
                        "macro_data": {"actual": actual, "target": target_macro,
                                       "incomplete_items": int(eaten["incomplete_items"]) if eaten else 0},
                        "water_ml": water.get(day, 0),
                        "workout_count": int(workout["workout_count"]) if workout else 0,
                        "training_volume": round(raw_volume, 1)}
        cursor += timedelta(days=1)
    return records


_ENERGY_CACHE_VERSION = "energy-v6-nutrient-presence"


def _cached_series_rows(db, start: str, end: str) -> dict[str, dict]:
    return {row["local_date"]: dict(row) for row in db.execute("""SELECT * FROM daily_energy_snapshots
        WHERE user_id=? AND local_date BETWEEN ? AND ? AND calc_version=?""",
        (USER_ID, start, end, _ENERGY_CACHE_VERSION))}


def _series_day_records(start: str, end: str) -> dict[str, dict]:
    expected = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    with connect() as db:
        cached = _cached_series_rows(db, start, end)
    if len(cached) != expected:
        # BEGIN IMMEDIATE keeps an in-flight writer from changing the ledger
        # between calculation and cache insertion. Source-table triggers evict
        # only affected dates after subsequent commits.
        with transaction() as db:
            cached = _cached_series_rows(db, start, end)
            if len(cached) != expected:
                fresh = _calculate_series_day_records(db, start, end)
                for day, record in fresh.items():
                    if day in cached:
                        continue
                    target = record["target"]
                    energy = record["energy"]
                    db.execute("""INSERT OR REPLACE INTO daily_energy_snapshots(
                        user_id,local_date,target_id,intake_kcal,bmr_kcal,tdee_kcal,activity_kcal,
                        expenditure_kcal,net_kcal,water_ml,workout_count,training_volume,
                        macro_json,raw_json,completeness,calc_version)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (USER_ID, day, target["id"] if target else None, energy["intake_kcal"],
                         energy["bmr_kcal"], energy["tdee_kcal"], energy["activity_kcal"],
                         energy["total_expenditure_kcal"], energy["net_kcal"],
                         record["water_ml"], record["workout_count"], record["training_volume"],
                         as_json(record["macro_data"]), as_json(record["raw"]),
                         "partial", _ENERGY_CACHE_VERSION))
                cached = _cached_series_rows(db, start, end)
    return {day: {"has_target": row["target_id"] is not None,
                  "target": {"bmr_kcal": row["bmr_kcal"]} if row["target_id"] else None,
                  "energy": {"intake_kcal": row["intake_kcal"],
                             "total_expenditure_kcal": row["expenditure_kcal"],
                             "net_kcal": row["net_kcal"]},
                  "macro_data": json.loads(row["macro_json"]),
                  "raw": {**json.loads(row["raw_json"]), "tdee_kcal": row["tdee_kcal"]},
                  "water_ml": row["water_ml"], "workout_count": row["workout_count"],
                  "training_volume": row["training_volume"]} for day, row in cached.items()}


def energy_series(start: str, end: str, granularity: str = "day") -> dict:
    start_date, end_date = date.fromisoformat(valid_date(start)), date.fromisoformat(valid_date(end))
    require(start_date <= end_date, "开始日期不能晚于结束日期")
    require((end_date - start_date).days <= 366, "单次最多查询 367 天")
    require(granularity in ("day", "week", "month", "year"), "统计粒度无效")
    daily = _series_day_records(start, end)
    buckets: dict[str, dict] = {}
    cursor = start_date
    while cursor <= end_date:
        record = daily[cursor.isoformat()]
        if granularity == "week":
            year, week, _ = cursor.isocalendar()
            key = f"{year}-W{week:02d}"
        elif granularity == "month":
            key = cursor.strftime("%Y-%m")
        elif granularity == "year":
            key = cursor.strftime("%Y")
        else:
            key = cursor.isoformat()
        bucket = buckets.setdefault(key, {"period": key, "days": 0, "target_days": 0, "logged_days": 0,
                                          "intake_kcal": 0.0,
                                          "expenditure_kcal": 0.0, "net_kcal": 0.0,
                                          "bmr_kcal": 0.0, "tdee_kcal": 0.0,
                                          "training_volume": 0.0, "water_ml": 0})
        bucket["days"] += 1
        if (record["energy"]["intake_kcal"] > 0 or record["water_ml"] > 0 or record["workout_count"] > 0):
            bucket["logged_days"] += 1
        bucket["intake_kcal"] += record["raw"]["intake_kcal"]
        if record["has_target"]:
            bucket["target_days"] += 1
            bucket["bmr_kcal"] += record["raw"]["bmr_kcal"]
            bucket["tdee_kcal"] += record["raw"]["tdee_kcal"]
            bucket["expenditure_kcal"] += record["raw"]["expenditure_kcal"]
            bucket["net_kcal"] += record["raw"]["net_kcal"]
        bucket["training_volume"] += record["raw"]["training_volume"]
        bucket["water_ml"] += record["water_ml"]
        cursor += timedelta(days=1)
    return {"start": start, "end": end, "granularity": granularity,
            "series": [{**v, "intake_kcal": round(v["intake_kcal"], 1),
                        "expenditure_kcal": round(v["expenditure_kcal"], 1) if v["target_days"] else None,
                        "net_kcal": round(v["net_kcal"], 1) if v["target_days"] else None,
                        "bmr_kcal": round(v["bmr_kcal"], 1) if v["target_days"] else None,
                        "tdee_kcal": round(v["tdee_kcal"], 1) if v["target_days"] else None,
                        "training_volume": round(v["training_volume"], 1)} for v in buckets.values()]}


def macro_summary(start: str, end: str) -> dict:
    start_date, end_date = date.fromisoformat(valid_date(start)), date.fromisoformat(valid_date(end))
    require(start_date <= end_date and (end_date - start_date).days <= 366, "查询日期范围无效")
    daily = _series_day_records(start, end)
    actual_totals = {key: 0.0 for key in ("carb_g", "protein_g", "fat_g")}
    target_totals = {"carb_g": 0.0, "protein_g": 0.0, "fat_g": 0.0}
    target_days = 0
    intake_kcal = 0.0
    incomplete_items = 0
    for day in sorted(daily):
        record = daily[day]
        macro = record["macro_data"]
        intake_kcal += macro["actual"]["kcal"]
        incomplete_items += macro["incomplete_items"]
        for key in actual_totals:
            actual_totals[key] += macro["actual"][key]
        if macro["target"] is not None:
            target_days += 1
            for key in target_totals:
                target_totals[key] += macro["target"][key]
    return {"start": start, "end": end,
            "actual": {key: round(value, 1) for key, value in actual_totals.items()},
            "target": {key: round(value, 1) for key, value in target_totals.items()},
            "target_days": target_days, "intake_kcal": round(intake_kcal, 1),
            "incomplete_items": incomplete_items}


def habit_summary(start: str, end: str) -> dict:
    """Describe recorded habits without treating missing logs as zero intake."""
    start_date, end_date = date.fromisoformat(valid_date(start)), date.fromisoformat(valid_date(end))
    require(start_date <= end_date and (end_date - start_date).days <= 366, "查询日期范围无效")
    with connect() as db:
        timezone_name = db.execute("SELECT timezone FROM users WHERE id=?", (USER_ID,)).fetchone()[0]
        current_day = date.fromisoformat(today(timezone_name))
        observed_end = min(end_date, current_day)
        closed_end = min(end_date, current_day - timedelta(days=1))
        observed_days = max(0, (observed_end - start_date).days + 1)
        closed_days = max(0, (closed_end - start_date).days + 1)
        water_rows = db.execute("""SELECT local_date,SUM(amount_ml) AS amount_ml
            FROM water_logs WHERE user_id=? AND local_date BETWEEN ? AND ?
            GROUP BY local_date""", (USER_ID, start, observed_end.isoformat())).fetchall() \
            if observed_days else []
        target_rows = db.execute("""SELECT effective_from,effective_to,water_ml
            FROM nutrition_targets WHERE user_id=? AND effective_from<=?
              AND (effective_to IS NULL OR effective_to>=?)
            ORDER BY effective_from DESC,rowid DESC""",
            (USER_ID, observed_end.isoformat(), start)).fetchall() if observed_days else []
        fiber = db.execute("""SELECT COUNT(*) AS consumed_items,
            COALESCE(SUM(CASE WHEN (i.nutrient_known_mask & 8)=8 THEN 1 ELSE 0 END),0)
                AS known_items,
            COALESCE(SUM(CASE WHEN (i.nutrient_known_mask & 8)=8 THEN i.fiber_g ELSE 0 END),0)
                AS known_g
            FROM meal_items i JOIN meals m ON m.id=i.meal_id
            WHERE m.user_id=? AND m.status='CONSUMED' AND m.deleted_at IS NULL
              AND m.local_date BETWEEN ? AND ?""",
            (USER_ID, start, observed_end.isoformat())).fetchone() if observed_days else None
        meal_rows = db.execute("""SELECT local_date,
            MAX(CASE WHEN meal_type='breakfast' THEN 1 ELSE 0 END) AS breakfast,
            MAX(CASE WHEN meal_type='lunch' THEN 1 ELSE 0 END) AS lunch,
            MAX(CASE WHEN meal_type='dinner' THEN 1 ELSE 0 END) AS dinner
            FROM meals WHERE user_id=? AND status='CONSUMED' AND deleted_at IS NULL
              AND local_date BETWEEN ? AND ? GROUP BY local_date""",
            (USER_ID, start, closed_end.isoformat())).fetchall() if closed_days else []
        plan_rows = db.execute("""SELECT s.scheduled_date,s.status,e.status AS enrollment_status,
            e.stopped_on FROM plan_session_instances s
            JOIN user_plan_enrollments e ON e.id=s.enrollment_id
            WHERE e.user_id=? AND s.scheduled_date BETWEEN ? AND ?""",
            (USER_ID, start, closed_end.isoformat())).fetchall() if closed_days else []
    evaluated_water_days = met_water_days = 0
    for row in water_rows:
        day = row["local_date"]
        if day > closed_end.isoformat():
            continue
        target = next((item for item in target_rows if item["effective_from"] <= day and
                       (item["effective_to"] is None or item["effective_to"] >= day)), None)
        if target is not None:
            evaluated_water_days += 1
            met_water_days += int(row["amount_ml"] >= target["water_ml"])
    logged_meal_days = len(meal_rows)
    three_meal_days = sum(bool(row["breakfast"] and row["lunch"] and row["dinner"])
                          for row in meal_rows)
    eligible_plans = []
    legacy_excluded = 0
    for row in plan_rows:
        if row["enrollment_status"] == "STOPPED":
            if row["stopped_on"] is None:
                legacy_excluded += 1
                continue
            if row["scheduled_date"] > row["stopped_on"] or (row["scheduled_date"] == row["stopped_on"]
                and row["status"] == "SCHEDULED"):
                continue
        elif row["enrollment_status"] != "ACTIVE":
            continue
        eligible_plans.append(row)
    completed_plans = sum(row["status"] == "COMPLETED" for row in eligible_plans)
    partial_plans = sum(row["status"] == "PARTIAL" for row in eligible_plans)
    known_items = int(fiber["known_items"]) if fiber else 0
    consumed_items = int(fiber["consumed_items"]) if fiber else 0
    return {"start": start, "end": end,
            "observed_through": observed_end.isoformat() if observed_days else None,
            "closed_through": closed_end.isoformat() if closed_days else None,
            "observed_days": observed_days, "closed_days": closed_days,
            "today_is_partial": start_date <= current_day <= end_date,
            "water": {"recorded_ml": sum(int(row["amount_ml"]) for row in water_rows),
                      "recorded_days": len(water_rows), "evaluated_goal_days": evaluated_water_days,
                      "met_goal_days": met_water_days},
            "fiber": {"known_g": round(float(fiber["known_g"]), 1) if known_items else None,
                      "known_items": known_items, "unknown_items": consumed_items - known_items,
                      "consumed_items": consumed_items},
            "meals": {"logged_closed_days": logged_meal_days,
                      "three_main_meals_logged_days": three_meal_days,
                      "three_meal_logging_pct": round(100 * three_meal_days / logged_meal_days, 1)
                      if logged_meal_days >= 3 else None},
            "training": {"scheduled_closed_sessions": len(eligible_plans),
                         "completed_sessions": completed_plans, "partial_sessions": partial_plans,
                         "completion_pct": round(100 * completed_plans / len(eligible_plans), 1)
                         if len(eligible_plans) >= 3 else None,
                         "legacy_stop_unknown_sessions": legacy_excluded}}


def body_composition_series(start: str, end: str) -> dict:
    start_date, end_date = date.fromisoformat(valid_date(start)), date.fromisoformat(valid_date(end))
    require(start_date <= end_date and (end_date - start_date).days <= 366, "查询日期范围无效")
    first_monday = start_date - timedelta(days=start_date.weekday())
    buckets = {}
    cursor = first_monday
    while cursor <= end_date:
        year, week, _ = cursor.isocalendar()
        buckets[f"{year}-W{week:02d}"] = {"week": f"{year}-W{week:02d}",
                                         "weight_kg": None, "body_fat_pct": None,
                                         "training_volume_kg": 0.0}
        cursor += timedelta(days=7)
    with connect() as db:
        # UTC timestamps close to midnight can fall on the next Shanghai day.
        # Include the adjacent dates, then filter using the actual local date.
        measurements = db.execute("""SELECT measured_at,weight_kg,body_fat_pct FROM body_measurements
            WHERE user_id=? AND substr(measured_at,1,10) BETWEEN ? AND ?
            ORDER BY measured_at,rowid""", (USER_ID, (start_date - timedelta(days=1)).isoformat(),
                                     (end_date + timedelta(days=1)).isoformat())).fetchall()
        volumes = db.execute("""SELECT w.local_date,SUM(s.volume) AS volume FROM exercise_sets s
            JOIN workout_sessions w ON w.id=s.session_id WHERE w.user_id=? AND w.status='COMPLETED'
            AND w.local_date BETWEEN ? AND ? AND s.completed_at IS NOT NULL
            GROUP BY w.local_date""", (USER_ID, start, end)).fetchall()
    for measurement in measurements:
        timestamp = datetime.fromisoformat(measurement["measured_at"])
        day = timestamp.astimezone(ZoneInfo("Asia/Shanghai")).date() if timestamp.tzinfo else timestamp.date()
        if day < start_date or day > end_date:
            continue
        year, week, _ = day.isocalendar()
        bucket = buckets[f"{year}-W{week:02d}"]
        bucket["weight_kg"] = round(float(measurement["weight_kg"]), 1)
        if measurement["body_fat_pct"] is not None:
            bucket["body_fat_pct"] = round(float(measurement["body_fat_pct"]), 1)
    for volume in volumes:
        day = date.fromisoformat(volume["local_date"])
        year, week, _ = day.isocalendar()
        buckets[f"{year}-W{week:02d}"]["training_volume_kg"] += float(volume["volume"])
    return {"start": start, "end": end, "series": [
        {**point, "training_volume_kg": round(point["training_volume_kg"], 1)} for point in buckets.values()]}


def rule_diagnosis(start: str, end: str, allow_agent: bool = True) -> dict:
    data = energy_series(start, end)
    logged_days = sum(x["logged_days"] for x in data["series"])
    target_days = sum(x["target_days"] for x in data["series"])
    intake = sum(x["intake_kcal"] for x in data["series"])
    net = sum(x["net_kcal"] or 0 for x in data["series"])
    current_day = today()
    completed = [point for point in data["series"] if point["period"] < current_day]
    completed_target_days = sum(point["target_days"] for point in completed)
    completed_net = sum(point["net_kcal"] or 0 for point in completed)
    has_unfinished_today = start <= current_day <= end
    observations = [f"有记录的 {logged_days} 天，平均摄入约 {intake / logged_days:.0f} kcal。" if logged_days
                    else "期间暂无摄入或运动记录，无法判断趋势。",
                    f"有目标的 {target_days} 天，累计净能量差约 {net:+.0f} kcal；负值表示估算赤字。{'今天尚未结束，仅供阶段性参考。' if has_unfinished_today else ''}" if target_days
                    else "期间没有完整代谢目标，净能量差暂不可计算。"]
    advice = []
    advice_details = []
    def add_advice(message: str, citations: list[dict]) -> None:
        advice.append(message)
        advice_details.append({"text": message, "evidence_refs": citations})

    period_ref = f"{start}..{end}"
    if not target_days:
        add_advice("请先在个人主页完善身体数据与阶段目标，再查看能量差分析。",
                   [{"period": period_ref, "metric": "target_days", "value": 0}])
    elif completed_target_days == 0:
        add_advice("今天的餐食与活动仍可能继续记录，暂不根据未结束的一天判断赤字或盈余。",
                   [{"period": period_ref, "metric": "completed_target_days", "value": 0}])
    elif completed_net < -500 * completed_target_days:
        add_advice("估算赤字较大，建议复核记录与目标，避免持续过度限制。",
                   [{"period": period_ref, "metric": "completed_mean_net_kcal",
                     "value": round(completed_net / completed_target_days, 1)}])
    elif completed_net > 300 * completed_target_days:
        add_advice("估算盈余较大，可检查份量与活动记录是否完整。",
                   [{"period": period_ref, "metric": "completed_mean_net_kcal",
                     "value": round(completed_net / completed_target_days, 1)}])
    else:
        add_advice("能量差处于较温和范围，可结合体重趋势持续观察。",
                   [{"period": period_ref, "metric": "completed_mean_net_kcal",
                     "value": round(completed_net / completed_target_days, 1)}])
    latest = day_summary(end)
    if latest["workout_count"] > 0 and latest["has_target"]:
        protein_goal = float(latest["target"]["protein_g"])
        if protein_goal > 0 and latest["macros"]["protein_g"] < protein_goal * 0.8:
            add_advice("今日有训练记录且蛋白质摄入尚未达到目标，可结合实际饥饿感补充含蛋白质的正餐或加餐。",
                       [{"period": end, "metric": "protein_g", "value": latest["macros"]["protein_g"]},
                        {"period": end, "metric": "protein_target_g", "value": protein_goal}])
        water_goal = int(latest["target"]["water_ml"])
        if latest["water_ml"] < water_goal * 0.75:
            add_advice("今日饮水记录偏少；训练后请按口渴程度、出汗量与个人情况补水。",
                       [{"period": end, "metric": "water_ml", "value": latest["water_ml"]},
                        {"period": end, "metric": "water_target_ml", "value": water_goal}])
    source = "rules-v1"
    model_name = "rules-v1"
    confidence = None
    snapshot = {"period": {"start": start, "end": end}, "series": data["series"],
                "latest_day": {"local_date": end, "workout_count": latest["workout_count"],
                               "water_ml": latest["water_ml"], "macros": latest["macros"],
                               "target": {key: latest["target"][key] for key in ("kcal", "protein_g", "water_ml")}
                               if latest["has_target"] else None}}
    if allow_agent and configured() and target_days:
        try:
            snapshot["body_composition"] = body_composition_series(start, end)["series"]
            agent_input = {**snapshot, "instruction": "仅依据给定统计数据提出生活方式建议；不得给出医疗诊断、药物或极端热量限制。advice 每项须包含 text 和引用 series 中日期及指标的 evidence_refs。"}
            output = invoke("nutrition_diagnosis", agent_input, timeout=15)
            candidate_observations = output.get("observations")
            candidate_advice = output.get("advice")
            point_by_period = {point["period"]: point for point in data["series"]}
            permitted_metrics = {"intake_kcal", "expenditure_kcal", "net_kcal", "bmr_kcal",
                                 "training_volume", "water_ml", "target_days", "logged_days"}
            checked = []
            if isinstance(candidate_advice, list):
                for item in candidate_advice:
                    if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not 1 <= len(item["text"]) <= 180:
                        break
                    refs = item.get("evidence_refs")
                    if not isinstance(refs, list) or not 1 <= len(refs) <= 5:
                        break
                    citations = []
                    for ref in refs:
                        if not isinstance(ref, dict):
                            break
                        period, metric = ref.get("period"), ref.get("metric")
                        point = point_by_period.get(period) if isinstance(period, str) else None
                        if point is None or not isinstance(metric, str) or metric not in permitted_metrics or point[metric] is None:
                            break
                        citations.append({"period": period, "metric": metric, "value": point[metric]})
                    if len(citations) != len(refs):
                        break
                    checked.append({"text": item["text"], "evidence_refs": citations})
            if (isinstance(candidate_observations, list) and isinstance(candidate_advice, list)
                    and 1 <= len(candidate_observations) <= 6 and 1 <= len(checked) <= 6
                    and len(checked) == len(candidate_advice)
                    and all(isinstance(x, str) and 1 <= len(x) <= 180 for x in candidate_observations)):
                observations = candidate_observations
                advice_details = checked
                advice = [item["text"] for item in checked]
                source = "agent-v1"
                reported_model = output.get("model")
                model_name = reported_model if isinstance(reported_model, str) and re.fullmatch(
                    r"[A-Za-z0-9._/-]{1,80}", reported_model) else "gateway-unspecified"
                raw_confidence = output.get("confidence")
                if type(raw_confidence) in (int, float) and 0 <= raw_confidence <= 1:
                    confidence = round(float(raw_confidence), 2)
                snapshot["instruction"] = agent_input["instruction"]
        except ApiError:
            pass
    add_advice("估算结果仅供记录与复盘，不构成医疗诊断。", [])
    return {"start": start, "end": end, "source": source, "observations": observations,
            "advice": advice, "advice_details": advice_details, "confidence": confidence,
            "model_name": model_name,
            "evidence": data["series"], "_input_snapshot": snapshot}


def generate_diagnosis(start: str, end: str) -> dict:
    result = rule_diagnosis(start, end)
    snapshot = result.pop("_input_snapshot")
    content = {key: value for key, value in result.items() if key != "evidence"}
    digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    model_name = result["model_name"]
    prompt_version = "nutrition_diagnosis.v1" if result["source"] == "agent-v1" else "rule-diagnosis.v1"
    created_at = utc_now()
    report_id = new_id()
    with transaction() as db:
        version = db.execute("""SELECT COALESCE(MAX(version),0)+1 FROM diagnostic_reports
            WHERE user_id=? AND period_start=? AND period_end=?""", (USER_ID, start, end)).fetchone()[0]
        agent_run_id = None
        if result["source"] == "agent-v1":
            agent_run_id = new_id()
            db.execute("""INSERT INTO agent_runs(id,user_id,agent_type,provider,model,prompt_version,
                input_hash,output_json,status) VALUES (?,?,?,?,?,?,?,?,?)""",
                (agent_run_id, USER_ID, "nutrition_diagnosis", "configured_gateway", model_name,
                 prompt_version, digest, as_json(content), "SUCCEEDED"))
        db.execute("""INSERT INTO diagnostic_reports(id,user_id,period_start,period_end,
            metrics_snapshot_json,agent_run_id,content_json,confidence,version,created_at,
            model_name,prompt_version,input_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (report_id, USER_ID, start, end, as_json(snapshot), agent_run_id,
             as_json(content), result["confidence"], version, created_at,
             model_name, prompt_version, digest))
    return {**result, "id": report_id, "version": version, "created_at": created_at,
            "model_name": model_name, "prompt_version": prompt_version, "input_hash": digest}


def diagnosis_history(start: str, end: str) -> dict:
    start, end = valid_date(start), valid_date(end)
    require(start <= end, "开始日期不能晚于结束日期")
    with connect() as db:
        rows = db.execute("""SELECT id,version,created_at,model_name,prompt_version,input_hash,
            confidence,content_json FROM diagnostic_reports WHERE user_id=? AND period_start=?
            AND period_end=? ORDER BY version DESC LIMIT 20""", (USER_ID, start, end)).fetchall()
    return {"start": start, "end": end, "items": [
        {"id": row["id"], "version": row["version"], "created_at": row["created_at"],
         "model_name": row["model_name"], "prompt_version": row["prompt_version"],
         "input_hash": row["input_hash"], "confidence": row["confidence"],
         **json.loads(row["content_json"])} for row in rows]}
