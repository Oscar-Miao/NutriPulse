from __future__ import annotations

from app.domain.metabolism import met_kcal
from app.shared.errors import require


# Demo reference table, not a device measurement or medical-grade estimate.
MET_BY_INTENSITY = {
    "walking": {"low": 2.5, "moderate": 3.5, "high": 5.0},
    "running": {"low": 6.0, "moderate": 8.3, "high": 11.0},
    "cycling": {"low": 4.0, "moderate": 7.0, "high": 10.0},
    "swimming": {"low": 4.5, "moderate": 6.0, "high": 8.0},
    "yoga": {"low": 2.0, "moderate": 2.5, "high": 3.5},
    "strength": {"low": 3.0, "moderate": 4.0, "high": 6.0},
}
CALCULATION_VERSION = "met-demo-v1"


def estimate_activity(workout_type: str, intensity: str, weight_kg: float,
                      minutes: float, met_override: float | None = None) -> dict:
    require(workout_type in MET_BY_INTENSITY, "该运动需要手动填写热量")
    require(intensity in ("low", "moderate", "high"), "运动强度无效")
    met = met_override if met_override is not None else MET_BY_INTENSITY[workout_type][intensity]
    return {"met_value": met, "kcal": met_kcal(met, weight_kg, minutes),
            "calculation_version": CALCULATION_VERSION}
