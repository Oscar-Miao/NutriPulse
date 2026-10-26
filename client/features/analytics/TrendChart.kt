package com.example.appdemo.features.analytics

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.view.View
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.Ui
import org.json.JSONArray

class TrendChart(context: Context) : View(context) {
    var points: JSONArray = JSONArray()
        set(value) { field = value; invalidate() }
    private val brush = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), Ui.dp(context, 220))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val density = resources.displayMetrics.density
        val left = 36f * density
        val right = width - 42f * density
        val top = 23f * density
        val bottom = height - 35f * density
        val selected = ((points.length() - 8).coerceAtLeast(0) until points.length())
            .mapNotNull { points.optJSONObject(it) }
        if (selected.isEmpty()) return
        val fats = selected.mapNotNull { if (it.isNull("body_fat_pct")) null else it.optDouble("body_fat_pct") }
        val volumes = selected.map { it.optDouble("training_volume_kg", 0.0) }
        val fatMin = (fats.minOrNull() ?: 0.0) - 1
        val fatMax = (fats.maxOrNull() ?: 1.0) + 1
        val volumeMax = (volumes.maxOrNull() ?: 1.0).coerceAtLeast(1.0) * 1.1
        fun x(index: Int) = left + (right - left) * index / (selected.size - 1).coerceAtLeast(1)
        fun fatY(value: Double) = (bottom - (bottom - top) * (value - fatMin) / (fatMax - fatMin)).toFloat()
        fun volumeY(value: Double) = (bottom - (bottom - top) * value / volumeMax).toFloat()
        brush.color = 0xffdce6ea.toInt()
        brush.strokeWidth = 1f * density
        canvas.drawLine(left, bottom, right, bottom, brush)
        brush.textSize = 10f * resources.displayMetrics.scaledDensity
        brush.textAlign = Paint.Align.LEFT
        brush.color = Palette.fitness
        canvas.drawText("体脂 %", left, 13f * density, brush)
        brush.color = Palette.protein
        brush.textAlign = Paint.Align.RIGHT
        canvas.drawText("容量 kg", right, 13f * density, brush)
        for (index in selected.indices) {
            val xx = x(index)
            if (index > 0) {
                brush.color = Palette.protein
                brush.strokeWidth = 2.5f * density
                canvas.drawLine(x(index - 1), volumeY(volumes[index - 1]), xx, volumeY(volumes[index]), brush)
            }
            brush.color = Palette.protein
            canvas.drawCircle(xx, volumeY(volumes[index]), 3.3f * density, brush)
            val fat = selected[index].optDouble("body_fat_pct")
            if (!selected[index].isNull("body_fat_pct")) {
                brush.color = Palette.fitness
                if (index > 0 && !selected[index - 1].isNull("body_fat_pct")) {
                    canvas.drawLine(x(index - 1), fatY(selected[index - 1].optDouble("body_fat_pct")),
                        xx, fatY(fat), brush)
                }
                canvas.drawCircle(xx, fatY(fat), 3.3f * density, brush)
            }
            brush.color = Palette.muted
            brush.textAlign = Paint.Align.CENTER
            brush.textSize = 9f * resources.displayMetrics.scaledDensity
            canvas.drawText(selected[index].optString("week").takeLast(3), xx, height - 12f * density, brush)
        }
    }
}

/** Separate kg axis: body weight must not share the body-fat/volume dual axis. */
class WeightTrendChart(context: Context) : View(context) {
    var points: JSONArray = JSONArray()
        set(value) { field = value; invalidate() }
    private val brush = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), Ui.dp(context, 170))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val density = resources.displayMetrics.density
        val selected = ((points.length() - 8).coerceAtLeast(0) until points.length())
            .mapNotNull { points.optJSONObject(it) }
        val weights = selected.map { if (it.isNull("weight_kg")) null else it.optDouble("weight_kg") }
        val observed = weights.filterNotNull()
        brush.textSize = 11f * resources.displayMetrics.scaledDensity
        brush.color = Palette.muted
        if (observed.isEmpty()) {
            brush.textAlign = Paint.Align.CENTER
            canvas.drawText("所选范围附近暂无体重测量", width / 2f, height / 2f, brush)
            return
        }
        val left = 49f * density
        val right = width - 18f * density
        val top = 20f * density
        val bottom = height - 31f * density
        val low = (observed.minOrNull() ?: 0.0) - 0.8
        val high = (observed.maxOrNull() ?: 0.0) + 0.8
        fun x(index: Int) = left + (right - left) * index / (selected.size - 1).coerceAtLeast(1)
        fun y(value: Double) = (bottom - (bottom - top) * (value - low) / (high - low)).toFloat()
        brush.color = 0xffdce6ea.toInt()
        brush.strokeWidth = density
        canvas.drawLine(left, bottom, right, bottom, brush)
        canvas.drawLine(left, top, right, top, brush)
        brush.color = Palette.muted
        brush.textAlign = Paint.Align.RIGHT
        brush.textSize = 9f * resources.displayMetrics.scaledDensity
        canvas.drawText(String.format(java.util.Locale.getDefault(), "%.1f kg", high), left - 5f * density,
            top + 3f * density, brush)
        canvas.drawText(String.format(java.util.Locale.getDefault(), "%.1f", low), left - 5f * density,
            bottom + 3f * density, brush)
        for (index in selected.indices) {
            val value = weights[index]
            val xx = x(index)
            if (value != null) {
                brush.color = Palette.green
                brush.strokeWidth = 2.5f * density
                if (index > 0 && weights[index - 1] != null)
                    canvas.drawLine(x(index - 1), y(weights[index - 1]!!), xx, y(value), brush)
                canvas.drawCircle(xx, y(value), 3.5f * density, brush)
            }
            brush.color = Palette.muted
            brush.textAlign = Paint.Align.CENTER
            brush.textSize = 9f * resources.displayMetrics.scaledDensity
            canvas.drawText(selected[index].optString("week").takeLast(3), xx,
                height - 10f * density, brush)
        }
    }
}
