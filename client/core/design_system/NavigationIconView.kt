package com.example.appdemo.core.design_system

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.View

/** Stroke icons share one 24 dp coordinate system, so nav items align on every font/device. */
class NavigationIconView(context: Context, private val kind: Kind, private val tint: Int) : View(context) {
    enum class Kind { HOME, FITNESS, EAT, DATA, PROFILE, CAMERA }

    private val pen = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1.9f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        color = tint
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val size = Ui.dp(context, 25)
        setMeasuredDimension(resolveSize(size, widthMeasureSpec), resolveSize(size, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val size = minOf(width, height).toFloat()
        val scale = size / 24f
        canvas.save()
        canvas.translate((width - size) / 2f, (height - size) / 2f)
        canvas.scale(scale, scale)
        when (kind) {
            Kind.HOME -> {
                canvas.drawPath(Path().apply {
                    moveTo(3f, 10f); lineTo(12f, 3f); lineTo(21f, 10f)
                    moveTo(5f, 9f); lineTo(5f, 21f); lineTo(19f, 21f); lineTo(19f, 9f)
                    moveTo(10f, 21f); lineTo(10f, 14f); lineTo(14f, 14f); lineTo(14f, 21f)
                }, pen)
            }
            Kind.FITNESS -> {
                canvas.drawLine(7f, 12f, 17f, 12f, pen)
                canvas.drawLine(5f, 7f, 5f, 17f, pen)
                canvas.drawLine(8f, 5f, 8f, 19f, pen)
                canvas.drawLine(16f, 5f, 16f, 19f, pen)
                canvas.drawLine(19f, 7f, 19f, 17f, pen)
            }
            Kind.EAT -> {
                canvas.drawLine(5f, 3f, 5f, 9f, pen)
                canvas.drawLine(8f, 3f, 8f, 9f, pen)
                canvas.drawLine(11f, 3f, 11f, 9f, pen)
                canvas.drawPath(Path().apply {
                    moveTo(5f, 9f); quadTo(8f, 12f, 11f, 9f)
                    moveTo(8f, 11f); lineTo(8f, 21f)
                }, pen)
                canvas.drawOval(15f, 3f, 21f, 11f, pen)
                canvas.drawLine(18f, 11f, 18f, 21f, pen)
            }
            Kind.DATA -> {
                canvas.drawRoundRect(3f, 3f, 21f, 21f, 2f, 2f, pen)
                canvas.drawLine(7f, 17f, 7f, 13f, pen)
                canvas.drawLine(12f, 17f, 12f, 8f, pen)
                canvas.drawLine(17f, 17f, 17f, 11f, pen)
            }
            Kind.PROFILE -> {
                canvas.drawCircle(12f, 8f, 3.5f, pen)
                canvas.drawPath(Path().apply {
                    moveTo(4f, 21f); cubicTo(4f, 16f, 8f, 14.5f, 12f, 14.5f)
                    cubicTo(16f, 14.5f, 20f, 16f, 20f, 21f)
                }, pen)
            }
            Kind.CAMERA -> {
                canvas.drawRoundRect(3f, 6f, 21f, 20f, 2f, 2f, pen)
                canvas.drawPath(Path().apply {
                    moveTo(7f, 6f); lineTo(9f, 3.5f); lineTo(15f, 3.5f); lineTo(17f, 6f)
                }, pen)
                canvas.drawCircle(12f, 13f, 3.2f, pen)
            }
        }
        canvas.restore()
    }
}
