package com.example.appdemo.core.design_system

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import android.widget.ArrayAdapter

object Palette {
    val green = Color.rgb(46, 204, 113)
    val carb = Color.rgb(243, 156, 18)
    val fitness = Color.rgb(255, 82, 82)
    val protein = Color.rgb(52, 152, 219)
    val fat = Color.rgb(241, 196, 15)
    val ice = Color.rgb(0, 190, 197)
    val background = Color.rgb(248, 249, 250)
    val deepGreen = Color.rgb(0, 108, 73)
    val lightGreen = Color.rgb(223, 249, 237)
    val softBlue = Color.rgb(236, 243, 254)
    val ink = Color.rgb(11, 28, 48)
    val muted = Color.rgb(94, 106, 118)
    val disabled = Color.rgb(220, 226, 230)
    val white = Color.WHITE
}

object Ui {
    fun dp(context: Context, value: Int): Int = (value * context.resources.displayMetrics.density).toInt()

    fun shape(context: Context, color: Int, radius: Int = 16): GradientDrawable =
        GradientDrawable().apply { setColor(color); cornerRadius = dp(context, radius).toFloat() }

    fun gradient(context: Context, start: Int, end: Int, radius: Int = 16): GradientDrawable =
        GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(start, end)).apply {
            cornerRadius = dp(context, radius).toFloat()
        }

    fun column(context: Context): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
    }

    fun row(context: Context): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
    }

    fun text(context: Context, value: String, size: Float = 14f, color: Int = Palette.ink,
             bold: Boolean = false): TextView = TextView(context).apply {
        text = value
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        includeFontPadding = true
    }

    fun title(context: Context, value: String): TextView = text(context, value, 25f, Palette.ink, true).apply {
        setPadding(0, dp(context, 8), 0, dp(context, 14))
    }

    fun subtitle(context: Context, value: String): TextView = text(context, value, 18f, Palette.ink, true).apply {
        setPadding(0, dp(context, 12), 0, dp(context, 9))
    }

    fun card(context: Context): LinearLayout = column(context).apply {
        background = shape(context, Palette.white, 16)
        elevation = dp(context, 2).toFloat()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val softShadow = Color.argb(10, 0, 0, 0) // ~= rgba(0, 0, 0, 0.04)
            outlineAmbientShadowColor = softShadow
            outlineSpotShadowColor = softShadow
        }
        setPadding(dp(context, 16), dp(context, 16), dp(context, 16), dp(context, 16))
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(context, 12) }
    }

    fun button(context: Context, label: String, color: Int = Palette.green,
               action: () -> Unit): Button = Button(context).apply {
        text = label
        textSize = 15f
        isAllCaps = false
        setTextColor(Palette.white)
        background = shape(context, color, 14)
        minHeight = dp(context, 48)
        setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
        setOnClickListener { action() }
    }

    fun field(context: Context, hintText: String, value: String = "", numeric: Boolean = false): EditText =
        EditText(context).apply {
            hint = hintText
            setText(value)
            textSize = 15f
            setTextColor(Palette.ink)
            setHintTextColor(Palette.muted)
            background = shape(context, Palette.background, 10)
            setPadding(dp(context, 12), dp(context, 10), dp(context, 12), dp(context, 10))
            if (numeric) inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                dp(context, 48)).apply { bottomMargin = dp(context, 8) }
        }

    fun picker(context: Context, values: List<String>): Spinner = Spinner(context).apply {
        adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, values)
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
            dp(context, 48)).apply { bottomMargin = dp(context, 8) }
    }

    fun gap(context: Context, height: Int = 8): View = View(context).apply {
        layoutParams = LinearLayout.LayoutParams(1, dp(context, height))
    }

    fun badge(context: Context, value: String, color: Int): TextView = text(context, value, 12f, color, true).apply {
        setPadding(dp(context, 9), dp(context, 4), dp(context, 9), dp(context, 4))
        background = shape(context, Color.argb(28, Color.red(color), Color.green(color), Color.blue(color)), 12)
    }

    fun pill(context: Context, value: String, foreground: Int, surface: Int,
             action: (() -> Unit)? = null): TextView = text(context, value, 12f, foreground, true).apply {
        gravity = Gravity.CENTER
        includeFontPadding = false
        setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
        background = shape(context, surface, 999)
        if (action != null) setOnClickListener { action() }
    }
}
