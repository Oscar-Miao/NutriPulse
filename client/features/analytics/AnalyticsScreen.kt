package com.example.appdemo.features.analytics

import android.app.DatePickerDialog
import android.view.View
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.ProgressBar
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.time.UserCalendar
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

object AnalyticsScreen {
    private var selectedDate: LocalDate = UserCalendar.today()
    private var lastDefaultToday: LocalDate = selectedDate
    private var selectedPeriod = 1
    private var energyRequestId = 0
    private var macroRequestId = 0
    private var habitRequestId = 0
    private var diagnosisRequestId = 0

    fun render(host: ScreenHost): View {
        val currentToday = UserCalendar.today()
        if (selectedDate == lastDefaultToday) selectedDate = currentToday
        lastDefaultToday = currentToday
        val context = host.screenContext
        val page = Ui.column(context)
        page.addView(Ui.text(context, "健康数据", 25f, Palette.ink, true))
        page.addView(Ui.text(context, "每一点进步，都值得看见", 13f, Palette.muted))
        page.addView(Ui.gap(context, 16))
        val periodRow = Ui.row(context).apply {
            background = Ui.shape(context, android.graphics.Color.rgb(235, 238, 240), 14)
            setPadding(Ui.dp(context, 4), Ui.dp(context, 4), Ui.dp(context, 4), Ui.dp(context, 4))
        }
        val periodTabs = listOf("日", "周", "月", "年").map { label ->
            Ui.text(context, label, 14f, Palette.muted, true).apply {
                gravity = Gravity.CENTER
                periodRow.addView(this, LinearLayout.LayoutParams(0, Ui.dp(context, 36), 1f))
            }
        }
        page.addView(periodRow)
        page.addView(Ui.gap(context, 12))
        val dateButton = Ui.pill(context, "📅  截止 $selectedDate  ▾", Palette.ink, Palette.white)
        dateButton.elevation = Ui.dp(context, 1).toFloat()
        page.addView(dateButton, LinearLayout.LayoutParams(-1, Ui.dp(context, 42)).apply {
            bottomMargin = Ui.dp(context, 14)
        })
        val result = Ui.column(context)
        page.addView(result)
        val energyCard = Ui.card(context)
        energyCard.addView(Ui.text(context, "摄入与消耗复合趋势", 18f, Palette.ink, true))
        val energyChart = EnergyChart(context)
        energyCard.addView(energyChart)
        page.addView(energyCard)
        val macroCard = Ui.card(context)
        macroCard.addView(Ui.text(context, "三大营养素供能结构", 18f, Palette.ink, true))
        val macroContent = Ui.column(context)
        macroCard.addView(macroContent)
        page.addView(macroCard)
        val habitCard = Ui.card(context)
        habitCard.addView(Ui.text(context, "生活习惯记录", 18f, Palette.ink, true))
        habitCard.addView(Ui.text(context,
            "仅展示已记录数据；漏记不等于零摄入，今天未结束也不计为训练失败。", 12f, Palette.muted))
        val habitContent = Ui.column(context)
        habitCard.addView(habitContent)
        page.addView(habitCard)
        val trendCard = Ui.card(context)
        trendCard.addView(Ui.text(context, "体脂率 × 训练容量趋势", 18f, Palette.ink, true))
        trendCard.addView(Ui.text(context, "双轴：红线体脂率，蓝线每周训练容量；缺失体脂不补造数据。", 12f, Palette.muted))
        val trend = TrendChart(context)
        trendCard.addView(trend)
        page.addView(trendCard)
        val weightCard = Ui.card(context)
        weightCard.addView(Ui.text(context, "体重趋势", 18f, Palette.ink, true))
        weightCard.addView(Ui.text(context,
            "按周显示最近一次实际测量；无测量的周留空，不延续上一周数值。", 12f, Palette.muted))
        val weightTrend = WeightTrendChart(context)
        weightCard.addView(weightTrend)
        page.addView(weightCard)
        val diagnosis = Ui.card(context)
        diagnosis.addView(Ui.text(context, "营养诊断", 18f, Palette.ink, true))
        diagnosis.addView(Ui.text(context, "每次重新生成都会保留旧版；建议可展开查看引用的数据。", 12f, Palette.muted))
        val diagnosisHistory = Ui.column(context)
        diagnosis.addView(diagnosisHistory)
        diagnosis.addView(Ui.gap(context, 10))
        diagnosis.addView(Ui.button(context, "生成 / 重新生成分析", Palette.green) {
            val (start,end) = range(selectedPeriod)
            diagnosisHistory.removeAllViews()
            diagnosisHistory.addView(Ui.text(context, "正在分析所选周期…", 14f, Palette.muted))
            host.api.post("/analytics/diagnostics", JSONObject().put("start", start.toString()).put("end", end.toString())) { data, error ->
                if (selectedDate != end || range(selectedPeriod).first != start) return@post
                if (error != null) {
                    diagnosisHistory.removeAllViews()
                    diagnosisHistory.addView(Ui.text(context, error, 14f, Palette.fitness))
                } else loadDiagnosisHistory(host, diagnosisHistory, start, end)
            }
        })
        page.addView(diagnosis)
        page.addView(Ui.gap(context, 12))
        page.addView(Ui.button(context, "导出当前周期 PDF", Palette.ice) {
            val index = selectedPeriod
            val (start, end) = range(index)
            android.app.AlertDialog.Builder(context)
                .setTitle("导出个人健康报告？")
                .setMessage("将导出 $start 至 $end 的饮食、运动、身体组成和分析数据。PDF 会保存到你选择的位置；分享前请检查其中的个人健康信息。")
                .setNegativeButton("取消", null)
                .setPositiveButton("选择保存位置") { _, _ ->
                    host.exportAnalyticsPdf(listOf("day", "week", "month", "year")[index], end.toString())
                }.show()
        })
        fun reload() {
            periodTabs.forEachIndexed { index, tab ->
                tab.setTextColor(if (index == selectedPeriod) Palette.deepGreen else Palette.muted)
                tab.background = if (index == selectedPeriod) Ui.shape(context, Palette.white, 11) else null
                tab.elevation = if (index == selectedPeriod) Ui.dp(context, 1).toFloat() else 0f
            }
            load(host, result, energyChart, selectedPeriod)
            val (start, end) = range(selectedPeriod)
            loadDiagnosisHistory(host, diagnosisHistory, start, end)
            loadMacros(host, macroContent, start, end)
            loadHabits(host, habitContent, start, end)
            val trendStart = selectedDate.minusWeeks(7).with(java.time.DayOfWeek.MONDAY)
            host.api.get("/analytics/body-composition?start=$trendStart&end=$selectedDate") { data, _ ->
                if (selectedDate == end) {
                    val points = data?.optJSONArray("series") ?: JSONArray()
                    trend.points = points
                    weightTrend.points = points
                }
            }
        }
        periodTabs.forEachIndexed { index, tab ->
            tab.setOnClickListener { selectedPeriod = index; reload() }
        }
        dateButton.setOnClickListener {
            DatePickerDialog(context, { _, year, month, day ->
                selectedDate = LocalDate.of(year, month + 1, day)
                dateButton.text = "📅  截止 $selectedDate  ▾"
                reload()
            }, selectedDate.year, selectedDate.monthValue - 1, selectedDate.dayOfMonth).show()
        }
        reload()
        return page
    }

    private fun loadMacros(host: ScreenHost, macroContent: LinearLayout,
                           start: LocalDate, end: LocalDate) {
        val context = host.screenContext
        val requestId = ++macroRequestId
        host.api.get("/analytics/macros?start=$start&end=$end") { day, error ->
            if (selectedDate != end || requestId != macroRequestId) return@get
            macroContent.removeAllViews()
            if (error != null || day == null) {
                macroContent.addView(Ui.text(context, error ?: "无法读取营养结构", 13f, Palette.fitness))
                return@get
            }
            val actual = day.optJSONObject("actual") ?: JSONObject()
            val target = day.optJSONObject("target") ?: JSONObject()
            val values = listOf(Triple("碳水", "carb_g", Palette.carb),
                Triple("蛋白质", "protein_g", Palette.protein), Triple("脂肪", "fat_g", Palette.fat))
            val actualShares = MacroPercentages.fromEnergy(values.map { (_, key, _) ->
                actual.optDouble(key, 0.0) * if (key == "fat_g") 9 else 4
            })
            val targetShares = MacroPercentages.fromEnergy(values.map { (_, key, _) ->
                target.optDouble(key, 0.0) * if (key == "fat_g") 9 else 4
            })
            if (day.optInt("incomplete_items", 0) > 0) {
                macroContent.addView(Ui.text(context, "有 ${day.optInt("incomplete_items")} 项餐食的宏量营养素不完整或来源未知；已知克数仅供参考。",
                    12f, Palette.fitness))
            }
            if (actualShares == null) {
                macroContent.addView(Ui.text(context, "所选周期尚无可计算的三营养素记录。", 13f, Palette.muted))
                return@get
            }
            if (day.optInt("target_days", 0) == 0) {
                macroContent.addView(Ui.text(context, "所选周期没有生效目标，仅展示已记录摄入。",
                    12f, Palette.muted))
            }
            values.forEachIndexed { index, (name, key, color) ->
                val share = actualShares[index]
                val targetShare = targetShares?.get(index)
                val actualGrams = String.format(java.util.Locale.getDefault(), "%.1f", actual.optDouble(key, 0.0))
                macroContent.addView(Ui.gap(context, 7))
                macroContent.addView(Ui.text(context,
                    "$name ${actualGrams}g · 占比 $share% / 目标 ${if (targetShare != null) "$targetShare%" else "--"}",
                    13f, color, true))
                macroContent.addView(ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal).apply {
                    max = 100
                    progress = share
                    progressTintList = android.content.res.ColorStateList.valueOf(color)
                })
            }
        }
    }

    private fun loadHabits(host: ScreenHost, content: LinearLayout,
                           start: LocalDate, end: LocalDate) {
        val context = host.screenContext
        val requestId = ++habitRequestId
        content.removeAllViews()
        content.addView(Ui.text(context, "正在读取习惯记录…", 13f, Palette.muted))
        host.api.get("/analytics/habits?start=$start&end=$end") { data, error ->
            if (requestId != habitRequestId || range(selectedPeriod) != Pair(start, end)) return@get
            content.removeAllViews()
            if (error != null || data == null) {
                content.addView(Ui.text(context, error ?: "无法读取习惯记录", 13f, Palette.fitness))
                return@get
            }
            val observedDays = data.optInt("observed_days")
            if (observedDays == 0) {
                content.addView(Ui.text(context, "所选日期尚未发生，暂无可分析的记录。", 13f, Palette.muted))
                return@get
            }
            val water = data.optJSONObject("water") ?: JSONObject()
            val fiber = data.optJSONObject("fiber") ?: JSONObject()
            val meals = data.optJSONObject("meals") ?: JSONObject()
            val training = data.optJSONObject("training") ?: JSONObject()
            content.addView(Ui.gap(context, 10))
            content.addView(Ui.text(context,
                "饮水 · 已记 ${water.optInt("recorded_ml")} ml，覆盖 ${water.optInt("recorded_days")}/$observedDays 天",
                13f, Palette.ice, true))
            val evaluated = water.optInt("evaluated_goal_days")
            content.addView(Ui.text(context, if (evaluated > 0)
                "已结束且记水的目标日中，${water.optInt("met_goal_days")}/$evaluated 天达到建议量。未记录日不判为不足。"
                else "尚无可比较的已结束饮水目标日。", 12f, Palette.muted))
            content.addView(Ui.gap(context, 9))
            val consumed = fiber.optInt("consumed_items")
            val fiberLine = when {
                consumed == 0 -> "膳食纤维 · 尚无已吃餐食记录"
                fiber.isNull("known_g") -> "膳食纤维 · 已吃 $consumed 项，均未填写纤维数据"
                else -> "膳食纤维 · 已知 ${fiber.optDouble("known_g")} g，" +
                    "${fiber.optInt("known_items")}/$consumed 项有纤维数据"
            }
            content.addView(Ui.text(context, fiberLine, 13f, Palette.green, true))
            if (fiber.optInt("unknown_items") > 0)
                content.addView(Ui.text(context, "有 ${fiber.optInt("unknown_items")} 项纤维未知，已知克数不能当作完整摄入。",
                    12f, Palette.fitness))
            content.addView(Ui.gap(context, 9))
            val mealDays = meals.optInt("logged_closed_days")
            val threeMealDays = meals.optInt("three_main_meals_logged_days")
            content.addView(Ui.text(context,
                "三餐记账 · 已结束日中 $threeMealDays/$mealDays 个有记录日覆盖早、午、晚餐",
                13f, Palette.ink, true))
            content.addView(Ui.text(context, if (meals.isNull("three_meal_logging_pct"))
                "少于 3 个有记录日，暂不生成覆盖率；漏记不代表没有进食。"
                else "记账覆盖率 ${meals.optDouble("three_meal_logging_pct")}%；仅表示记录完整度，不评价真实饮食规律。",
                12f, Palette.muted))
            content.addView(Ui.gap(context, 9))
            val scheduled = training.optInt("scheduled_closed_sessions")
            val completed = training.optInt("completed_sessions")
            content.addView(Ui.text(context,
                "计划跟练 · 完整完成 $completed/$scheduled 次，部分完成 ${training.optInt("partial_sessions")} 次",
                13f, Palette.fitness, true))
            content.addView(Ui.text(context, if (training.isNull("completion_pct"))
                "少于 3 个已结束的有效计划日，暂不生成完成率。"
                else "已结束计划日的完整完成率 ${training.optDouble("completion_pct")}%（部分完成单列）。",
                12f, Palette.muted))
            if (training.optInt("legacy_stop_unknown_sessions") > 0)
                content.addView(Ui.text(context,
                    "${training.optInt("legacy_stop_unknown_sessions")} 个旧计划日缺少停训日期，未计入完成率。",
                    12f, Palette.muted))
            if (data.optBoolean("today_is_partial"))
                content.addView(Ui.text(context, "今天仍在进行中：饮水和纤维展示当前记录；三餐及跟练比例仅使用已结束日。",
                    12f, Palette.muted))
        }
    }

    private fun range(index: Int): Pair<LocalDate,LocalDate> = PeriodRange.forIndex(index, selectedDate)

    private fun loadDiagnosisHistory(host: ScreenHost, parent: LinearLayout,
                                     start: LocalDate, end: LocalDate) {
        val context = host.screenContext
        val requestId = ++diagnosisRequestId
        parent.removeAllViews()
        parent.addView(Ui.text(context, "正在读取诊断历史…", 13f, Palette.muted))
        host.api.get("/analytics/diagnostics?start=$start&end=$end") { data, error ->
            if (requestId != diagnosisRequestId || range(selectedPeriod) != Pair(start, end)) return@get
            parent.removeAllViews()
            if (error != null) {
                parent.addView(Ui.text(context, error, 13f, Palette.fitness))
                return@get
            }
            val items = data?.optJSONArray("items") ?: JSONArray()
            if (items.length() == 0) {
                parent.addView(Ui.text(context, "此周期尚未生成诊断。", 13f, Palette.muted))
                return@get
            }
            for (index in 0 until items.length()) {
                val item = items.optJSONObject(index) ?: continue
                parent.addView(Ui.gap(context, 9))
                val version = item.optInt("version")
                val source = if (item.optString("source") == "agent-v1") "AI 辅助" else "本地规则"
                val confidence = if (item.isNull("confidence")) "可信度未评估"
                    else "网关给出的置信度 ${(item.optDouble("confidence") * 100).toInt()}%"
                parent.addView(Ui.text(context, "第 $version 版 · $source · ${formatReportTime(item.optString("created_at"))}",
                    14f, Palette.ink, true))
                parent.addView(Ui.text(context, "${item.optString("model_name")} · $confidence · 输入指纹 ${item.optString("input_hash").take(10)}…",
                    11f, Palette.muted))
                val details = Ui.column(context).apply { visibility = if (index == 0) View.VISIBLE else View.GONE }
                val observations = item.optJSONArray("observations") ?: JSONArray()
                for (i in 0 until observations.length())
                    details.addView(Ui.text(context, "• ${observations.optString(i)}", 13f, Palette.ink))
                details.addView(Ui.gap(context, 5))
                val advice = item.optJSONArray("advice_details") ?: JSONArray()
                for (i in 0 until advice.length()) {
                    val entry = advice.optJSONObject(i) ?: continue
                    details.addView(Ui.text(context, "建议：${entry.optString("text")}", 13f, Palette.green, true))
                    val refs = entry.optJSONArray("evidence_refs") ?: JSONArray()
                    if (refs.length() > 0) {
                        val evidence = (0 until refs.length()).mapNotNull { refs.optJSONObject(it) }.joinToString("；") { ref ->
                            "${ref.optString("period")} ${metricName(ref.optString("metric"))} ${ref.opt("value")}"
                        }
                        details.addView(Ui.text(context, "依据：$evidence", 11f, Palette.muted))
                    }
                    details.addView(Ui.gap(context, 6))
                }
                parent.addView(details)
                if (index > 0) parent.addView(Ui.button(context, "展开 / 收起第 $version 版", Palette.ice) {
                    details.visibility = if (details.visibility == View.VISIBLE) View.GONE else View.VISIBLE
                })
            }
        }
    }

    private fun metricName(key: String): String = when (key) {
        "target_days" -> "目标覆盖天数"
        "completed_target_days" -> "已结束且有目标的天数"
        "completed_mean_net_kcal" -> "已结束日平均净热量 kcal"
        "net_kcal" -> "净热量 kcal"
        "intake_kcal" -> "摄入 kcal"
        "expenditure_kcal" -> "总消耗 kcal"
        "bmr_kcal" -> "基础代谢 kcal"
        "training_volume" -> "训练容量 kg"
        "water_ml" -> "饮水 ml"
        "water_target_ml" -> "饮水目标 ml"
        "protein_g" -> "蛋白质 g"
        "protein_target_g" -> "蛋白质目标 g"
        "logged_days" -> "有记录天数"
        else -> key
    }

    private fun formatReportTime(raw: String): String = try {
        OffsetDateTime.parse(raw).atZoneSameInstant(UserCalendar.zone)
            .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")) + " 北京时间"
    } catch (_: Exception) { raw.take(16) + "（时区未知）" }

    private fun load(host: ScreenHost, parent: LinearLayout, chart: EnergyChart, index: Int) {
        val context = host.screenContext
        val requestId = ++energyRequestId
        parent.removeAllViews()
        parent.addView(Ui.text(context, "正在读取周期概览…", 14f, Palette.muted))
        val (start,end) = range(index)
        val granularity = listOf("day", "day", "week", "month")[index]
        host.api.get("/analytics/energy?start=$start&end=$end&granularity=$granularity") { data, error ->
            if (requestId != energyRequestId) return@get
            parent.removeAllViews()
            if (error != null) {
                chart.points = JSONArray()
                val notice = Ui.card(context)
                notice.addView(Ui.text(context, "暂时无法读取统计", 14f, Palette.ink, true))
                notice.addView(Ui.text(context, error, 12f, Palette.muted))
                parent.addView(notice)
                return@get
            }
            val series = data?.optJSONArray("series") ?: JSONArray()
            chart.points = series
            if (series.length() == 0) {
                parent.addView(Ui.text(context, "所选周期尚无可统计的记录", 13f, Palette.muted))
                return@get
            }
            val points = (0 until series.length()).mapNotNull(series::optJSONObject)
            val dayCount = points.sumOf { it.optInt("days", 1).coerceAtLeast(1) }
            val intakeTotal = points.sumOf { it.optDouble("intake_kcal", 0.0) }
            val netTotal = points.sumOf { it.optDouble("net_kcal", 0.0) }
            val volumeTotal = points.sumOf { it.optDouble("training_volume", 0.0) }
            val targetDays = points.sumOf { it.optInt("target_days", 0) }
            val loggedDays = points.sumOf { it.optInt("logged_days", 0) }
            val stats = Ui.row(context)
            listOf(
                Triple("日均摄入", if (loggedDays > 0) "${(intakeTotal / dayCount).toInt()} kcal" else "--", Palette.green),
                Triple("热量平衡", if (targetDays > 0) "${if (netTotal >= 0) "+" else ""}${netTotal.toInt()}" else "--", Palette.fitness),
                Triple("训练容量", "${volumeTotal.toInt()} kg", Palette.protein)
            ).forEach { (label, value, color) ->
                val tile = Ui.card(context).apply {
                    setPadding(Ui.dp(context, 10), Ui.dp(context, 12), Ui.dp(context, 8), Ui.dp(context, 12))
                    addView(Ui.text(context, label, 11f, Palette.muted))
                    addView(Ui.text(context, value, 17f, color, true))
                }
                stats.addView(tile, LinearLayout.LayoutParams(0, -2, 1f).apply {
                    marginEnd = Ui.dp(context, 6)
                })
            }
            parent.addView(stats)
            val detailLines = mutableListOf<String>()
            for (i in 0 until series.length()) {
                val point = series.optJSONObject(i) ?: continue
                val intake = point.optDouble("intake_kcal", 0.0)
                val expenditure = point.optDouble("expenditure_kcal", 0.0)
                val net = point.optDouble("net_kcal", 0.0)
                val hasTarget = point.optInt("target_days", 0) > 0
                detailLines += "${point.optString("period")}  摄入 ${intake.toInt()} kcal · 消耗 ${if (hasTarget) "${expenditure.toInt()} kcal" else "--"} · " +
                    "净差 ${if (hasTarget) "${if (net >= 0) "+" else ""}${net.toInt()} kcal" else "--"}"
            }
            parent.addView(Ui.pill(context, "查看周期明细  ›", Palette.deepGreen, Palette.lightGreen) {
                android.app.AlertDialog.Builder(context)
                    .setTitle("$start 至 $end 能量明细")
                    .setMessage(detailLines.joinToString("\n\n"))
                    .setPositiveButton("完成", null)
                    .show()
            }, LinearLayout.LayoutParams(-1, Ui.dp(context, 38)).apply {
                bottomMargin = Ui.dp(context, 10)
            })
        }
    }
}
