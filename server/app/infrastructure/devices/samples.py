from __future__ import annotations

import sqlite3


def effective_samples(db: sqlite3.Connection, user_id: str, sample_type: str,
                      start: str | None = None, end: str | None = None) -> list[dict]:
    """Return one canonical source row per provider/type/external ID.

    Older clients could create a fresh connection after revocation. Their raw
    rows remain exportable, while the newest live row wins the ledger. During
    a staged Health Connect batch, the previous finalized row wins until the
    replacement is activated; a stale (pending=2) replacement still hides it.
    """
    # Rank all dates for only the external IDs seen in the requested range.
    # This handles cross-day corrections without sorting a five-year ledger
    # for every one-day dashboard request.
    if start is not None and end is not None:
        candidate_cte = """WITH candidate_keys AS (
            SELECT DISTINCT s.external_id FROM device_samples s
            JOIN device_connections c ON c.id=s.connection_id
            WHERE c.user_id=? AND c.status IN ('ACTIVE','REVOKED')
              AND s.sample_type=? AND s.local_date BETWEEN ? AND ?
        )"""
        candidate_join = "JOIN candidate_keys k ON k.external_id=s.external_id"
        date_filter = " AND local_date BETWEEN ? AND ?"
        params = (user_id, sample_type, start, end, user_id, sample_type, start, end)
    else:
        candidate_cte = candidate_join = date_filter = ""
        params = (user_id, sample_type)
    rows = db.execute(f"""{candidate_cte} SELECT * FROM (
        SELECT s.*,c.provider,c.last_synced_at,c.status AS connection_status,
            ROW_NUMBER() OVER (
                PARTITION BY c.provider,s.sample_type,s.external_id
                ORDER BY CASE WHEN s.pending_activation=1 THEN 1 ELSE 0 END,
                    CASE WHEN c.status='ACTIVE' THEN 0 ELSE 1 END,
                    c.rowid DESC,s.rowid DESC
            ) AS source_rank
        FROM device_samples s JOIN device_connections c ON c.id=s.connection_id
        {candidate_join}
        WHERE c.user_id=? AND c.status IN ('ACTIVE','REVOKED')
          AND s.sample_type=?
    ) WHERE source_rank=1 AND pending_activation=0{date_filter}""", params).fetchall()
    return [dict(row) for row in rows]


def related_days(db: sqlite3.Connection, user_id: str, provider: str,
                 external_ids: set[str]) -> set[str]:
    """Days whose canonical sample may change when these source IDs change."""
    days: set[str] = set()
    identifiers = sorted(external_ids)
    for offset in range(0, len(identifiers), 400):
        batch = identifiers[offset:offset + 400]
        placeholders = ",".join("?" for _ in batch)
        for row in db.execute(f"""SELECT DISTINCT s.local_date FROM device_samples s
            JOIN device_connections c ON c.id=s.connection_id
            WHERE c.user_id=? AND c.provider=? AND s.external_id IN ({placeholders})""",
            (user_id, provider, *batch)):
            days.add(row[0])
    return days
