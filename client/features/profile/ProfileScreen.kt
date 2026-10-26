package com.example.appdemo.features.profile

import android.app.AlertDialog
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.networking.ApiClient
import org.json.JSONArray
import org.json.JSONObject

object ProfileScreen {
    private val activityKeys = listOf("sedentary", "light", "moderate", "high", "very_high")
    private val goalKeys = listOf("fat_loss", "maintenance", "muscle_gain", "recovery")
    private val allergenNames = mapOf("peanut" to "花生", "egg" to "鸡蛋", "milk" to "牛奶",
        "soy" to "大豆", "fish" to "鱼类", "shellfish" to "虾蟹", "tree_nut" to "坚果",
        "wheat" to "小麦", "sesame" to "芝麻")

    fun render(host: ScreenHost): View {
        val context = host.screenContext
        val page = Ui.column(context)
        page.addView(Ui.text(context, "METABOLIC PROFILE", 11f, Palette.deepGreen, true))
        page.addView(Ui.text(context, "个人设置与健康目标", 25f, Palette.ink, true))
        page.addView(Ui.gap(context, 16))
        val identity = Ui.card(context).apply {
            background = Ui.gradient(context, Palette.white, Palette.lightGreen, 16)
        }
        val identityRow = Ui.row(context)
        val identityAvatar = Ui.pill(context, "我", Palette.deepGreen, Palette.lightGreen).apply {
            textSize = 23f
        }
        identityRow.addView(identityAvatar, LinearLayout.LayoutParams(Ui.dp(context, 52), Ui.dp(context, 52)))
        val identityCopy = Ui.column(context).apply {
            setPadding(Ui.dp(context, 12), 0, 0, 0)
        }
        val identityName = Ui.text(context, "我的健康档案", 17f, Palette.ink, true)
        identityCopy.addView(identityName)
        identityCopy.addView(Ui.text(context, "记录身体变化，调整今日计划", 12f, Palette.muted))
        identityRow.addView(identityCopy)
        identity.addView(identityRow)
        page.addView(identity)
        val status = Ui.card(context)
        status.background = android.graphics.drawable.GradientDrawable(
            android.graphics.drawable.GradientDrawable.Orientation.TL_BR,
            intArrayOf(0xff1e3148.toInt(), 0xff17635b.toInt())).apply {
            cornerRadius = Ui.dp(context, 16).toFloat()
        }
        val statusHeader = Ui.row(context)
        statusHeader.addView(Ui.text(context, "✦ NutriPulse 智能代谢测算", 15f, Palette.white, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        statusHeader.addView(Ui.pill(context, "实时自适应", Palette.lightGreen,
            0xff2d625d.toInt()))
        status.addView(statusHeader)
        status.addView(Ui.gap(context, 12))
        val targetText = Ui.text(context, "完善档案后计算每日营养目标", 22f, 0xff8ef4c2.toInt(), true)
        status.addView(targetText)
        status.addView(Ui.gap(context, 14))
        val targetMetricsRow = Ui.row(context)
        val bmrMetric = Ui.text(context, "静息 BMR\n--", 13f, Palette.white, true)
        val tdeeMetric = Ui.text(context, "总消耗 TDEE\n--", 13f, Palette.white, true)
        val waterMetric = Ui.text(context, "饮水建议\n--", 13f, Palette.white, true)
        listOf(bmrMetric, tdeeMetric, waterMetric).forEach { metric ->
            metric.background = Ui.shape(context, 0xff30475a.toInt(), 10)
            metric.setPadding(Ui.dp(context, 9), Ui.dp(context, 10), Ui.dp(context, 5), Ui.dp(context, 10))
            targetMetricsRow.addView(metric, LinearLayout.LayoutParams(0, -2, 1f).apply {
                marginEnd = Ui.dp(context, 5)
            })
        }
        status.addView(targetMetricsRow)
        status.addView(Ui.text(context, "三大营养素目标", 12f, Palette.white, true).apply {
            setPadding(0, Ui.dp(context, 13), 0, Ui.dp(context, 7))
        })
        val macroBar = Ui.row(context)
        macroBar.visibility = View.GONE
        val macroSegments = listOf(Palette.carb, Palette.green, 0xffff7187.toInt()).map { color ->
            View(context).apply {
                background = Ui.shape(context, color, 999)
                macroBar.addView(this, LinearLayout.LayoutParams(0, Ui.dp(context, 7), 1f))
            }
        }
        status.addView(macroBar)
        val targetMacros = Ui.text(context, "碳水 --   蛋白质 --   脂肪 --", 12f, Palette.white)
        status.addView(Ui.gap(context, 8))
        status.addView(targetMacros)
        val targetProvenance = Ui.text(context, "", 11f, Palette.white)
        status.addView(Ui.gap(context, 7))
        status.addView(targetProvenance)
        val basics = Ui.card(context)
        basics.addView(Ui.text(context, "基础生理数据", 18f, Palette.ink, true))
        basics.addView(Ui.text(context, "填写真实数据后，系统会重新计算代谢目标", 12f, Palette.muted))
        basics.addView(Ui.gap(context, 12))
        val name = Ui.field(context, "昵称")
        val birth = Ui.field(context, "YYYY-MM-DD")
        val sex = Ui.picker(context, listOf("男（公式）", "女（公式）"))
        val height = Ui.field(context, "身高 cm", numeric = true)
        val weight = Ui.field(context, "当前体重 kg", numeric = true)
        val bodyFat = Ui.field(context, "体脂率 %（可选）", numeric = true)
        val activity = Ui.picker(context, listOf("久坐", "轻度活动", "中度活动", "高强度活动", "极高活动"))
        listOf("昵称" to name, "生理性别（用于代谢公式）" to sex).forEach { (label, field) ->
            basics.addView(Ui.text(context, label, 12f, Palette.muted, true))
            basics.addView(Ui.gap(context, 4))
            basics.addView(field)
            basics.addView(Ui.gap(context, 4))
        }
        fun addPairedFields(leftLabel: String, left: View, rightLabel: String, right: View) {
            val row = Ui.row(context)
            listOf(leftLabel to left, rightLabel to right).forEach { (label, field) ->
                val cell = Ui.column(context)
                cell.addView(Ui.text(context, label, 12f, Palette.muted, true))
                cell.addView(Ui.gap(context, 4))
                cell.addView(field)
                row.addView(cell, LinearLayout.LayoutParams(0, -2, 1f).apply {
                    marginEnd = Ui.dp(context, 6)
                })
            }
            basics.addView(row)
            basics.addView(Ui.gap(context, 4))
        }
        addPairedFields("出生日期", birth, "身高 cm", height)
        addPairedFields("当前体重 kg", weight, "体脂率 %（可选）", bodyFat)
        basics.addView(Ui.text(context, "日常活动量", 12f, Palette.muted, true))
        basics.addView(activity)
        basics.addView(Ui.button(context, "保存身体数据并计算目标", Palette.green) {
            val h = height.text.toString().toDoubleOrNull()
            val w = weight.text.toString().toDoubleOrNull()
            if (birth.text.isBlank() || h == null || w == null) {
                host.message("请填写出生日期、身高和当前体重")
                return@button
            }
            val payload = JSONObject().put("display_name", name.text.toString().ifBlank { "我" })
                .put("birth_date", birth.text.toString()).put("formula_sex", if (sex.selectedItemPosition == 0) "male" else "female")
                .put("height_cm", h).put("activity_level", activityKeys[activity.selectedItemPosition])
            host.api.put("/profile", payload) { _, error ->
                if (error != null) host.message(error)
                else host.api.post("/measurements", JSONObject().put("weight_kg", w).apply {
                    bodyFat.text.toString().toDoubleOrNull()?.let { put("body_fat_pct", it) }
                }) { _, measurementError ->
                    if (measurementError != null) host.message(measurementError)
                    else { host.message("身体数据已保存"); host.refresh() }
                }
            }
        })
        page.addView(basics)

        val goals = Ui.card(context)
        goals.addView(Ui.text(context, "阶段目标", 18f, Palette.ink, true))
        goals.addView(Ui.text(context, "选择当前阶段，先预览再确认启用", 12f, Palette.muted))
        goals.addView(Ui.gap(context, 8))
        var selectedGoalIndex = 0
        val goalCards = mutableListOf<TextView>()
        fun selectGoal(index: Int) {
            selectedGoalIndex = index
            goalCards.forEachIndexed { cardIndex, card ->
                card.background = Ui.shape(context,
                    if (cardIndex == index) Palette.lightGreen else Palette.background, 12)
                card.setTextColor(if (cardIndex == index) Palette.deepGreen else Palette.ink)
            }
        }
        listOf(
            "减脂 · 适度热量赤字" to "控制摄入，保持蛋白质充足",
            "维持健康 · 能量动态平衡" to "保持活力与稳定习惯",
            "增肌 · 适度热量盈余" to "结合力量训练逐步进阶",
            "恢复回归 · 稳步建立节奏" to "按身体状态循序恢复"
        ).forEachIndexed { index, (label, note) ->
            val card = Ui.text(context, "$label\n$note", 14f, Palette.ink, true).apply {
                setPadding(Ui.dp(context, 14), Ui.dp(context, 12), Ui.dp(context, 14), Ui.dp(context, 12))
                setOnClickListener { selectGoal(index) }
            }
            goalCards.add(card)
            goals.addView(card, LinearLayout.LayoutParams(-1, -2).apply {
                bottomMargin = Ui.dp(context, 7)
            })
        }
        selectGoal(0)
        goals.addView(Ui.button(context, "切换目标", Palette.green) {
            val selected = goalKeys[selectedGoalIndex]
            host.api.post("/goals/preview", JSONObject().put("goal_type", selected)) { preview, previewError ->
                if (previewError != null || preview == null) {
                    host.message(previewError ?: "无法试算新目标")
                    return@post
                }
                val proposed = preview.optJSONObject("proposed_target")
                val current = preview.optJSONObject("current_target")
                val inputs = preview.optJSONObject("inputs")
                val message = if (proposed != null) {
                    val currentLine = if (current == null) "当前尚无营养目标"
                        else "当前目标 ${current.optDouble("kcal").toInt()} kcal/天"
                    "$currentLine\n新目标 ${proposed.optDouble("target_kcal").toInt()} kcal/天" +
                        "\nBMR ${proposed.optDouble("bmr_kcal").toInt()} · TDEE ${proposed.optDouble("tdee_kcal").toInt()} kcal" +
                        "\n碳水 ${proposed.optDouble("carb_g").toInt()}g · 蛋白质 ${proposed.optDouble("protein_g").toInt()}g · 脂肪 ${proposed.optDouble("fat_g").toInt()}g" +
                        "\n输入：${inputs?.optInt("age")} 岁、${inputs?.optDouble("height_cm")} cm、${inputs?.optDouble("weight_kg")} kg、活动等级 ${inputs?.optString("activity_level")}" +
                        "\n算法 ${proposed.optString("algorithm_version")} · ${preview.optString("effective_from")} 起生效。以上均为估算，历史记录保留。"
                } else {
                    val missing = preview.optJSONArray("missing_fields") ?: JSONArray()
                    val missingText = (0 until missing.length()).joinToString("、") { missing.optString(it) }
                    if (current == null) "尚缺 $missingText。确认后只保存阶段目标，补齐资料前不会生成热量预算。"
                    else "尚缺 $missingText。为避免沿用不适用的旧预算，请先补齐资料，再切换目标。"
                }
                val dialog = AlertDialog.Builder(context).setTitle("确认切换为${listOf("减脂", "维持健康", "增肌", "恢复回归")[selectedGoalIndex]}")
                    .setMessage(message)
                    .setNegativeButton(if (preview.optBoolean("can_activate")) "取消" else "知道了", null)
                if (preview.optBoolean("can_activate")) dialog.setPositiveButton("确认启用") { _, _ ->
                        val payload = JSONObject().put("goal_type", selected)
                            .put("preview_fingerprint", preview.optString("input_fingerprint"))
                        host.api.post("/goals", payload) { _, error ->
                            if (error != null) host.message(error) else host.refresh()
                        }
                    }
                dialog.show()
            }
        })
        page.addView(goals)
        page.addView(status)

        val preferences = Ui.card(context)
        preferences.addView(Ui.text(context, "饮食限制与用餐偏好", 18f, Palette.ink, true))
        preferences.addView(Ui.text(context, "逗号分隔：花生、鸡蛋、牛奶、大豆、鱼类、虾蟹、坚果、小麦、芝麻；也支持英文代码。未识别的过敏原会拒绝保存。实际配料及交叉接触仍须自行核对。",
            12f, Palette.muted))
        val allergyField = Ui.field(context, "过敏原，例如 花生,牛奶")
        val restrictionField = Ui.field(context, "忌口食材")
        val likesField = Ui.field(context, "喜欢的食材，例如 chicken, rice")
        val dislikesField = Ui.field(context, "不喜欢的食材")
        val costField = Ui.field(context, "单餐最高预算 ¥（可选，仅按估算价筛选）", numeric = true)
        val cookField = Ui.field(context, "最长备餐+烹饪分钟（可选，仅自煮）", numeric = true)
        val flavorField = Ui.field(context, "偏好口味：清淡,咸鲜,甜口,香辣")
        val scenarioField = Ui.picker(context, listOf("自己下厨", "外卖", "堂食", "便利店"))
        preferences.addView(allergyField)
        preferences.addView(restrictionField)
        preferences.addView(likesField)
        preferences.addView(dislikesField)
        preferences.addView(costField)
        preferences.addView(cookField)
        preferences.addView(flavorField)
        preferences.addView(Ui.text(context, "默认用餐场景", 12f, Palette.muted))
        preferences.addView(scenarioField)
        preferences.addView(Ui.button(context, "保存饮食偏好", Palette.ice) {
            val costText = costField.text.toString().trim()
            val cookText = cookField.text.toString().trim()
            val cost = costText.toDoubleOrNull()
            val minutes = cookText.toIntOrNull()
            if ((costText.isNotEmpty() && (cost == null || cost < 1 || cost > 1000)) ||
                (cookText.isNotEmpty() && (minutes == null || minutes < 5 || minutes > 240))) {
                host.message("单餐预算需为 1-1000 元，烹饪时长需为 5-240 分钟")
                return@button
            }
            val flavors = flavorField.text.toString().split(',', '，').map { it.trim() }
                .filter { it.isNotEmpty() }.distinct()
            if (flavors.size > 8 || flavors.any { it !in listOf("清淡", "咸鲜", "甜口", "香辣") }) {
                host.message("口味仅支持：清淡、咸鲜、甜口、香辣")
                return@button
            }
            fun split(value: String): JSONArray = JSONArray().apply {
                value.split(',', '，').map { it.trim().lowercase() }.filter { it.isNotEmpty() }.forEach { put(it) }
            }
            val weights = JSONArray()
            for (value in listOf(likesField.text.toString(), dislikesField.text.toString()).withIndex()) {
                val category = if (value.index == 0) "like_food" else "dislike_food"
                value.value.split(',', '，').map { it.trim().lowercase() }.filter { it.isNotEmpty() }
                    .forEach { weights.put(JSONObject().put("category", category).put("value_code", it)
                        .put("weight", if (value.index == 0) 1 else -1)) }
            }
            val dining = JSONObject().put("flavors", JSONArray(flavors))
                .put("preferred_scenario", listOf("self_cook", "takeout", "dine_in", "convenience")[scenarioField.selectedItemPosition])
            if (cost != null) dining.put("max_cost_cny", cost)
            if (minutes != null) dining.put("max_cook_minutes", minutes)
            val data = JSONObject().put("allergies", split(allergyField.text.toString()))
                .put("restrictions", split(restrictionField.text.toString())).put("preferences", weights)
                .put("dining", dining)
            host.api.put("/preferences", data) { _, error ->
                if (error != null) host.message(error) else host.message("饮食限制与用餐偏好已保存")
            }
        })
        page.addView(preferences)

        val trainingCard = Ui.card(context)
        trainingCard.addView(Ui.text(context, "训练偏好与限制", 18f, Palette.ink, true))
        val trainingLevel = Ui.picker(context, listOf("初学", "进阶", "高阶", "恢复期"))
        val daysPerWeek = Ui.field(context, "每周训练天数（1-7）", numeric = true)
        val sessionMinutes = Ui.field(context, "每次训练分钟数", numeric = true)
        val activeKcalGoal = Ui.field(context, "每日活动热量目标（50-2000 kcal）", numeric = true)
        val equipment = Ui.field(context, "可用器械，逗号分隔")
        val limitations = Ui.field(context, "动作限制，逗号分隔")
        listOf(trainingLevel, daysPerWeek, sessionMinutes, activeKcalGoal,
            equipment, limitations).forEach(trainingCard::addView)
        trainingCard.addView(Ui.button(context, "保存训练偏好", Palette.fitness) {
            fun words(value: String) = JSONArray().apply {
                value.split(',', '，').map { it.trim() }.filter { it.isNotEmpty() }.forEach { put(it) }
            }
            val body = JSONObject().put("level", listOf("beginner", "intermediate", "advanced", "recovery")[trainingLevel.selectedItemPosition])
                .put("days_per_week", daysPerWeek.text.toString().toIntOrNull() ?: 0)
                .put("session_minutes", sessionMinutes.text.toString().toIntOrNull() ?: 0)
                .put("active_kcal_goal", activeKcalGoal.text.toString().toIntOrNull() ?: 0)
                .put("equipment", words(equipment.text.toString()))
                .put("limitations", words(limitations.text.toString()))
            host.api.put("/training-profile", body) { _, error ->
                if (error != null) host.message(error) else host.message("训练偏好已保存")
            }
        })
        page.addView(trainingCard)

        val devices = Ui.card(context)
        devices.addView(Ui.text(context, "设备授权与同步", 18f, Palette.ink, true))
        devices.addView(Ui.text(context,
            "撤销后停止导入。选择保留历史时，过去的设备记录仍参与统计；选择删除历史将重算过往数据，并可能改变身体测量、营养目标和诊断。",
            12f, Palette.muted))
        val deviceList = Ui.column(context)
        devices.addView(deviceList)
        host.api.get("/devices") { result, error ->
            if (error != null) {
                deviceList.addView(Ui.text(context, "设备状态读取失败：$error", 12f, Palette.muted))
                return@get
            }
            val items = result?.optJSONArray("items") ?: JSONArray()
            if (items.length() == 0) {
                deviceList.addView(Ui.text(context, "尚无设备连接；可在健身页连接 Health Connect。", 12f, Palette.muted))
            }
            for (index in 0 until items.length()) {
                val device = items.optJSONObject(index) ?: continue
                val id = device.optString("id")
                val provider = device.optString("provider")
                val label = when (provider) {
                    "health_connect" -> "Health Connect"
                    "apple_health" -> "Apple Health（桥接）"
                    else -> "手动设备导入"
                }
                val active = device.optString("status") == "ACTIVE"
                val sampleCount = device.optInt("sample_count")
                deviceList.addView(Ui.gap(context, 10))
                deviceList.addView(Ui.text(context,
                    "$label · ${if (active) "已连接" else "已停用"} · $sampleCount 条样本", 14f, Palette.ink, true))
                val synced = device.optString("last_synced_at")
                if (synced.isNotBlank() && synced != "null")
                    deviceList.addView(Ui.text(context, "最近同步：$synced", 12f, Palette.muted))
                if (active) {
                    deviceList.addView(Ui.button(context, "管理连接与历史", Palette.ice) {
                        AlertDialog.Builder(context).setTitle("$label：选择处理方式")
                            .setItems(arrayOf("停止同步，保留原始历史", "停止同步，并永久删除该设备历史")) { _, choice ->
                                val deleteHistory = choice == 1
                                val impact = if (deleteHistory)
                                    "将永久删除该连接的 $sampleCount 条样本、关联身体测量和依赖它们的目标，并清除已有 AI 诊断。其他设备和手工记录不删除。无法撤销。"
                                else "将撤销连接并停止后续同步。服务器保留原始样本，过往活动热量、步数和冲突处置继续参与统计。"
                                AlertDialog.Builder(context).setTitle("确认处理 $label")
                                    .setMessage(impact + if (provider == "health_connect")
                                        "\n同时将尝试撤销本应用的 Health Connect 系统权限。" else "")
                                    .setNegativeButton("取消", null)
                                    .setPositiveButton(if (deleteHistory) "永久删除并撤销" else "确认撤销") { _, _ ->
                                        host.revokeDeviceConnection(id, provider, deleteHistory)
                                    }.show()
                            }.show()
                    })
                } else if (sampleCount > 0) {
                    deviceList.addView(Ui.button(context, "删除已停用设备的保留历史", Palette.fitness) {
                        AlertDialog.Builder(context).setTitle("永久删除 $label 历史？")
                            .setMessage("将永久删除该连接的 $sampleCount 条样本、关联身体测量与目标，并清除已有 AI 诊断。此操作无法撤销。")
                            .setNegativeButton("取消", null)
                            .setPositiveButton("永久删除") { _, _ ->
                                host.revokeDeviceConnection(id, provider, true)
                            }.show()
                    })
                }
            }
        }
        page.addView(devices)

        val privacy = Ui.card(context)
        privacy.addView(Ui.text(context, "个人数据与隐私", 18f, Palette.ink, true))
        privacy.addView(Ui.text(context, "可分类导出 JSON；清空会同时移除依赖这些记录的推荐、诊断或设备数据，且无法撤销。",
            12f, Palette.muted))
        val dataCategories = listOf("all", "diet", "fitness", "agent", "profile")
        val dataCategoryPicker = Ui.picker(context, listOf("全部个人数据", "饮食记录", "运动与设备", "AI 对话与推荐", "身体档案"))
        privacy.addView(dataCategoryPicker)
        privacy.addView(Ui.button(context, "导出所选类别 JSON", Palette.ice) {
            val category = dataCategories[dataCategoryPicker.selectedItemPosition]
            AlertDialog.Builder(context).setTitle("导出敏感健康数据")
                .setMessage("导出文件可能包含身体测量、饮食及运动详情。请保存到可信位置，不要公开分享。")
                .setNegativeButton("取消", null).setPositiveButton("选择保存位置") { _, _ ->
                    host.exportPersonalData(category)
                }.show()
        })
        privacy.addView(Ui.gap(context, 6))
        privacy.addView(Ui.button(context, "清空所选类别数据", Palette.fitness) {
            val category = dataCategories[dataCategoryPicker.selectedItemPosition]
            host.api.get("/privacy/delete-preview?category=$category") { preview, error ->
                if (error != null || preview == null) {
                    host.message(error ?: "无法读取清空影响")
                    return@get
                }
                val phrase = preview.optString("confirmation_phrase")
                val confirmation = Ui.field(context, "输入 $phrase 以确认")
                val body = Ui.column(context).apply {
                    setPadding(Ui.dp(context, 18), 0, Ui.dp(context, 18), 0)
                    addView(Ui.text(context, preview.optString("impact"), 14f, Palette.ink))
                    addView(Ui.gap(context, 8))
                    addView(Ui.text(context, "涉及约 ${preview.optInt("record_count")} 条记录；服务器数据清空后不可恢复。", 13f, Palette.fitness))
                    addView(confirmation)
                }
                AlertDialog.Builder(context).setTitle("确认永久清空？")
                    .setView(body).setNegativeButton("取消", null)
                    .setPositiveButton("永久清空") { _, _ ->
                        val typed = confirmation.text.toString().trim()
                        if (typed != phrase) {
                            host.message("确认短语不匹配，未删除任何数据")
                            return@setPositiveButton
                        }
                        if (!host.beginPersonalDataDeletion(category)) return@setPositiveButton
                        host.api.post("/privacy/delete", JSONObject().put("category", category)
                            .put("confirmation_phrase", typed)) { response, deleteError ->
                            if (deleteError != null) {
                                host.cancelPersonalDataDeletion(category)
                                host.message(deleteError)
                            }
                            else {
                                host.personalDataDeleted(category)
                                host.message(if (response?.optString("target_recalculated") == "false")
                                    "数据已清空，但营养目标未重算；请在个人页重新保存身体数据"
                                    else "所选类别已清空；如有旧备份或导出文件，请另行处理")
                            }
                        }
                    }.show()
            }
        })
        page.addView(privacy)

        val diagnostics = Ui.card(context)
        diagnostics.addView(Ui.text(context, "连接诊断", 18f, Palette.ink, true))
        diagnostics.addView(Ui.text(context,
            "仅导出本次电脑服务运行中的最近 500 条请求状态、耗时与错误类型；不含请求正文、网址参数或访问令牌。重启服务后旧记录不保留。",
            12f, Palette.muted))
        diagnostics.addView(Ui.button(context, "导出脱敏诊断日志 JSON", Palette.ice) {
            AlertDialog.Builder(context).setTitle("导出连接诊断")
                .setMessage("日志不含健康正文，但仍包含请求时间与功能使用情况。分享前请检查内容。")
                .setNegativeButton("取消", null).setPositiveButton("选择保存位置") { _, _ ->
                    host.exportDiagnosticLogs()
                }.show()
        })
        page.addView(diagnostics)

        val connection = Ui.card(context)
        connection.addView(Ui.text(context, "本地电脑连接", 18f, Palette.ink, true))
        connection.addView(Ui.text(context, "模拟器默认 http://10.0.2.2:8787；真机填写电脑局域网地址，再输入电脑服务启动时显示的一次性配对码。仅在可信私有网络使用明文 HTTP。",
            12f, Palette.muted))
        val url = Ui.field(context, "服务地址", host.api.baseUrl)
        val pairingCode = Ui.field(context, "一次性配对码")
        connection.addView(url)
        connection.addView(pairingCode)
        connection.addView(Ui.button(context, "配对这台手机", Palette.ice) {
            host.api.pair(url.text.toString(), pairingCode.text.toString()) { _, error ->
                if (error != null) host.message(error)
                else {
                    pairingCode.setText("")
                    host.message("配对成功；令牌仅在当前电脑服务运行期间有效，最长 24 小时")
                    host.refresh()
                }
            }
        })
        connection.addView(Ui.text(context, "兼容旧方式：可手工填写服务端访问令牌；已保存的凭据不会在此回显。",
            12f, Palette.muted))
        val token = Ui.field(context, "手动访问令牌（可留空）")
        token.inputType = android.text.InputType.TYPE_CLASS_TEXT or
            android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        connection.addView(token)
        connection.addView(Ui.button(context, "保存地址或手动令牌", Palette.ice) {
            if (!ApiClient.isSafeServerUrl(url.text.toString().trim())) {
                host.message("服务地址必须为 HTTPS 或本机/局域网 HTTP")
                return@button
            }
            val newUrl = url.text.toString().trim().trimEnd('/')
            val oldUrl = host.api.baseUrl
            host.api.baseUrl = newUrl
            if (token.text.isNotBlank()) host.api.token = token.text.toString().trim()
            else if (newUrl != oldUrl) host.api.token = ""
            host.message(if (newUrl != oldUrl && token.text.isBlank())
                "地址已保存；旧地址的访问凭据已清除，请重新配对" else "连接设置已保存")
            host.refresh()
        })
        connection.addView(Ui.button(context, "清除本机访问凭据", Palette.muted) {
            host.api.token = ""
            host.message("本机访问凭据已清除")
        })
        page.addView(connection)

        host.api.get("/profile") { data, error ->
            if (error != null) {
                targetText.text = "连接服务后显示营养目标"
                targetProvenance.text = error
                return@get
            }
            val p = data?.optJSONObject("profile")
            val measurement = data?.optJSONObject("measurement")
            val target = data?.optJSONObject("target")
            val activeGoal = data?.optJSONObject("goal")
            name.setText(p?.optString("display_name") ?: "")
            identityName.text = p?.optString("display_name")?.takeIf { it.isNotBlank() } ?: "我的健康档案"
            birth.setText(if (p?.isNull("birth_date") == false) p.optString("birth_date") else "")
            sex.setSelection(if (p?.optString("formula_sex") == "female") 1 else 0)
            height.setText(if (p?.isNull("height_cm") == false) p.optString("height_cm") else "")
            weight.setText(if (measurement != null) measurement.optString("weight_kg") else "")
            bodyFat.setText(if (measurement?.isNull("body_fat_pct") == false)
                measurement.optString("body_fat_pct") else "")
            activity.setSelection(activityKeys.indexOf(p?.optString("activity_level")).coerceAtLeast(0))
            selectGoal(goalKeys.indexOf(activeGoal?.optString("goal_type")).coerceAtLeast(0))
            val allergies = data?.optJSONArray("allergies") ?: JSONArray()
            val restrictions = data?.optJSONArray("restrictions") ?: JSONArray()
            allergyField.setText((0 until allergies.length()).joinToString(",") {
                val code = allergies.optString(it)
                allergenNames[code] ?: code
            })
            restrictionField.setText((0 until restrictions.length()).joinToString(",") { restrictions.optString(it) })
            val foodPreferences = data?.optJSONArray("preferences") ?: JSONArray()
            fun values(category: String) = (0 until foodPreferences.length()).mapNotNull {
                foodPreferences.optJSONObject(it)?.takeIf { it.optString("category") == category }?.optString("value_code")
            }.joinToString(",")
            likesField.setText(values("like_food"))
            dislikesField.setText(values("dislike_food"))
            val dining = data?.optJSONObject("dining")
            costField.setText(if (dining?.isNull("max_cost_cny") == false) dining.optString("max_cost_cny") else "")
            cookField.setText(if (dining?.isNull("max_cook_minutes") == false) dining.optString("max_cook_minutes") else "")
            val flavors = dining?.optJSONArray("flavors") ?: JSONArray()
            flavorField.setText((0 until flavors.length()).joinToString(",") { flavors.optString(it) })
            scenarioField.setSelection(listOf("self_cook", "takeout", "dine_in", "convenience")
                .indexOf(dining?.optString("preferred_scenario")).coerceAtLeast(0))
            val training = data?.optJSONObject("training")
            if (training != null) {
                trainingLevel.setSelection(listOf("beginner", "intermediate", "advanced", "recovery")
                    .indexOf(training.optString("level")).coerceAtLeast(0))
                daysPerWeek.setText(training.optString("days_per_week"))
                sessionMinutes.setText(training.optString("session_minutes"))
                activeKcalGoal.setText(training.optString("active_kcal_goal", "300"))
                val devices = training.optJSONArray("equipment") ?: JSONArray()
                val limits = training.optJSONArray("limitations") ?: JSONArray()
                equipment.setText((0 until devices.length()).joinToString(",") { devices.optString(it) })
                limitations.setText((0 until limits.length()).joinToString(",") { limits.optString(it) })
            }
            targetText.text = if (target == null) "请完善身体数据与阶段目标"
                else "${target.optDouble("kcal").toInt()} kcal / 天"
            if (target != null) {
                macroBar.visibility = View.VISIBLE
                bmrMetric.text = "静息 BMR\n${target.optDouble("bmr_kcal").toInt()} kcal"
                tdeeMetric.text = "总消耗 TDEE\n${target.optDouble("tdee_kcal").toInt()} kcal"
                waterMetric.text = "饮水建议\n${target.optInt("water_ml")} ml"
                targetMacros.text = "碳水 ${target.optDouble("carb_g").toInt()}g   蛋白质 ${target.optDouble("protein_g").toInt()}g   脂肪 ${target.optDouble("fat_g").toInt()}g"
                val macroEnergy = listOf(target.optDouble("carb_g") * 4,
                    target.optDouble("protein_g") * 4, target.optDouble("fat_g") * 9)
                macroSegments.forEachIndexed { index, segment ->
                    segment.layoutParams = (segment.layoutParams as LinearLayout.LayoutParams).apply {
                        this.weight = macroEnergy[index].toFloat().coerceAtLeast(1f)
                    }
                }
                val inputs = target.optJSONObject("inputs")
                val inputText = if (inputs != null && inputs.length() > 0)
                    " · 输入 ${inputs.optInt("age")}岁/${inputs.optDouble("height_cm")}cm/${inputs.optDouble("weight_kg")}kg/${inputs.optString("activity_level")}"
                    else " · 历史目标未保存输入快照"
                targetProvenance.text = "Mifflin-St Jeor · ${target.optString("algorithm_version")}$inputText\n生成于 ${target.optString("created_at")} UTC"
            }
        }
        return page
    }
}
