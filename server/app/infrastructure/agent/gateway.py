from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app.shared.errors import ApiError


def configured() -> bool:
    return bool(os.environ.get("NUTRIPULSE_AGENT_URL"))


def invoke(agent_type: str, payload: dict, timeout: int = 45) -> dict:
    """Call a configured HTTPS agent gateway using a stable JSON envelope.

    Request: {"agent_type": "food_vision|food_chat|meal_recommendation|diagnosis|workout_recovery", "input": {...}}
    Response: a JSON object specific to the agent type, documented in server/README.md.
    """
    url = os.environ.get("NUTRIPULSE_AGENT_URL", "")
    if not url:
        raise ApiError("AGENT_UNAVAILABLE", "尚未配置联网 Agent 服务", 503)
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1:"):
        raise ApiError("AGENT_CONFIGURATION_ERROR", "Agent 地址必须使用 HTTPS 或本机回环地址", 503)
    body = json.dumps({"agent_type": agent_type, "input": payload}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"}
    token = os.environ.get("NUTRIPULSE_AGENT_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise ApiError("AGENT_UNAVAILABLE", "联网 Agent 服务返回错误", 503)
            raw = response.read(2 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise ApiError("AGENT_UNAVAILABLE", "联网 Agent 服务不可用，请稍后重试", 503) from error
    if len(raw) > 2 * 1024 * 1024:
        raise ApiError("AGENT_INVALID_RESPONSE", "Agent 响应过大", 502)
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ApiError("AGENT_INVALID_RESPONSE", "Agent 响应不是有效 JSON", 502) from error
    if not isinstance(result, dict):
        raise ApiError("AGENT_INVALID_RESPONSE", "Agent 响应格式无效", 502)
    return result
