package com.example.appdemo.features.diet

import android.app.DatePickerDialog
import android.app.AlertDialog
import android.content.Context
import android.view.View
import android.view.Gravity
import android.widget.LinearLayout
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.RingGauge
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.database.PhotoDraftStore
import com.example.appdemo.core.database.ArticleCache
import com.example.appdemo.core.time.UserCalendar
import org.json.JSONArray
import org.json.JSONObject
import android.util.Base64
import java.time.LocalDate
import java.time.ZoneId

object DietScreen {
    private val mealKeys = listOf("breakfast", "lunch", "dinner", "snack")
    private val mealNames = listOf("早餐", "午餐", "晚餐", "加餐与饮品")
    private fun profileToday(): LocalDate = UserCalendar.today()
    private var selectedDate: String = profileToday().toString()
    private var lastDefaultToday: String = selectedDate
    private data class ScanFields(val panel: LinearLayout, val name: android.widget.EditText,
                                  val grams: android.widget.EditText, val kcal: android.widget.EditText,
                                  val original: JSONObject?, var kcalManuallyEdited: Boolean = false)

    fun render(host: ScreenHost): View {
        val currentToday = profileToday().toString()
        if (selectedDate == lastDefaultToday) selectedDate = currentToday
        lastDefaultToday = currentToday
        val context = host.screenContext
        val page = Ui.column(context)
        val greetingWord = when (java.time.LocalTime.now(UserCalendar.zone).hour) {
            in 5..10 -> "早安"; in 11..17 -> "午安"; else -> "晚上好"
        }
        val greeting = Ui.row(context)
        val avatar = Ui.text(context, "你", 17f, Palette.deepGreen, true).apply {
            gravity = Gravity.CENTER
            background = Ui.shape(context, Palette.lightGreen, 999)
        }
        greeting.addView(avatar, LinearLayout.LayoutParams(Ui.dp(context, 44), Ui.dp(context, 44)).apply {
            marginEnd = Ui.dp(context, 9)
        })
        val greetingCopy = Ui.column(context)
        val greetingName = Ui.text(context, "$greetingWord，朋友 👋", 17f, Palette.ink, true).apply {
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        greetingCopy.addView(greetingName)
        greetingCopy.addView(Ui.badge(context, "控摄入，看结构", Palette.deepGreen),
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT))
        greeting.addView(greetingCopy, LinearLayout.LayoutParams(0,
            LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val chosenDay = LocalDate.parse(selectedDate)
        val date = Ui.pill(context, "${chosenDay.monthValue}月${chosenDay.dayOfMonth}日⌄",
            Palette.deepGreen, Palette.white) {
            val current = LocalDate.parse(selectedDate)
            DatePickerDialog(context, { _, y, m, d ->
                selectedDate = LocalDate.of(y, m + 1, d).toString()
                host.refresh()
            }, current.year, current.monthValue - 1, current.dayOfMonth).apply {
                datePicker.maxDate = profileToday().plusDays(90).atTime(23, 59, 59)
                    .atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            }.show()
        }
        greeting.addView(date)
        page.addView(greeting)
        page.addView(Ui.gap(context, 14))
        val articleSection = Ui.column(context)
        val articleCache = ArticleCache(context)
        val articleServer = host.api.baseUrl
        fun showArticles(items: JSONArray, cachedAt: Long? = null) {
            articleSection.removeAllViews()
            if (items.length() == 0) return
            articleSection.addView(Ui.subtitle(context, "每日健康资讯"))
            val articleList = Ui.column(context)
            articleSection.addView(articleList)
            ArticleCarousel.render(host, articleList, items, cachedAt)
        }
        articleCache.load(articleServer)?.let { showArticles(it.articles, it.updatedAt) }

        val overview = Ui.card(context)
        overview.setPadding(Ui.dp(context, 18), Ui.dp(context, 15),
            Ui.dp(context, 18), Ui.dp(context, 18))
        overview.addView(Ui.text(context, "今日能量预算", 14f, Palette.deepGreen, true))
        val ring = RingGauge(context)
        overview.addView(ring)
        val balance = Ui.text(context, "目标 --  ·  已摄入 --  ·  运动 --", 13f, Palette.muted)
        balance.textAlignment = View.TEXT_ALIGNMENT_CENTER
        overview.addView(balance)
        overview.addView(Ui.gap(context, 12))
        val macroTiles = Ui.row(context)
        macroTiles.background = Ui.shape(context, Palette.softBlue, 14)
        macroTiles.setPadding(Ui.dp(context, 7), Ui.dp(context, 7), Ui.dp(context, 2), Ui.dp(context, 7))
        overview.addView(macroTiles)
        val macroNotice = Ui.text(context, "", 12f, Palette.fitness)
        macroNotice.visibility = View.GONE
        overview.addView(macroNotice)
        renderMacros(context, macroTiles, null, null)
        page.addView(overview)

        val photoDraft = PhotoDraftStore(context)
        if (photoDraft.exists()) {
            val draftCard = Ui.card(context)
            draftCard.addView(Ui.text(context, "待识别照片草稿", 16f, Palette.ink, true))
            draftCard.addView(Ui.text(context, "照片仅加密保存在本机，联网后可重试；不会自动上传。", 12f, Palette.muted))
            val draftActions = Ui.row(context)
            draftActions.addView(Ui.button(context, "重试识别", Palette.green) {
                val draft = photoDraft.load()
                if (draft == null) {
                    photoDraft.clear()
                    host.message("照片草稿无法读取，已清除，请重新拍摄")
                    host.refresh()
                } else submitPhoto(host, draft.first, draft.second, true, draft.third)
            }, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f).apply { marginEnd = Ui.dp(context, 6) })
            draftActions.addView(Ui.button(context, "删除草稿", Palette.fitness) {
                AlertDialog.Builder(context).setTitle("删除本机照片草稿？")
                    .setMessage("删除后无法恢复，且不会影响已经记录的餐食。")
                    .setNegativeButton("取消", null).setPositiveButton("删除") { _, _ ->
                        photoDraft.clear()
                        host.refresh()
                    }.show()
            }, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f))
            draftCard.addView(draftActions)
            page.addView(draftCard)
        }
        val scanBanner = Ui.row(context).apply {
            background = Ui.gradient(context, Palette.deepGreen, Palette.green)
            setPadding(Ui.dp(context, 16), Ui.dp(context, 12),
                Ui.dp(context, 15), Ui.dp(context, 12))
            elevation = Ui.dp(context, 3).toFloat()
            setOnClickListener { openScanner(host) }
            contentDescription = "AI 智能拍照识餐"
        }
        val cameraTile = android.widget.FrameLayout(context).apply {
            background = Ui.shape(context, 0x33ffffff, 12)
            addView(com.example.appdemo.core.design_system.NavigationIconView(context,
                com.example.appdemo.core.design_system.NavigationIconView.Kind.CAMERA, Palette.white),
                android.widget.FrameLayout.LayoutParams(Ui.dp(context, 26), Ui.dp(context, 26), Gravity.CENTER))
        }
        scanBanner.addView(cameraTile, LinearLayout.LayoutParams(Ui.dp(context, 42), Ui.dp(context, 42)).apply {
            marginEnd = Ui.dp(context, 10)
        })
        val bannerCopy = Ui.column(context)
        bannerCopy.addView(Ui.text(context, "AI 智能拍照识餐", 16f, Palette.white, true))
        bannerCopy.addView(Ui.text(context, "对准餐盘，快速估算营养摄入", 12f, Palette.white))
        scanBanner.addView(bannerCopy, LinearLayout.LayoutParams(0,
            LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        scanBanner.addView(Ui.text(context, "›", 28f, Palette.white, true))
        page.addView(scanBanner, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = Ui.dp(context, 9)
        })
        val mealHeading = Ui.row(context)
        mealHeading.addView(Ui.subtitle(context,
            if (selectedDate == currentToday) "今日餐次打卡" else "选定日期餐次"), LinearLayout.LayoutParams(0,
            LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val mealCount = Ui.text(context, "四餐结构化记录", 12f, Palette.deepGreen, true)
        mealHeading.addView(mealCount)
        page.addView(mealHeading)
        val mealList = Ui.column(context)
        page.addView(mealList)
        renderMealCards(host, mealList, JSONArray())
        val waterAndSteps = Ui.row(context).apply { gravity = Gravity.TOP }
        val waterCard = Ui.card(context).apply {
            setPadding(Ui.dp(context, 12), Ui.dp(context, 12), Ui.dp(context, 12), Ui.dp(context, 12))
            minimumHeight = Ui.dp(context, 152)
        }
        waterCard.addView(Ui.text(context, "饮水打卡", 14f, Palette.deepGreen, true))
        val waterText = Ui.text(context, "-- / -- ml", 15f, Palette.ink, true)
        var waterTotal = 0
        waterCard.addView(waterText)
        waterCard.addView(Ui.gap(context, 5))
        val waterProgress = android.widget.ProgressBar(context, null,
            android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progressTintList = android.content.res.ColorStateList.valueOf(Palette.green)
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(Palette.softBlue)
        }
        waterCard.addView(waterProgress, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, Ui.dp(context, 5)))
        waterCard.addView(Ui.gap(context, 10))
        val quickWaterKey = java.util.UUID.randomUUID().toString()
        val waterDay = selectedDate
        var quickWaterPending = false
        lateinit var addWaterButton: android.widget.TextView
        addWaterButton = Ui.pill(context, "+ 250 ml", Palette.white, Palette.deepGreen) {
            if (!quickWaterPending) {
                quickWaterPending = true
                addWaterButton.isEnabled = false
                host.api.post("/water-logs", JSONObject().put("local_date", waterDay)
                    .put("amount_ml", 250), quickWaterKey) { _, error ->
                    quickWaterPending = false
                    if (error != null) {
                        addWaterButton.isEnabled = true
                        host.message("$error；重试会继续使用同一笔饮水记录")
                    } else host.refresh()
                }
            }
        }
        waterCard.addView(addWaterButton)
        waterCard.addView(Ui.gap(context, 6))
        waterCard.addView(Ui.pill(context, "−250 / 自定义", Palette.deepGreen, Palette.softBlue) {
            AlertDialog.Builder(context).setTitle("调整饮水记录")
                .setItems(arrayOf("减少今日累计 250 ml", "添加自定义饮水量")) { _, action ->
                    if (action == 0) {
                        host.api.put("/water-logs/days/$selectedDate",
                            JSONObject().put("total_ml", (waterTotal - 250).coerceAtLeast(0))) { _, error ->
                            if (error != null) host.message(error) else host.refresh()
                        }
                    } else {
                        val amount = Ui.field(context, "本次饮水 ml", numeric = true)
                        val operationKey = java.util.UUID.randomUUID().toString()
                        var submittedAmount: Int? = null
                        val dialog = AlertDialog.Builder(context).setTitle("添加饮水记录").setView(amount)
                            .setNegativeButton("取消", null).setPositiveButton("添加", null).create()
                        dialog.setOnShowListener {
                            val saveButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                            saveButton.setOnClickListener {
                                val ml = amount.text.toString().toIntOrNull()
                                if (ml == null || ml !in 1..5000) {
                                    host.message("请输入 1–5000 ml 的饮水量")
                                    return@setOnClickListener
                                }
                                if (submittedAmount != null && submittedAmount != ml) {
                                    host.message("上次提交结果可能已入账；请先检查饮水记录，再添加新的一笔")
                                    return@setOnClickListener
                                }
                                submittedAmount = ml
                                saveButton.isEnabled = false
                                host.api.post("/water-logs", JSONObject().put("local_date", waterDay)
                                    .put("amount_ml", ml), operationKey) { _, error ->
                                    if (error != null) {
                                        saveButton.isEnabled = true
                                        host.message("$error；可重试同一笔记录")
                                    } else { dialog.dismiss(); host.refresh() }
                                }
                            }
                        }
                        dialog.show()
                    }
                }
                .show()
        })
        waterAndSteps.addView(waterCard, LinearLayout.LayoutParams(0,
            LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = Ui.dp(context, 8) })
        val stepsCard = Ui.card(context).apply {
            setPadding(Ui.dp(context, 12), Ui.dp(context, 12), Ui.dp(context, 12), Ui.dp(context, 12))
            minimumHeight = Ui.dp(context, 152)
        }
        stepsCard.addView(Ui.text(context, "今日步数", 14f, Palette.deepGreen, true))
        val stepsText = Ui.text(context, "-- 步", 17f, Palette.ink, true)
        stepsCard.addView(stepsText)
        val stepsSource = Ui.text(context, "设备数据尚未同步", 11f, Palette.muted)
        stepsCard.addView(Ui.gap(context, 8))
        stepsCard.addView(stepsSource)
        stepsCard.addView(Ui.gap(context, 8))
        stepsCard.addView(Ui.text(context, "在健身页连接运动设备", 11f, Palette.ice))
        waterAndSteps.addView(stepsCard, LinearLayout.LayoutParams(0,
            LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        page.addView(waterAndSteps)
        page.addView(articleSection)

        host.api.get("/articles") { data, error ->
            val items = data?.optJSONArray("items")
            if (error == null && items != null && items.length() > 0) {
                articleCache.save(articleServer, items)
                showArticles(items)
            } else {
                articleCache.load(articleServer)?.let { showArticles(it.articles, it.updatedAt) }
                    ?: articleSection.removeAllViews()
            }
        }
        host.api.get("/nutrition/days/$selectedDate") { data, error ->
            if (error != null) {
                ring.value = "--"
                ring.caption = "服务未连接"
                balance.text = "未读取到当日数据 · 请检查电脑服务与连接设置"
                renderMealCards(host, mealList, JSONArray())
                return@get
            }
            val summary = data?.optJSONObject("summary")
            val energy = summary?.optJSONObject("energy")
            val target = summary?.optJSONObject("target")
            val hasTarget = summary?.optBoolean("has_target") == true
            ring.value = if (hasTarget) "${energy?.optDouble("remaining_kcal", 0.0)?.toInt()}" else "--"
            ring.caption = if (hasTarget) "剩余热量" else "请完善档案"
            ring.fraction = if (hasTarget) ((energy?.optDouble("intake_kcal", 0.0) ?: 0.0) /
                (target?.optDouble("kcal", 1.0) ?: 1.0)).toFloat() else 0f
            balance.text = if (hasTarget)
                "目标 ${target?.optDouble("kcal", 0.0)?.toInt() ?: 0}  ·  已摄入 ${energy?.optDouble("intake_kcal", 0.0)?.toInt() ?: 0}  ·  运动 ${energy?.optDouble("activity_kcal", 0.0)?.toInt() ?: 0}"
                else "目标未设置 · 前往我的完善身体档案"
            val macro = summary?.optJSONObject("macros")
            renderMacros(context, macroTiles, macro, target)
            val incomplete = summary?.optInt("incomplete_macro_items", 0) ?: 0
            macroNotice.visibility = if (incomplete > 0) View.VISIBLE else View.GONE
            macroNotice.text = if (incomplete > 0)
                "$incomplete 项营养数据不完整 · 详见数据页" else ""
            waterTotal = summary?.optInt("water_ml", 0) ?: 0
            val waterGoal = target?.optInt("water_ml", 0) ?: 0
            waterText.text = if (waterGoal > 0) "$waterTotal / $waterGoal ml" else "$waterTotal ml · 目标未设"
            waterProgress.progress = if (waterGoal > 0) (waterTotal * 100 / waterGoal).coerceIn(0, 100) else 0
            val stepCount = summary?.optInt("steps", 0) ?: 0
            val source = when (summary?.optString("steps_source")) {
                "health_connect" -> "Health Connect"
                "manual_device_import" -> "手工导入"
                "apple_health" -> "Apple Health 桥接"
                else -> "暂无来源"
            }
            val syncedRaw = summary?.optString("steps_synced_at")?.takeIf { it.isNotBlank() }
            val synced = if (syncedRaw == null) "未同步" else try {
                java.time.OffsetDateTime.parse(syncedRaw).atZoneSameInstant(UserCalendar.zone)
                    .format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))
            } catch (_: Exception) { syncedRaw }
            stepsText.text = if (stepCount > 0) "${"%,d".format(stepCount)} 步" else "暂无步数记录"
            stepsSource.text = "$source · $synced"
            val recorded = (data?.optJSONArray("meals") ?: JSONArray()).let { list ->
                (0 until list.length()).count { list.optJSONObject(it)?.optString("status") == "CONSUMED" }
            }
            mealCount.text = "已记录 $recorded 餐"
            renderMealCards(host, mealList, data?.optJSONArray("meals") ?: JSONArray())
        }
        host.api.get("/profile") { data, error ->
            if (error == null) {
                val name = data?.optJSONObject("profile")?.optString("display_name")?.takeIf { it.isNotBlank() }
                if (name != null) {
                    greetingName.text = "$greetingWord，$name 👋"
                    avatar.text = name.take(1)
                }
            }
        }
        return page
    }

    fun openScanner(host: ScreenHost) {
        host.choosePhoto { image, mime ->
            submitPhoto(host, image, mime, false, java.util.UUID.randomUUID().toString())
        }
    }

    private fun submitPhoto(host: ScreenHost, image: ByteArray, mime: String,
                            fromDraft: Boolean, operationKey: String) {
        val context = host.screenContext
        host.message("正在识别餐食，请稍候…")
        val body = JSONObject().put("image_base64", Base64.encodeToString(image, Base64.NO_WRAP))
            .put("mime_type", mime)
        host.api.post("/food-scans", body, operationKey) { response, error ->
            val failure = if (response?.optString("status") == "PROCESSING")
                "原识餐任务仍在处理，请稍后重试" else error
            if (failure != null || response == null) {
                if (fromDraft) {
                    host.message("照片草稿保留在本机：${failure ?: "无有效响应"}")
                } else {
                    AlertDialog.Builder(context).setTitle("暂时无法识别照片")
                        .setMessage("${failure ?: "服务没有返回结果"}\n\n可以加密保存在本机，稍后手动重试。")
                        .setPositiveButton("保存本机草稿") { _, _ ->
                            try {
                                PhotoDraftStore(context).save(image, mime, operationKey)
                                host.message("已加密保存，请在饮食页重试识别")
                                host.refresh()
                            } catch (_: Exception) { host.message("照片草稿保存失败，请手工记餐") }
                        }
                        .setNeutralButton("手工记餐") { _, _ -> showMealDialog(host, mealKeys[currentMealIndex()]) }
                        .setNegativeButton("不保存", null).show()
                }
            } else if (response.optString("status") == "CONFIRMED") {
                if (fromDraft) PhotoDraftStore(context).clear()
                host.message("这张照片对应的餐食已经记录，无需重复确认")
                host.refresh()
            } else showScanReview(host, response, image, fromDraft)
        }
    }

    private fun currentMealIndex(): Int = when (java.time.LocalTime.now(UserCalendar.zone).hour) {
        in 5..10 -> 0; in 11..15 -> 1; in 16..21 -> 2; else -> 3
    }

    private fun renderMacros(context: Context, parent: LinearLayout, macro: JSONObject?, target: JSONObject?) {
        parent.removeAllViews()
        fun grams(value: Double): String = String.format(java.util.Locale.getDefault(), "%.1f", value)
        listOf(Triple("碳水", "carb_g", Palette.carb), Triple("蛋白质", "protein_g", Palette.protein),
            Triple("脂肪", "fat_g", Palette.fat)).forEach { (name, key, color) ->
            val used = macro?.optDouble(key, 0.0) ?: 0.0
            val goal = target?.optDouble(key, 0.0) ?: 0.0
            val tile = Ui.column(context).apply {
                background = Ui.shape(context, Palette.white, 12)
                setPadding(Ui.dp(context, 8), Ui.dp(context, 8), Ui.dp(context, 8), Ui.dp(context, 7))
            }
            val header = Ui.row(context)
            header.addView(Ui.text(context, name, 12f, color, true),
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            header.addView(Ui.text(context, if (goal > 0) "${(used / goal * 100).toInt()}%" else "--",
                11f, Palette.muted))
            tile.addView(header)
            tile.addView(Ui.gap(context, 8))
            val progress = android.widget.ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal).apply {
                max = 100
                this.progress = if (goal > 0) ((used / goal) * 100).toInt().coerceIn(0, 100) else 0
                progressTintList = android.content.res.ColorStateList.valueOf(color)
                progressBackgroundTintList = android.content.res.ColorStateList.valueOf(Palette.disabled)
            }
            tile.addView(progress, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
                Ui.dp(context, 5)))
            tile.addView(Ui.gap(context, 7))
            tile.addView(Ui.text(context, if (macro == null) "-- g" else "${grams(used)} g",
                12f, Palette.ink, true))
            tile.addView(Ui.text(context, when {
                goal <= 0 -> "目标未设置"
                used <= goal -> "剩 ${grams(goal - used)} g"
                else -> "超 ${grams(used - goal)} g"
            }, 10f, if (used > goal) Palette.fitness else Palette.muted))
            parent.addView(tile, LinearLayout.LayoutParams(0, Ui.dp(context, 88), 1f).apply {
                marginEnd = Ui.dp(context, 5)
            })
        }
    }

    private fun renderMealCards(host: ScreenHost, parent: LinearLayout, meals: JSONArray) {
        parent.removeAllViews()
        val context = host.screenContext
        mealKeys.forEachIndexed { index, key ->
            val card = Ui.card(context)
            val related = mutableListOf<JSONObject>()
            for (i in 0 until meals.length()) {
                val meal = meals.optJSONObject(i) ?: continue
                if (meal.optString("meal_type") == key) related.add(meal)
            }
            val header = Ui.row(context)
            val tileColors = listOf(Palette.lightGreen, 0xffffead5.toInt(),
                Palette.softBlue, 0xffffe7e9.toInt())
            val tile = Ui.text(context, listOf("早", "午", "晚", "加")[index],
                17f, listOf(Palette.deepGreen, Palette.carb, Palette.protein, Palette.fitness)[index], true).apply {
                gravity = Gravity.CENTER
                background = Ui.shape(context, tileColors[index], 11)
            }
            header.addView(tile, LinearLayout.LayoutParams(Ui.dp(context, 42), Ui.dp(context, 42)).apply {
                marginEnd = Ui.dp(context, 11)
            })
            val heading = Ui.column(context)
            heading.addView(Ui.text(context, mealNames[index], 16f, Palette.ink, true))
            heading.addView(Ui.text(context, if (related.isEmpty()) "尚未记录" else "已记 ${related.size} 条",
                12f, Palette.muted))
            header.addView(heading, LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            header.addView(Ui.pill(context, "+ 记录", Palette.white, Palette.deepGreen) {
                showMealDialog(host, key)
            })
            card.addView(header)
            for (meal in related) {
                val status = meal.optString("status")
                val items = meal.optJSONArray("items") ?: JSONArray()
                val names = (0 until items.length()).mapNotNull { items.optJSONObject(it)?.optString("display_name") }
                val kcal = (0 until items.length()).sumOf { items.optJSONObject(it)?.optDouble("kcal", 0.0) ?: 0.0 }
                val entry = Ui.column(context).apply {
                    background = Ui.shape(context, Palette.background, 12)
                    setPadding(Ui.dp(context, 10), Ui.dp(context, 9),
                        Ui.dp(context, 10), Ui.dp(context, 9))
                }
                card.addView(Ui.gap(context, 9))
                val detail = Ui.row(context)
                detail.addView(Ui.text(context, names.joinToString(" + "), 13f, Palette.ink, true).apply {
                    maxLines = 2
                    ellipsize = android.text.TextUtils.TruncateAt.END
                }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                detail.addView(Ui.badge(context, "${kcal.toInt()} kcal", Palette.deepGreen))
                entry.addView(detail)
                if (status == "PLANNED") {
                    entry.addView(Ui.text(context, "计划餐 · 尚未计入实际摄入", 11f, Palette.ice))
                }
                val actions = Ui.row(context)
                if (status == "PLANNED") {
                    actions.addView(Ui.pill(context, "✓ 已吃", Palette.white, Palette.green) {
                        host.api.post("/meals/${meal.optString("id")}", JSONObject().put("status", "CONSUMED")) { _, error ->
                            if (error != null) host.message(error) else host.refresh()
                        }
                    }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginEnd = Ui.dp(context, 7) })
                }
                actions.addView(Ui.pill(context, "编辑", Palette.deepGreen, Palette.lightGreen) {
                    showEditMealDialog(host, meal)
                }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginEnd = Ui.dp(context, 7) })
                actions.addView(Ui.pill(context, "删除", Palette.fitness, 0xffffe9eb.toInt()) {
                    AlertDialog.Builder(context).setTitle("删除这条餐食记录？")
                        .setMessage("删除后可在 5 秒内撤销。")
                        .setNegativeButton("取消", null).setPositiveButton("删除") { _, _ ->
                            val id = meal.optString("id")
                            host.api.delete("/meals/$id") { _, error ->
                                if (error != null) host.message(error)
                                else {
                                    host.refresh()
                                    host.undoableMessage("餐食已删除") {
                                        host.api.post("/meals/$id/restore", JSONObject()) { _, restoreError ->
                                            if (restoreError != null) host.message(restoreError) else host.refresh()
                                        }
                                    }
                                }
                            }
                        }.show()
                })
                entry.addView(Ui.gap(context, 6))
                entry.addView(actions)
                card.addView(entry)
            }
            parent.addView(card)
        }
    }

    private fun showMealDialog(host: ScreenHost, mealType: String) {
        val context = host.screenContext
        val form = Ui.column(context).apply { setPadding(Ui.dp(context, 18), Ui.dp(context, 8), Ui.dp(context, 18), 0) }
        val name = Ui.field(context, "食物名称")
        val amount = Ui.field(context, "份量数值", numeric = true)
        val unitKeys = listOf("g", "ml", "份", "个")
        val unit = Ui.picker(context, listOf("克 g", "毫升 ml", "份", "个"))
        val grams = Ui.field(context, "换算克数（可选，未知请留空）", numeric = true)
        grams.visibility = View.GONE
        val kcal = Ui.field(context, "热量（kcal）", numeric = true)
        val carb = Ui.field(context, "碳水（g，可选）", numeric = true)
        val protein = Ui.field(context, "蛋白质（g，可选）", numeric = true)
        val fat = Ui.field(context, "脂肪（g，可选）", numeric = true)
        val fiber = Ui.field(context, "膳食纤维（g，可选）", numeric = true)
        val note = Ui.field(context, "备注（可选）")
        var selectedFood: JSONObject? = null
        var frequentPerUnit: JSONObject? = null
        var conversionGPerUnit: Double? = null
        var suppressChanges = false
        var lastUnitIndex = 0
        val nutritionFields = listOf(kcal, carb, protein, fat, fiber)
        val nutritionKeys = listOf("kcal", "carb_g", "protein_g", "fat_g", "fiber_g")
        val nutrientBits = mapOf("carb_g" to 1, "protein_g" to 2, "fat_g" to 4, "fiber_g" to 8)
        fun recalculateFromGrams() {
            val food = selectedFood ?: return
            val weight = grams.text.toString().toDoubleOrNull()
            suppressChanges = true
            if (weight != null && weight > 0) {
                nutritionFields.forEachIndexed { index, field ->
                    val key = nutritionKeys[index]
                    field.setText(if (food.has(key)) String.format(java.util.Locale.US, "%.1f",
                        food.optDouble(key, 0.0) * weight / 100.0) else "")
                }
            } else nutritionFields.forEach { it.setText("") }
            suppressChanges = false
        }
        fun recalculateFromPortion(quantity: Double) {
            val values = frequentPerUnit ?: return
            suppressChanges = true
            nutritionFields.forEachIndexed { index, field ->
                val key = nutritionKeys[index]
                field.setText(if (values.has(key)) String.format(java.util.Locale.US, "%.1f",
                    values.optDouble(key, 0.0) * quantity) else "")
            }
            suppressChanges = false
        }
        fun fillFromCatalog(food: JSONObject) {
            selectedFood = food
            frequentPerUnit = null
            conversionGPerUnit = null
            suppressChanges = true
            lastUnitIndex = 0
            unit.setSelection(0)
            name.setText(food.optString("name"))
            if (amount.text.isBlank()) amount.setText("100")
            grams.setText(amount.text.toString())
            grams.visibility = View.GONE
            suppressChanges = false
            recalculateFromGrams()
        }
        fun fillFromFrequent(food: JSONObject) {
            val index = unitKeys.indexOf(food.optString("unit")).coerceAtLeast(0)
            val priorAmount = food.optDouble("amount", 0.0)
            val priorGrams = if (food.isNull("grams")) null else food.optDouble("grams", 0.0)
            val knownMask = food.optInt("nutrient_known_mask", 0)
            val normalized = if (priorGrams != null && priorGrams > 0) JSONObject().apply {
                put("name", food.optString("display_name"))
                if (!food.isNull("food_id")) put("id", food.optString("food_id"))
                nutritionKeys.forEach { key ->
                    if (key == "kcal" || (knownMask and (nutrientBits[key] ?: 0)) != 0)
                        put(key, food.optDouble(key, 0.0) * 100.0 / priorGrams)
                }
            } else null
            selectedFood = normalized
            frequentPerUnit = if (normalized == null && priorAmount > 0) JSONObject().apply {
                nutritionKeys.forEach { key ->
                    if (key == "kcal" || (knownMask and (nutrientBits[key] ?: 0)) != 0)
                        put(key, food.optDouble(key, 0.0) / priorAmount)
                }
            } else null
            conversionGPerUnit = if (index != 0 && priorGrams != null && priorAmount > 0)
                priorGrams / priorAmount else null
            suppressChanges = true
            lastUnitIndex = index
            unit.setSelection(index)
            name.setText(food.optString("display_name"))
            amount.setText(priorAmount.toString())
            grams.setText(priorGrams?.toString() ?: "")
            nutritionFields.forEachIndexed { fieldIndex, field ->
                val key = nutritionKeys[fieldIndex]
                field.setText(if (key == "kcal" || (knownMask and (nutrientBits[key] ?: 0)) != 0)
                    food.optDouble(key, 0.0).toString() else "")
            }
            grams.visibility = if (index == 0) View.GONE else View.VISIBLE
            suppressChanges = false
        }
        form.addView(Ui.button(context, "从食品库查找（每 100g 参考值）", Palette.ice) {
            val query = Ui.field(context, "食品名称，留空浏览全部")
            AlertDialog.Builder(context).setTitle("查找常见食物").setView(query)
                .setNegativeButton("取消", null).setPositiveButton("搜索") { _, _ ->
                    val encoded = java.net.URLEncoder.encode(query.text.toString().trim(), "UTF-8")
                    host.api.get("/foods?q=$encoded") { data, error ->
                        if (error != null) { host.message(error); return@get }
                        val foods = data?.optJSONArray("items") ?: JSONArray()
                        if (foods.length() == 0) { host.message("未找到食物，可直接手工填写"); return@get }
                        val labels = Array(foods.length()) { index ->
                            val food = foods.optJSONObject(index)
                            "${food?.optString("name") ?: ""} · ${food?.optDouble("kcal", 0.0)?.toInt() ?: 0} kcal/100g"
                        }
                        AlertDialog.Builder(context).setTitle("选择食品")
                            .setItems(labels) { _, index -> foods.optJSONObject(index)?.let(::fillFromCatalog) }
                            .setNegativeButton("取消", null).show()
                    }
                }.show()
        })
        form.addView(Ui.gap(context, 6))
        form.addView(Ui.button(context, "选择常用食物（沿用上次记录份量）", Palette.green) {
            host.api.get("/foods/frequent") { data, error ->
                if (error != null) { host.message(error); return@get }
                val foods = data?.optJSONArray("items") ?: JSONArray()
                if (foods.length() == 0) { host.message("暂无常用食物，请先记录一餐"); return@get }
                val labels = Array(foods.length()) { index ->
                    val food = foods.optJSONObject(index)
                    "${food?.optString("display_name") ?: ""} · ${food?.optDouble("amount", 0.0) ?: 0.0}${food?.optString("unit") ?: ""} · ${food?.optDouble("kcal", 0.0)?.toInt() ?: 0} kcal"
                }
                AlertDialog.Builder(context).setTitle("常用食物")
                    .setItems(labels) { _, index -> foods.optJSONObject(index)?.let(::fillFromFrequent) }
                    .setNegativeButton("取消", null).show()
            }
        })
        listOf(name, amount, unit, grams, kcal, carb, protein, fat, fiber, note).forEach(form::addView)
        form.addView(Ui.text(context, "未填写的营养素会标记为未知，统计页提示数据不完整。非克单位无换算时请手填热量。",
            12f, Palette.muted))
        val feedback = Ui.text(context, "", 12f, Palette.fitness)
        form.addView(feedback)
        name.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (!suppressChanges) { selectedFood = null; frequentPerUnit = null }
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        nutritionFields.forEach { field -> field.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (!suppressChanges) { selectedFood = null; frequentPerUnit = null }
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        }) }
        unit.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                grams.visibility = if (position == 0) View.GONE else View.VISIBLE
                if (suppressChanges || position == lastUnitIndex) return
                lastUnitIndex = position
                conversionGPerUnit = null
                val hadPortionBasis = frequentPerUnit != null
                frequentPerUnit = null
                suppressChanges = true
                grams.setText(if (position == 0) amount.text.toString() else "")
                if (hadPortionBasis) nutritionFields.forEach { it.setText("") }
                suppressChanges = false
                recalculateFromGrams()
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
        amount.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (suppressChanges) return
                val value = s.toString().toDoubleOrNull() ?: return
                val converted = if (unit.selectedItemPosition == 0) value
                    else conversionGPerUnit?.let { value * it }
                if (converted != null) grams.setText(String.format(java.util.Locale.US, "%.1f", converted))
                else recalculateFromPortion(value)
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        grams.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (suppressChanges) return
                val weight = s.toString().toDoubleOrNull()
                val count = amount.text.toString().toDoubleOrNull()
                if (unit.selectedItemPosition != 0 && weight != null && weight > 0 && count != null && count > 0)
                    conversionGPerUnit = weight / count
                recalculateFromGrams()
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        val scroll = android.widget.ScrollView(context).apply { addView(form) }
        val operationKey = java.util.UUID.randomUUID().toString()
        var submittedPayload: String? = null
        val dialog = AlertDialog.Builder(context).setTitle("记录${mealNames[mealKeys.indexOf(mealType)]}")
            .setView(scroll).setNegativeButton("取消", null).setPositiveButton("保存", null).create()
        dialog.setOnShowListener {
            val saveButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            saveButton.setOnClickListener {
                val quantity = amount.text.toString().toDoubleOrNull()
                val energy = kcal.text.toString().toDoubleOrNull()
                val weight = if (unit.selectedItemPosition == 0) quantity else
                    grams.text.toString().toDoubleOrNull()
                if (name.text.isBlank() || quantity == null || quantity <= 0 || energy == null || energy < 0 ||
                    (grams.text.isNotBlank() && (weight == null || weight <= 0))) {
                    feedback.text = "请填写名称、有效份量和热量；克数换算未知可留空"
                    scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
                    return@setOnClickListener
                }
                val optionalNutrients = listOf("carb_g" to carb, "protein_g" to protein,
                    "fat_g" to fat, "fiber_g" to fiber)
                if (optionalNutrients.any { (_, field) -> field.text.isNotBlank() &&
                        (field.text.toString().toDoubleOrNull()?.let { it < 0 } != false) }) {
                    feedback.text = "已填写的营养素必须是非负数字；未知请留空"
                    scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
                    return@setOnClickListener
                }
                val item = JSONObject().put("display_name", name.text.toString().trim())
                    .put("amount", quantity).put("unit", unitKeys[unit.selectedItemPosition]).put("kcal", energy)
                optionalNutrients.forEach { (key, field) ->
                    if (field.text.isNotBlank()) item.put(key, field.text.toString().toDouble())
                }
                if (weight != null) item.put("grams", weight)
                if (selectedFood?.optString("name") == name.text.toString().trim() &&
                    selectedFood?.optString("id")?.isNotBlank() == true)
                    item.put("food_id", selectedFood?.optString("id"))
                val payload = JSONObject().put("local_date", selectedDate).put("meal_type", mealType)
                    .put("items", JSONArray().put(item))
                    .put("note", note.text.toString().trim())
                val encoded = payload.toString()
                if (submittedPayload != null && submittedPayload != encoded) {
                    feedback.text = "上次提交结果可能已入账。请先关闭并检查饮食记录；如需修改，再编辑已有记录。"
                    scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
                    return@setOnClickListener
                }
                submittedPayload = encoded
                feedback.text = "正在保存…"
                saveButton.isEnabled = false
                host.api.post("/meals", payload, operationKey) { _, error ->
                    if (error != null) {
                        feedback.text = error
                        saveButton.isEnabled = true
                        scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
                    } else { dialog.dismiss(); host.refresh() }
                }
            }
        }
        dialog.show()
    }

    private fun showEditMealDialog(host: ScreenHost, meal: JSONObject) {
        val context = host.screenContext
        val form = Ui.column(context).apply {
            setPadding(Ui.dp(context, 16), Ui.dp(context, 8), Ui.dp(context, 16), Ui.dp(context, 8))
        }
        form.addView(Ui.text(context, "餐别", 14f, Palette.ink, true))
        val mealPicker = Ui.picker(context, mealNames)
        mealPicker.setSelection(mealKeys.indexOf(meal.optString("meal_type")).coerceAtLeast(0))
        form.addView(mealPicker)
        val controls = mutableListOf<Pair<JSONObject, List<android.widget.EditText>>>()
        val items = meal.optJSONArray("items") ?: JSONArray()
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            val knownMask = item.optInt("nutrient_known_mask", 0)
            fun knownValue(key: String, bit: Int): String =
                if ((knownMask and bit) != 0) item.optDouble(key).toString() else ""
            form.addView(Ui.subtitle(context, "食物 ${i + 1}"))
            val unit = item.optString("unit", "g")
            val fields = listOf(
                Ui.field(context, "食物名称", item.optString("display_name")),
                Ui.field(context, "份量（$unit）", item.optDouble("amount").toString(), true),
                Ui.field(context, "换算克数（未知可留空）",
                    if (item.isNull("grams")) "" else item.optDouble("grams").toString(), true),
                Ui.field(context, "热量 kcal", item.optDouble("kcal").toString(), true),
                Ui.field(context, "碳水 g（未知可留空）", knownValue("carb_g", 1), true),
                Ui.field(context, "蛋白质 g（未知可留空）", knownValue("protein_g", 2), true),
                Ui.field(context, "脂肪 g（未知可留空）", knownValue("fat_g", 4), true),
                Ui.field(context, "膳食纤维 g（未知可留空）", knownValue("fiber_g", 8), true))
            if (unit == "g") fields[2].visibility = View.GONE
            fields.forEach(form::addView)
            controls.add(item to fields)
        }
        val scroll = android.widget.ScrollView(context).apply { addView(form) }
        val dialog = AlertDialog.Builder(context).setTitle("编辑餐食").setView(scroll)
            .setNegativeButton("取消", null).setPositiveButton("保存", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val updated = JSONArray()
                for ((original, fields) in controls) {
                    val amount = fields[1].text.toString().toDoubleOrNull()
                    val unit = original.optString("unit", "g")
                    val grams = if (unit == "g") amount else fields[2].text.toString().toDoubleOrNull()
                    val kcal = fields[3].text.toString().toDoubleOrNull()
                    if (fields[0].text.isBlank() || amount == null || amount <= 0 ||
                        kcal == null || kcal < 0 || (fields[2].text.isNotBlank() &&
                            (grams == null || grams <= 0))) {
                        host.message("请核对名称、份量、可选克数和热量")
                        return@setOnClickListener
                    }
                    val optional = listOf("carb_g", "protein_g", "fat_g", "fiber_g")
                    if (optional.indices.any { index -> fields[index + 4].text.isNotBlank() &&
                            (fields[index + 4].text.toString().toDoubleOrNull()?.let { it < 0 } != false) }) {
                        host.message("已填写的营养素必须是非负数字；未知请留空")
                        return@setOnClickListener
                    }
                    val changed = JSONObject().put("display_name", fields[0].text.toString().trim())
                        .put("amount", amount).put("unit", unit).put("kcal", kcal)
                        .put("user_edited", true)
                    if (grams != null) changed.put("grams", grams)
                    if (original.optString("display_name") == fields[0].text.toString().trim() &&
                        !original.isNull("food_id")) changed.put("food_id", original.optString("food_id"))
                    optional.forEachIndexed { index, key ->
                        if (fields[index + 4].text.isNotBlank())
                            changed.put(key, fields[index + 4].text.toString().toDouble())
                    }
                    updated.put(changed)
                }
                host.api.post("/meals/${meal.optString("id")}", JSONObject()
                    .put("meal_type", mealKeys[mealPicker.selectedItemPosition]).put("items", updated)) { _, error ->
                    if (error != null) host.message(error) else { dialog.dismiss(); host.refresh() }
                }
            }
        }
        dialog.show()
    }

    private fun showScanReview(host: ScreenHost, response: JSONObject, image: ByteArray,
                               fromDraft: Boolean = false) {
        val context = host.screenContext
        val result = response.optJSONObject("result") ?: return
        val items = result.optJSONArray("items") ?: return
        val form = Ui.column(context).apply { setPadding(Ui.dp(context, 16), 0, Ui.dp(context, 16), 0) }
        form.addView(Ui.badge(context, "● AI 视觉引擎 · 识别完成", Palette.deepGreen))
        form.addView(Ui.gap(context, 12))
        val photo = android.graphics.BitmapFactory.decodeByteArray(image, 0, image.size,
            android.graphics.BitmapFactory.Options().apply { inSampleSize = 2 })
        if (photo != null) {
            val preview = android.widget.ImageView(context).apply {
                setImageBitmap(photo)
                scaleType = android.widget.ImageView.ScaleType.CENTER_CROP
                background = Ui.shape(context, Palette.softBlue, 16)
                clipToOutline = true
                contentDescription = "待核对的餐食照片"
            }
            form.addView(preview, LinearLayout.LayoutParams(-1, Ui.dp(context, 205)).apply {
                bottomMargin = Ui.dp(context, 12)
            })
        }
        form.addView(Ui.text(context, "AI 智能识别完成 · ${items.length()} 种食材", 17f, Palette.ink, true))
        form.addView(Ui.gap(context, 10))
        form.addView(Ui.text(context, "这张照片属于哪一餐？", 14f, Palette.ink, true))
        val mealPicker = Ui.picker(context, mealNames)
        mealPicker.setSelection(currentMealIndex())
        form.addView(mealPicker)
        val warning = result.optJSONArray("warnings")
        if (warning != null && warning.length() > 0) {
            form.addView(Ui.text(context, (0 until warning.length()).joinToString("；") { warning.optString(it) },
                13f, Palette.fitness))
        }
        val itemContainer = Ui.column(context)
        form.addView(itemContainer)
        val edited = mutableListOf<ScanFields>()
        val total = Ui.text(context, "", 16f, Palette.green, true)
        fun updateTotal() {
            fun grams(value: Double) = String.format(java.util.Locale.getDefault(), "%.1f", value)
            val calories = edited.sumOf { it.kcal.text.toString().toDoubleOrNull() ?: 0.0 }
            val carb = edited.sumOf { field ->
                (field.original?.optDouble("carb_g", 0.0) ?: 0.0) *
                    ((field.grams.text.toString().toDoubleOrNull() ?: 0.0) /
                        (field.original?.optDouble("estimated_grams", 1.0) ?: 1.0))
            }
            val protein = edited.sumOf { field ->
                (field.original?.optDouble("protein_g", 0.0) ?: 0.0) *
                    ((field.grams.text.toString().toDoubleOrNull() ?: 0.0) /
                        (field.original?.optDouble("estimated_grams", 1.0) ?: 1.0))
            }
            val fat = edited.sumOf { field ->
                (field.original?.optDouble("fat_g", 0.0) ?: 0.0) *
                    ((field.grams.text.toString().toDoubleOrNull() ?: 0.0) /
                        (field.original?.optDouble("estimated_grams", 1.0) ?: 1.0))
            }
            val incomplete = edited.count { field ->
                val original = field.original
                original == null || listOf("carb_g", "protein_g", "fat_g").any { key ->
                    !original.has(key) || original.isNull(key)
                }
            }
            total.text = "本次合计 ${calories.toInt()} kcal  ·  已知碳水 ${grams(carb)}g  蛋白 ${grams(protein)}g  脂肪 ${grams(fat)}g" +
                if (incomplete > 0) "\n$incomplete 项营养未知，确认后会在饮食和数据页标记不完整" else ""
        }
        fun watch(field: android.widget.EditText, changed: () -> Unit) {
            field.addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = changed()
                override fun afterTextChanged(s: android.text.Editable?) {}
            })
        }
        fun addItem(item: JSONObject?) {
            if (edited.size >= 30) { host.message("最多保留 30 项食物"); return }
            val panel = Ui.card(context).apply {
                background = Ui.shape(context, Palette.softBlue, 12)
                elevation = 0f
            }
            val itemHeading = Ui.row(context)
            itemHeading.addView(Ui.text(context, item?.optString("name") ?: "补充食物", 15f, Palette.ink, true),
                LinearLayout.LayoutParams(0, -2, 1f))
            itemHeading.addView(Ui.badge(context,
                if (item != null) "可信度 ${(item.optDouble("confidence") * 100).toInt()}%" else "手工补充",
                Palette.deepGreen))
            panel.addView(itemHeading)
            panel.addView(Ui.gap(context, 8))
            val name = Ui.field(context, "名称", item?.optString("name") ?: "")
            val grams = Ui.field(context, "克数", item?.optDouble("estimated_grams")?.toString() ?: "", true)
            val kcal = Ui.field(context, "热量 kcal", item?.optDouble("kcal")?.toString() ?: "", true)
            panel.addView(Ui.text(context, "食物名称", 11f, Palette.muted, true))
            panel.addView(name)
            val amountLabels = Ui.row(context)
            amountLabels.addView(Ui.text(context, "估算克数 g", 11f, Palette.muted, true),
                LinearLayout.LayoutParams(0, -2, 1f))
            amountLabels.addView(Ui.text(context, "估算热量 kcal", 11f, Palette.muted, true),
                LinearLayout.LayoutParams(0, -2, 1f))
            panel.addView(amountLabels)
            val amounts = Ui.row(context)
            amounts.addView(grams, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f).apply {
                marginEnd = Ui.dp(context, 7)
            })
            amounts.addView(kcal, LinearLayout.LayoutParams(0, Ui.dp(context, 48), 1f))
            panel.addView(amounts)
            val fields = ScanFields(panel, name, grams, kcal, item)
            panel.addView(Ui.gap(context, 8))
            panel.addView(Ui.pill(context, "移除这一项", Palette.fitness,
                android.graphics.Color.rgb(255, 236, 235)) {
                edited.remove(fields)
                itemContainer.removeView(panel)
                updateTotal()
            })
            itemContainer.addView(panel)
            edited.add(fields)
            var changingAutomatically = false
            watch(grams) {
                if (item != null && !fields.kcalManuallyEdited) {
                    val value = grams.text.toString().toDoubleOrNull()
                    val reference = item.optDouble("estimated_grams", 0.0)
                    if (value != null && reference > 0) {
                        changingAutomatically = true
                        kcal.setText(String.format(java.util.Locale.US, "%.1f", item.optDouble("kcal") * value / reference))
                        changingAutomatically = false
                    }
                }
                updateTotal()
            }
            watch(kcal) {
                if (!changingAutomatically) fields.kcalManuallyEdited = true
                updateTotal()
            }
            updateTotal()
        }
        for (i in 0 until items.length()) items.optJSONObject(i)?.let(::addItem)
        form.addView(Ui.button(context, "+ 补充遗漏食物", Palette.ice) { addItem(null) })
        form.addView(Ui.gap(context, 8))
        val totalCard = Ui.card(context).apply {
            background = Ui.shape(context, Palette.softBlue, 16)
            elevation = 0f
        }
        totalCard.addView(Ui.text(context, "本次打卡新增能量", 13f, Palette.deepGreen, true))
        totalCard.addView(total)
        form.addView(totalCard)
        val screen = Ui.column(context).apply { setBackgroundColor(Palette.background) }
        val header = Ui.row(context).apply {
            setPadding(Ui.dp(context, 16), Ui.dp(context, 10), Ui.dp(context, 16), Ui.dp(context, 10))
            setBackgroundColor(Palette.white)
        }
        val back = Ui.pill(context, "‹ 返回", Palette.ink, Palette.background)
        header.addView(back)
        header.addView(Ui.text(context, "AI Food Scanner", 18f, Palette.ink, true).apply {
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(0, -2, 1f))
        header.addView(Ui.text(context, "✦", 21f, Palette.deepGreen, true))
        screen.addView(header)
        val scroll = android.widget.ScrollView(context).apply {
            clipToPadding = false
            setPadding(0, Ui.dp(context, 14), 0, Ui.dp(context, 10))
            addView(form)
        }
        screen.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        val footer = Ui.column(context).apply {
            setPadding(Ui.dp(context, 16), Ui.dp(context, 10), Ui.dp(context, 16), Ui.dp(context, 14))
            setBackgroundColor(Palette.white)
        }
        val confirm = Ui.button(context, "确认打卡并记录", Palette.deepGreen) {}
        footer.addView(confirm)
        screen.addView(footer)
        val dialog = AlertDialog.Builder(context).setView(screen).create()
        back.setOnClickListener { dialog.dismiss() }
        confirm.setOnClickListener {
            val approved = JSONArray()
            for (field in edited) {
                val grams = field.grams.text.toString().toDoubleOrNull()
                val kcal = field.kcal.text.toString().toDoubleOrNull()
                if (field.name.text.isBlank() || grams == null || grams <= 0 || kcal == null || kcal < 0) {
                    host.message("请核对所有食物的名称、克数和热量")
                    return@setOnClickListener
                }
                val original = field.original
                val ratio = grams / (original?.optDouble("estimated_grams", grams) ?: grams)
                val recorded = JSONObject().put("display_name", field.name.text.toString())
                    .put("amount", grams).put("unit", "g").put("grams", grams).put("kcal", kcal)
                    .put("confidence", original?.optDouble("confidence", 0.0) ?: 0.0)
                    .put("user_edited", true)
                listOf("carb_g", "protein_g", "fat_g").forEach { key ->
                    if (original?.has(key) == true)
                        recorded.put(key, original.optDouble(key, 0.0) * ratio)
                }
                approved.put(recorded)
            }
            if (approved.length() == 0) { host.message("请至少保留一项食物"); return@setOnClickListener }
            val payload = JSONObject().put("local_date", selectedDate)
                .put("meal_type", mealKeys[mealPicker.selectedItemPosition])
                .put("items", approved)
            host.api.post("/food-scans/${response.optString("id")}/confirm", payload) { _, error ->
                if (error != null) host.message(error)
                else {
                    if (fromDraft) PhotoDraftStore(context).clear()
                    dialog.dismiss()
                    host.refresh()
                }
            }
        }
        dialog.show()
        dialog.window?.setLayout(android.view.WindowManager.LayoutParams.MATCH_PARENT,
            android.view.WindowManager.LayoutParams.MATCH_PARENT)
    }
}
