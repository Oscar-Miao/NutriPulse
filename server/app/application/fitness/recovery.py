"""Post-workout nutrition context, grounded in the saved training and day ledger."""

from __future__ import annotations

import logging

from app.application.analytics.service import day_summary
from app.application.fitness.service import get_workout
from app.infrastructure.agent.gateway import configured, invoke
from app.shared.errors import ApiError, require
from app.shared.util import today, utc_now


REFERENCE = {
    "title": "ISSN Position Stand: Nutrient Timing (2017)",
    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC5596471/",
}


def recovery_advice(workout_id: str) -> dict:
    workout = get_workout(workout_id)
    require(workout["status"] == "COMPLETED", "只有已完成的训练可生成恢复建议")
    state = day_summary(workout["local_date"])
    target = state["target"] or {}
    has_target = state["has_target"]
    protein_gap = max(0.0, float(target.get("protein_g") or 0) -
                      float(state["macros"]["protein_g"])) if has_target else None
    carb_gap = max(0.0, float(target.get("carb_g") or 0) -
                   float(state["macros"]["carb_g"])) if has_target else None
    remaining = float(state["energy"]["remaining_kcal"]) if has_target else None
    water_target = int(target["water_ml"]) if has_target else None
    minutes = float(workout["minutes"])
    volume = float(workout["total_volume"])
    options = []
    notices = []

    if not has_target:
        options.append({"id": "complete_profile", "text":
            "训练已记录。先在个人页完善身体资料和目标，才能计算可靠的当日营养缺口。"})
    else:
        if workout["workout_type"] == "strength" and protein_gap >= 10:
            options.append({"id": "protein", "text":
                f"今天已知记录距蛋白质目标还差约 {protein_gap:.0f} g；下一餐可选择符合个人忌口的普通食物，并按实际份量记录。"})
        if minutes >= 60 and carb_gap >= 20:
            options.append({"id": "carb", "text":
                f"这次训练持续 {minutes:.0f} 分钟，今天已知记录距碳水目标还差约 {carb_gap:.0f} g；可在后续正餐中结合剩余热量预算安排主食。"})
        if water_target is not None and water_target - state["water_ml"] >= 300:
            options.append({"id": "water", "text":
                f"饮水账本为 {state['water_ml']} ml，距日常目标还差约 {water_target - state['water_ml']} ml；按口渴和实际情况补水，系统未测量汗液流失。"})
        if remaining is not None and remaining < 150:
            notices.append("当前饮食记录的目标剩余额度较低；运动热量只是估算，不应据此自动把全部消耗加回摄入预算。")
        if state["incomplete_macro_items"]:
            notices.append(f"今天有 {state['incomplete_macro_items']} 项已吃餐食的宏量营养素不完整；缺口仅基于已知数据，可能偏大。")
        if not options:
            options.append({"id": "routine", "text":
                "现有账本未提示需要额外安排特定营养素；继续按既定饮食目标、正常餐次和休息计划执行。"})

    if workout["local_date"] != today():
        notices.append("这是历史训练的回顾，依据该日当前账本重新计算，不代表当时的即时建议。")
    notices.append("仅作一般运动饮食参考，不用于诊断、治疗或替代专业营养建议。")
    evidence = {
        "workout_id": workout_id, "local_date": workout["local_date"],
        "workout_type": workout["workout_type"], "minutes": round(minutes, 1),
        "training_volume_kg": round(volume, 1), "estimated_kcal": round(float(workout["kcal"]), 1),
        "kcal_source": workout["kcal_source"], "has_target": has_target,
        "protein_gap_g": round(protein_gap, 1) if protein_gap is not None else None,
        "carb_gap_g": round(carb_gap, 1) if carb_gap is not None else None,
        "remaining_kcal": round(remaining, 1) if remaining is not None else None,
        "water_ml": state["water_ml"], "water_target_ml": water_target,
        "incomplete_macro_items": state["incomplete_macro_items"],
    }
    source = "rules-v1"
    if configured() and len(options) > 1:
        try:
            response = invoke("workout_recovery", {
                "evidence": evidence, "allowed_advice": options,
                "instruction": "只能返回 advice_ids 数组，选择 1-3 个 allowed_advice 的 id；不得生成新文字、食物或剂量。",
            }, timeout=12)
            ordered = response.get("advice_ids")
            allowed = {item["id"]: item for item in options}
            if (isinstance(ordered, list) and 1 <= len(ordered) <= 3 and
                    len(ordered) == len(set(ordered)) and
                    all(isinstance(key, str) and key in allowed for key in ordered)):
                options = [allowed[key] for key in ordered]
                source = "agent-selected-v1"
        except (ApiError, TypeError) as error:
            logging.warning("workout recovery agent unavailable or invalid: %s", type(error).__name__)
    return {"source": source, "generated_at": utc_now(), "summary": {
                "minutes": evidence["minutes"], "estimated_kcal": evidence["estimated_kcal"],
                "kcal_source": evidence["kcal_source"],
                "training_volume_kg": evidence["training_volume_kg"]},
            "advice": options, "notices": notices, "evidence": evidence,
            "reference": REFERENCE}
