from __future__ import annotations

from app.domain.activity import overlap_seconds
from app.infrastructure.db.database import connect, transaction
from app.infrastructure.devices.samples import effective_samples
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, new_id, utc_now, valid_date


RESOLUTIONS = {"KEEP_DEVICE", "KEEP_MANUAL", "MERGE_NON_OVERLAPPING"}


def refresh_day(db, day: str) -> int:
    """Materialize only demonstrable interval overlaps; keep prior choices if unchanged."""
    day = valid_date(day)
    all_samples = effective_samples(db, USER_ID, "active_energy", day, day)
    provider_totals: dict[str, float] = {}
    for sample in all_samples:
        provider_totals[sample["provider"]] = provider_totals.get(sample["provider"], 0.0) + float(sample["value"])
    chosen = min(provider_totals, key=lambda name: (-provider_totals[name], name)) if provider_totals else None
    samples = [sample for sample in all_samples if sample["provider"] == chosen]
    # A coarse aggregate in the selected provider prevents interval-level
    # reasoning for this date; do not show a falsely precise conflict.
    if any(overlap_seconds(sample["start_at"], sample["end_at"],
                           sample["start_at"], sample["end_at"]) <= 0 for sample in samples):
        samples = []
    workouts = db.execute("""SELECT id,start_at,end_at FROM workout_sessions
        WHERE user_id=? AND local_date=? AND status='COMPLETED'""",
        (USER_ID, day)).fetchall()
    active_pairs = set()
    for sample in samples:
        for workout in workouts:
            overlap = overlap_seconds(sample["start_at"], sample["end_at"],
                                      workout["start_at"], workout["end_at"])
            if overlap <= 0:
                continue
            pair = (sample["id"], workout["id"])
            active_pairs.add(pair)
            existing = db.execute("""SELECT id,overlap_seconds,resolution FROM sync_conflicts
                WHERE sample_id=? AND domain_record_id=? AND reason='TIME_OVERLAP'""", pair).fetchone()
            if existing is None:
                db.execute("""INSERT INTO sync_conflicts(id,user_id,sample_id,domain_record_id,
                    reason,overlap_seconds) VALUES (?,?,?,?,'TIME_OVERLAP',?)""",
                    (new_id(), USER_ID, *pair, overlap))
            elif float(existing["overlap_seconds"]) != overlap:
                # A changed time window invalidates an earlier user decision.
                db.execute("""UPDATE sync_conflicts SET overlap_seconds=?,resolution=NULL,resolved_at=NULL
                    WHERE id=?""", (overlap, existing["id"]))
            elif existing["resolution"] == "NO_LONGER_OVERLAPS":
                db.execute("UPDATE sync_conflicts SET resolution=NULL,resolved_at=NULL WHERE id=?",
                           (existing["id"],))
    former = db.execute("""SELECT sc.id,sc.sample_id,sc.domain_record_id FROM sync_conflicts sc
        LEFT JOIN device_samples s ON s.id=sc.sample_id
        LEFT JOIN workout_sessions w ON w.id=sc.domain_record_id
        WHERE sc.user_id=? AND sc.reason='TIME_OVERLAP'
          AND (s.local_date=? OR w.local_date=?)""", (USER_ID, day, day)).fetchall()
    for row in former:
        if (row["sample_id"], row["domain_record_id"]) not in active_pairs:
            db.execute("""UPDATE sync_conflicts SET resolution='NO_LONGER_OVERLAPS',resolved_at=?
                WHERE id=? AND resolution IS NOT 'NO_LONGER_OVERLAPS'""", (utc_now(), row["id"]))
    return sum(1 for row in db.execute("""SELECT id FROM sync_conflicts WHERE user_id=?
        AND reason='TIME_OVERLAP' AND resolution IS NULL""", (USER_ID,)))


def list_conflicts(day: str | None = None, include_resolved: bool = False) -> list[dict]:
    if day is not None:
        valid_date(day)
    with connect() as db:
        rows = db.execute("""SELECT sc.*,s.local_date,s.value AS device_kcal,s.start_at AS device_start_at,
            s.end_at AS device_end_at,c.provider,w.kcal AS manual_kcal,w.workout_type,
            w.start_at AS workout_start_at,w.end_at AS workout_end_at
            FROM sync_conflicts sc JOIN device_samples s ON s.id=sc.sample_id
            JOIN device_connections c ON c.id=s.connection_id
            JOIN workout_sessions w ON w.id=sc.domain_record_id
            WHERE sc.user_id=? AND c.status IN ('ACTIVE','REVOKED') AND s.pending_activation=0
              AND sc.reason='TIME_OVERLAP'
              AND (? IS NULL OR s.local_date=?)
              AND (?=1 OR sc.resolution IS NULL)
            ORDER BY s.local_date DESC,s.start_at DESC""",
            (USER_ID, day, day, int(include_resolved))).fetchall()
        if not rows:
            return []
        days = {row["local_date"] for row in rows}
        if len(days) <= 30:
            effective_ids = {sample["id"] for sample_day in days for sample in
                effective_samples(db, USER_ID, "active_energy", sample_day, sample_day)}
        else:
            effective_ids = {sample["id"] for sample in effective_samples(
                db, USER_ID, "active_energy", min(days), max(days))}
    return [dict(row) for row in rows if row["sample_id"] in effective_ids][:100]


def resolve_conflict(conflict_id: str, resolution: str) -> dict:
    require(resolution in RESOLUTIONS, "冲突处置方式无效")
    with transaction() as db:
        row = db.execute("""SELECT sc.id,sc.resolution,sc.sample_id,sc.domain_record_id,
            s.local_date,s.start_at AS device_start_at,s.end_at AS device_end_at,
            s.pending_activation,
            w.start_at AS workout_start_at,w.end_at AS workout_end_at,c.status AS connection_status
            FROM sync_conflicts sc JOIN device_samples s ON s.id=sc.sample_id
            JOIN device_connections c ON c.id=s.connection_id
            JOIN workout_sessions w ON w.id=sc.domain_record_id
            WHERE sc.id=? AND sc.user_id=? AND sc.reason='TIME_OVERLAP'""",
            (conflict_id, USER_ID)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "运动同步冲突不存在", 404)
        effective_ids = {sample["id"] for sample in effective_samples(
            db, USER_ID, "active_energy", row["local_date"], row["local_date"])}
        require(row["sample_id"] in effective_ids and
                overlap_seconds(row["device_start_at"], row["device_end_at"],
                                row["workout_start_at"], row["workout_end_at"]) > 0,
                "该冲突已失效，请刷新列表", "VERSION_CONFLICT")
        db.execute("UPDATE sync_conflicts SET resolution=?,resolved_at=? WHERE id=?",
                   (resolution, utc_now(), conflict_id))
        # The choice changes activity energy without changing source ledger rows.
        db.execute("DELETE FROM daily_energy_snapshots WHERE user_id=? AND local_date=?",
                   (USER_ID, row["local_date"]))
    return {"id": conflict_id, "resolution": resolution, "local_date": row["local_date"]}
