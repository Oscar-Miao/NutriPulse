"""Single-user data portability and explicitly confirmed category erasure.

Only fixed SQL templates are used. Public food, recipe, exercise and article
catalogues are deliberately excluded from personal exports and erasure.
"""

from __future__ import annotations

import json
import logging

from app.infrastructure.db.database import connect, transaction
from app.shared.errors import require
from app.shared.util import USER_ID, utc_now


EXPORT_QUERIES = {
    "users": "SELECT * FROM users WHERE id=?",
    "profiles": "SELECT * FROM profiles WHERE user_id=?",
    "body_measurements": "SELECT * FROM body_measurements WHERE user_id=? ORDER BY measured_at",
    "goals": "SELECT * FROM goals WHERE user_id=? ORDER BY start_date",
    "nutrition_targets": "SELECT * FROM nutrition_targets WHERE user_id=? ORDER BY effective_from",
    "user_allergies": "SELECT * FROM user_allergies WHERE user_id=?",
    "user_dietary_restrictions": "SELECT * FROM user_dietary_restrictions WHERE user_id=?",
    "user_preferences": "SELECT * FROM user_preferences WHERE user_id=?",
    "dining_preferences": "SELECT * FROM dining_preferences WHERE user_id=?",
    "training_profiles": "SELECT * FROM training_profiles WHERE user_id=?",
    "meals": "SELECT * FROM meals WHERE user_id=? ORDER BY local_date",
    "meal_items": "SELECT i.* FROM meal_items i JOIN meals m ON m.id=i.meal_id WHERE m.user_id=?",
    "water_logs": "SELECT * FROM water_logs WHERE user_id=? ORDER BY local_date",
    "workout_sessions": "SELECT * FROM workout_sessions WHERE user_id=? ORDER BY local_date",
    "exercise_sets": "SELECT s.* FROM exercise_sets s JOIN workout_sessions w ON w.id=s.session_id WHERE w.user_id=?",
    "user_plan_enrollments": "SELECT * FROM user_plan_enrollments WHERE user_id=?",
    "plan_session_instances": """SELECT s.* FROM plan_session_instances s
        JOIN user_plan_enrollments e ON e.id=s.enrollment_id WHERE e.user_id=? ORDER BY s.scheduled_date""",
    # Never export a credential reference even when it is currently unused.
    "device_connections": """SELECT id,user_id,provider,external_user_ref,scopes_json,
        sync_cursor,status,last_synced_at FROM device_connections WHERE user_id=?""",
    "device_samples": """SELECT s.* FROM device_samples s JOIN device_connections c
        ON c.id=s.connection_id WHERE c.user_id=? ORDER BY s.local_date""",
    "sync_conflicts": "SELECT * FROM sync_conflicts WHERE user_id=?",
    "food_scan_jobs": "SELECT * FROM food_scan_jobs WHERE user_id=?",
    "media_assets": "SELECT * FROM media_assets WHERE owner_user_id=?",
    "recommendation_sessions": "SELECT * FROM recommendation_sessions WHERE user_id=?",
    "recommendation_items": """SELECT i.* FROM recommendation_items i
        JOIN recommendation_sessions s ON s.id=i.session_id WHERE s.user_id=?""",
    "recommendation_feedback": "SELECT * FROM recommendation_feedback WHERE user_id=?",
    "chat_sessions": "SELECT * FROM chat_sessions WHERE user_id=?",
    "chat_messages": """SELECT m.* FROM chat_messages m JOIN chat_sessions s
        ON s.id=m.session_id WHERE s.user_id=?""",
    "agent_runs": "SELECT * FROM agent_runs WHERE user_id=?",
    "diagnostic_reports": "SELECT * FROM diagnostic_reports WHERE user_id=?",
    "daily_energy_snapshots": "SELECT * FROM daily_energy_snapshots WHERE user_id=?",
    "audit_logs": "SELECT * FROM audit_logs WHERE user_id=?",
    # The demo has exactly one local user; outbox events have no user_id.
    "outbox_events": "SELECT * FROM outbox_events",
}

EXPORT_GROUPS = {
    "profile": ("users", "profiles", "body_measurements", "goals", "nutrition_targets",
                "user_allergies", "user_dietary_restrictions", "user_preferences",
                "dining_preferences", "training_profiles"),
    "diet": ("meals", "meal_items", "water_logs"),
    "fitness": ("workout_sessions", "exercise_sets", "user_plan_enrollments",
                "plan_session_instances",
                "device_connections", "device_samples", "sync_conflicts"),
    "agent": ("food_scan_jobs", "media_assets", "recommendation_sessions",
              "recommendation_items", "recommendation_feedback", "chat_sessions", "chat_messages", "agent_runs"),
    "analytics": ("diagnostic_reports", "daily_energy_snapshots"),
}

IMPACTS = {
    "diet": "清空四餐及饮水记录；同时清空识餐、推荐、对话和诊断等相关衍生数据。运动和个人档案保留。",
    "fitness": "清空运动、训练计划、设备连接及样本；导入的身体测量会清除。相关推荐、对话和诊断也会清空。",
    "agent": "清空识餐任务、推荐、对话、Agent 运行记录及诊断；已经确认的餐食和运动账本保留。",
    "profile": "重置基础资料、目标、身体测量、饮食/训练偏好并断开设备；相关 AI 与分析记录清空，饮食和运动账本保留。",
    "all": "清空本地用户的全部个人数据并重建空白档案；公共食物、菜谱、训练计划和资讯库保留。",
}


def _category(value: str) -> str:
    require(value in IMPACTS, "数据类别无效")
    return value


def _tables_for_export(category: str) -> list[str]:
    if category == "all":
        return list(EXPORT_QUERIES)
    names = []
    if category == "profile":
        names += list(EXPORT_GROUPS["profile"])
        names += ["device_connections", "device_samples", "sync_conflicts"]
    elif category == "fitness":
        names += list(EXPORT_GROUPS["fitness"])
        # Device-derived measurements and targets can be invalidated by erasure.
        names += ["body_measurements", "nutrition_targets"]
    elif category == "diet":
        names += list(EXPORT_GROUPS["diet"])
    names += list(EXPORT_GROUPS["agent"] + EXPORT_GROUPS["analytics"])
    names.append("outbox_events")
    return list(dict.fromkeys(names))


def _read_json_columns(row: dict) -> dict:
    for key, value in list(row.items()):
        if key.endswith("_json") and isinstance(value, str):
            try:
                row[key[:-5]] = json.loads(value)
                del row[key]
            except ValueError:
                pass
    return row


def export_data(category: str) -> dict:
    category = _category(category)
    with connect() as db:
        db.execute("BEGIN")
        tables = {}
        for name in _tables_for_export(category):
            args = () if name == "outbox_events" else (USER_ID,)
            tables[name] = [_read_json_columns(dict(row)) for row in db.execute(EXPORT_QUERIES[name], args)]
    return {"format": "nutripulse-personal-data-v1", "exported_at": utc_now(),
            "category": category, "tables": tables,
            "notes": ["这是本地数据库记录的 JSON 副本，不含访问令牌。",
                      "公共食品、训练计划和资讯库不属于个人数据，因此不在此文件中。"]}


def _counts(db, category: str) -> dict:
    if category == "all":
        names = list(EXPORT_QUERIES)
    elif category == "agent":
        names = list(EXPORT_GROUPS["agent"] + EXPORT_GROUPS["analytics"])
    elif category == "diet":
        names = list(EXPORT_GROUPS["diet"] + EXPORT_GROUPS["agent"] + EXPORT_GROUPS["analytics"])
    elif category == "fitness":
        names = list(EXPORT_GROUPS["fitness"] + EXPORT_GROUPS["agent"] + EXPORT_GROUPS["analytics"])
    else:
        names = list(EXPORT_GROUPS["profile"] +
                     ("device_connections", "device_samples", "sync_conflicts") +
                     EXPORT_GROUPS["agent"] + EXPORT_GROUPS["analytics"])
    names.append("outbox_events")
    counts = {}
    for name in dict.fromkeys(names):
        query = EXPORT_QUERIES[name]
        args = () if name == "outbox_events" else (USER_ID,)
        counts[name] = db.execute(f"SELECT COUNT(*) FROM ({query})", args).fetchone()[0]
    if category == "fitness":
        counts["imported_body_measurements"] = db.execute("""SELECT COUNT(*) FROM body_measurements
            WHERE user_id=? AND device_sample_id IN (SELECT s.id FROM device_samples s
            JOIN device_connections c ON c.id=s.connection_id WHERE c.user_id=?)""",
            (USER_ID, USER_ID)).fetchone()[0]
        if counts["imported_body_measurements"]:
            counts["nutrition_targets"] = db.execute("SELECT COUNT(*) FROM nutrition_targets WHERE user_id=?",
                                                      (USER_ID,)).fetchone()[0]
    return counts


def deletion_preview(category: str) -> dict:
    category = _category(category)
    with connect() as db:
        counts = _counts(db, category)
    return {"category": category, "impact": IMPACTS[category], "counts": counts,
            "record_count": sum(counts.values()), "confirmation_phrase": f"DELETE_{category.upper()}",
            "recoverable": False}


def _clear_agent(db) -> None:
    db.execute("DELETE FROM diagnostic_reports WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM food_scan_jobs WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM media_assets WHERE owner_user_id=?", (USER_ID,))
    db.execute("DELETE FROM recommendation_feedback WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM recommendation_sessions WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM chat_sessions WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM agent_runs WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM daily_energy_snapshots WHERE user_id=?", (USER_ID,))


def _clear_devices(db) -> int:
    db.execute("DELETE FROM sync_conflicts WHERE user_id=?", (USER_ID,))
    imported = db.execute("""DELETE FROM body_measurements WHERE user_id=? AND device_sample_id IN
        (SELECT s.id FROM device_samples s JOIN device_connections c ON c.id=s.connection_id
         WHERE c.user_id=?)""", (USER_ID, USER_ID)).rowcount
    db.execute("DELETE FROM device_connections WHERE user_id=?", (USER_ID,))
    return imported


def _clear_fitness(db) -> bool:
    db.execute("DELETE FROM workout_sessions WHERE user_id=?", (USER_ID,))
    db.execute("DELETE FROM user_plan_enrollments WHERE user_id=?", (USER_ID,))
    removed_measurements = _clear_devices(db)
    if removed_measurements:
        db.execute("DELETE FROM nutrition_targets WHERE user_id=?", (USER_ID,))
    return bool(removed_measurements)


def _clear_profile(db) -> None:
    _clear_devices(db)
    for table in ("nutrition_targets", "body_measurements", "goals", "user_allergies",
                  "user_dietary_restrictions", "user_preferences", "dining_preferences"):
        db.execute(f"DELETE FROM {table} WHERE user_id=?", (USER_ID,))
    db.execute("""UPDATE profiles SET birth_date=NULL,formula_sex=NULL,height_cm=NULL,
        activity_level='light',profile_version=profile_version+1,updated_at=CURRENT_TIMESTAMP
        WHERE user_id=?""", (USER_ID,))
    db.execute("UPDATE users SET display_name='我',updated_at=CURRENT_TIMESTAMP WHERE id=?", (USER_ID,))
    db.execute("""UPDATE training_profiles SET level='beginner',days_per_week=3,
        session_minutes=45,active_kcal_goal=300,equipment_json='[]',limitations_json='[]',updated_at=CURRENT_TIMESTAMP
        WHERE user_id=?""", (USER_ID,))


def delete_data(category: str, confirmation_phrase: str) -> dict:
    category = _category(category)
    require(confirmation_phrase == f"DELETE_{category.upper()}", "确认短语不匹配，未删除任何数据")
    refresh_target = False
    with transaction() as db:
        counts = _counts(db, category)
        if category in ("diet", "fitness", "agent", "profile", "all"):
            _clear_agent(db)
        if category in ("diet", "all"):
            db.execute("DELETE FROM meals WHERE user_id=?", (USER_ID,))
            db.execute("DELETE FROM water_logs WHERE user_id=?", (USER_ID,))
        if category in ("fitness", "all"):
            refresh_target = _clear_fitness(db) and category == "fitness"
        if category in ("profile", "all"):
            _clear_profile(db)
        if category == "all":
            db.execute("DELETE FROM audit_logs WHERE user_id=?", (USER_ID,))
            db.execute("DELETE FROM users WHERE id=?", (USER_ID,))
            db.execute("INSERT INTO users(id,display_name) VALUES (?, '我')", (USER_ID,))
            db.execute("INSERT INTO profiles(user_id) VALUES (?)", (USER_ID,))
            db.execute("INSERT INTO training_profiles(user_id) VALUES (?)", (USER_ID,))
        # Single-user outbox can contain deleted entities and dates.
        db.execute("DELETE FROM outbox_events")
    target_recalculated = None
    if refresh_target:
        from app.application.profile.service import _refresh_target_if_ready
        try:
            _refresh_target_if_ready()
            target_recalculated = True
        except Exception:
            # Erasure has already committed; report the secondary failure
            # rather than misrepresenting the deletion as rolled back.
            logging.error("target recalculation failed after fitness erasure")
            target_recalculated = False
    return {"category": category, "deleted_counts": counts,
            "deleted_at": utc_now(), "recoverable": False,
            "target_recalculated": target_recalculated}
