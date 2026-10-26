from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.shared.errors import require


ACTIVITY_FACTORS = {
    "sedentary": Decimal("1.2"),
    "light": Decimal("1.375"),
    "moderate": Decimal("1.55"),
    "high": Decimal("1.725"),
    "very_high": Decimal("1.9"),
}
GOAL_ADJUSTMENTS = {
    "fat_loss": Decimal("-400"),
    "maintenance": Decimal("0"),
    "muscle_gain": Decimal("250"),
    "recovery": Decimal("0"),
}
MACRO_RATIOS = {
    "fat_loss": (Decimal("0.45"), Decimal("0.30"), Decimal("0.25")),
    "maintenance": (Decimal("0.50"), Decimal("0.25"), Decimal("0.25")),
    "muscle_gain": (Decimal("0.50"), Decimal("0.30"), Decimal("0.20")),
    "recovery": (Decimal("0.50"), Decimal("0.25"), Decimal("0.25")),
}


def rounded(value: Decimal, digits: str = "1") -> float:
    return float(value.quantize(Decimal(digits), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Targets:
    bmr_kcal: float
    tdee_kcal: float
    target_kcal: float
    carb_g: float
    protein_g: float
    fat_g: float
    algorithm_version: str = "mifflin-v1"


def calculate_targets(age: int, height_cm: float, weight_kg: float,
                      formula_sex: str, activity_level: str, goal_type: str) -> Targets:
    require(18 <= age <= 120, "年龄需在 18-120 岁之间")
    require(100 <= height_cm <= 230, "身高需在 100-230 cm 之间")
    require(25 <= weight_kg <= 350, "体重需在 25-350 kg 之间")
    require(formula_sex in ("male", "female"), "请选择计算公式使用的生理性别")
    require(activity_level in ACTIVITY_FACTORS, "无效的活动等级")
    require(goal_type in GOAL_ADJUSTMENTS, "无效的阶段目标")
    w, h, a = Decimal(str(weight_kg)), Decimal(str(height_cm)), Decimal(age)
    bmr = Decimal(10) * w + Decimal("6.25") * h - Decimal(5) * a
    bmr += Decimal(5) if formula_sex == "male" else Decimal(-161)
    tdee = bmr * ACTIVITY_FACTORS[activity_level]
    target = max(Decimal(1200), tdee + GOAL_ADJUSTMENTS[goal_type])
    carb_ratio, protein_ratio, fat_ratio = MACRO_RATIOS[goal_type]
    return Targets(
        bmr_kcal=rounded(bmr), tdee_kcal=rounded(tdee), target_kcal=rounded(target),
        carb_g=rounded(target * carb_ratio / Decimal(4), "0.1"),
        protein_g=rounded(target * protein_ratio / Decimal(4), "0.1"),
        fat_g=rounded(target * fat_ratio / Decimal(9), "0.1"),
    )


def met_kcal(met: float, weight_kg: float, minutes: float) -> float:
    require(1 <= met <= 25, "MET 值需在 1-25 之间")
    require(25 <= weight_kg <= 350, "体重需在 25-350 kg 之间")
    require(1 <= minutes <= 1440, "运动时长需在 1-1440 分钟之间")
    return rounded(Decimal(str(met)) * Decimal("3.5") * Decimal(str(weight_kg))
                   / Decimal(200) * Decimal(str(minutes)), "0.1")


def training_volume(sets: list[dict]) -> float:
    return rounded(sum((Decimal(str(s.get("weight_kg") or 0)) *
                        Decimal(str(s.get("reps") or 0)) for s in sets if s.get("completed", True)),
                       Decimal(0)), "0.1")
