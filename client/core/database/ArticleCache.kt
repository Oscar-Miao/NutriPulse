package com.example.appdemo.core.database

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Public article metadata only; never stores profile or authentication data. */
class ArticleCache(context: Context) {
    private val preferences = context.getSharedPreferences("nutripulse_article_cache", Context.MODE_PRIVATE)

    data class Snapshot(val articles: JSONArray, val updatedAt: Long)

    fun load(serverUrl: String): Snapshot? {
        return try {
            if (preferences.getString("server_url", null) != serverUrl) null
            else {
                val updatedAt = preferences.getLong("updated_at", 0)
                val articles = JSONArray(preferences.getString("articles", "[]"))
                if (updatedAt <= 0 || articles.length() == 0) null else Snapshot(articles, updatedAt)
            }
        } catch (_: Exception) { null }
    }

    fun save(serverUrl: String, articles: JSONArray) {
        val safe = JSONArray()
        for (index in 0 until minOf(articles.length(), 10)) {
            val item = articles.optJSONObject(index) ?: continue
            val link = item.optString("source_url")
            if (!isHttpsUrl(link)) continue
            val row = JSONObject()
                .put("title", item.optString("title").take(120))
                .put("summary", item.optString("summary").take(280))
                .put("source", item.optString("source").take(120))
                .put("source_url", link)
            val cover = item.optString("cover_url")
            if (isHttpsUrl(cover)) row.put("cover_url", cover)
            safe.put(row)
        }
        if (safe.length() == 0) return
        preferences.edit().putString("server_url", serverUrl)
            .putString("articles", safe.toString())
            .putLong("updated_at", System.currentTimeMillis()).apply()
    }

    companion object {
        fun isHttpsUrl(raw: String): Boolean {
            if (raw.length > 2048) return false
            return try {
                val uri = java.net.URI(raw)
                uri.scheme.equals("https", ignoreCase = true) && !uri.host.isNullOrBlank() &&
                    uri.userInfo == null && uri.fragment == null && uri.port in listOf(-1, 443)
            } catch (_: Exception) { false }
        }
    }
}
