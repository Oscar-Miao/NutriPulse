package com.example.appdemo.features.diet

import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.database.ArticleCache
import org.json.JSONArray
import java.net.URL
import java.net.HttpURLConnection
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object ArticleCarousel {
    fun render(host: ScreenHost, parent: LinearLayout, articles: JSONArray, cachedAt: Long? = null) {
        val context = host.screenContext
        parent.removeAllViews()
        if (articles.length() == 0) return
        if (cachedAt != null) {
            val time = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.CHINA).format(Date(cachedAt))
            parent.addView(Ui.text(context, "最近缓存 · 更新于 $time（断网时仍可阅读）", 12f, Palette.muted))
        }
        val strip = Ui.row(context)
        for (index in 0 until articles.length()) {
            val article = articles.optJSONObject(index) ?: continue
            val card = Ui.card(context)
            card.layoutParams = LinearLayout.LayoutParams(Ui.dp(context, 278), ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { marginEnd = Ui.dp(context, 12) }
            val image = ImageView(context).apply {
                scaleType = ImageView.ScaleType.CENTER_CROP
                background = GradientDrawable(GradientDrawable.Orientation.TL_BR,
                    intArrayOf(0xffd8fbe8.toInt(), 0xffcfeefa.toInt())).apply {
                    cornerRadius = Ui.dp(context, 12).toFloat()
                }
                contentDescription = "文章配图"
            }
            card.addView(image, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(context, 140)))
            card.addView(Ui.gap(context, 9))
            card.addView(Ui.text(context, article.optString("title"), 16f, Palette.ink, true).apply { maxLines = 2 })
            card.addView(Ui.text(context, article.optString("source"), 12f, Palette.green, true))
            card.setOnClickListener {
                val url = article.optString("source_url")
                if (ArticleCache.isHttpsUrl(url)) {
                    try { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                    catch (_: Exception) { host.message("暂时无法打开文章") }
                }
            }
            strip.addView(card)
            val cover = article.optString("cover_url")
            if (ArticleCache.isHttpsUrl(cover)) loadCover(cover, image)
        }
        parent.addView(HorizontalScrollView(context).apply {
            isHorizontalScrollBarEnabled = false
            clipToPadding = false
            addView(strip)
        })
    }

    private fun loadCover(url: String, image: ImageView) {
        Thread {
            try {
                val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 4_000
                    readTimeout = 5_000
                    instanceFollowRedirects = false
                }
                if (connection.responseCode != 200) { connection.disconnect(); return@Thread }
                val bytes = connection.inputStream.use { stream ->
                    val output = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(8192)
                    while (true) {
                        val count = stream.read(buffer)
                        if (count < 0) break
                        output.write(buffer, 0, count)
                        if (output.size() > 1_500_000) return@Thread
                    }
                    output.toByteArray()
                }
                connection.disconnect()
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return@Thread
                val sample = generateSequence(1) { it * 2 }
                    .first { bounds.outWidth / it <= 1200 && bounds.outHeight / it <= 1200 }
                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size,
                    BitmapFactory.Options().apply { inSampleSize = sample }) ?: return@Thread
                Handler(Looper.getMainLooper()).post { image.setImageBitmap(bitmap) }
            } catch (_: Exception) { /* Keep the calm gradient placeholder. */ }
        }.start()
    }
}
