package com.example.appdemo

import android.os.Bundle
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.content.FileProvider
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import com.example.appdemo.core.design_system.Palette
import com.example.appdemo.core.design_system.NavigationIconView
import com.example.appdemo.core.design_system.ScreenHost
import com.example.appdemo.core.design_system.Ui
import com.example.appdemo.core.database.PhotoDraftStore
import com.example.appdemo.core.device_adapters.HealthConnectAdapter
import com.example.appdemo.core.files.PhotoNormalizer
import com.example.appdemo.core.networking.ApiClient
import com.example.appdemo.core.time.UserCalendar
import com.example.appdemo.features.analytics.AnalyticsScreen
import com.example.appdemo.features.diet.DietScreen
import com.example.appdemo.features.fitness.FitnessScreen
import com.example.appdemo.features.profile.ProfileScreen
import com.example.appdemo.features.what_to_eat.WhatToEatScreen
import com.google.android.material.snackbar.Snackbar
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity(), ScreenHost {
    override val screenContext get() = this
    override val api by lazy { ApiClient(this) }
    private lateinit var root: LinearLayout
    private var currentTab = 0
    private val healthHandler = Handler(Looper.getMainLooper())
    private var syncingHealth = false
    private var healthRevocationInProgress = false
    private val healthTicker = object : Runnable {
        override fun run() {
            if (healthRevocationInProgress || currentTab != 1 || !getSharedPreferences("nutripulse", MODE_PRIVATE)
                    .getBoolean("health_auto_sync", false)) return
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    if (HealthConnectClient.getSdkStatus(this@MainActivity) == HealthConnectClient.SDK_AVAILABLE) {
                        val granted = HealthConnectClient.getOrCreate(this@MainActivity)
                            .permissionController.getGrantedPermissions()
                        if (granted.isNotEmpty()) runOnUiThread {
                            if (!healthRevocationInProgress) syncHealthNow(granted, true)
                        }
                    }
                } catch (_: Exception) { /* Retry only while Fitness is visible. */ }
            }
            healthHandler.postDelayed(this, 60_000)
        }
    }
    private var pendingPhoto: ((ByteArray, String) -> Unit)? = null
    private var pendingExportCategory: String? = null
    private var pendingReportPeriod: String? = null
    private var pendingReportEnd: String? = null
    private var pendingReportBytes: ByteArray? = null
    private var reportDownloading = false
    private var cameraUri: Uri? = null
    private var cameraFile: java.io.File? = null
    private val healthPermissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()) { granted ->
        if (granted.isNotEmpty()) syncHealthNow(granted)
        else message("未获得健康数据权限；可随时在系统设置中重新授权")
    }
    private val photoPicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) loadPhoto(uri)
        else pendingPhoto = null
    }
    private val jsonDocument = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")) { uri ->
        val category = pendingExportCategory
        pendingExportCategory = null
        if (uri == null || category == null) return@registerForActivityResult
        val path = if (category == "diagnostics") "/diagnostics/logs?limit=500"
                   else "/privacy/export?category=$category"
        api.get(path) { data, error ->
            if (error != null || data == null) {
                message(error ?: "导出失败")
                return@get
            }
            Thread {
                try {
                    contentResolver.openOutputStream(uri, "wt").use { output ->
                        if (output == null) throw IllegalStateException("无法写入选定文件")
                        output.write(data.toString(2).toByteArray(Charsets.UTF_8))
                    }
                    runOnUiThread { message(if (category == "diagnostics")
                        "诊断日志已保存；分享前仍请检查文件内容" else "个人数据 JSON 已保存；请妥善保管") }
                } catch (error: Exception) {
                    runOnUiThread { message(error.localizedMessage ?: "导出文件写入失败") }
                }
            }.start()
        }
    }
    private val pdfDocument = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/pdf")) { uri ->
        val period = pendingReportPeriod
        val end = pendingReportEnd
        val bytes = pendingReportBytes
        pendingReportPeriod = null
        pendingReportEnd = null
        pendingReportBytes = null
        if (uri == null || period == null || end == null) return@registerForActivityResult
        fun save(pdf: ByteArray) {
            Thread {
                try {
                    contentResolver.openOutputStream(uri, "wt").use { output ->
                        if (output == null) throw IllegalStateException("无法写入选定文件")
                        output.write(pdf)
                    }
                    runOnUiThread { message("PDF 已保存，包含个人健康信息，请妥善保管") }
                } catch (error: Exception) {
                    runOnUiThread { message(error.localizedMessage ?: "PDF 写入失败") }
                }
            }.start()
        }
        if (bytes != null) save(bytes)
        else api.downloadReport(period, end) { restored, error ->
            if (restored != null) save(restored)
            else message(error ?: "报告重新下载失败；选定的文件尚未写入")
        }
    }
    private val camera = registerForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        val uri = cameraUri
        val file = cameraFile
        cameraUri = null
        cameraFile = null
        if (saved && uri != null) loadPhoto(uri, file)
        else { pendingPhoto = null; file?.delete() }
    }

    private fun loadPhoto(uri: Uri, tempFile: java.io.File? = null) {
        val callback = pendingPhoto
        pendingPhoto = null
        if (callback == null) return
        Thread {
            try {
                val output = java.io.ByteArrayOutputStream()
                contentResolver.openInputStream(uri).use { input ->
                    if (input == null) throw IllegalArgumentException("无法读取照片")
                    val buffer = ByteArray(8192)
                    while (true) {
                        val size = input.read(buffer)
                        if (size < 0) break
                        output.write(buffer, 0, size)
                        if (output.size() > 12_000_000) throw IllegalArgumentException("照片超过 12 MB，请选择较小图片")
                    }
                }
                val bytes = output.toByteArray()
                val normalized = PhotoNormalizer.normalize(bytes)
                Handler(Looper.getMainLooper()).post { callback(normalized.first, normalized.second) }
            } catch (error: Exception) {
                Handler(Looper.getMainLooper()).post { message(error.localizedMessage ?: "读取照片失败") }
            } finally {
                tempFile?.delete()
            }
        }.start()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        root = Ui.column(this).apply { setBackgroundColor(Palette.background) }
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }
        currentTab = savedInstanceState?.getInt("current_tab") ?: 0
        pendingExportCategory = savedInstanceState?.getString("pending_export_category")
        pendingReportPeriod = savedInstanceState?.getString("pending_report_period")
        pendingReportEnd = savedInstanceState?.getString("pending_report_end")
        refresh()
        scheduleHealthTick()
    }

    override fun onDestroy() {
        healthHandler.removeCallbacks(healthTicker)
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt("current_tab", currentTab)
        outState.putString("pending_export_category", pendingExportCategory)
        outState.putString("pending_report_period", pendingReportPeriod)
        outState.putString("pending_report_end", pendingReportEnd)
        super.onSaveInstanceState(outState)
    }

    override fun navigate(tab: Int) {
        currentTab = tab.coerceIn(0, 4)
        refresh()
        scheduleHealthTick()
    }

    private fun scheduleHealthTick() {
        healthHandler.removeCallbacks(healthTicker)
        if (currentTab == 1 && getSharedPreferences("nutripulse", MODE_PRIVATE)
                .getBoolean("health_auto_sync", false)) healthHandler.postDelayed(healthTicker, 60_000)
    }

    override fun refresh() {
        root.removeAllViews()
        root.addView(appHeader())
        val page = when (currentTab) {
            0 -> DietScreen.render(this)
            1 -> FitnessScreen.render(this)
            2 -> WhatToEatScreen.render(this)
            3 -> AnalyticsScreen.render(this)
            else -> ProfileScreen.render(this)
        }
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            setPadding(Ui.dp(this@MainActivity, 16), Ui.dp(this@MainActivity, 8),
                Ui.dp(this@MainActivity, 16), Ui.dp(this@MainActivity, 24))
            addView(page)
        }
        root.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(bottomNav())
    }

    private fun appHeader(): View {
        val header = Ui.row(this).apply {
            setBackgroundColor(Palette.background)
            setPadding(Ui.dp(this@MainActivity, 16), 0, Ui.dp(this@MainActivity, 16), 0)
        }
        val mark = Ui.text(this, "N", 20f, Palette.deepGreen, true).apply {
            gravity = Gravity.CENTER
            background = Ui.shape(this@MainActivity, Palette.lightGreen, 11)
            includeFontPadding = false
        }
        header.addView(mark, LinearLayout.LayoutParams(Ui.dp(this, 34), Ui.dp(this, 34)).apply {
            marginEnd = Ui.dp(this@MainActivity, 9)
        })
        val brand = Ui.column(this)
        brand.addView(Ui.text(this, "NutriPulse", 17f, Palette.ink, true).apply {
            includeFontPadding = false
        })
        brand.addView(Ui.text(this, listOf("Diet Hub", "Fitness Hub", "What to Eat", "Analytics Hub", "Profile Hub")[currentTab],
            10f, Palette.deepGreen, true).apply { includeFontPadding = false })
        header.addView(brand, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        val avatar = Ui.text(this, "我", 14f, Palette.deepGreen, true).apply {
            gravity = Gravity.CENTER
            background = Ui.shape(this@MainActivity, Palette.softBlue, 999)
            setOnClickListener { navigate(4) }
            contentDescription = "打开个人主页"
        }
        header.addView(avatar, LinearLayout.LayoutParams(Ui.dp(this, 36), Ui.dp(this, 36)))
        return header.apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this@MainActivity, 58))
        }
    }

    private fun bottomNav(): View {
        val nav = Ui.row(this).apply {
            setBackgroundColor(Palette.white)
            elevation = Ui.dp(this@MainActivity, 8).toFloat()
            setPadding(Ui.dp(this@MainActivity, 4), 0, Ui.dp(this@MainActivity, 4), 0)
        }
        val labels = listOf("饮食", "健身", "吃什么", "数据", "我的")
        val icons = listOf(NavigationIconView.Kind.HOME, NavigationIconView.Kind.FITNESS,
            NavigationIconView.Kind.EAT, NavigationIconView.Kind.DATA, NavigationIconView.Kind.PROFILE)
        labels.forEachIndexed { index, label ->
            val color = if (index == currentTab) {
                if (index == 1) Palette.fitness else Palette.green
            } else Palette.muted
            val item = FrameLayout(this).apply {
                isClickable = true
                isFocusable = true
                contentDescription = label
                setOnClickListener { navigate(index) }
            }
            if (index == 2) {
                val center = FrameLayout(this).apply {
                    background = Ui.shape(this@MainActivity, Palette.green, 999)
                    elevation = Ui.dp(this@MainActivity, 4).toFloat()
                }
                center.addView(NavigationIconView(this, icons[index], Palette.white),
                    FrameLayout.LayoutParams(Ui.dp(this, 26), Ui.dp(this, 26), Gravity.CENTER))
                item.addView(center, FrameLayout.LayoutParams(Ui.dp(this, 46), Ui.dp(this, 46),
                    Gravity.TOP or Gravity.CENTER_HORIZONTAL))
            } else item.addView(NavigationIconView(this, icons[index], color),
                FrameLayout.LayoutParams(Ui.dp(this, 25), Ui.dp(this, 25),
                    Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = Ui.dp(this@MainActivity, 11) })
            item.addView(Ui.text(this, label, 11f, color, index == currentTab).apply {
                gravity = Gravity.CENTER
                includeFontPadding = false
            }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 17),
                Gravity.BOTTOM).apply { bottomMargin = Ui.dp(this@MainActivity, 8) })
            nav.addView(item, LinearLayout.LayoutParams(0, Ui.dp(this, 72), 1f))
        }
        return nav
    }

    override fun message(text: String) {
        Snackbar.make(root, text, Snackbar.LENGTH_LONG).show()
    }

    override fun undoableMessage(text: String, undo: () -> Unit) {
        Snackbar.make(root, text, 5_000).setAction("撤销") { undo() }.show()
    }

    override fun choosePhoto(done: (ByteArray, String) -> Unit) {
        pendingPhoto = done
        android.app.AlertDialog.Builder(this).setTitle("拍照识餐")
            .setItems(arrayOf("打开相机拍摄", "从相册选择")) { _, index ->
                if (index == 0) {
                    try {
                        val file = java.io.File.createTempFile("meal_", ".jpg", cacheDir)
                        cameraFile = file
                        cameraUri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
                        camera.launch(cameraUri)
                    } catch (error: Exception) {
                        pendingPhoto = null
                        message("无法打开相机：${error.localizedMessage ?: "请检查设备"}")
                    }
                } else photoPicker.launch("image/*")
            }.setOnCancelListener { pendingPhoto = null }.show()
    }

    override fun syncHealthConnect() {
        if (healthRevocationInProgress) {
            message("正在撤销 Health Connect 连接，请稍候")
            return
        }
        if (HealthConnectClient.getSdkStatus(this) != HealthConnectClient.SDK_AVAILABLE) {
            message("此设备暂未提供 Health Connect，请在系统中安装或更新")
            return
        }
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val granted = HealthConnectClient.getOrCreate(this@MainActivity)
                    .permissionController.getGrantedPermissions()
                runOnUiThread {
                    if (healthRevocationInProgress) return@runOnUiThread
                    if (granted.containsAll(HealthConnectAdapter.permissions)) syncHealthNow(granted)
                    else healthPermissionLauncher.launch(HealthConnectAdapter.permissions)
                }
            } catch (error: Exception) {
                runOnUiThread { message("检查健康数据权限失败：${error.localizedMessage ?: "请重试"}") }
            }
        }
    }

    override fun revokeDeviceConnection(connectionId: String, provider: String, deleteHistory: Boolean) {
        if (provider == "health_connect") {
            if (syncingHealth || healthRevocationInProgress) {
                message("Health Connect 正在同步或处理授权，请完成后重试")
                return
            }
            healthRevocationInProgress = true
            getSharedPreferences("nutripulse", MODE_PRIVATE).edit()
                .putBoolean("health_auto_sync", false).apply()
            healthHandler.removeCallbacks(healthTicker)
        }
        val suffix = if (deleteHistory) "?delete_history=true" else ""
        api.delete("/devices/$connectionId$suffix") { result, error ->
            if (error != null || result == null) {
                healthRevocationInProgress = false
                message(error ?: "设备连接处理失败；请重试")
                return@delete
            }
            val summary = if (deleteHistory)
                "已删除 ${result.optInt("removed_samples")} 条设备样本；请检查更新后的营养目标"
                else "已停止同步；保留的设备历史继续参与过往统计"
            if (provider != "health_connect") {
                message(summary)
                refresh()
                return@delete
            }
            CoroutineScope(Dispatchers.IO).launch {
                val revoked = try {
                    if (HealthConnectClient.getSdkStatus(this@MainActivity) == HealthConnectClient.SDK_AVAILABLE) {
                        HealthConnectClient.getOrCreate(this@MainActivity)
                            .permissionController.revokeAllPermissions()
                    }
                    true
                } catch (_: Exception) { false }
                runOnUiThread {
                    healthRevocationInProgress = false
                    message(if (revoked) summary else
                        "$summary；系统健康权限可能仍有效，请在 Health Connect 设置中手动撤销")
                    refresh()
                }
            }
        }
    }

    override fun exportPersonalData(category: String) {
        pendingExportCategory = category
        jsonDocument.launch("NutriPulse_${category}_${UserCalendar.today()}.json")
    }

    override fun exportDiagnosticLogs() {
        pendingExportCategory = "diagnostics"
        jsonDocument.launch("NutriPulse_diagnostics_${UserCalendar.today()}.json")
    }

    override fun exportAnalyticsPdf(period: String, end: String) {
        if (reportDownloading) return
        reportDownloading = true
        message("正在生成当前周期报告…")
        api.downloadReport(period, end) { bytes, error ->
            reportDownloading = false
            if (bytes == null) {
                message(error ?: "报告下载失败")
                return@downloadReport
            }
            pendingReportPeriod = period
            pendingReportEnd = end
            pendingReportBytes = bytes
            pdfDocument.launch("NutriPulse_${period}_${end}.pdf")
        }
    }

    override fun personalDataDeleted(category: String) {
        if (category in setOf("diet", "agent", "all")) PhotoDraftStore(this).clear()
        if (category in setOf("fitness", "profile", "all")) {
            getSharedPreferences("nutripulse", MODE_PRIVATE).edit()
                .remove("health_auto_sync").apply()
            healthHandler.removeCallbacks(healthTicker)
            CoroutineScope(Dispatchers.IO).launch {
                val revoked = try {
                    if (HealthConnectClient.getSdkStatus(this@MainActivity) == HealthConnectClient.SDK_AVAILABLE) {
                        HealthConnectClient.getOrCreate(this@MainActivity)
                            .permissionController.revokeAllPermissions()
                    }
                    true
                } catch (_: Exception) { false }
                runOnUiThread {
                    healthRevocationInProgress = false
                    if (!revoked) message("服务器数据已清空；请在 Health Connect 设置中手动撤销系统权限")
                }
            }
        }
        if (category == "all") {
            api.token = ""
            getSharedPreferences("nutripulse", MODE_PRIVATE).edit().remove("server_url").apply()
            getSharedPreferences("nutripulse_drafts", MODE_PRIVATE).edit().clear().apply()
        }
        refresh()
    }

    override fun beginPersonalDataDeletion(category: String): Boolean {
        if (category !in setOf("fitness", "profile", "all")) return true
        if (syncingHealth || healthRevocationInProgress) {
            message("设备正在同步或撤销授权，请完成后再清空相关数据")
            return false
        }
        healthRevocationInProgress = true
        healthHandler.removeCallbacks(healthTicker)
        return true
    }

    override fun cancelPersonalDataDeletion(category: String) {
        if (category in setOf("fitness", "profile", "all")) {
            healthRevocationInProgress = false
            scheduleHealthTick()
        }
    }

    private fun syncHealthNow(granted: Set<String>, silent: Boolean = false) {
        if (syncingHealth || healthRevocationInProgress) return
        syncingHealth = true
        if (!silent) message("正在同步 Health Connect 最近 7 天数据…")
        val syncDay = UserCalendar.today()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val samples = HealthConnectAdapter.readRecentSamples(this@MainActivity, granted, syncDay)
                runOnUiThread {
                    val energyAllowed = granted.contains(
                        androidx.health.connect.client.permission.HealthPermission.getReadPermission(
                            androidx.health.connect.client.records.ActiveCaloriesBurnedRecord::class))
                    if (samples.length() == 0 && !energyAllowed) {
                        syncingHealth = false
                        if (!silent) message("没有发现可同步的健康记录")
                        return@runOnUiThread
                    }
                    api.post("/devices", org.json.JSONObject().put("provider", "health_connect")
                        .put("scopes", org.json.JSONArray(HealthConnectAdapter.permissions.toList()))) { device, error ->
                        if (error != null) { syncingHealth = false; if (!silent) message(error); return@post }
                        val id = device?.optString("id") ?: ""
                        if (id.isBlank()) {
                            syncingHealth = false
                            if (!silent) message("服务端未返回设备连接标识")
                            return@post
                        }
                        val batchId = java.util.UUID.randomUUID().toString()
                        val count = maxOf(1, (samples.length() + 499) / 500)
                        val dates = org.json.JSONArray().apply {
                            for (offset in 6 downTo 0) put(syncDay.minusDays(offset.toLong()).toString())
                        }
                        fun upload(index: Int, added: Int, changed: Int) {
                            val chunk = org.json.JSONArray()
                            for (position in index * 500 until minOf(samples.length(), (index + 1) * 500))
                                chunk.put(samples.optJSONObject(position))
                            val payload = org.json.JSONObject().put("samples", chunk)
                            if (energyAllowed) {
                                payload.put("sync_batch_id", batchId)
                                    .put("stage_active_energy", true)
                                if (index == count - 1) payload.put("activate_active_dates", dates)
                            }
                            api.post("/devices/$id/samples", payload) { result, importError ->
                                if (importError != null) {
                                    syncingHealth = false
                                    if (!silent) message("健康数据第 ${index + 1}/$count 批同步失败：$importError；下次可重试")
                                } else if (index + 1 < count) {
                                    upload(index + 1, added + (result?.optInt("imported") ?: 0),
                                        changed + (result?.optInt("updated") ?: 0))
                                } else {
                                    syncingHealth = false
                                    getSharedPreferences("nutripulse", MODE_PRIVATE).edit()
                                        .putBoolean("health_auto_sync", true).apply()
                                    scheduleHealthTick()
                                    if (!silent) message("同步完成：新增 ${added + (result?.optInt("imported") ?: 0)}，" +
                                        "更新 ${changed + (result?.optInt("updated") ?: 0)} 条；" +
                                        "待处理重叠 ${result?.optInt("pending_conflicts", 0) ?: 0} 项")
                                    refresh()
                                }
                            }
                        }
                        upload(0, 0, 0)
                    }
                }
            } catch (error: Exception) {
                runOnUiThread {
                    syncingHealth = false
                    if (!silent) message("同步失败：${error.localizedMessage ?: "健康数据读取错误"}")
                }
            }
        }
    }
}
