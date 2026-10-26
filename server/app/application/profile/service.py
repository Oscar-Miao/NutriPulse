from __future__ import annotations

import hashlib
import json
from datetime import date

from app.domain.metabolism import GOAL_ADJUSTMENTS, calculate_targets
from app.infrastructure.db.database import connect, row_dict, transaction
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, json_value, new_id, number, today, utc_now


ALLERGEN_ALIASES = {
    "peanut": "peanut", "花生": "peanut",
    "egg": "egg", "鸡蛋": "egg", "蛋类": "egg",
    "milk": "milk", "牛奶": "milk", "乳制品": "milk", "奶类": "milk",
    "soy": "soy", "大豆": "soy", "黄豆": "soy", "豆制品": "soy",
    "fish": "fish", "鱼": "fish", "鱼类": "fish",
    "shellfish": "shellfish", "虾蟹": "shellfish", "甲壳类": "shellfish", "贝类": "shellfish",
    "tree_nut": "tree_nut", "坚果": "tree_nut", "树坚果": "tree_nut",
    "wheat": "wheat", "小麦": "wheat", "麸质": "wheat",
    "sesame": "sesame", "芝麻": "sesame",
}


def _age(birth_date: str, on: date) -> int:
    born = date.fromisoformat(birth_date)
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def get_profile() -> dict:
    with connect() as db:
        profile = row_dict(db.execute("""SELECT u.id, u.display_name, u.timezone, p.birth_date,
            p.formula_sex, p.height_cm, p.activity_level, p.profile_version
            FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.id=?""", (USER_ID,)).fetchone())
        measurement = row_dict(db.execute("SELECT * FROM body_measurements WHERE user_id=? ORDER BY measured_at DESC,rowid DESC LIMIT 1", (USER_ID,)).fetchone())
        goal = row_dict(db.execute("SELECT * FROM goals WHERE user_id=? AND status='ACTIVE'", (USER_ID,)).fetchone())
        current_day = today(profile["timezone"])
        target = row_dict(db.execute("""SELECT * FROM nutrition_targets WHERE user_id=?
            AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)
            ORDER BY effective_from DESC,rowid DESC LIMIT 1""",
            (USER_ID, current_day, current_day)).fetchone())
        allergies = [r[0] for r in db.execute("SELECT allergen_code FROM user_allergies WHERE user_id=? AND active=1", (USER_ID,))]
        restrictions = [r[0] for r in db.execute("SELECT restriction_code FROM user_dietary_restrictions WHERE user_id=? AND active=1", (USER_ID,))]
        preferences = [dict(r) for r in db.execute("SELECT category,value_code,weight FROM user_preferences WHERE user_id=? AND active=1", (USER_ID,))]
        dining = row_dict(db.execute("""SELECT max_cost_cny,max_cook_minutes,flavor_codes_json,
            preferred_scenario FROM dining_preferences WHERE user_id=?""", (USER_ID,)).fetchone())
        training = row_dict(db.execute("SELECT * FROM training_profiles WHERE user_id=?", (USER_ID,)).fetchone())
    if dining:
        dining["flavors"] = json_value(dining.pop("flavor_codes_json"), [])
    else:
        dining = {"max_cost_cny": None, "max_cook_minutes": None,
                  "flavors": [], "preferred_scenario": "self_cook"}
    if training:
        training["equipment"] = json_value(training.pop("equipment_json"), [])
        training["limitations"] = json_value(training.pop("limitations_json"), [])
    if target:
        target["inputs"] = json_value(target.pop("input_snapshot_json", None), {})
    return {"profile": profile, "measurement": measurement, "goal": goal, "target": target,
            "allergies": allergies, "restrictions": restrictions, "preferences": preferences,
            "dining": dining,
            "training": training}


def update_profile(data: dict) -> dict:
    previous = get_profile()
    p = previous["profile"]
    display_name = str(data.get("display_name", p["display_name"])).strip()
    require(1 <= len(display_name) <= 40, "昵称需在 1-40 字之间")
    birth_date = data.get("birth_date", p["birth_date"])
    if birth_date:
        try:
            age = _age(birth_date, date.fromisoformat(today(p["timezone"])))
        except ValueError:
            raise ApiError("VALIDATION_ERROR", "出生日期无效")
        require(18 <= age <= 120, "当前版本只支持 18-120 岁用户")
    formula_sex = data.get("formula_sex", p["formula_sex"])
    require(formula_sex in (None, "male", "female"), "公式性别无效")
    height = data.get("height_cm", p["height_cm"])
    if height is not None:
        height = number(height, "身高", 100, 230)
    require(not (previous["goal"] and previous["target"]) or
            (birth_date and formula_sex and height is not None),
            "现有营养目标生效期间不能清空出生日期、公式性别或身高")
    level = data.get("activity_level", p["activity_level"])
    require(level in ("sedentary", "light", "moderate", "high", "very_high"), "活动等级无效")
    with transaction() as db:
        db.execute("UPDATE users SET display_name=?, updated_at=? WHERE id=?", (display_name, utc_now(), USER_ID))
        db.execute("""UPDATE profiles SET birth_date=?, formula_sex=?, height_cm=?, activity_level=?,
            profile_version=profile_version+1, updated_at=? WHERE user_id=?""",
            (birth_date, formula_sex, height, level, utc_now(), USER_ID))
    _refresh_target_if_ready()
    return get_profile()


def set_training_profile(data: dict) -> dict:
    level = data.get("level", "beginner")
    require(level in ("beginner", "intermediate", "advanced", "recovery"), "训练水平无效")
    days = int(number(data.get("days_per_week", 3), "每周训练天数", 1, 7))
    minutes = int(number(data.get("session_minutes", 45), "单次训练时长", 10, 240))
    active_goal = int(number(data.get("active_kcal_goal", 300), "每日活动热量目标", 50, 2000))
    equipment = data.get("equipment", [])
    limitations = data.get("limitations", [])
    for name, values in (("器械", equipment), ("限制", limitations)):
        require(isinstance(values, list) and len(values) <= 20 and
                all(isinstance(x, str) and 1 <= len(x.strip()) <= 80 for x in values), f"{name}列表无效")
    with transaction() as db:
        db.execute("""INSERT INTO training_profiles(user_id,level,days_per_week,session_minutes,
            equipment_json,limitations_json,active_kcal_goal) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET level=excluded.level,days_per_week=excluded.days_per_week,
            session_minutes=excluded.session_minutes,equipment_json=excluded.equipment_json,
            limitations_json=excluded.limitations_json,active_kcal_goal=excluded.active_kcal_goal,
            updated_at=CURRENT_TIMESTAMP""",
            (USER_ID, level, days, minutes, as_json(equipment), as_json(limitations), active_goal))
    return get_profile()


def add_measurement(data: dict) -> dict:
    weight = number(data.get("weight_kg"), "体重", 25, 350)
    fat = data.get("body_fat_pct")
    if fat is not None:
        fat = number(fat, "体脂率", 0, 100)
    ident = new_id()
    with transaction() as db:
        db.execute("""INSERT INTO body_measurements(id,user_id,measured_at,weight_kg,body_fat_pct,source_type)
            VALUES (?,?,?,?,?,?)""", (ident, USER_ID, data.get("measured_at") or utc_now(), weight, fat, "manual"))
    _refresh_target_if_ready()
    return get_profile()


def set_goal(data: dict) -> dict:
    goal_type = data.get("goal_type")
    require(goal_type in ("fat_loss", "maintenance", "muscle_gain", "recovery"), "目标类型无效")
    expected = data.get("preview_fingerprint")
    if expected is not None and expected != preview_goal({"goal_type": goal_type})["input_fingerprint"]:
        raise ApiError("VERSION_CONFLICT", "档案或测量数据已变化，请重新预览目标", 409)
    state = get_profile()
    inputs, missing = _goal_inputs(state, goal_type)
    require(not missing or state["target"] is None,
            "当前资料不完整，补齐后才能安全切换目标")
    current_date = inputs["effective_date"]
    proposed = calculate_targets(inputs["age"], inputs["height_cm"], inputs["weight_kg"],
                                 inputs["formula_sex"], inputs["activity_level"], goal_type) if not missing else None
    ident = new_id()
    target_weight = data.get("target_weight_kg")
    if target_weight is not None:
        target_weight = number(target_weight, "目标体重", 25, 350)
    with transaction() as db:
        db.execute("UPDATE goals SET status='ENDED', end_date=? WHERE user_id=? AND status='ACTIVE'", (current_date, USER_ID))
        db.execute("""INSERT INTO goals(id,user_id,goal_type,start_date,target_weight_kg,status)
            VALUES (?,?,?,?,?,'ACTIVE')""", (ident, USER_ID, goal_type, current_date, target_weight))
        if proposed:
            _persist_target(db, proposed, inputs, ident)
    return get_profile()


def _goal_inputs(state: dict, goal_type: str) -> tuple[dict, list[str]]:
    p, m = state["profile"], state["measurement"]
    missing = []
    for field, label in (("birth_date", "出生日期"), ("formula_sex", "公式性别"),
                         ("height_cm", "身高")):
        if not p[field]:
            missing.append(label)
    if not m:
        missing.append("体重测量")
    day = today(p["timezone"])
    inputs = {"goal_type": goal_type, "effective_date": day,
              "birth_date": p["birth_date"], "formula_sex": p["formula_sex"],
              "height_cm": p["height_cm"], "activity_level": p["activity_level"],
              "profile_version": p["profile_version"],
              "measurement_id": m["id"] if m else None,
              "measurement_source": m["source_type"] if m else None,
              "measured_at": m["measured_at"] if m else None,
              "weight_kg": m["weight_kg"] if m else None}
    if not missing:
        inputs["age"] = _age(p["birth_date"], date.fromisoformat(day))
    return inputs, missing


def preview_goal(data: dict) -> dict:
    goal_type = data.get("goal_type")
    require(goal_type in GOAL_ADJUSTMENTS, "目标类型无效")
    state = get_profile()
    inputs, missing = _goal_inputs(state, goal_type)
    fingerprint_inputs = {"inputs": inputs,
                          "current_goal_id": state["goal"]["id"] if state["goal"] else None,
                          "current_target_id": state["target"]["id"] if state["target"] else None}
    fingerprint = hashlib.sha256(json.dumps(fingerprint_inputs, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode("utf-8")).hexdigest()
    proposed = None
    if not missing:
        proposed = vars(calculate_targets(inputs["age"], inputs["height_cm"],
                                          inputs["weight_kg"], inputs["formula_sex"],
                                          inputs["activity_level"], goal_type))
    current = state["target"]
    return {"goal_type": goal_type, "ready": not missing, "missing_fields": missing,
            "can_activate": not missing or current is None,
            "effective_from": inputs["effective_date"], "inputs": inputs,
            "current_target": current, "proposed_target": proposed,
            "delta_kcal": round(proposed["target_kcal"] - current["kcal"], 1)
            if proposed and current else None,
            "input_fingerprint": fingerprint}


def set_preferences(data: dict) -> dict:
    allergies = data.get("allergies", [])
    restrictions = data.get("restrictions", [])
    preferences = data.get("preferences", [])
    require(isinstance(allergies, list) and len(allergies) <= 50, "过敏原列表无效")
    require(isinstance(restrictions, list) and len(restrictions) <= 50, "忌口列表无效")
    require(isinstance(preferences, list) and len(preferences) <= 100, "偏好列表无效")
    dining = data.get("dining")
    if dining is not None:
        require(isinstance(dining, dict), "用餐偏好无效")
        cost = dining.get("max_cost_cny")
        minutes = dining.get("max_cook_minutes")
        cost = number(cost, "单餐预算", 1, 1000) if cost is not None else None
        if minutes is not None:
            parsed_minutes = number(minutes, "最长烹饪时间", 5, 240)
            require(parsed_minutes.is_integer(), "最长烹饪时间须为整数分钟")
            minutes = int(parsed_minutes)
        flavors = dining.get("flavors", [])
        require(isinstance(flavors, list) and len(flavors) <= 8 and
                all(isinstance(x, str) and x in ("清淡", "咸鲜", "甜口", "香辣") for x in flavors),
                "口味偏好无效")
        scenario = dining.get("preferred_scenario", "self_cook")
        require(scenario in ("self_cook", "takeout", "dine_in", "convenience"), "偏好场景无效")
    with transaction() as db:
        db.execute("DELETE FROM user_allergies WHERE user_id=?", (USER_ID,))
        db.execute("DELETE FROM user_dietary_restrictions WHERE user_id=?", (USER_ID,))
        db.execute("DELETE FROM user_preferences WHERE user_id=?", (USER_ID,))
        seen_allergies = set()
        for item in allergies:
            raw_code = str(item).strip().lower()
            code = ALLERGEN_ALIASES.get(raw_code)
            require(code is not None,
                    f"暂不支持过敏原「{raw_code[:30]}」，请不要依赖推荐判断该食物是否安全")
            if code in seen_allergies:
                continue
            seen_allergies.add(code)
            db.execute("INSERT INTO user_allergies(id,user_id,allergen_code) VALUES (?,?,?)", (new_id(), USER_ID, code))
        seen_restrictions = set()
        for item in restrictions:
            code = str(item).strip().lower()
            require(0 < len(code) <= 80, "忌口代码无效")
            if code in seen_restrictions:
                continue
            seen_restrictions.add(code)
            db.execute("INSERT INTO user_dietary_restrictions(id,user_id,restriction_code) VALUES (?,?,?)", (new_id(), USER_ID, code))
        seen_preferences = set()
        for item in preferences:
            require(isinstance(item, dict), "偏好项无效")
            category = str(item.get("category", "")).strip()
            value = str(item.get("value_code", "")).strip()
            require(category and value and len(category) <= 40 and len(value) <= 80, "偏好项无效")
            weight = number(item.get("weight", 1), "偏好权重", -1, 1)
            if (category, value) in seen_preferences:
                continue
            seen_preferences.add((category, value))
            db.execute("""INSERT INTO user_preferences(id,user_id,category,value_code,weight)
                VALUES (?,?,?,?,?)""", (new_id(), USER_ID, category, value, weight))
        if dining is not None:
            db.execute("""INSERT INTO dining_preferences(user_id,max_cost_cny,max_cook_minutes,
                flavor_codes_json,preferred_scenario) VALUES (?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET max_cost_cny=excluded.max_cost_cny,
                max_cook_minutes=excluded.max_cook_minutes,flavor_codes_json=excluded.flavor_codes_json,
                preferred_scenario=excluded.preferred_scenario,updated_at=CURRENT_TIMESTAMP""",
                (USER_ID, cost, minutes, as_json(list(dict.fromkeys(flavors))), scenario))
    return get_profile()


def _persist_target(db, target, inputs: dict, goal_id: str) -> None:
    day = inputs["effective_date"]
    db.execute("UPDATE nutrition_targets SET effective_to=? WHERE user_id=? AND effective_to IS NULL", (day, USER_ID))
    db.execute("""INSERT INTO nutrition_targets(id,user_id,effective_from,kcal,bmr_kcal,tdee_kcal,
        carb_g,protein_g,fat_g,algorithm_version,input_snapshot_json,goal_id,
        measurement_id,profile_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (new_id(), USER_ID, day, target.target_kcal, target.bmr_kcal, target.tdee_kcal,
         target.carb_g, target.protein_g, target.fat_g, target.algorithm_version,
         as_json(inputs), goal_id, inputs["measurement_id"], inputs["profile_version"]))


def _refresh_target_if_ready() -> None:
    state = get_profile()
    g = state["goal"]
    if not g:
        return
    inputs, missing = _goal_inputs(state, g["goal_type"])
    if missing:
        return
    target = calculate_targets(inputs["age"], inputs["height_cm"], inputs["weight_kg"],
                               inputs["formula_sex"], inputs["activity_level"], g["goal_type"])
    with transaction() as db:
        _persist_target(db, target, inputs, g["id"])
