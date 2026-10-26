"""Versioned, explainable meal ranking after hard safety constraints."""

from __future__ import annotations

import hashlib
import json
import logging
import os


DEFAULT_WEIGHTS = {
    "macro": 0.35,
    "calorie": 0.20,
    "preference": 0.15,
    "stage": 0.10,
    "scenario": 0.10,
    "diversity": 0.05,
    "feedback": 0.05,
}


def scoring_config() -> tuple[dict[str, float], str]:
    """Allow a validated local-server override; never accept partial weights."""
    weights = DEFAULT_WEIGHTS.copy()
    raw = os.environ.get("NUTRIPULSE_RECOMMENDATION_WEIGHTS")
    if raw:
        try:
            candidate = json.loads(raw)
            if (not isinstance(candidate, dict) or set(candidate) != set(weights)
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not 0 <= v <= 1 for v in candidate.values())
                    or abs(sum(candidate.values()) - 1.0) > 1e-6):
                raise ValueError("weights must contain seven nonnegative values summing to 1")
            weights = {key: float(candidate[key]) for key in DEFAULT_WEIGHTS}
        except (TypeError, ValueError):
            logging.warning("invalid recommendation weights; using defaults")
    digest = hashlib.sha256(json.dumps(weights, sort_keys=True).encode()).hexdigest()[:8]
    return weights, f"recommend-v3-weighted-{digest}"


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def score_candidate(*, nutrition: dict, desired_kcal: float, macro_gaps: dict,
                    meal_fraction: float, goal_type: str | None, ingredients: list[dict],
                    recipe_flavors: set[str], preferred_flavors: set[str],
                    preferences: list[dict], recent_count: int,
                    feedback_type: str | None, weights: dict[str, float]) -> tuple[float, dict]:
    macro_matches = []
    for key in ("carb_g", "protein_g", "fat_g"):
        wanted = max(0.0, float(macro_gaps[key]) * meal_fraction)
        if wanted:
            macro_matches.append(_clamp(100 - abs(float(nutrition[key]) - wanted) / wanted * 100))
    macro = sum(macro_matches) / len(macro_matches) if macro_matches else 50.0
    calorie = _clamp(100 - abs(float(nutrition["kcal"]) - desired_kcal) /
                     max(desired_kcal, 1.0) * 100)

    preference = 50.0
    ingredient_terms = {str(part["food_id"]).lower() for part in ingredients} | {
        str(part["name"]).lower() for part in ingredients}
    for item in preferences:
        category = item.get("category")
        if category not in ("like_food", "dislike_food"):
            continue
        if str(item.get("value_code", "")).lower() in ingredient_terms:
            preference += (25 if category == "like_food" else -25) * abs(float(item["weight"]))
    if preferred_flavors and preferred_flavors & recipe_flavors:
        preference += 20

    protein_need = max(0.0, float(macro_gaps["protein_g"]) * meal_fraction)
    protein_fit = _clamp(float(nutrition["protein_g"]) / protein_need * 100) if protein_need else 70.0
    if goal_type == "fat_loss":
        stage = 0.7 * protein_fit + 0.3 * _clamp(float(nutrition["fiber_g"]) / 8 * 100)
    elif goal_type == "muscle_gain":
        stage = 0.7 * protein_fit + 0.3 * _clamp(float(nutrition["kcal"]) /
                                                   max(desired_kcal * 0.8, 1) * 100)
    elif goal_type == "recovery":
        carb_need = max(0.0, float(macro_gaps["carb_g"]) * meal_fraction)
        carb_fit = _clamp(float(nutrition["carb_g"]) / carb_need * 100) if carb_need else 70.0
        stage = 0.5 * protein_fit + 0.5 * carb_fit
    elif goal_type == "maintenance":
        stage = 70.0
    else:
        stage = 50.0

    components = {
        "macro": round(macro, 1), "calorie": round(calorie, 1),
        "preference": round(_clamp(preference), 1), "stage": round(_clamp(stage), 1),
        "scenario": 100.0,  # Mismatched scenarios were already hard-filtered.
        "diversity": round(_clamp(100 - 30 * recent_count), 1),
        "feedback": {None: 100.0, "DISLIKE": 0.0, "REPEATED": 20.0,
                     "UNSUITABLE": 0.0}.get(feedback_type, 100.0),
    }
    total = round(sum(weights[key] * components[key] for key in DEFAULT_WEIGHTS), 1)
    return total, components
