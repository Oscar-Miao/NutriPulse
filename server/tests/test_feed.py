import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.infrastructure.content.feed import (
    _AllowlistRedirect, _clean, _published_at, _safe_url, public_articles, refresh_feed,
)
from app.infrastructure.db.database import connect, migrate
from app.shared.errors import ApiError


class FakeResponse:
    def __init__(self, url, content):
        self.url = url
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, _):
        return self.content


class FeedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = {key: os.environ.get(key) for key in
                    ("NUTRIPULSE_DB", "NUTRIPULSE_RSS_URL", "NUTRIPULSE_RSS_ALLOWED_HOSTS")}
        os.environ["NUTRIPULSE_DB"] = str(Path(self.temp.name) / "feed.sqlite3")
        os.environ["NUTRIPULSE_RSS_URL"] = "https://feed.example.com/rss.xml"
        os.environ["NUTRIPULSE_RSS_ALLOWED_HOSTS"] = "images.example.com"
        migrate()

    def tearDown(self):
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    def feed(self, content, final_url="https://feed.example.com/rss.xml"):
        class FakeOpener:
            def open(self, *_args, **_kwargs):
                return FakeResponse(final_url, content.encode("utf-8"))
        with patch("app.infrastructure.content.feed.urllib.request.build_opener", return_value=FakeOpener()):
            return refresh_feed()

    def test_import_sanitizes_content_and_filters_links(self):
        xml = """<rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
          <item><title>Good &lt;b&gt;Title&lt;/b&gt;</title>
            <description>&lt;script&gt;bad()&lt;/script&gt;&lt;p&gt;Healthy&lt;/p&gt;</description>
            <link>https://feed.example.com/story</link>
            <pubDate>Fri, 02 Oct 2026 12:00:00 +0800</pubDate>
            <media:content url="https://images.example.com/cover.jpg"/></item>
          <item><title>Blocked</title><link>https://evil.example.org/story</link></item>
          </channel></rss>"""
        self.assertEqual(self.feed(xml)["imported"], 1)
        self.assertEqual(self.feed(xml)["imported"], 0)
        with connect() as db:
            rows = [dict(r) for r in db.execute("SELECT source,source_url,title,summary,cover_url,published_at FROM articles")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Good Title")
        self.assertEqual(rows[0]["summary"], "Healthy")
        self.assertEqual(rows[0]["published_at"], "2026-10-02 04:00:00")
        self.assertEqual(rows[0]["cover_url"], "https://images.example.com/cover.jpg")
        self.assertEqual(public_articles(rows)[0]["title"], "Good Title")

    def test_unsafe_urls_redirect_and_failed_refresh_keep_cache(self):
        trusted = {"feed.example.com"}
        for url in ("http://feed.example.com/a", "https://feed.example.com.evil.org/a",
                    "https://user@feed.example.com/a", "https://feed.example.com:8888/a",
                    "https://127.0.0.1/a", "https://feed.example.com/a#part"):
            self.assertFalse(_safe_url(url, trusted), url)
        self.assertTrue(_safe_url("https://feed.example.com/a", trusted))
        redirect = _AllowlistRedirect(trusted)
        with self.assertRaises(ApiError):
            redirect.redirect_request(None, None, 302, "", {}, "https://evil.example.org/a")
        good = "<rss><channel><item><title>News</title><link>https://feed.example.com/a</link></item></channel></rss>"
        self.feed(good)
        with self.assertRaises(ApiError):
            self.feed("<rss/>", final_url="https://evil.example.org/rss")
        with self.assertRaises(ApiError):
            self.feed("<!DOCTYPE foo><rss/>")
        with connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 1)

    def test_clean_and_date_fallback(self):
        self.assertEqual(_clean("&lt;script&gt;bad&lt;/script&gt;Good", 100), "Good")
        self.assertEqual(_published_at("invalid", __import__("datetime").datetime(2026, 10, 3)),
                         "2026-10-03 00:00:00")


if __name__ == "__main__":
    unittest.main()
