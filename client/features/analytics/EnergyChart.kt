package com.example.appdemo.features.analytics

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.View
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.Ui
import org.json.JSONArray

class EnergyChart(context: Context) : View(context) {
    var points: JSONArray = JSONArray()
        set(value) { field = value; requestLayout(); invalidate() }
    private val brush = Paint(Paint.ANTI_ALIAS_FLAG)

    private fun hasPlotData(): Boolean = (0 until points.length()).any { index ->
        points.optJSONObject(index)?.let { point ->
            point.optDouble("intake_kcal", 0.0) > 0.0 ||
                point.optDouble("expenditure_kcal", 0.0) > 0.0 ||
                point.optDouble("bmr_kcal", 0.0) > 0.0
        } == true
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec),
            Ui.dp(context, if (hasPlotData()) 218 else 112))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val density = resources.displayMetrics.density
        val left = 14f * density
        val right = width - 14f * density
        val top = 24f * density
        val bottom = height - 34f * density
        val selected = ((points.length() - 8).coerceAtLeast(0) until points.length())
            .mapNotNull { points.optJSONObject(it) }
        if (!hasPlotData()) {
            brush.color = Palette.muted
            brush.textSize = 13f * resources.displayMetrics.scaledDensity
            brush.textAlign = Paint.Align.CENTER
            canvas.drawText("暂无可绘制的能量记录", width / 2f, height / 2f, brush)
            return
        }
        val maximum = selected.maxOf { maxOf(it.optDouble("intake_kcal", 0.0),
            it.optDouble("expenditure_kcal", 0.0), it.optDouble("bmr_kcal", 0.0)) }.coerceAtLeast(1.0)
        fun y(value: Double) = (bottom - (bottom - top) * value / (maximum * 1.1)).toFloat()
        val step = (right - left) / selected.size
        brush.color = 0xffdce6ea.toInt()
        brush.strokeWidth = density
        canvas.drawLine(left, bottom, right, bottom, brush)
        val bmrPath = Path()
        var hasBmr = false
        selected.forEachIndexed { index, point ->
            val center = left + step * (index + 0.5f)
            val bar = minOf(step * 0.21f, 12f * density)
            val intake = point.optDouble("intake_kcal", 0.0)
            val expense = point.optDouble("expenditure_kcal", 0.0)
            brush.color = Palette.green
            canvas.drawRoundRect(center - bar - 1.5f * density, y(intake), center - 1.5f * density,
                bottom, 3f * density, 3f * density, brush)
            if (point.optInt("target_days") > 0) {
                brush.color = Palette.fitness
                canvas.drawRoundRect(center + 1.5f * density, y(expense), center + bar + 1.5f * density,
                    bottom, 3f * density, 3f * density, brush)
                val by = y(point.optDouble("bmr_kcal"))
                if (!hasBmr) bmrPath.moveTo(center, by) else bmrPath.lineTo(center, by)
                hasBmr = true
            } else hasBmr = false
            brush.textSize = 9f * resources.displayMetrics.scaledDensity
            brush.textAlign = Paint.Align.CENTER
            brush.color = Palette.muted
            canvas.drawText(point.optString("period").takeLast(5), center, height - 10f * density, brush)
        }
        brush.color = Palette.ice
        brush.strokeWidth = 2f * density
        brush.style = Paint.Style.STROKE
        canvas.drawPath(bmrPath, brush)
        brush.style = Paint.Style.FILL
        brush.textAlign = Paint.Align.LEFT
        brush.textSize = 11f * resources.displayMetrics.scaledDensity
        brush.color = Palette.green
        canvas.drawText("■ 摄入", left, 13f * density, brush)
        brush.color = Palette.fitness
        canvas.drawText("■ 总消耗", left + 62f * density, 13f * density, brush)
        brush.color = Palette.ice
        canvas.drawText("— BMR", left + 145f * density, 13f * density, brush)
    }
}
