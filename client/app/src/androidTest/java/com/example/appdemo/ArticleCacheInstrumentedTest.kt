package com.example.appdemo

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.appdemo.core.database.ArticleCache
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ArticleCacheInstrumentedTest {
    @Test
    fun keepsOnlyPublicSafeMetadataAndSeparatesServers() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.getSharedPreferences("nutripulse_article_cache", 0).edit().clear().commit()
        try {
            val valid = JSONObject().put("title", "营养小贴士")
                .put("source", "测试资讯")
                .put("source_url", "https://example.com/article")
                .put("cover_url", "http://example.com/unsafe.png")
                .put("private_token", "must-not-cache")
            val invalid = JSONObject().put("title", "无效")
                .put("source_url", "https://user@example.com/article")
            val cache = ArticleCache(context)
            cache.save("http://10.0.2.2:8787", JSONArray().put(valid).put(invalid))
            val snapshot = cache.load("http://10.0.2.2:8787")
            assertNotNull(snapshot)
            assertEquals(1, snapshot!!.articles.length())
            assertFalse(snapshot.articles.getJSONObject(0).has("private_token"))
            assertFalse(snapshot.articles.getJSONObject(0).has("cover_url"))
            assertNull(cache.load("https://another.example.com"))
        } finally {
            context.getSharedPreferences("nutripulse_article_cache", 0).edit().clear().commit()
        }
    }
}
