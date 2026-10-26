package com.example.appdemo.features.what_to_eat

import android.app.AlertDialog
import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.content.Context
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.widget.LinearLayout
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.time.UserCalendar
import org.json.JSONArray
import org.json.JSONObject

object WhatToEatScreen {
    private val mealValues = listOf("breakfast", "lunch", "dinner", "snack")
    private val scenarios = listOf("self_cook", "takeout", "dine_in", "convenience")
    private var recommendationRequestId = 0

    fun render(host: ScreenHost): View {
        val context = host.screenContext
        val pageDay = UserCalendar.today().toString()
        val page = Ui.column(context)
        page.addView(Ui.text(context, "今天吃什么？", 25f, Palette.ink, true))
        page.addView(Ui.text(context, "$pageDay · 根据今日账本与饮食偏好挑选", 13f, Palette.muted))
        val budget = Ui.card(context).apply {
            background = Ui.gradient(context, Palette.white, Palette.lightGreen, 16)
        }
        budget.addView(Ui.text(context, "当前剩余热量", 13f, Palette.deepGreen, true))
        val remaining = Ui.text(context, "-- kcal", 30f, Palette.deepGreen, true)
        budget.addView(remaining)
        val budgetNote = Ui.text(context, "结合阶段目标、已记餐食与过敏忌口动态计算", 12f, Palette.muted)
        budget.addView(budgetNote)
        page.addView(Ui.gap(context, 10))
        page.addView(budget)
        val controls = Ui.card(context)
        controls.addView(Ui.text(context, "想吃哪一餐？", 14f, Palette.ink, true))
        val mealPicker = Ui.picker(context, listOf("早餐", "午餐", "晚餐", "加餐"))
        mealPicker.setSelection(mealValues.indexOf("dinner"))
        controls.addView(mealPicker)
        controls.addView(Ui.text(context, "用餐场景", 14f, Palette.ink, true))
        val scenarioPicker = Ui.picker(context, listOf("自己下厨", "外卖", "堂食", "便利店"))
        controls.addView(scenarioPicker)
        val result = Ui.column(context)
        var selectedMeal = mealPicker.selectedItemPosition
        var selectedScenario = scenarioPicker.selectedItemPosition
        var scenarioTouched = false
        var userRequested = false
        fun invalidateResults() {
            recommendationRequestId++
            result.removeAllViews()
            result.addView(Ui.text(context, "条件已变更，请重新生成推荐。", 13f, Palette.muted))
        }
        mealPicker.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (position != selectedMeal) {
                    selectedMeal = position
                    invalidateResults()
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
        scenarioPicker.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (position != selectedScenario) {
                    selectedScenario = position
                    scenarioTouched = true
                    invalidateResults()
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
        controls.addView(Ui.button(context, "生成推荐", Palette.green) {
            if (pageDay != UserCalendar.today().toString()) {
                host.message("日期已变化，正在刷新今日预算")
                host.refresh()
                return@button
            }
            userRequested = true
            request(host, result, pageDay, mealValues[mealPicker.selectedItemPosition],
                scenarios[scenarioPicker.selectedItemPosition], false)
        })
        page.addView(controls)
        val blindAction = Ui.pill(context, "🎲  盲盒 · 帮我随机选", Palette.deepGreen,
            Palette.lightGreen) {
            if (pageDay != UserCalendar.today().toString()) {
                host.message("日期已变化，正在刷新今日预算")
                host.refresh()
                return@pill
            }
            userRequested = true
            request(host, result, pageDay, mealValues[mealPicker.selectedItemPosition],
                scenarios[scenarioPicker.selectedItemPosition], true)
        }
        page.addView(blindAction, LinearLayout.LayoutParams(-1, Ui.dp(context, 44)))
        val chatAction = Ui.row(context).apply {
            background = Ui.gradient(context, Palette.deepGreen, Palette.green)
            setPadding(Ui.dp(context, 16), Ui.dp(context, 13), Ui.dp(context, 16), Ui.dp(context, 13))
            setOnClickListener { openChat(host) }
            contentDescription = "打开 AI 饮食顾问多轮对话"
        }
        chatAction.addView(Ui.text(context, "✦", 24f, Palette.white, true),
            LinearLayout.LayoutParams(Ui.dp(context, 38), LinearLayout.LayoutParams.WRAP_CONTENT))
        val chatCopy = Ui.column(context)
        chatCopy.addView(Ui.text(context, "召唤 AI 饮食顾问", 16f, Palette.white, true))
        chatCopy.addView(Ui.text(context, "聊清需求，确认后再加入饮食计划", 12f, Palette.white))
        chatAction.addView(chatCopy, LinearLayout.LayoutParams(0,
            LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        chatAction.addView(Ui.text(context, "›", 26f, Palette.white, true))
        page.addView(Ui.gap(context, 11))
        page.addView(chatAction)
        page.addView(Ui.subtitle(context, "适合你的方案"))
        page.addView(result)
        host.api.get("/analytics/days?date=$pageDay") { data, error ->
            remaining.text = if (error == null && data?.optBoolean("has_target") == true)
                "${data.optJSONObject("energy")?.optDouble("remaining_kcal", 0.0)?.toInt()} kcal" else "-- kcal"
            budgetNote.text = when {
                error != null -> "连接电脑服务后显示今日营养预算"
                data?.optBoolean("has_target") != true -> "完善身体档案与阶段目标后显示预算"
                else -> "结合阶段目标、已记餐食与过敏忌口动态计算"
            }
        }
        host.api.get("/profile") { data, _ ->
            val preferred = data?.optJSONObject("dining")?.optString("preferred_scenario")
            if (!scenarioTouched) {
                selectedScenario = scenarios.indexOf(preferred).coerceAtLeast(0)
                scenarioPicker.setSelection(selectedScenario)
            }
            if (!userRequested) {
                if (pageDay != UserCalendar.today().toString()) host.refresh()
                else request(host, result, pageDay, mealValues[mealPicker.selectedItemPosition],
                    scenarios[scenarioPicker.selectedItemPosition], false)
            }
        }
        return page
    }

    private fun request(host: ScreenHost, result: LinearLayout, day: String, meal: String,
                        scenario: String, shuffle: Boolean, avoidRecipeId: String? = null) {
        val context = host.screenContext
        val requestId = ++recommendationRequestId
        result.removeAllViews()
        result.addView(Ui.text(context, "正在计算营养匹配方案…", 14f, Palette.muted))
        val body = JSONObject().put("local_date", day)
            .put("meal_type", meal).put("scenario", scenario).put("shuffle", shuffle)
        if (avoidRecipeId != null) body.put("avoid_recipe_id", avoidRecipeId)
        host.api.post("/recommendations/meals", body) { data, error ->
            if (requestId != recommendationRequestId) return@post
            if (day != UserCalendar.today().toString()) {
                host.refresh()
                return@post
            }
            result.removeAllViews()
            if (error != null) {
                result.addView(Ui.text(context, error, 14f, Palette.fitness))
                return@post
            }
            val source = data?.optJSONObject("session")?.optString("constraint_version")
            result.addView(Ui.text(context, if (source == "agent-v1")
                "联网智能推荐 · 已校验饮食限制" else "本地安全规则推荐 · Agent 未连接或不可用",
                12f, Palette.muted))
            val snapshot = try { JSONObject(data?.optJSONObject("session")?.optString("context_snapshot_json") ?: "{}") }
                catch (_: Exception) { JSONObject() }
            val blindBox = snapshot.optJSONObject("blind_box")
            if (shuffle && blindBox != null) {
                result.addView(Ui.text(context, "盲盒抽中 1 份 · 安全候选 ${blindBox.optInt("candidate_count")} 道 · 池版本 ${blindBox.optString("pool_version").take(8)}",
                    14f, Palette.ice, true))
            }
            val stage = when (snapshot.optString("goal_type")) {
                "fat_loss" -> "减脂"; "muscle_gain" -> "增肌"; "recovery" -> "恢复"; "maintenance" -> "维持"; else -> "未设目标"
            }
            val proteinGap = snapshot.optJSONObject("macro_gaps")?.optDouble("protein_g", 0.0) ?: 0.0
            result.addView(Ui.text(context, "$stage · 剩余 ${snapshot.optDouble("remaining_kcal", 0.0).toInt()} kcal · 蛋白质缺口 ${proteinGap.toInt()}g",
                12f, Palette.protein))
            val dining = snapshot.optJSONObject("dining")
            val limits = listOfNotNull(
                if (dining?.isNull("max_cost_cny") == false) "单餐估算 ≤¥${dining.optDouble("max_cost_cny").toInt()}" else null,
                if (scenario == "self_cook" && dining?.isNull("max_cook_minutes") == false)
                    "备餐+烹饪 ≤${dining.optInt("max_cook_minutes")} 分钟" else null
            )
            if (limits.isNotEmpty()) result.addView(Ui.text(context, limits.joinToString(" · "), 12f, Palette.muted))
            result.addView(Ui.gap(context, 7))
            val items = data?.optJSONArray("items") ?: JSONArray()
            if (items.length() == 0) {
                result.addView(Ui.text(context, "当前限制条件下暂时没有安全匹配的菜谱，请调整条件或手工记录。",
                    14f, Palette.muted))
            }
            for (i in 0 until items.length()) {
                val item = items.optJSONObject(i) ?: continue
                val card = Ui.card(context)
                val recommendationHeading = Ui.row(context)
                recommendationHeading.addView(Ui.text(context, item.optString("title"), 17f, Palette.ink, true),
                    LinearLayout.LayoutParams(0, -2, 1f))
                recommendationHeading.addView(Ui.badge(context,
                    "匹配 ${item.optDouble("score").toInt()} 分", Palette.green))
                card.addView(recommendationHeading)
                val duration = if (scenario == "self_cook")
                    " · 约 ${item.optInt("prep_minutes") + item.optInt("cook_minutes")} 分钟" else ""
                val costText = Ui.text(context, "", 12f, Palette.muted)
                card.addView(costText)
                val nutrition = item.optJSONObject("nutrition")
                card.addView(Ui.gap(context, 7))
                val portions = listOf(0.5, 1.0, 1.5, 2.0)
                val servingPicker = Ui.picker(context, listOf("半份", "标准 1 份", "1.5 份", "2 份"))
                servingPicker.setSelection(1)
                card.addView(servingPicker)
                val nutritionText = Ui.text(context, "", 13f, Palette.protein)
                val addButton = Ui.button(context, "加入今日饮食计划", Palette.green) {
                    host.api.post("/recommendations/${item.optString("id")}/accept",
                        JSONObject().put("servings", portions[servingPicker.selectedItemPosition])) { _, acceptError ->
                        if (acceptError != null) host.message(acceptError)
                        else {
                            host.message("已加入计划，实际食用后请到饮食页确认")
                            host.navigate(0)
                        }
                    }
                }
                fun updateNutrition() {
                    val factor = portions[servingPicker.selectedItemPosition]
                    val selectedKcal = (nutrition?.optDouble("kcal", 0.0) ?: 0.0) * factor
                    val overEnergy = snapshot.optBoolean("has_target") &&
                        selectedKcal > maxOf(snapshot.optDouble("remaining_kcal", 0.0), 0.0) + 100
                    val maxCost = dining?.optDouble("max_cost_cny", Double.NaN) ?: Double.NaN
                    val overCost = !maxCost.isNaN() &&
                        (item.isNull("estimated_cost_cny") ||
                            item.optDouble("estimated_cost_cny") * factor > maxCost)
                    addButton.isEnabled = !overEnergy && !overCost
                    addButton.background = Ui.shape(context,
                        if (addButton.isEnabled) Palette.green else Palette.disabled, 14)
                    addButton.setTextColor(if (addButton.isEnabled) Palette.white else Palette.muted)
                    nutritionText.text = "${selectedKcal.toInt()} kcal  ·  蛋白质 ${((nutrition?.optDouble("protein_g",0.0) ?: 0.0) * factor).toInt()}g  ·  碳水 ${((nutrition?.optDouble("carb_g",0.0) ?: 0.0) * factor).toInt()}g" +
                        when {
                            overEnergy -> "\n当前份数超出剩余热量，请减少份数"
                            overCost -> "\n当前份数超出估算价格上限，请减少份数"
                            else -> ""
                        }
                    nutritionText.setTextColor(if (overEnergy || overCost) Palette.fitness else Palette.protein)
                    val cost = if (item.isNull("estimated_cost_cny")) "价格未知" else
                        "估算 ¥${(item.optDouble("estimated_cost_cny") * factor).toInt()}"
                    costText.text = "$cost$duration · 实际配料与价格以商家/称量为准"
                }
                servingPicker.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
                    override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) = updateNutrition()
                    override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
                }
                updateNutrition()
                card.addView(nutritionText)
                val reasons = item.optJSONArray("reasons") ?: JSONArray()
                card.addView(Ui.text(context, (0 until reasons.length()).map { reasons.optString(it) }.joinToString(" · "),
                    12f, Palette.muted))
                card.addView(Ui.gap(context, 8))
                val currentFeedback = when (item.optString("feedback_type")) {
                    "DISLIKE" -> " · 已标记不喜欢"
                    "REPEATED" -> " · 已标记最近吃过"
                    "UNSUITABLE" -> " · 已标记不合适"
                    else -> ""
                }
                val feedbackAction = Ui.pill(context, "反馈这道菜$currentFeedback", Palette.muted,
                    Palette.background) {
                    val labels = arrayOf("不喜欢", "最近吃过", "不合适", "撤销反馈")
                    val values = arrayOf("DISLIKE", "REPEATED", "UNSUITABLE", "CLEAR")
                    AlertDialog.Builder(context).setTitle("调整后续推荐")
                        .setItems(labels) { _, selected ->
                            host.api.post("/recommendations/${item.optString("id")}/feedback",
                                JSONObject().put("feedback_type", values[selected])) { _, feedbackError ->
                                if (feedbackError != null) host.message(feedbackError)
                                else {
                                    host.message(if (values[selected] == "CLEAR") "已撤销反馈" else "已记录反馈，重新排序中")
                                    request(host, result, day, meal, scenario, shuffle)
                                }
                            }
                        }.setNegativeButton("取消", null).show()
                }
                val recipeAction = Ui.pill(context, "查看菜谱与建议", Palette.protein,
                    Palette.softBlue) {
                    showRecipe(host, item.optString("candidate_ref_id"), item.optJSONArray("modifications"),
                        portions[servingPicker.selectedItemPosition])
                }
                val cardActions = Ui.row(context)
                listOf(feedbackAction, recipeAction).forEach { action ->
                    cardActions.addView(action, LinearLayout.LayoutParams(0, Ui.dp(context, 39), 1f).apply {
                        marginEnd = Ui.dp(context, 6)
                    })
                }
                card.addView(cardActions)
                card.addView(Ui.text(context,
                    "反馈只调整排序；永久忌口请到“我的”设置。", 11f, Palette.muted))
                card.addView(Ui.gap(context, 9))
                card.addView(addButton)
                result.addView(card)
            }
            if (shuffle && items.length() > 0) {
                result.addView(Ui.gap(context, 8))
                result.addView(Ui.button(context, "换一个安全方案", Palette.ice) {
                    request(host, result, day, meal, scenario, true,
                        items.optJSONObject(0)?.optString("candidate_ref_id"))
                })
                if (blindBox != null) showBlindBoxWheel(context, blindBox)
            }
        }
    }

    private fun showBlindBoxWheel(context: Context, blindBox: JSONObject) {
        val pool = blindBox.optJSONArray("candidate_pool") ?: return
        val choices = (0 until pool.length()).mapNotNull { pool.optJSONObject(it) }
        if (choices.isEmpty()) return
        val selected = choices.indexOfFirst { it.optString("recipe_id") == blindBox.optString("drawn_recipe_id") }
        if (selected < 0) return
        val column = Ui.column(context).apply {
            setPadding(Ui.dp(context, 12), Ui.dp(context, 8), Ui.dp(context, 12), Ui.dp(context, 8))
        }
        val wheel = BlindBoxWheelView(context, choices.map { it.optString("name") }).apply {
            contentDescription = "盲盒转盘，候选 ${choices.size} 道，正在抽选"
        }
        column.addView(wheel)
        val caption = Ui.text(context, "正在从已通过饮食限制的菜谱中抽选…", 14f, Palette.muted)
        caption.textAlignment = View.TEXT_ALIGNMENT_CENTER
        caption.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        column.addView(caption)
        val dialog = AlertDialog.Builder(context).setTitle("盲盒大转盘")
            .setView(column).setPositiveButton("查看抽中的方案", null).create()
        dialog.show()
        val viewButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
        viewButton.isEnabled = false
        val sweep = 360f / choices.size
        val finalAngle = 360f * 5 - (selected + 0.5f) * sweep
        val animator = ValueAnimator.ofFloat(0f, finalAngle).apply {
            duration = 1900L
            interpolator = DecelerateInterpolator()
            addUpdateListener { wheel.rotationDegrees = it.animatedValue as Float }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    if (dialog.isShowing) {
                        caption.text = "抽中：${choices[selected].optString("name")} · 可查看理由、换一个或预记入"
                        wheel.contentDescription = caption.text.toString()
                        viewButton.isEnabled = true
                    }
                }
            })
        }
        dialog.setOnDismissListener { animator.cancel() }
        animator.start()
    }

    private fun showRecipe(host: ScreenHost, recipeId: String, modifications: JSONArray?, servings: Double) {
        host.api.get("/recipes/$recipeId") { data, error ->
            if (error != null) { host.message(error); return@get }
            val context = host.screenContext
            val ingredients = data?.optJSONArray("ingredients") ?: JSONArray()
            val instructions = data?.optJSONArray("instructions") ?: JSONArray()
            val ingredientLines = (0 until ingredients.length()).mapNotNull { ingredients.optJSONObject(it) }
                .joinToString("\n") { "• ${it.optString("name")} ${(it.optDouble("grams") * servings).toInt()}g" }
            val stepLines = (0 until instructions.length()).joinToString("\n") { "${it + 1}. ${instructions.optString(it)}" }
            val tips = (0 until (modifications?.length() ?: 0)).joinToString("\n") { "• ${modifications?.optString(it)}" }
            val nutrition = data?.optJSONObject("nutrition_per_serving")
            val nutritionLine = if (nutrition == null) "营养估算暂缺" else {
                fun grams(key: String): String = String.format(java.util.Locale.getDefault(), "%.1f",
                    nutrition.optDouble(key, 0.0) * servings)
                "营养估算：${(nutrition.optDouble("kcal", 0.0) * servings).toInt()} kcal · " +
                    "碳水 ${grams("carb_g")}g · 蛋白质 ${grams("protein_g")}g · " +
                    "脂肪 ${grams("fat_g")}g · 膳食纤维 ${grams("fiber_g")}g"
            }
            val costLine = if (data?.has("estimated_cost_cny") == true && !data.isNull("estimated_cost_cny"))
                "估算价格：¥${(data.optDouble("estimated_cost_cny") * servings).toInt()} · 非实时报价"
                else "估算价格：未知 · 请以实际价格为准"
            val instructionsTitle = if (data?.optString("scenario") == "self_cook") "烹饪步骤" else "点餐提示"
            val substitutions = data?.optJSONArray("substitutions") ?: JSONArray()
            val substitutionLines = (0 until substitutions.length()).mapNotNull { substitutions.optJSONObject(it) }
                .joinToString("\n") { option ->
                    val preview = option.optJSONObject("nutrition_per_serving_if_used")
                    val replacementGrams = option.optDouble("grams_per_serving") * servings
                    val previewKcal = (preview?.optDouble("kcal", 0.0) ?: 0.0) * servings
                    fun previewGrams(key: String) = String.format(java.util.Locale.getDefault(), "%.1f",
                        (preview?.optDouble(key, 0.0) ?: 0.0) * servings)
                    "• ${option.optString("original_name")} → ${option.optString("replacement_name")} " +
                        "${replacementGrams.toInt()}g；换用后全餐约 ${previewKcal.toInt()} kcal，" +
                        "碳水 ${previewGrams("carb_g")}g、蛋白质 ${previewGrams("protein_g")}g、" +
                        "脂肪 ${previewGrams("fat_g")}g"
                }
            val substitutionNote = if (data?.optString("scenario") == "self_cook")
                "\n\n食材替换参考：\n${substitutionLines.ifBlank { "暂无经过核验的替换项" }}" +
                    "\n仅供备餐参考；若实际换用，请在饮食页修改预记餐食并重新核对配料、价格和营养。"
                else ""
            val dietaryWarning = if (data?.optBoolean("matches_current_restrictions", true) == false)
                "\n⚠ 当前个人饮食限制与此菜谱冲突，请重新生成推荐，勿直接采用。" else ""
            AlertDialog.Builder(context).setTitle(data?.optString("name") ?: "菜谱")
                .setMessage("份数：${servings} 份$dietaryWarning\n$nutritionLine\n$costLine\n预计用时：${(data?.optInt("prep_minutes") ?: 0) + (data?.optInt("cook_minutes") ?: 0)} 分钟\n食材：\n$ingredientLines\n\n$instructionsTitle：\n$stepLines\n\n调整建议：\n$tips$substitutionNote")
                .setPositiveButton("知道了", null).show()
        }
    }

    fun openChat(host: ScreenHost) {
        host.api.post("/agent/chats", JSONObject()) { session, error ->
            if (error != null) { host.message(error); return@post }
            val chatId = session?.optString("id") ?: return@post
            val context = host.screenContext
            val container = Ui.column(context).apply {
                setPadding(Ui.dp(context, 16), Ui.dp(context, 8), Ui.dp(context, 16), 0)
            }
            val transcript = Ui.text(context, "你可以说：我今天晚餐想吃热的，20 分钟内能做好。", 14f, Palette.muted)
            container.addView(transcript)
            container.addView(Ui.gap(context, 12))
            val proposalView = Ui.text(context, "尚无待确认方案", 14f, Palette.protein)
            container.addView(proposalView)
            container.addView(Ui.gap(context, 8))
            val input = Ui.field(context, "输入饮食需求")
            container.addView(input)
            val acceptButton = Ui.button(context, "确认方案并加入饮食计划", Palette.green) {}
            acceptButton.isEnabled = false
            container.addView(Ui.button(context, "发送", Palette.ice) {
                val content = input.text.toString().trim()
                if (content.isEmpty()) { host.message("请输入需求"); return@button }
                transcript.append("\n\n我：$content")
                input.setText("")
                host.api.post("/agent/chats/$chatId/messages", JSONObject().put("content", content)) { reply, replyError ->
                    if (replyError != null) transcript.append("\n\n系统：$replyError")
                    else {
                        transcript.append("\n\n助手：${reply?.optString("reply") ?: ""}")
                        val proposal = reply?.optJSONObject("proposal")
                        if (proposal != null) {
                            transcript.append("\n\n已生成可预记入方案，请核对后确认。")
                            val foods = proposal.optJSONArray("items") ?: JSONArray()
                            val mealName = when (proposal.optString("meal_type")) {
                                "breakfast" -> "早餐"; "lunch" -> "午餐"; "dinner" -> "晚餐"; else -> "加餐"
                            }
                            val entries = (0 until foods.length()).mapNotNull { foods.optJSONObject(it) }
                            val allMacrosKnown = entries.all { food ->
                                listOf("carb_g", "protein_g", "fat_g").all { key ->
                                    food.has(key) && !food.isNull(key)
                                }
                            }
                            val allergens = entries.flatMap { food ->
                                val tags = food.optJSONArray("allergens") ?: JSONArray()
                                (0 until tags.length()).mapNotNull { tags.optString(it).takeIf(String::isNotBlank) }
                            }.distinct()
                            val macroLine = if (allMacrosKnown) {
                                fun total(key: String) = String.format(java.util.Locale.getDefault(), "%.1f",
                                    entries.sumOf { it.optDouble(key) })
                                "碳水 ${total("carb_g")}g · 蛋白质 ${total("protein_g")}g · 脂肪 ${total("fat_g")}g"
                            } else "宏量营养素未完整估算，请核对"
                            proposalView.text = buildString {
                                append("$mealName · 待预记入")
                                proposal.optString("recipe_name").takeIf(String::isNotBlank)?.let {
                                    append("\n菜谱：$it")
                                }
                                append("\n总热量约 ${entries.sumOf { it.optDouble("kcal") }.toInt()} kcal · $macroLine")
                                if (proposal.has("estimated_cost_cny") && !proposal.isNull("estimated_cost_cny"))
                                    append("\n估算单餐费用 ¥${proposal.optDouble("estimated_cost_cny")}，以实际价格为准")
                                append("\n可能过敏原：${if (allergens.isEmpty()) "未标注，仍需核对" else allergens.joinToString("、")}")
                                entries.forEach { food ->
                                    append("\n• ${food.optString("name")} ${food.optDouble("grams")}g · ${food.optDouble("kcal").toInt()} kcal")
                                }
                            }
                            acceptButton.isEnabled = true
                        }
                    }
                }
            })
            container.addView(Ui.gap(context, 8))
            container.addView(acceptButton)
            val scroll = android.widget.ScrollView(context).apply { addView(container) }
            val dialog = AlertDialog.Builder(context).setTitle("饮食对话助手")
                .setView(scroll).setNegativeButton("关闭", null).create()
            acceptButton.setOnClickListener {
                AlertDialog.Builder(context).setTitle("确认预记入饮食计划？")
                    .setMessage(proposalView.text)
                    .setNegativeButton("返回核对", null).setPositiveButton("确认") { _, _ ->
                        host.api.post("/agent/chats/$chatId/accept", JSONObject()) { _, acceptError ->
                            if (acceptError != null) host.message(acceptError)
                            else { dialog.dismiss(); host.message("方案已预记入饮食页"); host.navigate(0) }
                        }
                    }.show()
            }
            dialog.show()
        }
    }
}
