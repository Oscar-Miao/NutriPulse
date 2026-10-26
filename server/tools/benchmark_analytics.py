"""Disposable SQLite benchmark for the PRD's five-year Demo capacity.

Run from server/: python tools/benchmark_analytics.py --runs 5
Only a TemporaryDirectory database is created; the configured production DB is never opened.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.analytics.service import energy_series, macro_summary
from app.infrastructure.db.database import connect, migrate
from app.infrastructure.db.seed import seed


FIRST_DAY = date(2022, 1, 1)
SPAN_DAYS = 1826


def ident(prefix: str, index: int) -> str:
    return prefix + f"{index:031x}"


def insert_batches(db, sql: str, rows, size: int = 2000) -> None:
    chunk = []
    for row in rows:
        chunk.append(row)
        if len(chunk) == size:
            db.executemany(sql, chunk)
            chunk.clear()
    if chunk:
        db.executemany(sql, chunk)


def populate(meal_items: int, workout_sessions: int, sets_per_workout: int,
             device_samples: int) -> None:
    day = lambda index: (FIRST_DAY + timedelta(days=index % SPAN_DAYS)).isoformat()
    meal_count = math.ceil(meal_items / 10)
    with connect() as db:
        db.execute("PRAGMA synchronous=OFF")  # Synthetic data generation only.
        db.execute("""INSERT INTO nutrition_targets(id,user_id,effective_from,kcal,bmr_kcal,
            tdee_kcal,carb_g,protein_g,fat_g,algorithm_version)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ident("t", 1), "local-user", FIRST_DAY.isoformat(), 2100, 1600, 2200,
             230, 130, 70, "benchmark-v1"))
        insert_batches(db, """INSERT INTO meals(id,user_id,local_date,meal_type,status)
            VALUES (?,?,?,?,?)""", ((ident("m", i), "local-user", day(i), "lunch",
                                    "PLANNED" if i % 10 == 0 else "CONSUMED")
                                   for i in range(meal_count)))
        insert_batches(db, """INSERT INTO meal_items(id,meal_id,display_name,amount,unit,
            grams,kcal,carb_g,protein_g,fat_g) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ((ident("i", i), ident("m", i // 10), "合成食物", 100, "g", 100,
              100.1, 12.1, 6.2, 3.1) for i in range(meal_items)))
        insert_batches(db, """INSERT INTO workout_sessions(id,user_id,local_date,start_at,
            workout_type,status,minutes,kcal) VALUES (?,?,?,?,?,?,?,?)""",
            ((ident("w", i), "local-user", day(i), f"{day(i)}T08:00:00+08:00",
              "strength", "COMPLETED" if i % 12 else "DRAFT", 45, 220.1)
             for i in range(workout_sessions)))
        insert_batches(db, """INSERT INTO exercise_sets(id,session_id,exercise_name,set_no,
            weight_kg,reps,completed_at,volume) VALUES (?,?,?,?,?,?,?,?)""",
            ((ident("s", i), ident("w", i // sets_per_workout), "合成动作",
              i % sets_per_workout + 1, 40, 10, f"{day(i // sets_per_workout)}T08:30:00+08:00", 400)
             for i in range(workout_sessions * sets_per_workout)))
        db.executemany("""INSERT INTO device_connections(id,user_id,provider,status)
            VALUES (?,?,?,'ACTIVE')""", [(ident("c", 1), "local-user", "health_connect"),
                                          (ident("c", 2), "local-user", "manual_device_import")])
        insert_batches(db, """INSERT INTO device_samples(id,connection_id,external_id,
            sample_type,start_at,local_date,value,unit) VALUES (?,?,?,?,?,?,?,?)""",
            ((ident("d", i), ident("c", i % 2 + 1), f"sample-{i}",
              "active_energy" if i % 3 else "steps", f"{day(i)}T08:00:00+08:00",
              day(i), 12 if i % 3 else 250, "kcal" if i % 3 else "count")
             for i in range(device_samples)))
        insert_batches(db, """INSERT INTO water_logs(id,user_id,occurred_at,local_date,amount_ml)
            VALUES (?,?,?,?,?)""", ((ident("h", i), "local-user", f"{day(i)}T12:00:00+08:00",
                                    day(i), 250) for i in range(SPAN_DAYS)))
        db.commit()


def measure(start: str, end: str, granularity: str, runs: int,
            metric: str = "energy") -> dict:
    query = (lambda: macro_summary(start, end)) if metric == "macros" else (
        lambda: energy_series(start, end, granularity))
    with connect() as db:
        db.execute("DELETE FROM daily_energy_snapshots WHERE user_id='local-user' AND local_date BETWEEN ? AND ?",
                   (start, end))
        db.commit()
    before = time.perf_counter()
    result = query()
    cold_ms = (time.perf_counter() - before) * 1000
    timings = []
    for _ in range(runs):
        before = time.perf_counter()
        result = query()
        timings.append((time.perf_counter() - before) * 1000)
    ordered = sorted(timings)
    return {"days": (date.fromisoformat(end) - date.fromisoformat(start)).days + 1,
            "buckets": len(result["series"]) if metric == "energy" else 1,
            "cold_ms": round(cold_ms, 1),
            "warm_median_ms": round(statistics.median(ordered), 1),
            "warm_p95_ms": round(ordered[math.ceil(0.95 * runs) - 1], 1),
            "warm_max_ms": round(ordered[-1], 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meal-items", type=int, default=200_000)
    parser.add_argument("--workout-sessions", type=int, default=10_000)
    parser.add_argument("--sets-per-workout", type=int, default=10)
    parser.add_argument("--device-samples", type=int, default=50_000)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if min(args.meal_items, args.workout_sessions, args.sets_per_workout,
           args.device_samples, args.runs) < 1:
        parser.error("All sizes and runs must be positive")
    previous_db = os.environ.get("NUTRIPULSE_DB")
    with tempfile.TemporaryDirectory(prefix="nutripulse_analytics_benchmark_") as folder:
        os.environ["NUTRIPULSE_DB"] = str(Path(folder) / "benchmark.sqlite3")
        try:
            migrate()
            seed()
            before = time.perf_counter()
            populate(args.meal_items, args.workout_sessions, args.sets_per_workout,
                     args.device_samples)
            print(f"Synthetic rows: meal_items={args.meal_items}, exercise_sets="
                  f"{args.workout_sessions * args.sets_per_workout}, device_samples={args.device_samples}; "
                  f"setup_s={time.perf_counter() - before:.1f}")
            print("Year:", measure("2025-10-02", "2026-10-03", "month", args.runs))
            print("Year macros:", measure("2025-10-02", "2026-10-03", "month",
                                          args.runs, "macros"))
            print("Month:", measure("2026-09-01", "2026-09-30", "day", args.runs))
            print("Month macros:", measure("2026-09-01", "2026-09-30", "day",
                                           args.runs, "macros"))
        finally:
            if previous_db is None:
                os.environ.pop("NUTRIPULSE_DB", None)
            else:
                os.environ["NUTRIPULSE_DB"] = previous_db


if __name__ == "__main__":
    main()
