from __future__ import annotations

import json
import random
import logging
import hashlib

from app.application.analytics.service import day_summary
from app.application.nutrition.service import create_meal
from app.application.profile.service import get_profile
from app.application.recommendation.scoring import score_candidate, scoring_config
from app.infrastructure.agent.gateway import configured, invoke
from app.infrastructure.db.database import connect, row_dict, transaction
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, json_value, new_id, today, utc_now, valid_date


def _candidate_rows():
    with connect() as db:
        recipes = [dict(r) for r in db.execute("SELECT * FROM recipes ORDER BY id")]
        for recipe in recipes:
            recipe["ingredients"] = [dict(r) for r in db.execute("""SELECT f.id AS food_id,f.name,
                f.kcal,f.carb_g,f.protein_g,f.fat_g,f.fiber_g,ri.grams,f.allergens_json,f.verified
                FROM recipe_ingredients ri JOIN food_items f ON f.id=ri.food_id
                WHERE ri.recipe_id=? ORDER BY ri.rowid""", (recipe["id"],))]
    return recipes


def _violates_ingredients(ingredients: list[dict], excluded: set[str]) -> bool:
    if any(x["food_id"].lower() in excluded or x["name"].lower() in excluded for x in ingredients):
        return True
    if excluded and any(not x.get("verified") for x in ingredients):
        return True
    if any(excluded & set(json_value(x.get("allergens_json"), [])) for x in ingredients):
        return True
    ids = {x["food_id"] for x in ingredients}
    if ("vegetarian" in excluded or "素食" in excluded) and ids & {"chicken", "beef", "salmon"}:
        return True
    if ("vegan" in excluded or "纯素" in excluded) and ids & {"chicken", "beef", "salmon", "egg", "yogurt"}:
        return True
    return False


def _within_energy_budget(kcal: float, remaining_kcal: float) -> bool:
    # Match the recommendation tolerance at both presentation and acceptance.
    return kcal <= max(remaining_kcal, 0.0) + 100.0


def _ingredient_nutrition(ingredients: list[dict]) -> dict:
    return {key: round(sum(float(x[key]) * float(x["grams"]) / 100 for x in ingredients), 1)
            for key in ("kcal", "carb_g", "protein_g", "fat_g", "fiber_g")}


def recommend(data: dict) -> dict:
    day = valid_date(data.get("local_date") or today())
    meal_type = data.get("meal_type", "dinner")
    require(meal_type in ("breakfast", "lunch", "dinner", "snack"), "餐别无效")
    state, profile = day_summary(day), get_profile()
    dining = profile["dining"]
    scenario = data.get("scenario") or dining["preferred_scenario"]
    require(scenario in ("self_cook", "takeout", "dine_in", "convenience"), "场景无效")
    max_cost = dining["max_cost_cny"]
    max_minutes = dining["max_cook_minutes"]
    flavors = set(dining["flavors"])
    excluded = set(profile["allergies"]) | set(profile["restrictions"])
    remaining = state["energy"]["remaining_kcal"] if state["has_target"] else 650
    meal_fraction = 0.4 if meal_type != "snack" else 0.2
    desired = max(250, min(900, remaining * meal_fraction))
    target = state["target"] or {}
    macro_gaps = {name: max(0.0, float(target.get(name) or 0) - state["macros"][name])
                  for name in ("carb_g", "protein_g", "fat_g")}
    goal_type = profile["goal"]["goal_type"] if profile["goal"] else None
    weights, ranking_version = scoring_config()
    with connect() as db:
        feedback = {row["recipe_id"]: row["feedback_type"] for row in db.execute(
            "SELECT recipe_id,feedback_type FROM recommendation_feedback WHERE user_id=?", (USER_ID,))}
        recent = {row["recipe_id"]: row["meal_count"] for row in db.execute("""
            SELECT i.candidate_ref_id AS recipe_id,COUNT(*) AS meal_count
            FROM meals m JOIN recommendation_items i ON i.id=m.source_ref_id
            WHERE m.user_id=? AND m.local_date BETWEEN date(?, '-6 days') AND ?
              AND m.status IN ('PLANNED','CONSUMED') AND m.deleted_at IS NULL
              AND m.source_type='recommendation'
            GROUP BY i.candidate_ref_id""", (USER_ID, day, day))}
    candidates = []
    for recipe in _candidate_rows():
        if recipe["scenario"] != scenario:
            continue
        # Unknown prices cannot be claimed to fit a monetary ceiling.
        if max_cost is not None and (recipe["estimated_cost_cny"] is None or
                                     recipe["estimated_cost_cny"] > max_cost):
            continue
        if scenario == "self_cook" and max_minutes is not None and \
                recipe["prep_minutes"] + recipe["cook_minutes"] > max_minutes:
            continue
        allergens = set(json_value(recipe["allergens_json"], []))
        if excluded & allergens:
            continue
        ingredients = recipe["ingredients"]
        # A hard restriction can also refer to an ingredient name or ID.
        if _violates_ingredients(ingredients, excluded):
            continue
        nutrition = _ingredient_nutrition(ingredients)
        # Keep calorie overshoot visible only if there is no safer choice.
        if state["has_target"] and not _within_energy_budget(nutrition["kcal"], remaining):
            continue
        opinion = feedback.get(recipe["id"])
        score, components = score_candidate(nutrition=nutrition, desired_kcal=desired,
            macro_gaps=macro_gaps, meal_fraction=meal_fraction, goal_type=goal_type,
            ingredients=ingredients, recipe_flavors=set(json_value(recipe["flavors_json"], [])),
            preferred_flavors=flavors, preferences=profile["preferences"],
            recent_count=recent.get(recipe["id"], 0), feedback_type=opinion, weights=weights)
        candidates.append({"recipe": recipe, "nutrition": nutrition, "score": score,
                           "score_components": components, "feedback_type": opinion})
    candidates.sort(key=lambda x: (x["feedback_type"] is not None,
                                   -x["score"], x["recipe"]["id"]))
    agent_reasons = {}
    agent_modifications = {}
    source = "rules-v1"
    if candidates and configured():
        try:
            output = invoke("meal_recommendation", {
                "goal_type": profile["goal"]["goal_type"] if profile["goal"] else None,
                "meal_type": meal_type, "scenario": scenario,
                "remaining_kcal": remaining, "desired_kcal": desired, "macro_gaps": macro_gaps,
                "preferences": profile["preferences"],
                "dining": dining,
                "allergies": profile["allergies"], "restrictions": profile["restrictions"],
                "safe_candidates": [{"id": x["recipe"]["id"], "name": x["recipe"]["name"],
                                     "nutrition": x["nutrition"],
                                     "estimated_cost_cny": x["recipe"]["estimated_cost_cny"],
                                     "total_minutes": x["recipe"]["prep_minutes"] + x["recipe"]["cook_minutes"]}
                                    for x in candidates],
                "instruction": "只能在 safe_candidates 内排序；返回 recipe_ids 数组，可选 reasons_by_id 和 modifications_by_id 对象。不得新增候选或食材。"
            }, timeout=15)
            ordered = output.get("recipe_ids")
            allowed = {x["recipe"]["id"]: x for x in candidates}
            if isinstance(ordered, list) and ordered and all(isinstance(x, str) and x in allowed for x in ordered):
                unique = list(dict.fromkeys(ordered))
                candidates = [allowed[x] for x in unique] + [x for x in candidates if x["recipe"]["id"] not in unique]
                agent_reasons = output.get("reasons_by_id") if isinstance(output.get("reasons_by_id"), dict) else {}
                agent_modifications = output.get("modifications_by_id") if isinstance(output.get("modifications_by_id"), dict) else {}
                # Model ordering must not silently erase explicit negative feedback.
                candidates.sort(key=lambda x: {"REPEATED": 1, "DISLIKE": 2,
                                               "UNSUITABLE": 2}.get(x["feedback_type"], 0))
                source = "agent-v1"
        except ApiError as error:
            logging.warning("meal recommendation agent unavailable: %s", error.code)
    blind_box = None
    if data.get("shuffle"):
        avoid = data.get("avoid_recipe_id")
        require(avoid is None or isinstance(avoid, str), "上次抽中的菜谱标识无效")
        pool = [{"recipe_id": x["recipe"]["id"], "name": x["recipe"]["name"],
                 "score": x["score"]}
                for x in candidates]
        version_input = {"day": day, "meal_type": meal_type, "scenario": scenario,
                         "allergies": sorted(profile["allergies"]),
                         "restrictions": sorted(profile["restrictions"]),
                         "dining": dining, "remaining_kcal": remaining,
                         "pool": sorted(pool, key=lambda x: x["recipe_id"])}
        pool_version = hashlib.sha256(json.dumps(version_input, ensure_ascii=False,
                                                 sort_keys=True).encode("utf-8")).hexdigest()[:16]
        alternatives = [x for x in candidates if x["recipe"]["id"] != avoid]
        chosen = random.choice(alternatives or candidates) if candidates else None
        blind_box = {"pool_version": pool_version, "candidate_count": len(candidates),
                     "candidate_pool": pool,
                     "previous_recipe_id": avoid, "drawn_recipe_id": chosen["recipe"]["id"] if chosen else None,
                     "drawn_at": utc_now()}
        candidates = [chosen] if chosen else []
    else:
        candidates = candidates[:5]
    session_id = new_id()
    context = {"has_target": state["has_target"], "remaining_kcal": remaining,
               "desired_kcal": desired, "macro_gaps": macro_gaps,
               "allergies": profile["allergies"], "restrictions": profile["restrictions"],
               "goal_type": goal_type, "scenario": scenario, "dining": dining,
               "feedback": feedback, "recent_recipe_counts": recent,
               "scoring_weights": weights, "ranking_version": ranking_version,
               "score_components": {x["recipe"]["id"]: x["score_components"] for x in candidates}}
    if blind_box is not None:
        context["blind_box"] = blind_box
    with transaction() as db:
        db.execute("""INSERT INTO recommendation_sessions(id,user_id,local_date,meal_type,
            context_snapshot_json,constraint_version,status) VALUES (?,?,?,?,?,?,'PRESENTED')""",
            (session_id, USER_ID, day, meal_type, as_json(context), source))
        for rank,item in enumerate(candidates, 1):
            recipe = item["recipe"]
            db.execute("""INSERT INTO recommendation_items(id,session_id,candidate_type,candidate_ref_id,
                title,nutrition_json,score,reason_json,modification_json,rank)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (new_id(),session_id,"recipe",recipe["id"],recipe["name"],as_json(item["nutrition"]),
                 item["score"],as_json(_safe_texts(agent_reasons.get(recipe["id"]),
                     ["符合已配置过敏原和忌口", "参考当前热量与营养素缺口"])),
                 as_json(_safe_texts(agent_modifications.get(recipe["id"]),
                     ["按实际称量调整份量", "烹调时少油，酱汁分装"])),rank))
    return get_recommendations(session_id)


def _safe_texts(value, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    result = [text.strip() for text in value if isinstance(text, str) and 0 < len(text.strip()) <= 120]
    return result[:3] or fallback


def get_recommendations(session_id: str) -> dict:
    with connect() as db:
        session = row_dict(db.execute("SELECT * FROM recommendation_sessions WHERE id=? AND user_id=?",
                                      (session_id, USER_ID)).fetchone())
        if not session:
            raise ApiError("NOT_FOUND", "推荐会话不存在", 404)
        items = [dict(r) for r in db.execute("""SELECT i.*,
            r.estimated_cost_cny,r.prep_minutes,r.cook_minutes,r.flavors_json,
            f.feedback_type
            FROM recommendation_items i LEFT JOIN recipes r ON r.id=i.candidate_ref_id
            LEFT JOIN recommendation_feedback f ON f.user_id=? AND f.recipe_id=i.candidate_ref_id
            WHERE i.session_id=? ORDER BY i.rank""", (USER_ID, session_id))]
    for item in items:
        item["nutrition"] = json_value(item.pop("nutrition_json"), {})
        item["reasons"] = json_value(item.pop("reason_json"), [])
        item["modifications"] = json_value(item.pop("modification_json"), [])
        item["flavors"] = json_value(item.pop("flavors_json"), [])
    return {"session": session, "items": items}


def submit_feedback(item_id: str, feedback_type: str) -> dict:
    require(feedback_type in ("DISLIKE", "REPEATED", "UNSUITABLE", "CLEAR"), "反馈类型无效")
    with transaction() as db:
        row = db.execute("""SELECT i.candidate_ref_id AS recipe_id FROM recommendation_items i
            JOIN recommendation_sessions s ON s.id=i.session_id
            WHERE i.id=? AND s.user_id=? AND i.candidate_type='recipe'""",
            (item_id, USER_ID)).fetchone()
        if not row:
            raise ApiError("NOT_FOUND", "推荐项不存在", 404)
        recipe_id = row["recipe_id"]
        if feedback_type == "CLEAR":
            db.execute("DELETE FROM recommendation_feedback WHERE user_id=? AND recipe_id=?",
                       (USER_ID, recipe_id))
        else:
            db.execute("""INSERT INTO recommendation_feedback(id,user_id,recipe_id,source_item_id,
                feedback_type) VALUES (?,?,?,?,?)
                ON CONFLICT(user_id,recipe_id) DO UPDATE SET
                source_item_id=excluded.source_item_id,feedback_type=excluded.feedback_type,
                updated_at=CURRENT_TIMESTAMP""",
                (new_id(), USER_ID, recipe_id, item_id, feedback_type))
    return {"recipe_id": recipe_id, "feedback_type": None if feedback_type == "CLEAR" else feedback_type}


def accept(item_id: str, idempotency_key: str | None = None, servings: float = 1.0) -> dict:
    try:
        servings = float(servings)
    except (ValueError, TypeError):
        raise ApiError("VALIDATION_ERROR", "份数无效")
    require(servings in (0.5, 1.0, 1.5, 2.0), "份数需为 0.5、1、1.5 或 2")
    with connect() as db:
        row = db.execute("""SELECT i.*,s.local_date,s.meal_type,s.user_id,s.status AS session_status
            FROM recommendation_items i JOIN recommendation_sessions s ON s.id=i.session_id
            WHERE i.id=? AND s.user_id=?""", (item_id, USER_ID)).fetchone()
        if not row:
            raise ApiError("NOT_FOUND", "推荐项不存在", 404)
        old = db.execute("""SELECT id,status,deleted_at FROM meals
            WHERE user_id=? AND source_type='recommendation' AND source_ref_id=?""",
            (USER_ID, item_id)).fetchone()
        if old:
            if old["deleted_at"] is not None:
                raise ApiError("ALREADY_REMOVED", "这道推荐餐已删除；请重新生成推荐", 409)
            return {"meal_id": old["id"], "status": old["status"]}
        recipe = db.execute("SELECT * FROM recipes WHERE id=?", (row["candidate_ref_id"],)).fetchone()
        ingredients = [dict(r) for r in db.execute("""SELECT f.*,ri.grams FROM recipe_ingredients ri
            JOIN food_items f ON f.id=ri.food_id WHERE ri.recipe_id=?""", (recipe["id"],))]
    profile = get_profile()
    excluded = set(profile["allergies"]) | set(profile["restrictions"])
    dining = profile["dining"]
    cost = recipe["estimated_cost_cny"]
    if dining["max_cost_cny"] is not None and (cost is None or cost * servings > dining["max_cost_cny"]):
        raise ApiError("HARD_CONSTRAINT_VIOLATION", "当前份数超出单餐估算预算，请减少份数或重新推荐", 409)
    if recipe["scenario"] == "self_cook" and dining["max_cook_minutes"] is not None and \
            recipe["prep_minutes"] + recipe["cook_minutes"] > dining["max_cook_minutes"]:
        raise ApiError("HARD_CONSTRAINT_VIOLATION", "菜谱不再符合烹饪时长限制，请重新推荐", 409)
    if excluded & set(json_value(recipe["allergens_json"], [])):
        raise ApiError("HARD_CONSTRAINT_VIOLATION", "个人过敏或忌口配置已改变，请重新推荐", 409)
    if _violates_ingredients([{"food_id": f["id"], "name": f["name"],
                              "allergens_json": f["allergens_json"], "verified": f["verified"]}
                             for f in ingredients], excluded):
        raise ApiError("HARD_CONSTRAINT_VIOLATION", "个人饮食限制已改变，请重新推荐", 409)
    budget = day_summary(row["local_date"])
    if budget["has_target"]:
        nutrition = json_value(row["nutrition_json"], {})
        if not _within_energy_budget(float(nutrition.get("kcal", 0.0)) * servings,
                                     float(budget["energy"]["remaining_kcal"])):
            raise ApiError("HARD_CONSTRAINT_VIOLATION", "当前份数超出当日剩余热量，请减少份数或重新推荐", 409)
    items = [{"food_id": f["id"], "display_name": f["name"], "amount": round(f["grams"] * servings, 1), "unit": "g",
              "grams": round(f["grams"] * servings, 1), "kcal": round(f["kcal"] * f["grams"] * servings / 100, 1),
              "carb_g": round(f["carb_g"] * f["grams"] * servings / 100, 1),
              "protein_g": round(f["protein_g"] * f["grams"] * servings / 100, 1),
              "fat_g": round(f["fat_g"] * f["grams"] * servings / 100, 1),
              "fiber_g": round(f["fiber_g"] * f["grams"] * servings / 100, 1)} for f in ingredients]
    # One recommendation item may produce only one planned meal, regardless
    # of transport-level request keys or repeated confirmation taps.
    meal = create_meal({"local_date": row["local_date"], "meal_type": row["meal_type"],
                        "status": "PLANNED", "source_type": "recommendation",
                        "source_ref_id": item_id, "note": f"{recipe['name']} ×{servings:g}", "items": items},
                       f"recommendation-{item_id}")
    with transaction() as db:
        db.execute("UPDATE recommendation_items SET accepted_at=COALESCE(accepted_at,?) WHERE id=?", (utc_now(), item_id))
        db.execute("UPDATE recommendation_sessions SET status='ACCEPTED' WHERE id=?", (row["session_id"],))
    return {"meal_id": meal["id"], "status": meal["status"]}


def recipe_detail(recipe_id: str) -> dict:
    for recipe in _candidate_rows():
        if recipe["id"] == recipe_id:
            recipe["instructions"] = json_value(recipe.pop("instructions_json"), [])
            recipe["allergens"] = json_value(recipe.pop("allergens_json"), [])
            recipe["nutrition_per_serving"] = _ingredient_nutrition(recipe["ingredients"])
            profile = get_profile()
            excluded = set(profile["allergies"]) | set(profile["restrictions"])
            recipe["matches_current_restrictions"] = not (
                excluded & set(recipe["allergens"]) or
                _violates_ingredients(recipe["ingredients"], excluded))
            recipe["substitutions"] = []
            if recipe["scenario"] == "self_cook":
                with connect() as db:
                    for original in recipe["ingredients"]:
                        if not original.get("verified") or not original.get("grams"):
                            continue
                        alternatives = db.execute("""SELECT f.id,f.name,f.kcal,f.carb_g,
                            f.protein_g,f.fat_g,f.fiber_g,f.allergens_json,f.verified
                            FROM food_substitutions s JOIN food_items f ON f.id=s.to_food_id
                            WHERE s.from_food_id=? ORDER BY s.rank,f.id""",
                            (original["food_id"],)).fetchall()
                        for raw in alternatives:
                            replacement = dict(raw)
                            if not replacement["verified"] or replacement["kcal"] <= 0 or _violates_ingredients(
                                    [{"food_id": replacement["id"], "name": replacement["name"],
                                      "allergens_json": replacement["allergens_json"],
                                      "verified": replacement["verified"]}], excluded):
                                continue
                            grams = round(float(original["kcal"]) * float(original["grams"]) /
                                          float(replacement["kcal"]), 1)
                            if grams <= 0 or grams > 500:
                                continue
                            after = {}
                            for key in ("kcal", "carb_g", "protein_g", "fat_g", "fiber_g"):
                                original_value = float(original[key]) * float(original["grams"]) / 100
                                replacement_value = float(replacement[key]) * grams / 100
                                after[key] = round(max(0.0, recipe["nutrition_per_serving"][key] -
                                                         original_value + replacement_value), 1)
                            recipe["substitutions"].append({
                                "original_food_id": original["food_id"],
                                "original_name": original["name"],
                                "replacement_food_id": replacement["id"],
                                "replacement_name": replacement["name"],
                                "grams_per_serving": grams,
                                "nutrition_per_serving_if_used": after,
                                "basis": "kcal_equivalent",
                            })
            return recipe
    raise ApiError("NOT_FOUND", "菜谱不存在", 404)
