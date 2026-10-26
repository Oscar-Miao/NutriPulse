package com.example.appdemo.core.design_system

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View

/** Stitch-style nutrition/activity progress ring. Values are display-only. */
class RingGauge(context: Context, private val accent: Int = Palette.green) : View(context) {
    var fraction: Float = 0f
        set(value) { field = value.coerceIn(0f, 1f); invalidate() }
    var value: String = "--"
        set(text) { field = text; invalidate() }
    var caption: String = "剩余热量"
        set(text) { field = text; invalidate() }
    var unit: String = "kcal"
        set(text) { field = text; invalidate() }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), Ui.dp(context, 188))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val density = resources.displayMetrics.density
        val cx = width / 2f
        val cy = height / 2f
        val radius = minOf(width * 0.30f, height * 0.40f)
        val stroke = 12f * density
        val bounds = RectF(cx - radius, cy - radius, cx + radius, cy + radius)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = stroke
        paint.strokeCap = Paint.Cap.ROUND
        paint.color = 0xffe6eff5.toInt()
        canvas.drawArc(bounds, 0f, 360f, false, paint)
        paint.color = accent
        canvas.drawArc(bounds, -90f, 360f * fraction, false, paint)
        paint.style = Paint.Style.FILL
        paint.textAlign = Paint.Align.CENTER
        paint.color = Palette.muted
        paint.textSize = 13f * resources.displayMetrics.scaledDensity
        canvas.drawText(caption, cx, cy - 20f * density, paint)
        paint.color = Palette.ink
        paint.isFakeBoldText = true
        paint.textSize = 35f * resources.displayMetrics.scaledDensity
        canvas.drawText(value, cx, cy + 19f * density, paint)
        paint.isFakeBoldText = false
        paint.color = accent
        paint.textSize = 13f * resources.displayMetrics.scaledDensity
        canvas.drawText(unit, cx, cy + 43f * density, paint)
    }
}
