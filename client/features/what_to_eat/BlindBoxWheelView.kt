package com.example.appdemo.features.what_to_eat

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.Ui
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/** The wheel is presentation only; the server chooses from its filtered pool. */
class BlindBoxWheelView(context: Context, private val choices: List<String>) : View(context) {
    private val colors = intArrayOf(Palette.green, Palette.protein, Palette.fat,
        Palette.ice, Palette.fitness, Palette.carb)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        textSize = Ui.dp(context, 12).toFloat()
        isFakeBoldText = true
    }
    var rotationDegrees: Float = 0f
        set(value) { field = value; invalidate() }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val offered = MeasureSpec.getSize(widthMeasureSpec)
        val size = min(if (offered > 0) offered else Ui.dp(context, 300), Ui.dp(context, 310))
        setMeasuredDimension(size, size + Ui.dp(context, 20))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (choices.isEmpty()) return
        val radius = min(width, height - Ui.dp(context, 20)) * 0.43f
        val centerX = width / 2f
        val centerY = height / 2f + Ui.dp(context, 8)
        val circle = RectF(centerX - radius, centerY - radius,
            centerX + radius, centerY + radius)
        val sweep = 360f / choices.size
        canvas.save()
        canvas.rotate(rotationDegrees, centerX, centerY)
        choices.forEachIndexed { index, name ->
            fill.color = colors[index % colors.size]
            canvas.drawArc(circle, -90f + index * sweep, sweep, true, fill)
            val angle = Math.toRadians((-90f + (index + 0.5f) * sweep).toDouble())
            label.color = if (colors[index % colors.size] == Palette.fat) Palette.ink else Palette.white
            val shortName = if (name.length > 5) name.take(5) + "…" else name
            canvas.drawText(shortName,
                centerX + cos(angle).toFloat() * radius * 0.62f,
                centerY + sin(angle).toFloat() * radius * 0.62f + label.textSize * 0.3f,
                label)
        }
        fill.color = Palette.white
        canvas.drawCircle(centerX, centerY, Ui.dp(context, 17).toFloat(), fill)
        fill.color = Palette.green
        canvas.drawCircle(centerX, centerY, Ui.dp(context, 10).toFloat(), fill)
        canvas.restore()
        val pointer = Path().apply {
            moveTo(centerX, centerY - radius + Ui.dp(context, 7))
            lineTo(centerX - Ui.dp(context, 11), centerY - radius - Ui.dp(context, 13))
            lineTo(centerX + Ui.dp(context, 11), centerY - radius - Ui.dp(context, 13))
            close()
        }
        fill.color = Palette.ink
        canvas.drawPath(pointer, fill)
    }
}
