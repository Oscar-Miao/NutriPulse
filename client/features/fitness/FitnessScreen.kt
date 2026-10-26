package com.example.appdemo.features.fitness

import android.app.AlertDialog
import android.content.Context
import android.view.View
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.time.UserCalendar
import org.json.JSONArray
import org.json.JSONObject

object FitnessScreen {
    private val types = listOf("walking", "running", "cycling", "swimming", "yoga", "strength", "custom")
    private val names = listOf("快走", "跑步", "骑行", "游泳", "瑜伽", "力量训练", "自定义")
    private data class SetInputs(val weight: EditText, val measure: EditText, val timed: Boolean,
                                 val rpe: EditText, val rir: EditText, val done: CheckBox,
                                 val exerciseName: String, val setNo: Int)

    fun render(host: ScreenHost): View {
        val context = host.screenContext
        val page = Ui.column(context)
        val heading = Ui.row(context)
        heading.addView(Ui.text(context, "今日运动活力", 21f, Palette.ink, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        val today = UserCalendar.today()
        heading.addView(Ui.pill(context, "${today.monthValue}月${today.dayOfMonth}日",
            Palette.deepGreen, Palette.white))
        page.addView(heading)
        page.addView(Ui.gap(context, 14))
        val hero = Ui.card(context)
        hero.addView(Ui.text(context, "今日动态消耗", 14f, Palette.muted))
        val calorieRow = Ui.row(context)
        val calories = Ui.text(context, "-- kcal", 34f, Palette.fitness, true)
        calorieRow.addView(calories, LinearLayout.LayoutParams(0, Ui.dp(context, 52), 1f))
        val goalBadge = Ui.pill(context, "目标 -- kcal", Palette.fitness,
            android.graphics.Color.rgb(255, 238, 236))
        calorieRow.addView(goalBadge)
        hero.addView(calorieRow)
        val progressTrack = View(context).apply {
            background = Ui.shape(context, android.graphics.Color.rgb(255, 238, 236), 999)
        }
        val progressFill = View(context).apply { background = Ui.shape(context, Palette.fitness, 999) }
        val progressFrame = android.widget.FrameLayout(context).apply {
            addView(progressTrack, android.widget.FrameLayout.LayoutParams(-1, Ui.dp(context, 8)))
            addView(progressFill, android.widget.FrameLayout.LayoutParams(0, Ui.dp(context, 8)))
        }
        hero.addView(progressFrame, LinearLayout.LayoutParams(-1, Ui.dp(context, 8)))
        hero.addView(Ui.gap(context, 16))
        val minuteStat = Ui.text(context, "--\n运动分钟", 14f, Palette.ink, true)
        val volumeStat = Ui.text(context, "--\n训练容量 kg", 14f, Palette.ink, true)
        val heartStat = Ui.text(context, "--\n最近心率 bpm", 14f, Palette.ink, true)
        val stepsStat = Ui.text(context, "--\n今日步数", 14f, Palette.ink, true)
        listOf(listOf(minuteStat, heartStat), listOf(stepsStat, volumeStat)).forEach { pair ->
            val row = Ui.row(context)
            pair.forEach { stat ->
                stat.gravity = Gravity.CENTER_VERTICAL
                stat.background = Ui.shape(context, Palette.background, 12)
                stat.setPadding(Ui.dp(context, 14), Ui.dp(context, 9), Ui.dp(context, 8), Ui.dp(context, 9))
                row.addView(stat, LinearLayout.LayoutParams(0, -2, 1f).apply {
                    marginEnd = Ui.dp(context, 6)
                })
            }
            hero.addView(row)
            hero.addView(Ui.gap(context, 7))
        }
        val summary = Ui.text(context, "等待今日活动数据…", 12f, Palette.muted)
        hero.addView(Ui.gap(context, 10))
        hero.addView(summary)
        val activitySource = Ui.text(context, "等待活动数据…", 12f, Palette.muted)
        activitySource.visibility = View.GONE
        hero.addView(activitySource)
        val sourceToggle = Ui.pill(context, "查看设备与估算来源  ▾", Palette.deepGreen, Palette.lightGreen)
        sourceToggle.setOnClickListener {
            activitySource.visibility = if (activitySource.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            sourceToggle.text = if (activitySource.visibility == View.VISIBLE) "收起设备与估算来源  ▴"
                else "查看设备与估算来源  ▾"
        }
        hero.addView(Ui.gap(context, 7))
        hero.addView(sourceToggle)
        page.addView(hero)
        val recordBanner = Ui.row(context).apply {
            background = Ui.gradient(context, Palette.fitness, android.graphics.Color.rgb(255, 120, 87), 16)
            setPadding(Ui.dp(context, 18), Ui.dp(context, 16), Ui.dp(context, 18), Ui.dp(context, 16))
            elevation = Ui.dp(context, 2).toFloat()
            setOnClickListener { showWorkoutDialog(host) }
        }
        val recordCopy = Ui.column(context)
        recordCopy.addView(Ui.text(context, "＋ 记录一次运动", 18f, Palette.white, true))
        recordCopy.addView(Ui.text(context, "有氧、力量与自定义热量", 12f, Palette.white))
        recordBanner.addView(recordCopy, LinearLayout.LayoutParams(0, -2, 1f))
        recordBanner.addView(Ui.text(context, "›", 30f, Palette.white, true))
        page.addView(recordBanner)
        page.addView(Ui.gap(context, 12))
        val quickActions = Ui.row(context)
        val strengthAction = Ui.pill(context, "按组记录", Palette.fitness,
            android.graphics.Color.rgb(255, 238, 236)) { showStrengthDialog(host) }
        val timerAction = Ui.pill(context, "计时动作", Palette.deepGreen, Palette.lightGreen) {
            showStrengthDialog(host, timedManual = true)
        }
        val deviceAction = Ui.pill(context, "同步设备", Palette.protein, Palette.softBlue) {
            host.syncHealthConnect()
        }
        listOf(strengthAction, timerAction, deviceAction).forEach { action ->
            quickActions.addView(action, LinearLayout.LayoutParams(0, Ui.dp(context, 40), 1f).apply {
                marginEnd = Ui.dp(context, 5)
            })
        }
        page.addView(quickActions)
        page.addView(Ui.subtitle(context, "今日已完成运动"))
        val logs = Ui.column(context)
        page.addView(logs)
        page.addView(Ui.subtitle(context, "设备与手工运动时间冲突"))
        val conflicts = Ui.column(context)
        conflicts.addView(Ui.text(context, "正在检查同步冲突…", 13f, Palette.muted))
        page.addView(conflicts)
        page.addView(Ui.subtitle(context, "官方跟练计划"))
        val active = Ui.text(context, "当前尚未选择计划", 14f, Palette.muted)
        page.addView(active)
        val activeActions = Ui.column(context)
        page.addView(activeActions)
        val filterStatus = Ui.text(context, "正在读取个人训练配置…", 12f, Palette.muted)
        page.addView(filterStatus)
        val filterButton = Ui.button(context, "只看适合我的", Palette.ice) {}
        filterButton.isEnabled = false
        page.addView(filterButton)
        val planList = Ui.column(context)
        page.addView(planList)
        var trainingLevel: String? = null
        var goalType: String? = null
        var onlyMine = false
        var planRequestId = 0
        fun loadPlans() {
            val requestId = ++planRequestId
            planList.removeAllViews()
            planList.addView(Ui.text(context, "正在加载训练计划…", 13f, Palette.muted))
            val planLevel = if (trainingLevel == "recovery") "beginner" else trainingLevel
            val path = if (onlyMine && planLevel != null)
                "/training-plans?level=$planLevel" +
                    (if (goalType != null) "&goal_type=$goalType" else "")
                else "/training-plans"
            host.api.get(path) { data, error ->
                if (requestId != planRequestId) return@get
                if (error != null) {
                    planList.removeAllViews()
                    planList.addView(Ui.text(context, "计划加载失败：$error", 13f, Palette.fitness))
                } else showPlans(host, planList, data?.optJSONArray("items") ?: JSONArray())
            }
        }
        filterButton.setOnClickListener {
            onlyMine = !onlyMine
            filterButton.text = if (onlyMine) "显示全部官方计划" else "只看适合我的"
            loadPlans()
        }
        host.api.get("/profile") { data, error ->
            if (error != null) {
                filterStatus.text = "个人配置暂不可用，可浏览全部官方计划"
                return@get
            }
            trainingLevel = data?.optJSONObject("training")?.optString("level")
                ?.takeIf { it in listOf("beginner", "intermediate", "advanced", "recovery") }
            goalType = data?.optJSONObject("goal")?.optString("goal_type")
                ?.takeIf { it in listOf("fat_loss", "maintenance", "muscle_gain", "recovery") }
            val levelName = when (trainingLevel) {
                "beginner" -> "初级"; "intermediate" -> "中级"; "advanced" -> "高级"
                "recovery" -> "恢复训练（按初级计划）"; else -> "未设置"
            }
            val goalName = when (goalType) {
                "fat_loss" -> "减脂"; "maintenance" -> "维持"; "muscle_gain" -> "增肌"
                "recovery" -> "恢复回归"; else -> "未设置"
            }
            filterStatus.text = "个人条件：$levelName · $goalName；筛选仅影响浏览，不改变当前跟练计划"
            filterButton.isEnabled = trainingLevel != null
        }
        loadPlans()

        val day = UserCalendar.today().toString()
        host.api.get("/fitness/days/$day") { data, error ->
            if (error != null) {
                calories.text = "-- kcal"
                summary.text = "本地服务未连接：$error"
                activitySource.text = "连接电脑服务后显示运动数据与设备来源"
                return@get
            }
            val s = data?.optJSONObject("summary")
            val activityKcal = s?.optJSONObject("energy")?.optDouble("activity_kcal", 0.0)?.toInt() ?: 0
            calories.text = "$activityKcal kcal"
            val goal = s?.optInt("activity_goal_kcal", 300) ?: 300
            val duration = s?.optDouble("workout_minutes", 0.0) ?: 0.0
            val strengthKcal = s?.optDouble("strength_kcal", 0.0) ?: 0.0
            goalBadge.text = "目标 $goal kcal"
            progressFrame.post {
                progressFill.layoutParams = (progressFill.layoutParams as android.widget.FrameLayout.LayoutParams).apply {
                    width = (progressFrame.width * (activityKcal.toFloat() / goal).coerceIn(0f, 1f)).toInt()
                }
            }
            minuteStat.text = "${duration.toInt()}\n运动分钟"
            volumeStat.text = "${s?.optDouble("training_volume", 0.0) ?: 0.0}\n训练容量 kg"
            val heart = if (s?.isNull("heart_rate_bpm") == false) s.optInt("heart_rate_bpm").toString() else "--"
            heartStat.text = "$heart\n最近心率 bpm"
            stepsStat.text = "${s?.optInt("steps", 0) ?: 0}\n今日步数"
            summary.text = "训练 ${s?.optInt("workout_count", 0) ?: 0} 次 · 力量估算 ${strengthKcal.toInt()} kcal"
            val source = when (s?.optString("activity_source")) {
                "device" -> "设备 ${when (s?.optString("activity_provider")) {
                    "health_connect" -> "Health Connect"
                    "manual_device_import" -> "手工导入"
                    "apple_health" -> "Apple Health 桥接"
                    else -> s?.optString("activity_provider").orEmpty()
                }}"
                "manual" -> "手工 / MET 运动账本"
                else -> "暂无活动记录"
            }
            fun optionalSummaryText(key: String): String? =
                if (s != null && !s.isNull(key)) s.optString(key).takeIf { it.isNotBlank() }
                else null
            val synced = optionalSummaryText("activity_synced_at")
            fun localTime(value: String): String = try {
                java.time.OffsetDateTime.parse(value)
                    .atZoneSameInstant(UserCalendar.zone)
                    .format(java.time.format.DateTimeFormatter.ofPattern("MM-dd HH:mm"))
            } catch (_: Exception) { value }
            val heartSampled = optionalSummaryText("heart_rate_sampled_at")
            val heartSource = optionalSummaryText("heart_rate_source") ?: "来源未标注"
            val quality = when (s?.optString("activity_quality")) {
                "time_window" -> "按时间窗核算"
                "daily_fallback" -> "日汇总保守核算，无法判断逐时段重叠"
                else -> "暂无可结算活动"
            }
            activitySource.text = "活动热量来源：$source" +
                (if (synced != null && s?.optString("activity_source") == "device") " · 最近同步 ${localTime(synced)}" else "") +
                "\n$quality" +
                " · 待处理冲突 ${s?.optInt("pending_activity_conflicts", 0) ?: 0} 项" +
                (if (heartSampled != null) "\n最近心率 $heart bpm · ${localTime(heartSampled)} · $heartSource" else
                    "\n暂无设备心率样本（不显示伪实时值）")
            val plan = data?.optJSONObject("active_plan")
            active.text = if (plan == null) "当前尚未选择计划" else "正在跟练：${plan.optString("name")}"
            activeActions.removeAllViews()
            if (plan != null) {
                val progress = plan.optJSONObject("progress") ?: JSONObject()
                val todaySession = plan.optJSONObject("today_session")
                val nextSession = plan.optJSONObject("next_session")
                val card = Ui.card(context)
                card.addView(Ui.text(context, "第 ${progress.optInt("current_week", 1)} / ${plan.optInt("weeks")} 周 · " +
                    "完整完成 ${progress.optInt("completed")} / ${progress.optInt("total")} 次 · " +
                    "部分完成 ${progress.optInt("partial")} 次", 13f, Palette.muted))
                if (todaySession == null) {
                    card.addView(Ui.text(context, if (nextSession == null) "今天无计划训练；本轮计划日程已走完。"
                        else "今天是休息日；下次 ${nextSession.optString("scheduled_date")} · ${nextSession.optString("title")}",
                        13f, Palette.muted))
                } else {
                    val result = when (todaySession.optString("status")) {
                        "COMPLETED" -> "（已完成）"
                        "PARTIAL" -> "（部分完成）"
                        else -> ""
                    }
                    card.addView(Ui.text(context, "今日 · ${todaySession.optString("title")}" +
                        result, 16f, Palette.ink, true))
                    val exercises = todaySession.optJSONArray("exercises") ?: JSONArray()
                    for (i in 0 until exercises.length())
                        card.addView(Ui.text(context, "• ${exercises.optString(i)}", 13f, Palette.muted))
                    if (todaySession.optString("status") == "SCHEDULED") {
                        card.addView(Ui.gap(context, 8))
                        card.addView(Ui.button(context, "替换计划动作并说明原因", Palette.ice) {
                            showPlanReplacementDialog(host, todaySession)
                        })
                        card.addView(Ui.gap(context, 5))
                        card.addView(Ui.button(context, "按组跟练并记录容量", Palette.fitness) {
                            showStrengthDialog(host, todaySession)
                        })
                        card.addView(Ui.gap(context, 5))
                        card.addView(Ui.button(context, "按时长完成计划", Palette.ice) {
                            showWorkoutDialog(host, todaySession)
                        })
                    }
                }
                activeActions.addView(card)
                activeActions.addView(Ui.button(context, "停止当前计划", Palette.muted) {
                    AlertDialog.Builder(context).setTitle("停止跟练？")
                        .setMessage("历史训练记录会保留，之后仍可重新选择计划。")
                        .setNegativeButton("取消", null).setPositiveButton("停止") { _, _ ->
                            host.api.post("/training-plans/active/stop", JSONObject()) { _, stopError ->
                                if (stopError != null) host.message(stopError) else host.refresh()
                            }
                        }.show()
                })
            }
            showLogs(context, logs, data?.optJSONArray("workouts") ?: JSONArray())
        }
        host.api.get("/devices/conflicts") { data, error ->
            conflicts.removeAllViews()
            if (error != null) conflicts.addView(Ui.text(context, "冲突检查失败：$error", 13f, Palette.fitness))
            else showConflicts(host, conflicts, data?.optJSONArray("items") ?: JSONArray())
        }
        return page
    }

    private fun showLogs(context: Context, parent: LinearLayout, logs: JSONArray) {
        parent.removeAllViews()
        if (logs.length() == 0) parent.addView(Ui.text(context, "今日还没有运动记录", 14f, Palette.muted))
        for (i in 0 until logs.length()) {
            val log = logs.optJSONObject(i) ?: continue
            val card = Ui.card(context)
            val index = types.indexOf(log.optString("workout_type"))
            card.addView(Ui.text(context, if (log.optString("workout_type") == "custom")
                log.optString("custom_name", "自定义") else if (index >= 0) names[index] else log.optString("workout_type"),
                17f, Palette.ink, true))
            card.addView(Ui.text(context, "${log.optDouble("minutes")} 分钟  ·  ${log.optDouble("kcal")} kcal  ·  容量 ${log.optDouble("total_volume")} kg",
                13f, Palette.muted))
            val source = if (log.optString("kcal_source") == "MANUAL") "手工热量" else
                "MET ${log.optDouble("met_value")} · ${when (log.optString("intensity")) {
                    "low" -> "轻度"; "high" -> "高强度"; else -> "中等强度"
                }}"
            card.addView(Ui.text(context, "$source · ${log.optString("calculation_version", "旧版")}",
                12f, Palette.muted))
            if (log.optString("plan_session_title").isNotBlank())
                card.addView(Ui.text(context, "计划跟练：${log.optString("plan_session_title")}", 12f, Palette.ice))
            parent.addView(card)
        }
    }

    private fun showConflicts(host: ScreenHost, parent: LinearLayout, items: JSONArray) {
        val context = host.screenContext
        if (items.length() == 0) {
            parent.addView(Ui.text(context, "暂无可判定的时间重叠冲突", 13f, Palette.muted))
            return
        }
        for (index in 0 until items.length()) {
            val conflict = items.optJSONObject(index) ?: continue
            val card = Ui.card(context)
            val overlap = (conflict.optDouble("overlap_seconds") / 60).toInt()
            card.addView(Ui.text(context, "${conflict.optString("local_date")} · 设备活动与" +
                "${conflict.optString("workout_type")}重叠约 $overlap 分钟",
                15f, Palette.ink, true))
            card.addView(Ui.text(context, "设备 ${conflict.optDouble("device_kcal").toInt()} kcal · " +
                "手工 ${conflict.optDouble("manual_kcal").toInt()} kcal · ${conflict.optString("provider")}",
                12f, Palette.muted))
            card.addView(Ui.text(context, "未选择时，重叠时段优先设备，非重叠手工时段仍计入。",
                12f, Palette.muted))
            val options = listOf(
                Triple("保留设备（整笔手工不计热量）", "KEEP_DEVICE", "整笔手工训练仍保留容量与时长，但热量不计入。"),
                Triple("保留手工（重叠时段用手工）", "KEEP_MANUAL", "仅重叠时段改用手工热量，其余设备时段保留。"),
                Triple("合并非重叠部分", "MERGE_NON_OVERLAPPING", "重叠时段用设备，未重叠手工时段另计入。"))
            for ((label, resolution, explanation) in options) {
                card.addView(Ui.button(context, label, Palette.ice) {
                    AlertDialog.Builder(context).setTitle("确认冲突处置")
                        .setMessage(explanation)
                        .setNegativeButton("取消", null).setPositiveButton("确认") { _, _ ->
                            host.api.post("/devices/conflicts/${conflict.optString("id")}/resolve",
                                JSONObject().put("resolution", resolution)) { _, error ->
                                if (error != null) host.message(error) else host.refresh()
                            }
                        }.show()
                })
                card.addView(Ui.gap(context, 4))
            }
            parent.addView(card)
        }
    }

    private fun showPlans(host: ScreenHost, parent: LinearLayout, plans: JSONArray) {
        parent.removeAllViews()
        val context = host.screenContext
        if (plans.length() == 0) {
            parent.addView(Ui.text(context, "当前条件下没有官方计划；可切回全部计划浏览。", 13f, Palette.muted))
            return
        }
        for (i in 0 until plans.length()) {
            val plan = plans.optJSONObject(i) ?: continue
            val card = Ui.card(context)
            card.addView(Ui.text(context, plan.optString("name"), 17f, Palette.ink, true))
            val levelName = when (plan.optString("level")) {
                "beginner" -> "初级"; "intermediate" -> "中级"; "advanced" -> "高级"; else -> "未标注水平"
            }
            val goalName = when (plan.optString("goal_type")) {
                "fat_loss" -> "减脂"; "maintenance" -> "维持"; "muscle_gain" -> "增肌"
                "recovery" -> "恢复回归"; else -> "通用"
            }
            card.addView(Ui.text(context,
                "$levelName · $goalName · ${plan.optInt("weeks")} 周 · 每周 ${plan.optInt("days_per_week")} 天 · 每次约 ${plan.optInt("estimated_minutes")} 分钟",
                12f, Palette.fitness))
            card.addView(Ui.text(context, plan.optString("description"), 13f, Palette.muted))
            val days = plan.optJSONArray("days") ?: JSONArray()
            card.addView(Ui.text(context, "首周：" + (0 until days.length()).mapNotNull {
                days.optJSONObject(it)?.optString("title") }.joinToString(" / "), 12f, Palette.muted))
            card.addView(Ui.gap(context))
            card.addView(Ui.button(context, "查看训练安排", Palette.ice) {
                val alternatives = plan.optJSONArray("alternatives") ?: JSONArray()
                val guidance = listOf(
                    "适用人群：${plan.optString("suitability")}",
                    "风险提示：${plan.optString("contraindications")}",
                    "热身：${plan.optString("warmup")}",
                    "冷身：${plan.optString("cooldown")}",
                    "进阶：${plan.optString("progression_rule")}",
                    "替代动作：" + (0 until alternatives.length()).joinToString("；") { alternatives.optString(it) },
                    "完成标准：${plan.optString("completion_rule")}",
                    "模板版本：v${plan.optInt("version")}")
                val schedule = (0 until days.length()).mapNotNull { dayIndex ->
                    days.optJSONObject(dayIndex)?.let { day ->
                        val exercises = try { JSONArray(day.optString("session_template_json")) }
                            catch (_: Exception) { JSONArray() }
                        "第 ${day.optInt("day_no")} 天 · ${day.optString("title")}\n" +
                            (0 until exercises.length()).joinToString("\n") { "  • ${exercises.optString(it)}" }
                    }
                }.joinToString("\n\n")
                AlertDialog.Builder(context).setTitle(plan.optString("name"))
                    .setMessage(guidance.joinToString("\n\n") + "\n\n首周安排：\n" + schedule)
                    .setPositiveButton("知道了", null).show()
            })
            card.addView(Ui.gap(context, 5))
            card.addView(Ui.button(context, "选择跟练", Palette.fitness) {
                AlertDialog.Builder(context).setTitle("开始跟练")
                    .setMessage("启用「${plan.optString("name")}」？当前计划会停止，历史记录会保留。")
                    .setNegativeButton("取消", null).setPositiveButton("启用") { _, _ ->
                        host.api.post("/training-plans/${plan.optString("id")}/enroll",
                            JSONObject().put("start_date", UserCalendar.today().toString())) { _, error ->
                            if (error != null) host.message(error) else host.refresh()
                        }
                    }.show()
            })
            parent.addView(card)
        }
    }

    private fun showPlanReplacementDialog(host: ScreenHost, session: JSONObject) {
        val context = host.screenContext
        val exercises = session.optJSONArray("exercises") ?: JSONArray()
        if (exercises.length() == 0) { host.message("该计划日没有可替换动作"); return }
        val form = Ui.column(context).apply {
            setPadding(Ui.dp(context, 18), Ui.dp(context, 8), Ui.dp(context, 18), 0)
        }
        form.addView(Ui.text(context, "仅修改这次个人跟练；官方模板与其他周不受影响。", 13f, Palette.muted))
        val picker = Ui.picker(context, (0 until exercises.length()).map { exercises.optString(it) })
        val replacement = Ui.field(context, "替换后的动作及组次数")
        val reason = Ui.field(context, "替换原因（必填）")
        val errorText = Ui.text(context, "", 12f, Palette.fitness)
        listOf(picker, replacement, reason, errorText).forEach(form::addView)
        val dialog = AlertDialog.Builder(context).setTitle("替换计划动作").setView(form)
            .setNegativeButton("取消", null).setPositiveButton("保存替换", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val newName = replacement.text.toString().trim()
                val why = reason.text.toString().trim()
                if (newName.isBlank() || why.length < 2) {
                    errorText.text = "请填写替换动作和至少 2 字的原因"
                    return@setOnClickListener
                }
                val body = JSONObject().put("index", picker.selectedItemPosition)
                    .put("replacement", newName).put("reason", why)
                host.api.post("/training-plans/active/sessions/${session.optString("id")}/replace", body) { _, error ->
                    if (error != null) errorText.text = error
                    else { dialog.dismiss(); host.refresh() }
                }
            }
        }
        dialog.show()
    }

    private fun showWorkoutDialog(host: ScreenHost, plannedSession: JSONObject? = null) {
        val context = host.screenContext
        val minimumDuration = plannedSession?.optInt("minimum_duration_minutes", 0) ?: 0
        val form = Ui.column(context).apply { setPadding(Ui.dp(context, 18), Ui.dp(context, 8), Ui.dp(context, 18), 0) }
        if (plannedSession != null) {
            form.addView(Ui.text(context, "计划训练 · ${plannedSession.optString("title")}", 16f, Palette.ink, true))
            val exercises = plannedSession.optJSONArray("exercises") ?: JSONArray()
            for (i in 0 until exercises.length())
                form.addView(Ui.text(context, "• ${exercises.optString(i)}", 13f, Palette.muted))
            form.addView(Ui.text(context,
                if (minimumDuration > 0) "计划最低时长 $minimumDuration 分钟；不足时标记为部分完成。"
                else "力量计划仅按时长记录会标记为部分完成。", 12f, Palette.muted))
        }
        val picker = Ui.picker(context, names)
        val intensityPicker = Ui.picker(context, listOf("轻度", "中等强度", "高强度"))
        intensityPicker.setSelection(1)
        val minutes = Ui.field(context, "运动时长（分钟）", numeric = true)
        if (minimumDuration > 0) minutes.setText(minimumDuration.toString())
        val kcal = Ui.field(context, "自定义消耗（kcal，可留空）", numeric = true)
        val customName = Ui.field(context, "自定义运动名称（选择自定义时填写）")
        listOf(picker, intensityPicker, minutes, kcal, customName).forEach(form::addView)
        val estimateText = Ui.text(context, "选择运动、强度和时长后可先估算；自定义运动需填写热量。",
            12f, Palette.muted)
        form.addView(Ui.button(context, "先估算活动消耗", Palette.ice) {
            val duration = minutes.text.toString().toDoubleOrNull()
            if (duration == null || duration !in 1.0..1440.0 || picker.selectedItemPosition == 6) {
                estimateText.text = "请选择非自定义运动，并填写 1–1440 分钟时长"
                return@button
            }
            val request = JSONObject().put("workout_type", types[picker.selectedItemPosition])
                .put("intensity", listOf("low", "moderate", "high")[intensityPicker.selectedItemPosition])
                .put("minutes", duration)
            estimateText.text = "正在按当前体重和强度估算…"
            host.api.post("/workouts/estimate", request) { result, error ->
                estimateText.text = if (error != null || result == null) error ?: "估算未返回数据" else {
                    val weightSource = if (result.optString("weight_source") == "demo_default")
                        "；暂用 70 kg 默认体重，请在我的页面录入体重" else ""
                    "约 ${result.optDouble("kcal").toInt()} kcal · MET ${result.optDouble("met_value")}" +
                        " · ${result.optString("calculation_version")}$weightSource\n" +
                        "仅供参考；保存时按当前选择重新计算，填写自定义热量则以手工值为准。"
                }
            }
        })
        form.addView(estimateText)
        val operationKey = java.util.UUID.randomUUID().toString()
        var submittedPayload: String? = null
        var submitting = false
        val dialog = AlertDialog.Builder(context).setTitle("快速记录运动").setView(form)
            .setNegativeButton("取消", null).setPositiveButton("保存", null).create()
        dialog.setOnShowListener {
            val saveButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            saveButton.setOnClickListener {
                val duration = minutes.text.toString().toDoubleOrNull()
                if (duration == null || duration <= 0 ||
                    (picker.selectedItemPosition == 6 &&
                        (customName.text.isBlank() || kcal.text.toString().toDoubleOrNull() == null))) {
                    host.message("请填写有效时长；自定义运动还需名称和热量")
                    return@setOnClickListener
                }
                val body = JSONObject().put("workout_type", types[picker.selectedItemPosition])
                    .put("minutes", duration).put("local_date",
                        plannedSession?.optString("scheduled_date") ?: UserCalendar.today().toString())
                if (picker.selectedItemPosition != 6)
                    body.put("intensity", listOf("low", "moderate", "high")[intensityPicker.selectedItemPosition])
                if (plannedSession != null) body.put("plan_session_id", plannedSession.optString("id"))
                if (picker.selectedItemPosition == 6) body.put("custom_name", customName.text.toString())
                kcal.text.toString().toDoubleOrNull()?.let { body.put("kcal", it) }
                fun submit() {
                    if (submitting) return
                    val encoded = body.toString()
                    if (submittedPayload != null && submittedPayload != encoded) {
                        host.message("上次提交结果可能已入账，请先检查训练记录；如需修改，请新建记录")
                        return
                    }
                    submittedPayload = encoded
                    submitting = true
                    saveButton.isEnabled = false
                    host.api.post("/workouts", body, operationKey) { saved, error ->
                        submitting = false
                        if (error != null) {
                            saveButton.isEnabled = true
                            host.message(error)
                        } else {
                            dialog.dismiss()
                            host.refresh()
                            saved?.optString("id")?.takeIf(String::isNotBlank)?.let {
                                showRecoveryAdvice(host, it)
                            }
                        }
                    }
                }
                if (plannedSession != null && minimumDuration > 0 && duration < minimumDuration)
                    AlertDialog.Builder(context).setTitle("按部分完成保存？")
                        .setMessage("记录时长 $duration 分钟，少于计划最低 $minimumDuration 分钟；这一天将标记为部分完成。")
                        .setNegativeButton("继续记录", null)
                        .setPositiveButton("部分完成并保存") { _, _ -> submit() }.show()
                else if (plannedSession != null && minimumDuration == 0)
                    AlertDialog.Builder(context).setTitle("按部分完成保存？")
                        .setMessage("这一天包含力量动作，仅记录时长不会计入训练容量，也不算完整完成计划日。")
                        .setNegativeButton("继续记录", null)
                        .setPositiveButton("部分完成并保存") { _, _ -> submit() }.show()
                else submit()
            }
        }
        dialog.show()
    }

    private fun showStrengthDialog(host: ScreenHost, plannedSession: JSONObject? = null,
                                   timedManual: Boolean = false) {
        val context = host.screenContext
        val form = Ui.column(context).apply {
            setPadding(Ui.dp(context, 16), Ui.dp(context, 8), Ui.dp(context, 16), Ui.dp(context, 8))
        }
        val exercise = Ui.field(context, "动作名称，例如卧推")
        val minutes = Ui.field(context, "训练总时长（分钟）", numeric = true)
        if (plannedSession == null) form.addView(exercise)
        else form.addView(Ui.text(context,
            "计划训练 · ${plannedSession.optString("title")} · ${plannedSession.optString("scheduled_date")}",
            16f, Palette.ink, true))
        form.addView(minutes)
        form.addView(Ui.text(context, "次数组与计时组分别记次数或持续秒数；计时组不计入 kg 训练容量。自重动作重量可留空。", 13f, Palette.muted))
        val rows = Ui.column(context)
        form.addView(rows)
        val fields = mutableListOf<SetInputs>()
        val restLabel: TextView = Ui.text(context, "组间休息尚未开始", 14f, Palette.muted)
        val pauseButton = Ui.button(context, "暂停", Palette.ice) {}
        var timer: android.os.CountDownTimer? = null
        var restRemainingMs = 0L
        var restDeadlineMs = 0L
        var restPaused = false
        fun showRemaining() {
            restLabel.text = "距离下一组还有 ${(restRemainingMs + 999) / 1000} 秒${if (restPaused) "（已暂停）" else ""}"
        }
        fun startRest(durationMs: Long = 90_000L) {
            timer?.cancel()
            restRemainingMs = durationMs.coerceAtLeast(0L)
            restPaused = false
            pauseButton.text = "暂停"
            restDeadlineMs = android.os.SystemClock.elapsedRealtime() + restRemainingMs
            showRemaining()
            timer = object : android.os.CountDownTimer(restRemainingMs, 1_000) {
                override fun onTick(millisUntilFinished: Long) {
                    restRemainingMs = (restDeadlineMs - android.os.SystemClock.elapsedRealtime()).coerceAtLeast(0L)
                    showRemaining()
                }
                override fun onFinish() {
                    restRemainingMs = 0L
                    restLabel.text = "休息结束，可以开始下一组"
                    host.message("组间休息结束")
                }
            }.start()
        }
        fun addSet(moveName: String = "", suggestedAmount: Int? = null, timed: Boolean = false,
                   target: LinearLayout = rows) {
            val row = Ui.row(context)
            val setNo = fields.count { it.exerciseName == moveName } + 1
            val label = Ui.text(context, "${setNo}组", 12f, Palette.ink, true)
            row.addView(label, LinearLayout.LayoutParams(Ui.dp(context, 40), Ui.dp(context, 48)))
            val weight = Ui.field(context, "重量 kg（自重留空）", numeric = true)
            row.addView(weight, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f))
            val measure = Ui.field(context, if (timed) "持续秒数" else "次数", numeric = true)
            suggestedAmount?.let { measure.setText(it.toString()) }
            row.addView(measure, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f))
            val done = CheckBox(context).apply {
                isChecked = false
                contentDescription = "${if (moveName.isBlank()) "当前动作" else moveName}第${setNo}组已完成"
                setOnCheckedChangeListener { _, checked -> if (checked) startRest() }
            }
            row.addView(done, LinearLayout.LayoutParams(Ui.dp(context, 50), Ui.dp(context, 48)))
            target.addView(row)
            val effortRow = Ui.row(context)
            effortRow.addView(Ui.text(context, "强度", 12f, Palette.muted),
                LinearLayout.LayoutParams(Ui.dp(context, 40), Ui.dp(context, 44)))
            val rpe = Ui.field(context, "RPE 0-10", numeric = true)
            val rir = Ui.field(context, "RIR 0-10", numeric = true)
            effortRow.addView(rpe, LinearLayout.LayoutParams(0, Ui.dp(context, 44), 1f))
            effortRow.addView(rir, LinearLayout.LayoutParams(0, Ui.dp(context, 44), 1f))
            target.addView(effortRow)
            fields.add(SetInputs(weight, measure, timed, rpe, rir, done, moveName, setNo))
        }
        if (plannedSession == null) {
            repeat(3) { addSet(timed = timedManual) }
            form.addView(Ui.button(context, "+ 添加一组", Palette.ice) {
                if (fields.size >= 30) host.message("单次最多记录 30 组") else addSet(timed = timedManual)
            })
        } else {
            val templates = plannedSession.optJSONArray("exercises") ?: JSONArray()
            for (i in 0 until templates.length()) {
                val text = templates.optString(i)
                val prescription = PlanPrescriptions.parse(text)
                val moveName = prescription.name
                val count = prescription.setCount
                val amount = prescription.targetAmount
                val timed = prescription.timed
                form.addView(Ui.text(context, text, 14f, Palette.ink, true))
                val group = Ui.column(context)
                form.addView(group)
                repeat(count) { addSet(moveName, amount, timed, group) }
                form.addView(Ui.button(context, "+ $moveName 一组", Palette.ice) {
                    if (fields.size >= 30) host.message("单次最多记录 30 组") else addSet(moveName, amount, timed, group)
                })
            }
            form.addView(Ui.text(context, "动作与组数来自官方模板；自重动作可留空重量，容量只计实际填写的外部负重，未完成组不计容量。",
                12f, Palette.muted))
        }
        form.addView(Ui.gap(context))
        form.addView(restLabel)
        form.addView(Ui.button(context, "重启 90 秒组间休息", Palette.fitness) { startRest() })
        val timerActions = Ui.row(context)
        pauseButton.setOnClickListener {
            if (restRemainingMs <= 0) {
                host.message("请先开始组间休息")
            } else if (restPaused) {
                startRest(restRemainingMs)
                pauseButton.text = "暂停"
            } else {
                timer?.cancel()
                restRemainingMs = (restDeadlineMs - android.os.SystemClock.elapsedRealtime()).coerceAtLeast(0L)
                restPaused = true
                showRemaining()
                pauseButton.text = "继续"
            }
        }
        timerActions.addView(pauseButton, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f).apply {
            marginEnd = Ui.dp(context, 5)
        })
        timerActions.addView(Ui.button(context, "+15 秒", Palette.ice) {
            if (restRemainingMs <= 0) host.message("请先开始组间休息")
            else if (restPaused) {
                restRemainingMs += 15_000L
                showRemaining()
            } else {
                startRest((restDeadlineMs - android.os.SystemClock.elapsedRealtime()).coerceAtLeast(0L) + 15_000L)
                pauseButton.text = "暂停"
            }
        }, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f).apply { marginEnd = Ui.dp(context, 5) })
        timerActions.addView(Ui.button(context, "跳过", Palette.muted) {
            timer?.cancel()
            restRemainingMs = 0L
            restPaused = false
            pauseButton.text = "暂停"
            restLabel.text = "已跳过休息，可以开始下一组"
        }, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f))
        form.addView(Ui.gap(context, 6))
        form.addView(timerActions)
        val scroll = android.widget.ScrollView(context).apply { addView(form) }
        val operationKey = java.util.UUID.randomUUID().toString()
        var submittedPayload: String? = null
        var submitting = false
        val dialog = AlertDialog.Builder(context).setTitle("力量训练按组记录").setView(scroll)
            .setNegativeButton("取消", null).setPositiveButton("保存训练", null).create()
        dialog.setOnDismissListener { timer?.cancel() }
        dialog.setOnShowListener {
            val saveButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            saveButton.setOnClickListener {
                val duration = minutes.text.toString().toDoubleOrNull()
                if ((plannedSession == null && exercise.text.isBlank()) || duration == null || duration <= 0) {
                    host.message("请填写动作名称与有效训练时长")
                    return@setOnClickListener
                }
                val sets = JSONArray()
                for ((index, set) in fields.withIndex()) {
                    val weightText = set.weight.text.toString().trim()
                    val w = weightText.toDoubleOrNull()
                    val amount = set.measure.text.toString().toIntOrNull() ?: if (!set.done.isChecked) 0 else null
                    val rpe = set.rpe.text.toString().toDoubleOrNull()
                    val rir = set.rir.text.toString().toDoubleOrNull()
                    if ((weightText.isNotEmpty() && w == null) || (w != null && w < 0) ||
                        amount == null || (set.done.isChecked && amount <= 0) ||
                        (rpe != null && rpe !in 0.0..10.0) || (rir != null && rir !in 0.0..10.0)) {
                        host.message("请核对第 ${index + 1} 组的重量与${if (set.timed) "秒数" else "次数"}")
                        return@setOnClickListener
                    }
                    sets.put(JSONObject().put("exercise_name",
                        if (plannedSession == null) exercise.text.toString().trim() else set.exerciseName)
                        .put("set_no", set.setNo).put("weight_kg", w ?: JSONObject.NULL)
                        .put("reps", if (set.timed) 0 else amount).apply {
                            if (set.timed && amount > 0) put("duration_sec", amount)
                        }
                        .put("completed", set.done.isChecked).apply {
                            if (rpe != null) put("rpe", rpe)
                            if (rir != null) put("rir", rir)
                        })
                }
                if (fields.none { it.done.isChecked }) { host.message("请至少完成一组"); return@setOnClickListener }
                val body = JSONObject().put("workout_type", "strength")
                    .put("minutes", duration).put("local_date",
                        plannedSession?.optString("scheduled_date") ?: UserCalendar.today().toString()).put("sets", sets)
                if (plannedSession != null) body.put("plan_session_id", plannedSession.optString("id"))
                fun submit() {
                    if (submitting) return
                    val encoded = body.toString()
                    if (submittedPayload != null && submittedPayload != encoded) {
                        host.message("上次提交结果可能已入账，请先检查训练记录；如需修改，请新建记录")
                        return
                    }
                    submittedPayload = encoded
                    submitting = true
                    saveButton.isEnabled = false
                    host.api.post("/workouts", body, operationKey) { saved, error ->
                        submitting = false
                        if (error != null) {
                            saveButton.isEnabled = true
                            host.message(error)
                        } else {
                            dialog.dismiss()
                            host.refresh()
                            saved?.optString("id")?.takeIf(String::isNotBlank)?.let {
                                showRecoveryAdvice(host, it)
                            }
                        }
                    }
                }
                if (plannedSession != null && fields.any { !it.done.isChecked })
                    AlertDialog.Builder(context).setTitle("按部分完成保存？")
                        .setMessage("仍有未完成组，保存后这一天将标记为部分完成，不能再补记到同一计划日。")
                        .setNegativeButton("继续记录", null)
                        .setPositiveButton("部分完成并保存") { _, _ -> submit() }.show()
                else submit()
            }
        }
        dialog.show()
    }

    private fun showRecoveryAdvice(host: ScreenHost, workoutId: String) {
        host.api.get("/workouts/$workoutId/recovery") { data, error ->
            if (error != null || data == null) {
                host.message("训练已保存；恢复建议暂不可用：${error ?: "服务未返回内容"}")
                return@get
            }
            val summary = data.optJSONObject("summary") ?: JSONObject()
            val advice = data.optJSONArray("advice") ?: JSONArray()
            val notices = data.optJSONArray("notices") ?: JSONArray()
            val source = if (data.optString("source") == "agent-selected-v1")
                "联网 Agent 从已校验建议中选择" else "本地规则建议"
            val message = buildString {
                append("$source · 本次 ${summary.optDouble("minutes").toInt()} 分钟")
                append("\n训练容量 ${summary.optDouble("training_volume_kg").toInt()} kg")
                append(" · 活动消耗估算 ${summary.optDouble("estimated_kcal").toInt()} kcal")
                for (i in 0 until advice.length()) {
                    advice.optJSONObject(i)?.optString("text")?.let { append("\n\n• $it") }
                }
                for (i in 0 until notices.length()) append("\n\n${notices.optString(i)}")
                append("\n\n可到数据页查看当日账本与诊断。")
            }
            AlertDialog.Builder(host.screenContext).setTitle("训练摘要与营养恢复提示")
                .setMessage(message).setNegativeButton("知道了", null)
                .setPositiveButton("查看数据") { _, _ -> host.navigate(3) }.show()
        }
    }
}
