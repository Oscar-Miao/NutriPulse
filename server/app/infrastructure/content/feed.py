from __future__ import annotations

import hashlib
import html
import ipaddress
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone

from app.infrastructure.db.database import transaction
from app.shared.errors import ApiError
from app.shared.util import new_id, utc_now


def _clean(value: str, limit: int) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", "", value,
                   flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]*>", "", value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _safe_url(value: str, allowed_hosts: set[str]) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        if parsed.scheme != "https" or host not in allowed_hosts or parsed.username is not None or parsed.password is not None:
            return False
        if port not in (None, 443) or parsed.fragment:
            return False
    except ValueError:
        return False
    try:
        ipaddress.ip_address(host)
        return False  # Never fetch URLs addressed by IP literal.
    except ValueError:
        return bool(host)


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _safe_url(newurl, self.allowed_hosts):
            raise ApiError("FEED_UNSAFE_REDIRECT", "资讯源跳转至未授权地址", 502)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _published_at(raw: str | None, fallback: datetime) -> str:
    try:
        value = parsedate_to_datetime(raw or "")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, IndexError):
        return fallback.strftime("%Y-%m-%d %H:%M:%S")


def allowed_hosts() -> set[str]:
    try:
        source = (urllib.parse.urlsplit(os.environ.get("NUTRIPULSE_RSS_URL", "").strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        source = ""
    extras = {host.strip().lower().rstrip(".") for host in
              os.environ.get("NUTRIPULSE_RSS_ALLOWED_HOSTS", "").split(",") if host.strip()}
    return ({source} if source else set()) | extras


def public_articles(rows: list[dict]) -> list[dict]:
    trusted = allowed_hosts()
    result = []
    for row in rows:
        if not _safe_url(row["source_url"], trusted):
            continue
        cleaned = dict(row)
        cleaned["title"] = _clean(cleaned["title"], 120)
        cleaned["summary"] = _clean(cleaned["summary"], 280)
        cleaned["source"] = _clean(cleaned["source"], 120)
        if not _safe_url(cleaned.get("cover_url") or "", trusted):
            cleaned["cover_url"] = None
        if cleaned["title"]:
            result.append(cleaned)
    return result


def refresh_feed() -> dict:
    url = os.environ.get("NUTRIPULSE_RSS_URL", "").strip()
    if not url:
        return {"status": "not_configured", "imported": 0}
    try:
        source = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError as error:
        raise ApiError("FEED_CONFIGURATION_ERROR", "资讯源 URL 无效", 503) from error
    trusted = allowed_hosts()
    if not _safe_url(url, trusted):
        raise ApiError("FEED_CONFIGURATION_ERROR", "资讯源必须是受信任域名的 HTTPS 地址", 503)
    request = urllib.request.Request(url, headers={"User-Agent": "NutriPulse/0.1"})
    try:
        opener = urllib.request.build_opener(_AllowlistRedirect(trusted))
        with opener.open(request, timeout=15) as response:
            if not _safe_url(response.geturl(), trusted):
                raise ApiError("FEED_UNSAFE_REDIRECT", "资讯源跳转至未授权地址", 502)
            content = response.read(1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise ApiError("FEED_UNAVAILABLE", "资讯源暂不可用", 503) from error
    if len(content) > 1024 * 1024:
        raise ApiError("FEED_INVALID", "资讯源响应过大", 502)
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", content, re.IGNORECASE):
        raise ApiError("FEED_INVALID", "资讯源包含不允许的 XML 声明", 502)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise ApiError("FEED_INVALID", "资讯源 XML 无效", 502) from error
    imported = 0
    now = datetime.now(timezone.utc)
    expiry = (now + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    with transaction() as db:
        for node in root.findall(".//item")[:20]:
            title = _clean(node.findtext("title") or "", 120)
            summary = _clean(node.findtext("description") or "", 280)
            link = (node.findtext("link") or "").strip()
            if not title or not _safe_url(link, trusted):
                continue
            enclosure = node.find("enclosure")
            media = node.find("{http://search.yahoo.com/mrss/}content")
            thumbnail = node.find("{http://search.yahoo.com/mrss/}thumbnail")
            cover = next((candidate for candidate in (
                enclosure.get("url") if enclosure is not None and (enclosure.get("type") or "").startswith("image/") else None,
                media.get("url") if media is not None else None,
                thumbnail.get("url") if thumbnail is not None else None,
            ) if candidate and _safe_url(candidate, trusted)), None)
            digest = hashlib.sha256((title + link).encode("utf-8")).hexdigest()
            count = db.execute("""INSERT OR IGNORE INTO articles(id,source,source_url,title,summary,
                cover_url,published_at,expires_at,content_hash) VALUES (?,?,?,?,?,?,?,?,?)""",
                (new_id(), source, link, title, summary, cover,
                 _published_at(node.findtext("pubDate"), now), expiry, digest)).rowcount
            imported += count
    return {"status": "ok", "imported": imported, "source": source}
