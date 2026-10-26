from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.exercise import MET_BY_INTENSITY, estimate_activity
from app.application.fitness.conflicts import refresh_day
from app.infrastructure.db.database import connect, row_dict, transaction
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, new_id, number, today, utc_now, valid_date


WORKOUT_TYPES = set(MET_BY_INTENSITY) | {"custom"}


def estimate_workout(data: dict) -> dict:
    workout_type = str(data.get("workout_type") or "").strip()
    require(workout_type in MET_BY_INTENSITY, "自定义运动需手动填写热量")
    intensity = data.get("intensity", "moderate")
    minutes = number(data.get("minutes"), "运动时长", 1, 1440)
    override = number(data["met_value"], "MET", 1, 25) if data.get("met_value") is not None else None
    with connect() as db:
        measurement = db.execute("""SELECT weight_kg FROM body_measurements WHERE user_id=?
            ORDER BY measured_at DESC,rowid DESC LIMIT 1""", (USER_ID,)).fetchone()
    weight = float(measurement[0]) if measurement else 70.0
    estimated = estimate_activity(workout_type, intensity, weight, minutes, override)
    return {"workout_type": workout_type, "intensity": intensity, "minutes": minutes,
            "weight_kg": weight, "weight_source": "measurement" if measurement else "demo_default",
            **estimated}


def list_exercises() -> list[dict]:
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM exercises ORDER BY category,name")]


def list_plans(level: str | None = None, goal_type: str | None = None) -> list[dict]:
    if level is not None:
        require(level in ("beginner", "intermediate", "advanced"), "训练水平筛选无效")
    if goal_type is not None:
        require(goal_type in ("fat_loss", "maintenance", "muscle_gain", "recovery"), "目标筛选无效")
    filters = ["status='PUBLISHED'"]
    values = []
    if level is not None:
        filters.append("level=?")
        values.append(level)
    if goal_type is not None:
        filters.append("goal_type=?")
        values.append(goal_type)
    with connect() as db:
        plans = [dict(r) for r in db.execute(
            f"SELECT * FROM training_plans WHERE {' AND '.join(filters)} ORDER BY code", values)]
        for plan in plans:
            plan["alternatives"] = json.loads(plan.pop("alternatives_json"))
            plan["days"] = [dict(r) for r in db.execute("SELECT * FROM plan_days WHERE plan_id=? AND week_no=1 ORDER BY day_no", (plan["id"],))]
    return plans


def enroll(plan_id: str, start_date: str | None = None) -> dict:
    day = valid_date(start_date or today())
    with transaction() as db:
        plan = db.execute("SELECT * FROM training_plans WHERE id=? AND status='PUBLISHED'", (plan_id,)).fetchone()
        if not plan:
            raise ApiError("NOT_FOUND", "训练计划不存在", 404)
        db.execute("""UPDATE user_plan_enrollments SET status='STOPPED',stopped_on=?
            WHERE user_id=? AND status='ACTIVE'""", (today(), USER_ID))
        ident = new_id()
        db.execute("""INSERT INTO user_plan_enrollments(id,user_id,plan_id,plan_version,start_date)
            VALUES (?,?,?,?,?)""", (ident, USER_ID, plan_id, plan["version"], day))
        _generate_schedule(db, ident, plan_id, day)
    return {"id": ident, "plan_id": plan_id, "start_date": day, "status": "ACTIVE"}


def _generate_schedule(db, enrollment_id: str, plan_id: str, start_date: str) -> None:
    start = date.fromisoformat(start_date)
    enrolled = db.execute("SELECT plan_version FROM user_plan_enrollments WHERE id=?",
                          (enrollment_id,)).fetchone()
    require(enrolled is not None, "跟练报名不存在")
    if enrolled[0] < 2:
        days = db.execute("""SELECT plan_day_id AS id,week_no,day_no,title,session_template_json
            FROM official_plan_template_history WHERE plan_id=? AND version=?
            ORDER BY week_no,day_no""", (plan_id, enrolled[0])).fetchall()
        if not days:
            raise ApiError("PLAN_TEMPLATE_MISSING", "旧版计划模板已丢失，请重新报名新版计划", 409)
    else:
        days = db.execute("""SELECT id,week_no,day_no,title,session_template_json FROM plan_days
            WHERE plan_id=? ORDER BY week_no,day_no""", (plan_id,)).fetchall()
    for day in days:
        scheduled = start + timedelta(days=(day["week_no"] - 1) * 7 + day["day_no"] - 1)
        session_id = new_id()
        db.execute("""INSERT INTO plan_session_instances(id,enrollment_id,plan_day_id,week_no,day_no,
            scheduled_date,title,template_json) VALUES (?,?,?,?,?,?,?,?)""",
            (session_id, enrollment_id, day["id"], day["week_no"], day["day_no"],
             scheduled.isoformat(), day["title"], day["session_template_json"]))
        # Old clients could attach only enrollment_id. Link a single unambiguous
        # completed workout from that scheduled date without guessing among many.
        legacy = db.execute("""SELECT id,end_at,workout_type,minutes FROM workout_sessions WHERE plan_instance_id=?
            AND local_date=? AND status='COMPLETED' AND plan_session_id IS NULL LIMIT 2""",
            (enrollment_id, scheduled.isoformat())).fetchall()
        if len(legacy) == 1:
            legacy_sets = [dict(row) for row in db.execute("""SELECT exercise_name,reps,duration_sec,completed_at FROM exercise_sets
                WHERE session_id=?""", (legacy[0]["id"],))]
            observed = [{"exercise_name": row["exercise_name"], "reps": row["reps"],
                         "duration_sec": row["duration_sec"],
                         "completed": row["completed_at"] is not None}
                        for row in legacy_sets]
            outcome = _plan_session_outcome(day["title"], json.loads(day["session_template_json"]),
                                            float(legacy[0]["minutes"]), observed)
            db.execute("UPDATE workout_sessions SET plan_session_id=? WHERE id=?", (session_id, legacy[0]["id"]))
            db.execute("""UPDATE plan_session_instances SET status=?,completed_at=? WHERE id=?""",
                       (outcome, legacy[0]["end_at"] or utc_now(), session_id))


def _session_dict(row) -> dict:
    session = dict(row)
    original = json.loads(session.pop("template_json"))
    replacements = json.loads(session.pop("overrides_json"))
    effective = list(original)
    for change in replacements:
        effective[change["index"]] = change["replacement"]
    session["exercises"] = effective
    session["original_exercises"] = original
    session["replacements"] = replacements
    session["minimum_duration_minutes"] = _cardio_minimum_minutes(session["title"], effective)
    return session


def _exercise_name(prescription: str) -> str:
    match = re.match(r"^(.*?)\s+\d+[×xX]\d+(?:[-–]\d+)?.*$", prescription)
    return match.group(1).strip() if match else prescription


def _cardio_minimum_minutes(title: str, prescriptions: list[str]) -> int | None:
    cardio_day = any(word in title for word in ("有氧", "间歇")) or any(
        "分钟" in item for item in prescriptions)
    if not cardio_day:
        return None
    minimum_minutes = 0
    for item in prescriptions:
        interval = re.search(r"(\d+)\s*分钟.*?\+\s*(\d+)\s*分钟.*?[×xX]\s*(\d+)", item)
        ordinary = re.search(r"(\d+)(?:\s*[-–]\s*\d+)?\s*分钟", item)
        if interval:
            minimum_minutes += (int(interval.group(1)) + int(interval.group(2))) * int(interval.group(3))
        elif ordinary:
            minimum_minutes += int(ordinary.group(1))
    return max(1, minimum_minutes)


def _plan_session_outcome(title: str, prescriptions: list[str],
                          minutes: float, sets: list[dict]) -> str:
    minimum_minutes = _cardio_minimum_minutes(title, prescriptions)
    if minimum_minutes is not None:
        return "COMPLETED" if minutes >= minimum_minutes else "PARTIAL"
    required: dict[tuple[str, bool], tuple[int, int]] = {}
    for item in prescriptions:
        match = re.match(r"^(.*?)\s+(\d+)[×xX](\d+)(?:[-–]\d+)?.*$", item)
        name = _exercise_name(item)
        count, minimum = (int(match.group(2)), int(match.group(3))) if match else (1, 1)
        timed = re.search(r"\d+\s*秒(?:/侧)?$", item) is not None
        key = (name, timed)
        prior_count, prior_minimum = required.get(key, (0, minimum))
        required[key] = (prior_count + count, max(prior_minimum, minimum))
    completed = {}
    for item in sets:
        name = item["exercise_name"]
        timed = item.get("duration_sec") is not None
        key = (name, timed)
        measured = int(item.get("duration_sec") or 0) if timed else int(item.get("reps") or 0)
        if item["completed"] and key in required and measured >= required[key][1]:
            completed[key] = completed.get(key, 0) + 1
    return "COMPLETED" if required and all(completed.get(key, 0) >= count
                                             for key, (count, _) in required.items()) else "PARTIAL"


def active_plan(day: str | None = None) -> dict | None:
    day = valid_date(day or today())
    with connect() as db:
        plan = row_dict(db.execute("""SELECT e.*,p.name,p.code,p.level,p.weeks,p.days_per_week
            FROM user_plan_enrollments e
            JOIN training_plans p ON p.id=e.plan_id WHERE e.user_id=? AND e.status='ACTIVE'
            ORDER BY e.created_at DESC LIMIT 1""", (USER_ID,)).fetchone())
        exists = db.execute("SELECT 1 FROM plan_session_instances WHERE enrollment_id=? LIMIT 1",
                            (plan["id"],)).fetchone() if plan else None
    if plan is None:
        return None
    if exists is None:  # Backfill enrollments made before migration 005.
        with transaction() as db:
            if db.execute("SELECT 1 FROM plan_session_instances WHERE enrollment_id=? LIMIT 1",
                          (plan["id"],)).fetchone() is None:
                _generate_schedule(db, plan["id"], plan["plan_id"], plan["start_date"])
    with connect() as db:
        rows = [_session_dict(row) for row in db.execute("""SELECT id,week_no,day_no,scheduled_date,title,
            template_json,overrides_json,status,completed_at FROM plan_session_instances
            WHERE enrollment_id=? ORDER BY scheduled_date""", (plan["id"],))]
    today_session = next((row for row in rows if row["scheduled_date"] == day), None)
    next_session = next((row for row in rows if row["scheduled_date"] >= day
                         and row["status"] == "SCHEDULED"), None)
    elapsed = (date.fromisoformat(day) - date.fromisoformat(plan["start_date"])).days
    current_week = max(1, min(plan["weeks"], elapsed // 7 + 1))
    plan["progress"] = {"total": len(rows),
                        "completed": sum(row["status"] == "COMPLETED" for row in rows),
                        "partial": sum(row["status"] == "PARTIAL" for row in rows),
                        "current_week": current_week}
    plan["today_session"] = today_session
    plan["next_session"] = next_session
    plan["week_sessions"] = [row for row in rows if row["week_no"] == current_week]
    return plan


def stop_active_plan() -> dict:
    plan = active_plan()
    if not plan:
        raise ApiError("NOT_FOUND", "当前没有正在跟练的计划", 404)
    with transaction() as db:
        stopped_on = today()
        db.execute("""UPDATE user_plan_enrollments SET status='STOPPED',stopped_on=?
            WHERE id=? AND user_id=?""", (stopped_on, plan["id"], USER_ID))
    return {"id": plan["id"], "status": "STOPPED", "stopped_on": stopped_on}


def replace_plan_exercise(session_id: str, data: dict) -> dict:
    index = data.get("index")
    require(type(index) is int and index >= 0, "请选择有效的计划动作")
    replacement = str(data.get("replacement") or "").strip()
    reason = str(data.get("reason") or "").strip()
    require(1 <= len(replacement) <= 100, "替换动作需为 1-100 字")
    require(2 <= len(reason) <= 200, "请填写 2-200 字的替换原因")
    with transaction() as db:
        row = db.execute("""SELECT s.* FROM plan_session_instances s
            JOIN user_plan_enrollments e ON e.id=s.enrollment_id
            WHERE s.id=? AND e.user_id=? AND e.status='ACTIVE'""", (session_id, USER_ID)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "正在跟练的计划训练不存在", 404)
        require(row["status"] == "SCHEDULED", "已完成的计划训练不能修改")
        session = _session_dict(row)
        require(index < len(session["exercises"]), "计划动作序号无效")
        current = session["exercises"][index]
        require(replacement != current, "替换动作不能与当前动作相同")
        history = session["replacements"]
        history.append({"index": index, "from": current, "replacement": replacement,
                        "reason": reason, "created_at": utc_now()})
        db.execute("UPDATE plan_session_instances SET overrides_json=? WHERE id=?",
                   (as_json(history), session_id))
        return _session_dict(db.execute("SELECT * FROM plan_session_instances WHERE id=?",
                                        (session_id,)).fetchone())


def create_workout(data: dict, idempotency_key: str | None = None) -> dict:
    day = valid_date(data.get("local_date") or today())
    workout_type = str(data.get("workout_type") or "").strip()
    require(workout_type in WORKOUT_TYPES, "运动类型无效")
    intensity = data.get("intensity", "moderate") if workout_type != "custom" else None
    require(intensity is None or intensity in ("low", "moderate", "high"), "运动强度无效")
    custom_name = str(data.get("custom_name") or "").strip() if workout_type == "custom" else None
    if workout_type == "custom":
        require(custom_name is not None and 1 <= len(custom_name) <= 100, "请填写自定义运动名称")
        require(data.get("kcal") is not None, "自定义运动需要填写消耗热量")
    minutes = number(data.get("minutes"), "运动时长", 1, 1440)
    if data.get("kcal") is not None:
        kcal = number(data["kcal"], "运动消耗", 0, 10000)
        kcal_source = "MANUAL"
        met = None
        calculation_version = "manual-v1"
    else:
        estimate = estimate_workout(data)
        met = estimate["met_value"]
        kcal = estimate["kcal"]
        kcal_source = "MET"
        calculation_version = estimate["calculation_version"]
    sets = data.get("sets", [])
    require(isinstance(sets, list) and len(sets) <= 100, "训练组列表无效")
    validated_sets = []
    for index, item in enumerate(sets):
        require(isinstance(item, dict), "训练组无效")
        name = str(item.get("exercise_name") or "").strip()
        require(1 <= len(name) <= 100, "动作名称无效")
        set_no_value = number(item.get("set_no", index + 1), "组号", 1, 100)
        reps_value = number(item.get("reps", 0), "次数", 0, 1000)
        duration_value = number(item["duration_sec"], "持续秒数", 1, 3600) \
            if item.get("duration_sec") is not None else None
        require(set_no_value.is_integer() and reps_value.is_integer() and
                (duration_value is None or duration_value.is_integer()),
                "组号、次数与持续秒数必须是整数")
        set_no = int(set_no_value)
        reps = int(reps_value)
        duration_sec = int(duration_value) if duration_value is not None else None
        require(not (reps > 0 and duration_sec is not None), "次数与持续秒数只能填写一种")
        # A null/missing load means a bodyweight exercise, not a measured 0 kg load.
        weight_kg = number(item["weight_kg"], "重量", 0, 1000) \
            if item.get("weight_kg") is not None else None
        completed = bool(item.get("completed", True))
        require(not completed or reps > 0 or duration_sec is not None,
                "已完成组须填写次数或持续秒数")
        rpe = number(item["rpe"], "主观强度 RPE", 0, 10) if item.get("rpe") is not None else None
        rir = number(item["rir"], "保留次数 RIR", 0, 10) if item.get("rir") is not None else None
        validated_sets.append({"id": new_id(), "exercise_id": item.get("exercise_id"),
                               "exercise_name": name, "set_no": set_no, "weight_kg": weight_kg,
                               "reps": reps, "duration_sec": duration_sec, "rpe": rpe, "rir": rir,
                               "completed": completed,
                               "volume": round(weight_kg * reps, 1) if completed and weight_kg is not None else 0.0})
    session_id = data.get("plan_session_id")
    require(session_id is None or isinstance(session_id, str), "计划训练标识无效")
    require(session_id is not None or data.get("plan_instance_id") is None,
            "计划训练必须指定计划日实例")
    start_raw, end_raw = data.get("start_at"), data.get("end_at")
    require((start_raw is None) == (end_raw is None), "训练开始和结束时间需同时填写")
    if start_raw is not None:
        try:
            start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
            require(start.tzinfo is not None and end.tzinfo is not None, "训练时间必须包含时区")
            start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        except ValueError:
            raise ApiError("VALIDATION_ERROR", "训练时间格式无效")
        require(0 < (end - start).total_seconds() <= 86400, "训练时间窗无效")
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
    with connect() as db:
        timezone_name = db.execute("SELECT timezone FROM users WHERE id=?", (USER_ID,)).fetchone()[0]
    try:
        local_zone = ZoneInfo(timezone_name)
    except (ValueError, KeyError):
        local_zone = ZoneInfo("Asia/Shanghai")
    if start_raw is not None:
        require(start.astimezone(local_zone).date().isoformat() == day and
                (end - timedelta(microseconds=1)).astimezone(local_zone).date().isoformat() == day,
                "跨日训练需拆分为各自然日记录")
    elif start.astimezone(local_zone).date().isoformat() != day:
        # Historical/future or midnight-spanning entries lack an asserted
        # interval; preserve their duration but do not pretend to know overlap.
        start = end
    start_at = start.isoformat()
    end_at = end.isoformat()
    ident = new_id()
    with transaction() as db:
        # Recheck under the write lock: concurrent retries must return the
        # committed workout before plan-session state validation runs.
        if idempotency_key:
            old = db.execute("SELECT id FROM workout_sessions WHERE idempotency_key=?",
                             (idempotency_key,)).fetchone()
            if old:
                return get_workout(old["id"])
        enrollment_id = None
        if session_id is not None:
            scheduled = db.execute("""SELECT s.enrollment_id,s.scheduled_date,s.status,s.title,s.template_json,
                s.overrides_json,e.status AS enrollment_status
                FROM plan_session_instances s JOIN user_plan_enrollments e ON e.id=s.enrollment_id
                WHERE s.id=? AND e.user_id=?""", (session_id, USER_ID)).fetchone()
            if scheduled is None:
                raise ApiError("NOT_FOUND", "计划训练不存在", 404)
            require(scheduled["enrollment_status"] == "ACTIVE", "该跟练计划已停止")
            require(scheduled["scheduled_date"] == day, "训练日期与计划日不一致")
            require(scheduled["status"] == "SCHEDULED", "该计划训练已经完成")
            enrollment_id = scheduled["enrollment_id"]
            require(data.get("plan_instance_id") in (None, enrollment_id), "计划报名标识不一致")
            effective = _session_dict(scheduled)["exercises"]
            allowed = {_exercise_name(item) for item in effective}
            require(all(item["exercise_name"] in allowed for item in validated_sets),
                    "训练动作不在当前计划日中；请先替换动作并记录原因")
            session_outcome = _plan_session_outcome(scheduled["title"], effective,
                                                    minutes, validated_sets)
        db.execute("""INSERT INTO workout_sessions(id,user_id,local_date,start_at,end_at,workout_type,status,
            minutes,met_value,kcal,kcal_source,plan_instance_id,idempotency_key,custom_name,plan_session_id,
            intensity,calculation_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ident, USER_ID, day, start_at, end_at,
             workout_type, "COMPLETED", minutes, met, kcal, kcal_source, enrollment_id, idempotency_key,
             custom_name, session_id, intensity, calculation_version))
        for item in validated_sets:
            db.execute("""INSERT INTO exercise_sets(id,session_id,exercise_id,exercise_name,set_no,weight_kg,
                reps,duration_sec,rpe,rir,completed_at,volume) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["id"], ident, item["exercise_id"], item["exercise_name"], item["set_no"],
                 item["weight_kg"], item["reps"], item["duration_sec"], item["rpe"], item["rir"],
                 utc_now() if item["completed"] else None, item["volume"]))
        if session_id is not None:
            db.execute("""UPDATE plan_session_instances SET status=?,completed_at=?
                WHERE id=? AND status='SCHEDULED'""", (session_outcome, utc_now(), session_id))
        db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
                   (new_id(), "WorkoutCompleted", ident, as_json({"local_date": day, "kcal": kcal})))
        refresh_day(db, day)
    return get_workout(ident)


def get_workout(ident: str) -> dict:
    with connect() as db:
        workout = row_dict(db.execute("SELECT * FROM workout_sessions WHERE id=? AND user_id=?", (ident, USER_ID)).fetchone())
        if not workout:
            raise ApiError("NOT_FOUND", "运动记录不存在", 404)
        workout["sets"] = [dict(r) for r in db.execute("SELECT * FROM exercise_sets WHERE session_id=? ORDER BY rowid", (ident,))]
        if workout["plan_session_id"]:
            plan_day = db.execute("SELECT title FROM plan_session_instances WHERE id=?",
                                  (workout["plan_session_id"],)).fetchone()
            workout["plan_session_title"] = plan_day["title"] if plan_day else None
    workout["total_volume"] = round(sum(float(item["volume"]) for item in workout["sets"]), 1)
    return workout


def list_workouts(day: str) -> list[dict]:
    valid_date(day)
    with connect() as db:
        ids = [r[0] for r in db.execute("SELECT id FROM workout_sessions WHERE user_id=? AND local_date=? ORDER BY created_at DESC", (USER_ID, day))]
    return [get_workout(ident) for ident in ids]
