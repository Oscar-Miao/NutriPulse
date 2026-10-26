from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.application.fitness.conflicts import refresh_day
from app.infrastructure.db.database import connect, row_dict, transaction
from app.infrastructure.devices.samples import related_days
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, new_id, number, utc_now, valid_date


SAMPLE_UNITS = {"active_energy": "kcal", "steps": "count", "heart_rate": "bpm",
                "body_weight": "kg", "body_fat": "percent"}


def connections() -> list[dict]:
    with connect() as db:
        return [dict(r) for r in db.execute("""SELECT c.id,c.provider,c.scopes_json,c.status,
            c.last_synced_at,(SELECT COUNT(*) FROM device_samples s WHERE s.connection_id=c.id)
            AS sample_count FROM device_connections c WHERE c.user_id=? ORDER BY c.rowid DESC""",
            (USER_ID,))]


def connect_device(data: dict) -> dict:
    provider = str(data.get("provider", "")).strip()
    require(provider in ("health_connect", "apple_health", "manual_device_import"), "设备来源无效")
    with transaction() as db:
        existing = db.execute("""SELECT id,status FROM device_connections WHERE user_id=? AND provider=?
            ORDER BY CASE status WHEN 'ACTIVE' THEN 0 WHEN 'REVOKED' THEN 1 ELSE 2 END,
            rowid DESC LIMIT 1""", (USER_ID, provider)).fetchone()
        if existing and existing["status"] == "ACTIVE":
            return {"id": existing["id"], "provider": provider, "status": "ACTIVE"}
        if existing and existing["status"] == "REVOKED":
            db.execute("""UPDATE device_connections SET status='ACTIVE',scopes_json=? WHERE id=?""",
                       (as_json(data.get("scopes", [])), existing["id"]))
            return {"id": existing["id"], "provider": provider, "status": "ACTIVE"}
        ident = new_id()
        db.execute("""INSERT INTO device_connections(id,user_id,provider,scopes_json,status)
            VALUES (?,?,?,?,?)""", (ident, USER_ID, provider, as_json(data.get("scopes", [])), "ACTIVE"))
    return {"id": ident, "provider": provider, "status": "ACTIVE"}


def import_samples(connection_id: str, data: dict) -> dict:
    samples = data.get("samples", [])
    require(isinstance(samples, list) and len(samples) <= 500, "单次最多导入 500 条样本")
    stage_active = data.get("stage_active_energy", False)
    require(type(stage_active) is bool, "活动样本分批状态无效")
    activate_dates = data.get("activate_active_dates", [])
    require(isinstance(activate_dates, list) and len(activate_dates) <= 31 and
            all(isinstance(day, str) for day in activate_dates), "活动样本激活日期无效")
    activate_dates = list(dict.fromkeys(valid_date(day) for day in activate_dates))
    batch_id = data.get("sync_batch_id")
    if stage_active or activate_dates:
        require(isinstance(batch_id, str) and 1 <= len(batch_id) <= 128,
                "分批同步标识无效")
    imported = duplicate = updated = 0
    affected_days: set[str] = set()
    changed_external_ids: set[str] = set()
    with transaction() as db:
        connection = db.execute("SELECT * FROM device_connections WHERE id=? AND user_id=? AND status='ACTIVE'",
                                (connection_id, USER_ID)).fetchone()
        if not connection:
            raise ApiError("NOT_FOUND", "设备连接不存在或已停用", 404)
        require(not (stage_active or activate_dates) or connection["provider"] == "health_connect",
                "仅 Health Connect 支持活动样本分批激活")
        timezone_name = db.execute("SELECT timezone FROM users WHERE id=?", (USER_ID,)).fetchone()[0]
        try:
            local_zone = ZoneInfo(timezone_name)
        except (ValueError, KeyError):
            local_zone = ZoneInfo("Asia/Shanghai")
        for sample in samples:
            require(isinstance(sample, dict), "设备样本无效")
            external_id = str(sample.get("external_id", "")).strip()
            sample_type = sample.get("sample_type")
            require(1 <= len(external_id) <= 128, "设备样本 ID 无效")
            require(sample_type in SAMPLE_UNITS, "设备样本类型无效")
            day = valid_date(sample.get("local_date"))
            value = number(sample.get("value"), "设备数值", 0, 1_000_000)
            existing = db.execute("""SELECT id,value,local_date,start_at,end_at,sample_type,
                pending_activation,import_batch_id FROM device_samples
                WHERE connection_id=? AND external_id=?""", (connection_id, external_id)).fetchone()
            if existing and existing["sample_type"] != sample_type:
                raise ApiError("VERSION_CONFLICT", "同一设备样本 ID 的类型不能改变", 409)
            stamp = str(sample.get("start_at") or (existing["start_at"] if existing else utc_now()))
            end_at = sample.get("end_at")
            if sample_type == "active_energy" and end_at is not None:
                try:
                    start_time = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    end_time = datetime.fromisoformat(str(end_at).replace("Z", "+00:00"))
                    require(start_time.tzinfo is not None and end_time.tzinfo is not None,
                            "活动样本时间必须包含时区")
                    start_time = start_time.astimezone(timezone.utc)
                    end_time = end_time.astimezone(timezone.utc)
                except ValueError:
                    raise ApiError("VALIDATION_ERROR", "活动样本时间格式无效")
                local_start = start_time.astimezone(local_zone)
                next_midnight = datetime.combine(date.fromisoformat(day) + timedelta(days=1),
                                                 datetime.min.time(), local_zone).astimezone(timezone.utc)
                require(local_start.date().isoformat() == day and start_time < end_time <= next_midnight and
                        (end_time - start_time).total_seconds() <= 86400,
                        "活动样本必须按用户时区拆分到单一自然日")
                stamp = start_time.isoformat()
                end_at = end_time.isoformat()
            elif end_at is not None:
                # Non-energy samples are point values; an interval here would be misleading.
                raise ApiError("VALIDATION_ERROR", "该设备样本类型不支持时间区间")
            staged = stage_active and sample_type == "active_energy" and end_at is not None
            marker = batch_id if staged else None
            if existing is None:
                db.execute("""INSERT INTO device_samples(id,connection_id,external_id,
                    sample_type,start_at,end_at,local_date,value,unit,pending_activation,
                    import_batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (new_id(), connection_id, external_id, sample_type, stamp,
                     end_at, day, value, SAMPLE_UNITS[sample_type], 1 if staged else 0, marker))
                imported += 1
                affected_days.add(day)
                changed_external_ids.add(external_id)
            elif (float(existing["value"]) != value or existing["local_date"] != day or
                  existing["start_at"] != stamp or existing["end_at"] != end_at or
                  existing["sample_type"] != sample_type):
                db.execute("""UPDATE device_samples SET value=?,local_date=?,start_at=?,end_at=?,
                    sample_type=?,unit=?,pending_activation=?,import_batch_id=? WHERE id=?""",
                    (value, day, stamp, end_at, sample_type, SAMPLE_UNITS[sample_type],
                     (0 if existing["pending_activation"] == 0 else 1) if staged else 0,
                     marker, existing["id"]))
                updated += 1
                affected_days.update((day, existing["local_date"]))
                changed_external_ids.add(external_id)
            else:
                duplicate += 1
                if staged and (existing["import_batch_id"] != marker or existing["pending_activation"] == 2):
                    db.execute("""UPDATE device_samples SET import_batch_id=?,
                        pending_activation=CASE WHEN pending_activation=2 THEN 1 ELSE pending_activation END
                        WHERE id=?""", (marker, existing["id"]))
                    affected_days.add(day)
                    changed_external_ids.add(external_id)
        for active_day in activate_dates:
            changed_external_ids.update(row[0] for row in db.execute(
                "SELECT external_id FROM device_samples WHERE connection_id=? AND local_date=?",
                (connection_id, active_day)))
            db.execute("""UPDATE device_samples SET pending_activation=2 WHERE connection_id=?
                AND sample_type='active_energy' AND local_date=?
                AND (end_at IS NULL OR COALESCE(import_batch_id,'')!=?)
                AND pending_activation!=2""", (connection_id, active_day, batch_id))
            db.execute("""UPDATE device_samples SET pending_activation=0 WHERE connection_id=?
                AND sample_type='active_energy' AND local_date=? AND end_at IS NOT NULL
                AND import_batch_id=? AND pending_activation!=0""",
                (connection_id, active_day, batch_id))
            affected_days.add(active_day)
        affected_days.update(related_days(db, USER_ID, connection["provider"], changed_external_ids))
        for affected_day in affected_days:
            db.execute("DELETE FROM daily_energy_snapshots WHERE user_id=? AND local_date=?",
                       (USER_ID, affected_day))
            refresh_day(db, affected_day)
        db.execute("UPDATE device_connections SET sync_cursor=?,last_synced_at=? WHERE id=?",
                   (data.get("sync_cursor"), utc_now(), connection_id))
        db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
                   (new_id(), "DeviceSamplesImported", connection_id, as_json({"count": imported, "updated": updated})))
    if imported or updated:
        _calibrate_body_measurements(connection_id)
    with connect() as db:
        pending = db.execute("""SELECT COUNT(*) FROM sync_conflicts WHERE user_id=?
            AND reason='TIME_OVERLAP' AND resolution IS NULL""", (USER_ID,)).fetchone()[0]
    return {"imported": imported, "updated": updated, "duplicates": duplicate,
            "pending_conflicts": int(pending)}


def _calibrate_body_measurements(connection_id: str) -> None:
    changed = False
    with transaction() as db:
        provider = db.execute("SELECT provider FROM device_connections WHERE id=?", (connection_id,)).fetchone()[0]
        weights = db.execute("""SELECT * FROM device_samples WHERE connection_id=? AND sample_type='body_weight'
            ORDER BY start_at""", (connection_id,)).fetchall()
        for weight in weights:
            if not 25 <= float(weight["value"]) <= 350:
                continue
            fat = db.execute("""SELECT value FROM device_samples WHERE connection_id=? AND sample_type='body_fat'
                AND local_date=? AND value BETWEEN 0 AND 100 ORDER BY start_at DESC LIMIT 1""",
                (connection_id, weight["local_date"])).fetchone()
            fat_value = float(fat["value"]) if fat else None
            existing = db.execute("SELECT id,weight_kg,body_fat_pct FROM body_measurements WHERE device_sample_id=?",
                                  (weight["id"],)).fetchone()
            if existing is None:
                db.execute("""INSERT INTO body_measurements(id,user_id,measured_at,weight_kg,body_fat_pct,
                    source_type,device_sample_id) VALUES (?,?,?,?,?,?,?)""",
                    (new_id(), USER_ID, weight["start_at"], float(weight["value"]), fat_value, provider, weight["id"]))
                changed = True
            elif float(existing["weight_kg"]) != float(weight["value"]) or existing["body_fat_pct"] != fat_value:
                db.execute("UPDATE body_measurements SET weight_kg=?,body_fat_pct=? WHERE id=?",
                           (float(weight["value"]), fat_value, existing["id"]))
                changed = True
    if changed:
        from app.application.profile.service import _refresh_target_if_ready
        _refresh_target_if_ready()


def disconnect(connection_id: str, delete_history: bool = False) -> dict:
    require(type(delete_history) is bool, "设备历史处理选项无效")
    removed_samples = removed_measurements = removed_targets = removed_reports = 0
    with transaction() as db:
        connection = db.execute("SELECT id,status,provider FROM device_connections WHERE id=? AND user_id=?",
                                (connection_id, USER_ID)).fetchone()
        if connection is None:
            raise ApiError("NOT_FOUND", "设备连接不存在", 404)
        source_ids = {row[0] for row in db.execute(
            "SELECT external_id FROM device_samples WHERE connection_id=?", (connection_id,))}
        days = related_days(db, USER_ID, connection["provider"], source_ids)
        if delete_history:
            sample_ids = "SELECT id FROM device_samples WHERE connection_id=?"
            measurement_ids = ("SELECT id FROM body_measurements WHERE user_id=? AND "
                               f"device_sample_id IN ({sample_ids})")
            removed_reports = db.execute("DELETE FROM diagnostic_reports WHERE user_id=?",
                                         (USER_ID,)).rowcount
            db.execute(f"DELETE FROM sync_conflicts WHERE user_id=? AND sample_id IN ({sample_ids})",
                       (USER_ID, connection_id))
            removed_targets = db.execute(
                f"DELETE FROM nutrition_targets WHERE user_id=? AND measurement_id IN ({measurement_ids})",
                (USER_ID, USER_ID, connection_id)).rowcount
            removed_measurements = db.execute(
                f"DELETE FROM body_measurements WHERE id IN ({measurement_ids})",
                (USER_ID, connection_id)).rowcount
            removed_samples = db.execute("DELETE FROM device_samples WHERE connection_id=?",
                                         (connection_id,)).rowcount
        db.execute("""UPDATE device_connections SET status='REVOKED',token_ref=NULL,
            sync_cursor=NULL,scopes_json='[]' WHERE id=?""", (connection_id,))
        for day in days:
            db.execute("DELETE FROM daily_energy_snapshots WHERE user_id=? AND local_date=?",
                       (USER_ID, day))
            refresh_day(db, day)
    target_recalculated = False
    if removed_measurements:
        from app.application.profile.service import _refresh_target_if_ready, get_profile
        _refresh_target_if_ready()
        target_recalculated = get_profile()["target"] is not None
    return {"id": connection_id, "status": "REVOKED", "history_retained": not delete_history,
            "removed_samples": removed_samples, "removed_measurements": removed_measurements,
            "removed_targets": removed_targets, "removed_diagnostics": removed_reports,
            "target_recalculated": target_recalculated}
