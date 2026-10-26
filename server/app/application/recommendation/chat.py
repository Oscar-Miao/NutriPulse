from __future__ import annotations

import json
import math

from app.application.analytics.service import day_summary
from app.application.nutrition.service import create_meal
from app.application.profile.service import get_profile
from app.application.recommendation.service import (_candidate_rows, _ingredient_nutrition,
                                                    _violates_ingredients, _within_energy_budget)
from app.infrastructure.agent.gateway import invoke
from app.infrastructure.db.database import connect, row_dict, transaction
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, json_value, new_id, today, utc_now


def _agent_number(value, label: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ApiError("AGENT_INVALID_RESPONSE", f"Agent {label}无效")
    require(math.isfinite(parsed) and minimum <= parsed <= maximum,
            f"Agent {label}无效", "AGENT_INVALID_RESPONSE")
    return parsed


def _safe_recipes(state: dict, budget: dict) -> dict[str, dict]:
    dining = state["dining"]
    excluded = {str(x).lower() for x in state["allergies"] + state["restrictions"]}
    safe = {}
    for recipe in _candidate_rows():
        if recipe["scenario"] != dining["preferred_scenario"]:
            continue
        cost = recipe["estimated_cost_cny"]
        if dining["max_cost_cny"] is not None and (cost is None or cost > dining["max_cost_cny"]):
            continue
        duration = recipe["prep_minutes"] + recipe["cook_minutes"]
        if recipe["scenario"] == "self_cook" and dining["max_cook_minutes"] is not None and \
                duration > dining["max_cook_minutes"]:
            continue
        if excluded & {str(x).lower() for x in json_value(recipe["allergens_json"], [])}:
            continue
        if _violates_ingredients(recipe["ingredients"], excluded):
            continue
        nutrition = _ingredient_nutrition(recipe["ingredients"])
        if budget["has_target"] and not _within_energy_budget(
                nutrition["kcal"], float(budget["energy"]["remaining_kcal"])):
            continue
        safe[recipe["id"]] = {"recipe": recipe, "nutrition": nutrition}
    return safe


def _canonical_proposal(proposal: dict, state: dict, budget: dict) -> dict:
    recipe_id = proposal.get("recipe_id")
    if recipe_id is None:
        if state["dining"]["max_cost_cny"] is not None:
            raise ApiError("HARD_CONSTRAINT_UNVERIFIED",
                           "设置单餐价格上限后，须选择可核算价格的服务端菜谱", 409)
        return proposal
    require(isinstance(recipe_id, str) and recipe_id,
            "Agent 菜谱引用无效", "AGENT_INVALID_RESPONSE")
    safe = _safe_recipes(state, budget).get(recipe_id)
    if safe is None:
        raise ApiError("HARD_CONSTRAINT_VIOLATION", "菜谱不再符合价格、食材或营养预算，请重新选择", 409)
    recipe = safe["recipe"]
    items = []
    for ingredient in recipe["ingredients"]:
        grams = float(ingredient["grams"])
        part = {"name": ingredient["name"], "food_id": ingredient["food_id"],
                "grams": grams, "allergens": json_value(ingredient["allergens_json"], [])}
        for field in ("kcal", "carb_g", "protein_g", "fat_g", "fiber_g"):
            part[field] = round(float(ingredient[field]) * grams / 100, 1)
        items.append(part)
    return {"meal_type": proposal.get("meal_type"), "recipe_id": recipe_id,
            "recipe_name": recipe["name"], "estimated_cost_cny": recipe["estimated_cost_cny"],
            "items": items}


def _check_proposal(proposal: dict, state: dict, budget: dict) -> None:
    require(proposal.get("meal_type") in ("breakfast", "lunch", "dinner", "snack") and
            isinstance(proposal.get("items"), list) and 1 <= len(proposal["items"]) <= 30,
            "Agent 方案格式无效", "AGENT_INVALID_RESPONSE")
    excluded = {str(x).lower() for x in state["allergies"] + state["restrictions"]}
    with connect() as db:
        foods = {row["id"].lower(): dict(row) for row in db.execute("SELECT * FROM food_items")}
        by_name = {row["name"].lower(): row for row in foods.values()}
    total_kcal = 0.0
    for item in proposal["items"]:
        require(isinstance(item, dict) and isinstance(item.get("name"), str) and
                1 <= len(item["name"].strip()) <= 100, "Agent 食物项无效", "AGENT_INVALID_RESPONSE")
        name = item["name"].strip().lower()
        _agent_number(item.get("grams"), "食物克数", 0.01, 10000)
        total_kcal += _agent_number(item.get("kcal"), "食物热量", 0, 20000)
        for nutrient in ("carb_g", "protein_g", "fat_g", "fiber_g"):
            if nutrient in item and item[nutrient] is not None:
                _agent_number(item[nutrient], nutrient, 0, 2000)
        food = foods.get(str(item.get("food_id", "")).lower()) or by_name.get(name)
        declared = item.get("allergens", [])
        require(isinstance(declared, list) and all(isinstance(x, str) for x in declared),
                "Agent 过敏原字段无效", "AGENT_INVALID_RESPONSE")
        actual_allergens = set(json.loads(food["allergens_json"])) if food else set()
        if excluded and food is not None and name != food["name"].lower():
            raise ApiError("HARD_CONSTRAINT_UNVERIFIED", "食物名称与已核验食材不一致，无法确认过敏安全", 409)
        tokens = {name, str(item.get("food_id", "")).lower()} | actual_allergens | {x.lower() for x in declared}
        if food and ("vegetarian" in excluded or "素食" in excluded) and food["id"] in {"chicken", "beef", "salmon"}:
            raise ApiError("HARD_CONSTRAINT_VIOLATION", "方案不符合素食限制", 409)
        if food and ("vegan" in excluded or "纯素" in excluded) and food["id"] in {"chicken", "beef", "salmon", "egg", "yogurt"}:
            raise ApiError("HARD_CONSTRAINT_VIOLATION", "方案不符合纯素限制", 409)
        if excluded & tokens:
            raise ApiError("HARD_CONSTRAINT_VIOLATION", "方案触及过敏原或忌口，已拦截", 409)
        if excluded and food is None:
            raise ApiError("HARD_CONSTRAINT_UNVERIFIED", "方案含未核验食材，无法确认过敏安全", 409)
    if budget["has_target"] and not _within_energy_budget(
            total_kcal, float(budget["energy"]["remaining_kcal"])):
        raise ApiError("HARD_CONSTRAINT_VIOLATION", "方案超出当日剩余热量，请重新调整", 409)


def new_chat() -> dict:
    profile = get_profile()["profile"]
    ident = new_id()
    with transaction() as db:
        db.execute("INSERT INTO chat_sessions(id,user_id,purpose,profile_version) VALUES (?,?,'meal_decision',?)",
                   (ident, USER_ID, profile["profile_version"]))
    return {"id": ident, "status": "ACTIVE", "messages": []}


def get_chat(chat_id: str) -> dict:
    with connect() as db:
        session = row_dict(db.execute("SELECT * FROM chat_sessions WHERE id=? AND user_id=?", (chat_id, USER_ID)).fetchone())
        if not session:
            raise ApiError("NOT_FOUND", "对话不存在", 404)
        messages = [dict(r) for r in db.execute("SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at,rowid", (chat_id,))]
    for message in messages:
        message["structured_payload"] = json.loads(message.pop("structured_payload_json")) if message["structured_payload_json"] else None
    return {"session": session, "messages": messages}


def send_message(chat_id: str, content: str) -> dict:
    session = get_chat(chat_id)
    require(session["session"]["status"] == "ACTIVE", "对话已结束")
    content = str(content).strip()
    require(1 <= len(content) <= 1000, "消息需在 1-1000 字之间")
    state = get_profile()
    budget = day_summary(today())
    with connect() as db:
        catalog = [{"id": r["id"], "name": r["name"]} for r in db.execute("SELECT id,name FROM food_items ORDER BY id")]
    safe_recipes = _safe_recipes(state, budget)
    history = [{"role": m["role"], "content": m["content_redacted"]} for m in session["messages"][-12:]]
    response = invoke("food_chat", {
        "messages": history + [{"role": "user", "content": content}],
        "context": {"goal_type": state["goal"]["goal_type"] if state["goal"] else None,
                    "remaining_kcal": budget["energy"]["remaining_kcal"],
                    "dining": state["dining"],
                    "allergies": state["allergies"], "restrictions": state["restrictions"],
                    "preferences": state["preferences"], "known_foods": catalog,
                    "safe_recipes": [{"recipe_id": key, "name": value["recipe"]["name"],
                                      "estimated_cost_cny": value["recipe"]["estimated_cost_cny"],
                                      "nutrition": value["nutrition"]}
                                     for key, value in safe_recipes.items()]},
        "instruction": "用中文多轮澄清并提出饮食方案。只返回 JSON：reply 字符串；可选 proposal 对象含 meal_type 和 recipe_id（从 safe_recipes 选择），服务端会按菜谱重建食材与价格。未设置价格上限时，也可返回含 items 的自由方案，每项提供 name、food_id、grams、kcal、allergens。过敏原、忌口与价格上限是绝对约束。"
    })
    reply = response.get("reply")
    require(isinstance(reply, str) and 1 <= len(reply) <= 4000, "Agent 回复格式无效", "AGENT_INVALID_RESPONSE")
    proposal = response.get("proposal")
    if proposal is not None:
        require(isinstance(proposal, dict), "Agent 方案格式无效", "AGENT_INVALID_RESPONSE")
        proposal = _canonical_proposal(proposal, state, budget)
        _check_proposal(proposal, state, budget)
    with transaction() as db:
        db.execute("INSERT INTO chat_messages(id,session_id,role,content_redacted) VALUES (?,?,?,?)",
                   (new_id(), chat_id, "user", content))
        db.execute("""INSERT INTO chat_messages(id,session_id,role,content_redacted,structured_payload_json)
            VALUES (?,?,?,?,?)""", (new_id(), chat_id, "assistant", reply,
                                    as_json(proposal) if proposal is not None else None))
    return {"reply": reply, "proposal": proposal, "chat_id": chat_id}


def accept_proposal(chat_id: str, idempotency_key: str | None = None) -> dict:
    chat = get_chat(chat_id)
    with connect() as db:
        previous = db.execute("""SELECT id,status,deleted_at FROM meals WHERE user_id=?
            AND source_type='chat_agent' AND source_ref_id=?""", (USER_ID, chat_id)).fetchone()
    if previous:
        if previous["deleted_at"] is not None:
            raise ApiError("ALREADY_REMOVED", "这份对话方案已删除；请重新开始对话", 409)
        return {"meal_id": previous["id"], "status": previous["status"]}
    require(chat["session"]["status"] == "ACTIVE", "对话已结束")
    proposals = [m["structured_payload"] for m in chat["messages"] if m["role"] == "assistant" and m["structured_payload"]]
    require(bool(proposals), "对话尚无可确认方案")
    proposal = proposals[-1]
    state = get_profile()
    budget = day_summary(today())
    if proposal.get("recipe_id"):
        refreshed = _canonical_proposal(proposal, state, budget)
        if refreshed != proposal:
            raise ApiError("HARD_CONSTRAINT_VIOLATION", "菜谱数据已变化，请重新确认方案", 409)
    else:
        proposal = _canonical_proposal(proposal, state, budget)
    _check_proposal(proposal, state, budget)
    items = []
    for item in proposal["items"]:
        recorded = {"display_name": item["name"], "amount": item["grams"],
                    "unit": "g", "grams": item["grams"], "kcal": item["kcal"]}
        for key in ("carb_g", "protein_g", "fat_g", "fiber_g"):
            if key in item and item[key] is not None:
                recorded[key] = item[key]
        items.append(recorded)
    # The chat session is the business idempotency boundary, not a fresh
    # client-generated request key on every tap.
    meal = create_meal({"meal_type": proposal["meal_type"], "status": "PLANNED", "items": items,
                        "source_type": "chat_agent", "source_ref_id": chat_id},
                       f"chat-{chat_id}")
    with transaction() as db:
        db.execute("UPDATE chat_sessions SET status='ACCEPTED',ended_at=? WHERE id=?", (utc_now(), chat_id))
    return {"meal_id": meal["id"], "status": "PLANNED"}
