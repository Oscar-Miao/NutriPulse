package com.example.appdemo.core.database

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Small local draft cache for forms while the computer is unavailable. */
class LocalDrafts(context: Context) {
    private val prefs = context.getSharedPreferences("nutripulse_drafts", Context.MODE_PRIVATE)

    fun save(key: String, data: JSONObject) {
        prefs.edit().putString(key, data.toString()).apply()
    }

    fun load(key: String): JSONObject? = prefs.getString(key, null)?.let { JSONObject(it) }

    fun clear(key: String) { prefs.edit().remove(key).apply() }
}
