from __future__ import annotations

from app.infrastructure.db.database import connect, row_dict, transaction
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, new_id, number, today, utc_now, valid_date


MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}


def list_foods(query: str = "") -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM food_items WHERE name LIKE ? ORDER BY verified DESC, name LIMIT 30",
                          (f"%{query[:80]}%",)).fetchall()
    return [dict(r) for r in rows]


def frequent_foods(limit: int = 10) -> list[dict]:
    """Most used actually consumed foods; use the latest weighed entry as a draft.

    Planned, archived and soft-deleted meals must not train a user's shortcuts.
    Nutrition values remain per recorded portion rather than fabricated per-100g
    values for foods with no reliable gram conversion.
    """
    with connect() as db:
        rows = db.execute("""WITH ranked AS (
            SELECT i.food_id,i.display_name,i.amount,i.unit,i.grams,i.kcal,
                   i.carb_g,i.protein_g,i.fat_g,i.fiber_g,i.nutrient_known_mask,m.local_date,
                   COUNT(*) OVER (PARTITION BY COALESCE(i.food_id,LOWER(TRIM(i.display_name)))) AS use_count,
                   ROW_NUMBER() OVER (PARTITION BY COALESCE(i.food_id,LOWER(TRIM(i.display_name)))
                       ORDER BY m.local_date DESC,m.created_at DESC,i.rowid DESC) AS rn
            FROM meal_items i JOIN meals m ON m.id=i.meal_id
            WHERE m.user_id=? AND m.status='CONSUMED' AND m.deleted_at IS NULL
        ) SELECT food_id,display_name,amount,unit,grams,kcal,carb_g,protein_g,fat_g,
                 fiber_g,nutrient_known_mask,local_date,use_count FROM ranked WHERE rn=1
          ORDER BY use_count DESC,local_date DESC,display_name LIMIT ?""",
          (USER_ID, limit)).fetchall()
    return [dict(row) for row in rows]


def _validated_items(items: list[dict]) -> list[dict]:
    require(isinstance(items, list) and 1 <= len(items) <= 30, "至少需要一项食物，最多 30 项")
    validated = []
    for item in items:
        require(isinstance(item, dict), "食物项无效")
        name = str(item.get("display_name") or item.get("name") or "").strip()
        require(1 <= len(name) <= 100, "食物名称需在 1-100 字之间")
        amount = number(item.get("amount", 1), "份量", 0.01, 10000)
        unit = str(item.get("unit") or "g").strip()
        require(unit in ("g", "ml", "份", "个"), "份量单位无效")
        def nutrient(key: str, label: str) -> float:
            value = item.get(key)
            return number(0 if value is None else value, label, 0, 2000)
        nutrient_bits = (("carb_g", 1), ("protein_g", 2), ("fat_g", 4), ("fiber_g", 8))
        if "nutrient_known_mask" in item:
            raw_mask = number(item["nutrient_known_mask"], "营养完整度标记", 0, 15)
            require(raw_mask.is_integer(), "营养完整度标记须为整数")
            known_mask = int(raw_mask)
            require(all((known_mask & bit) == 0 or item.get(key) is not None
                        for key, bit in nutrient_bits), "已知营养素不能缺少数值")
        else:
            known_mask = sum(bit for key, bit in nutrient_bits
                             if key in item and item[key] is not None)
        validated.append({
            "id": new_id(), "food_id": item.get("food_id"), "display_name": name,
            "amount": amount, "unit": unit,
            "grams": number(item["grams"], "克数", 0, 10000) if item.get("grams") is not None else None,
            "kcal": number(item.get("kcal"), "热量", 0, 20000),
            "carb_g": nutrient("carb_g", "碳水"),
            "protein_g": nutrient("protein_g", "蛋白质"),
            "fat_g": nutrient("fat_g", "脂肪"),
            "fiber_g": nutrient("fiber_g", "膳食纤维"),
            "nutrient_known_mask": known_mask,
            "confidence": item.get("confidence"),
            "user_edited": int(bool(item.get("user_edited", False))),
        })
    return validated


def _insert_meal(db, meal_id: str, day: str, meal_type: str, status: str,
                 items: list[dict], source_type: str, source_ref_id: str | None,
                 idempotency_key: str | None, note: str | None = None) -> None:
    stamp = utc_now()
    db.execute("""INSERT INTO meals(id,user_id,local_date,meal_type,status,planned_at,consumed_at,
        source_type,source_ref_id,idempotency_key,note) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (meal_id, USER_ID, day, meal_type, status, stamp if status == "PLANNED" else None,
         stamp if status == "CONSUMED" else None, source_type, source_ref_id, idempotency_key, note))
    for item in items:
        db.execute("""INSERT INTO meal_items(id,meal_id,food_id,display_name,amount,unit,grams,kcal,
            carb_g,protein_g,fat_g,fiber_g,nutrient_known_mask,confidence,user_edited)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item["id"], meal_id, item["food_id"], item["display_name"], item["amount"],
             item["unit"], item["grams"], item["kcal"], item["carb_g"], item["protein_g"],
             item["fat_g"], item["fiber_g"], item["nutrient_known_mask"], item["confidence"], item["user_edited"]))
    db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
               (new_id(), "MealLogged", meal_id, as_json({"local_date": day, "status": status})))


def create_meal(data: dict, idempotency_key: str | None = None) -> dict:
    day = valid_date(data.get("local_date") or today())
    meal_type = data.get("meal_type")
    require(meal_type in MEAL_TYPES, "餐别无效")
    status = data.get("status", "CONSUMED")
    require(status in ("PLANNED", "CONSUMED"), "新餐食状态无效")
    items = _validated_items(data.get("items", []))
    ident = new_id()
    with transaction() as db:
        old = db.execute("SELECT id FROM meals WHERE idempotency_key=?", (idempotency_key,)).fetchone() \
            if idempotency_key else None
        if old:
            ident = old["id"]
        else:
            _insert_meal(db, ident, day, meal_type, status, items,
                         str(data.get("source_type") or "manual"), data.get("source_ref_id"),
                         idempotency_key, data.get("note"))
    return get_meal(ident)


def get_meal(meal_id: str) -> dict:
    with connect() as db:
        meal = row_dict(db.execute("SELECT * FROM meals WHERE id=? AND user_id=? AND deleted_at IS NULL",
                                   (meal_id, USER_ID)).fetchone())
        if not meal:
            raise ApiError("NOT_FOUND", "餐食不存在", 404)
        meal["items"] = [dict(r) for r in db.execute("SELECT * FROM meal_items WHERE meal_id=? ORDER BY rowid", (meal_id,))]
    return meal


def list_meals(day: str) -> list[dict]:
    valid_date(day)
    with connect() as db:
        ids = [r[0] for r in db.execute("""SELECT id FROM meals WHERE user_id=? AND local_date=?
            AND deleted_at IS NULL AND status!='ARCHIVED' ORDER BY created_at DESC""", (USER_ID, day))]
    return [get_meal(ident) for ident in ids]


def update_meal(meal_id: str, data: dict) -> dict:
    original = get_meal(meal_id)
    status = data.get("status", original["status"])
    allowed = {"PLANNED": {"PLANNED", "CONSUMED", "ARCHIVED"},
               "CONSUMED": {"CONSUMED", "ARCHIVED"},
               "DRAFT": {"DRAFT", "PLANNED", "CONSUMED", "ARCHIVED"}}
    require(status in allowed.get(original["status"], set()), "餐食状态迁移无效")
    meal_type = data.get("meal_type", original["meal_type"])
    require(meal_type in MEAL_TYPES, "餐别无效")
    items = _validated_items(data["items"]) if "items" in data else None
    with transaction() as db:
        db.execute("""UPDATE meals SET meal_type=?, status=?, consumed_at=CASE WHEN ?='CONSUMED'
            AND consumed_at IS NULL THEN ? ELSE consumed_at END, note=?, updated_at=? WHERE id=?""",
            (meal_type, status, status, utc_now(), data.get("note", original["note"]), utc_now(), meal_id))
        if items is not None:
            db.execute("DELETE FROM meal_items WHERE meal_id=?", (meal_id,))
            for item in items:
                db.execute("""INSERT INTO meal_items(id,meal_id,food_id,display_name,amount,unit,grams,
                    kcal,carb_g,protein_g,fat_g,fiber_g,nutrient_known_mask,confidence,user_edited)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item["id"], meal_id, item["food_id"], item["display_name"], item["amount"],
                     item["unit"], item["grams"], item["kcal"], item["carb_g"], item["protein_g"],
                     item["fat_g"], item["fiber_g"], item["nutrient_known_mask"], item["confidence"], item["user_edited"]))
        db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
                   (new_id(), "MealStatusChanged", meal_id, as_json({"local_date": original["local_date"], "status": status})))
    return get_meal(meal_id)


def delete_meal(meal_id: str) -> dict:
    with transaction() as db:
        original = db.execute("SELECT local_date,status,deleted_at FROM meals WHERE id=? AND user_id=?",
                              (meal_id, USER_ID)).fetchone()
        if original is None:
            raise ApiError("NOT_FOUND", "餐食不存在", 404)
        if original["deleted_at"] is not None:
            return {"id": meal_id, "deleted": True}
        db.execute("UPDATE meals SET status_before_delete=?,status='ARCHIVED', deleted_at=?, updated_at=? WHERE id=?",
            (original["status"], utc_now(), utc_now(), meal_id))
        db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
                   (new_id(), "MealStatusChanged", meal_id, as_json({"local_date": original["local_date"], "status": "ARCHIVED"})))
    return {"id": meal_id, "deleted": True}


def restore_meal(meal_id: str) -> dict:
    with transaction() as db:
        row = db.execute("SELECT * FROM meals WHERE id=? AND user_id=? AND deleted_at IS NOT NULL",
                         (meal_id, USER_ID)).fetchone()
        if not row:
            raise ApiError("NOT_FOUND", "没有可撤销的删除记录", 404)
        from datetime import datetime, timezone
        deleted_at = datetime.fromisoformat(row["deleted_at"])
        require((datetime.now(timezone.utc) - deleted_at).total_seconds() <= 5,
                "撤销窗口已过期", "UNDO_EXPIRED")
        status = row["status_before_delete"] or "CONSUMED"
        db.execute("""UPDATE meals SET status=?,deleted_at=NULL,status_before_delete=NULL,updated_at=?
            WHERE id=?""", (status, utc_now(), meal_id))
        db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
                   (new_id(), "MealRestored", meal_id, as_json({"local_date": row["local_date"], "status": status})))
    return get_meal(meal_id)


def add_water(data: dict, idempotency_key: str | None = None) -> dict:
    day = valid_date(data.get("local_date") or today())
    amount = int(number(data.get("amount_ml"), "饮水量", 1, 5000))
    with transaction() as db:
        if idempotency_key:
            old = db.execute("SELECT id,local_date,amount_ml FROM water_logs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if old:
                return dict(old)
        ident = new_id()
        db.execute("""INSERT INTO water_logs(id,user_id,occurred_at,local_date,amount_ml,idempotency_key)
            VALUES (?,?,?,?,?,?)""", (ident, USER_ID, utc_now(), day, amount, idempotency_key))
    return {"id": ident, "local_date": day, "amount_ml": amount}


def set_water_total(day: str, data: dict) -> dict:
    day = valid_date(day)
    desired = int(number(data.get("total_ml"), "当日饮水总量", 0, 10000))
    with transaction() as db:
        current = int(db.execute("SELECT COALESCE(SUM(amount_ml),0) FROM water_logs WHERE user_id=? AND local_date=?",
                                 (USER_ID, day)).fetchone()[0])
        difference = desired - current
        while difference > 0:
            portion = min(5000, difference)
            db.execute("""INSERT INTO water_logs(id,user_id,occurred_at,local_date,amount_ml,source_type)
                VALUES (?,?,?,?,?,'adjustment')""", (new_id(), USER_ID, utc_now(), day, portion))
            difference -= portion
        if difference < 0:
            remove = -difference
            rows = db.execute("SELECT id,amount_ml FROM water_logs WHERE user_id=? AND local_date=? ORDER BY rowid DESC",
                              (USER_ID, day)).fetchall()
            for row in rows:
                if remove == 0:
                    break
                deducted = min(remove, row["amount_ml"])
                if deducted == row["amount_ml"]:
                    db.execute("DELETE FROM water_logs WHERE id=?", (row["id"],))
                else:
                    db.execute("UPDATE water_logs SET amount_ml=? WHERE id=?",
                               (row["amount_ml"] - deducted, row["id"]))
                remove -= deducted
        db.execute("INSERT INTO outbox_events(id,event_type,aggregate_id,payload_json) VALUES (?,?,?,?)",
                   (new_id(), "WaterAdjusted", day, as_json({"previous_ml": current, "total_ml": desired})))
    return {"local_date": day, "total_ml": desired}
