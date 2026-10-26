"""Create a synthetic, non-personal PDF for visual QA.

Run from server/: python tools/generate_sample_report.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.analytics.report import build_report
from app.application.fitness.service import create_workout
from app.application.nutrition.service import create_meal
from app.application.profile.service import add_measurement, set_goal, update_profile
from app.infrastructure.db.database import migrate
from app.infrastructure.db.seed import seed
from app.shared.util import today


def main() -> None:
    destination = Path(__file__).resolve().parents[2] / "output" / "pdf" / "NutriPulse_analytics_sample.pdf"
    old_db = os.environ.get("NUTRIPULSE_DB")
    with tempfile.TemporaryDirectory(prefix="nutripulse_pdf_qa_") as directory:
        os.environ["NUTRIPULSE_DB"] = str(Path(directory) / "synthetic.sqlite3")
        try:
            migrate()
            seed()
            update_profile({"display_name": "合成样例", "birth_date": "1998-05-01",
                            "formula_sex": "female", "height_cm": 165, "activity_level": "light"})
            end = date.fromisoformat(today())
            for days_ago, weight, fat in ((28, 60.4, 24.1), (14, 59.8, None)):
                day = end - timedelta(days=days_ago)
                add_measurement({"weight_kg": weight, "body_fat_pct": fat,
                                 "measured_at": f"{day.isoformat()}T02:00:00+00:00"})
            add_measurement({"weight_kg": 59, "body_fat_pct": 23.5})
            set_goal({"goal_type": "maintenance"})
            for days_ago in (5, 4, 2, 1, 0):
                day = (end - timedelta(days=days_ago)).isoformat()
                create_meal({"local_date": day, "meal_type": "lunch", "status": "CONSUMED",
                             "items": [{"display_name": "样例鸡胸肉饭", "amount": 1, "unit": "份",
                                        "kcal": 560 + days_ago * 12, "carb_g": 62,
                                        "protein_g": 42, "fat_g": 16}]})
            for days_ago in (4, 1):
                create_workout({"local_date": (end - timedelta(days=days_ago)).isoformat(),
                                "workout_type": "strength", "minutes": 45,
                                "sets": [{"exercise_name": "样例深蹲", "set_no": 1,
                                          "weight_kg": 40, "reps": 10}]})
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(build_report({"period": "week", "end": end.isoformat()},
                                                 synthetic_sample=True))
            print(destination)
        finally:
            if old_db is None:
                os.environ.pop("NUTRIPULSE_DB", None)
            else:
                os.environ["NUTRIPULSE_DB"] = old_db


if __name__ == "__main__":
    main()
