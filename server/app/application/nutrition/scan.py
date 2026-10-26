from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

from app.application.nutrition.service import _insert_meal, _validated_items, get_meal
from app.infrastructure.agent.gateway import invoke
from app.infrastructure.db.database import connect, row_dict, transaction
from app.infrastructure.files.image_upload import clean_upload_image
from app.shared.errors import ApiError, require
from app.shared.util import USER_ID, as_json, new_id, number, today, utc_now, valid_date


def _scan_response(row) -> dict:
    return {"id": row["id"], "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None}


def _agent_notes(value, field: str) -> list[str]:
    require(isinstance(value, list) and len(value) <= 10 and
            all(isinstance(note, str) and 0 < len(note.strip()) <= 200 for note in value),
            f"Agent {field}格式无效", "AGENT_INVALID_RESPONSE")
    return [note.strip() for note in value]


def create_scan(data: dict, idempotency_key: str | None = None) -> dict:
    encoded = data.get("image_base64")
    mime = data.get("mime_type", "image/jpeg")
    require(isinstance(encoded, str) and mime in ("image/jpeg", "image/png", "image/webp"), "请上传 JPEG、PNG 或 WebP 图片")
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ApiError("VALIDATION_ERROR", "图片编码无效")
    require(1_000 <= len(image) <= 3_500_000, "图片大小需在 1 KB 至 3.5 MB 之间")
    clean_image = clean_upload_image(image, mime)
    if idempotency_key is not None:
        require(isinstance(idempotency_key, str) and
                re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key) is not None,
                "识餐重试键无效")
    input_hash = hashlib.sha256(mime.encode("ascii") + b"\0" + image).hexdigest()
    ident = new_id()
    attempt_id = new_id()
    with transaction() as db:
        old = db.execute("SELECT * FROM food_scan_jobs WHERE user_id=? AND idempotency_key=?",
                         (USER_ID, idempotency_key)).fetchone() if idempotency_key else None
        if old:
            if old["input_hash"] != input_hash:
                raise ApiError("VERSION_CONFLICT", "同一识餐重试键不能用于不同照片", 409)
            ident = old["id"]
            if old["status"] in ("REVIEW_REQUIRED", "CONFIRMED"):
                return _scan_response(old)
            if old["status"] == "PROCESSING" and old["processing_started_at"]:
                started = datetime.fromisoformat(old["processing_started_at"])
                if (datetime.now(timezone.utc) - started).total_seconds() < 120:
                    return _scan_response(old)
            # A failed attempt can be retried. A process killed mid-call is
            # reclaimed after 120 s; its late result cannot overwrite this attempt.
            db.execute("""UPDATE food_scan_jobs SET status='PROCESSING',result_json=NULL,error_code=NULL,
                attempt_id=?,processing_started_at=? WHERE id=?""", (attempt_id, utc_now(), ident))
        else:
            db.execute("""INSERT INTO food_scan_jobs(id,user_id,status,idempotency_key,input_hash,
                attempt_id,processing_started_at) VALUES (?,?,'PROCESSING',?,?,?,?)""",
                (ident, USER_ID, idempotency_key, input_hash, attempt_id, utc_now()))
    started = time.monotonic()
    try:
        output = invoke("food_vision", {"image_base64": base64.b64encode(clean_image).decode("ascii"),
                                        "mime_type": "image/jpeg",
                                        "meal_type_hint": data.get("meal_type_hint"),
                                        "instruction": "识别食物，返回 items 数组；每项必须有 name, estimated_grams, kcal, carb_g, protein_g, fat_g, confidence。估算需标注不确定性。"})
        items = output.get("items")
        require(isinstance(items, list) and 1 <= len(items) <= 20, "Agent 没有返回有效食物清单", "AGENT_INVALID_RESPONSE")
        checked = []
        for item in items:
            require(isinstance(item, dict), "Agent 食物项无效", "AGENT_INVALID_RESPONSE")
            name = str(item.get("name", "")).strip()
            require(1 <= len(name) <= 100, "Agent 食物名称无效", "AGENT_INVALID_RESPONSE")
            require(all(key in item and item[key] is not None for key in
                        ("kcal", "carb_g", "protein_g", "fat_g")),
                    "Agent 营养字段不完整", "AGENT_INVALID_RESPONSE")
            grams = number(item.get("estimated_grams"), "估算克数", 1, 10000)
            confidence = number(item.get("confidence"), "置信度", 0, 1)
            checked.append({"name": name, "estimated_grams": grams,
                            "kcal": number(item.get("kcal"), "热量", 0, 20000),
                            "carb_g": number(item.get("carb_g"), "碳水", 0, 2000),
                            "protein_g": number(item.get("protein_g"), "蛋白质", 0, 2000),
                            "fat_g": number(item.get("fat_g"), "脂肪", 0, 2000),
                            "confidence": confidence,
                            "assumptions": _agent_notes(item.get("assumptions", []), "假设")})
        warnings = _agent_notes(output.get("warnings", []), "警告")
        if any(item["confidence"] < 0.7 for item in checked):
            warnings = list(warnings) + ["部分食物识别置信度较低，请核对名称和克数"]
        result = {"items": checked, "warnings": warnings}
        status, error_code = "REVIEW_REQUIRED", None
    except ApiError as error:
        result, status, error_code = None, "FAILED", error.code
    except Exception:
        logging.exception("food vision invocation failed")
        result, status, error_code = None, "FAILED", "AGENT_UNAVAILABLE"
    with transaction() as db:
        updated = db.execute("""UPDATE food_scan_jobs SET status=?,result_json=?,error_code=?,model_version=?
            WHERE id=? AND attempt_id=?""",
            (status, as_json(result) if result else None, error_code, "remote-v1", ident, attempt_id)).rowcount
        db.execute("""INSERT INTO agent_runs(id,user_id,agent_type,provider,model,prompt_version,input_hash,
            output_json,status,latency_ms,error_code) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (new_id(), USER_ID, "food_vision", "configured_gateway", "remote", "food_vision.v1",
             hashlib.sha256(clean_image).hexdigest(), as_json(result) if result else None,
             status if updated else "SUPERSEDED", int((time.monotonic() - started) * 1000), error_code))
    if not updated:
        current = get_scan(ident)
        return {"id": current["id"], "status": current["status"], "result": current["result"]}
    if status == "FAILED":
        raise ApiError(error_code or "AGENT_UNAVAILABLE", "识别未完成，请重试或手工记录", 503)
    return {"id": ident, "status": status, "result": result}


def get_scan(scan_id: str) -> dict:
    with connect() as db:
        row = row_dict(db.execute("SELECT * FROM food_scan_jobs WHERE id=? AND user_id=?", (scan_id, USER_ID)).fetchone())
    if not row:
        raise ApiError("NOT_FOUND", "识餐任务不存在", 404)
    row["result"] = json.loads(row.pop("result_json")) if row.get("result_json") else None
    return row


def confirm_scan(scan_id: str, data: dict) -> dict:
    scan = get_scan(scan_id)
    if scan["status"] == "CONFIRMED":
        with connect() as db:
            existing = db.execute("SELECT id FROM meals WHERE source_type='food_scan' AND source_ref_id=?", (scan_id,)).fetchone()
        if existing:
            return get_meal(existing["id"])
    require(scan["status"] == "REVIEW_REQUIRED", "识餐任务尚未可确认")
    day = valid_date(data.get("local_date") or today())
    meal_type = data.get("meal_type")
    require(meal_type in ("breakfast", "lunch", "dinner", "snack"), "餐别无效")
    if "items" in data:
        # An explicitly empty review means the user removed every suggestion.
        # Never fall back to the unreviewed model output in that case.
        raw_items = data["items"]
    else:
        raw_items = [
            {"display_name": item["name"], "amount": item["estimated_grams"], "unit": "g",
             "grams": item["estimated_grams"], "kcal": item["kcal"], "carb_g": item["carb_g"],
             "protein_g": item["protein_g"], "fat_g": item["fat_g"], "confidence": item["confidence"]}
            for item in scan["result"]["items"]]
    items = _validated_items(raw_items)
    ident = new_id()
    with transaction() as db:
        state = db.execute("SELECT status FROM food_scan_jobs WHERE id=?", (scan_id,)).fetchone()[0]
        if state == "CONFIRMED":
            existing = db.execute("SELECT id FROM meals WHERE source_type='food_scan' AND source_ref_id=?",
                                  (scan_id,)).fetchone()
            if not existing:
                raise ApiError("VERSION_CONFLICT", "识餐任务已确认但餐食缺失，请检查数据", 409)
            ident = existing["id"]
        else:
            _insert_meal(db, ident, day, meal_type, "CONSUMED", items,
                         "food_scan", scan_id, f"food-scan-{scan_id}")
            db.execute("UPDATE food_scan_jobs SET status='CONFIRMED' WHERE id=?", (scan_id,))
    return get_meal(ident)
