package com.example.appdemo

import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.lifecycle.lifecycleScope
import com.example.appdemo.core.database.PhotoDraftStore
import com.example.appdemo.core.database.SecureTokenStore
import com.example.appdemo.core.device_adapters.HealthConnectAdapter
import com.example.appdemo.core.files.PhotoNormalizer
import com.example.appdemo.core.time.UserCalendar
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File

/** Only operating-system integration lives here. All screens are Flutter widgets. */
class MainActivity : FlutterFragmentActivity() {
    private val prefs by lazy { getSharedPreferences("nutripulse", MODE_PRIVATE) }
    private val values by lazy { SecureValues(this) }
    private val tokens by lazy { SecureTokenStore(this) }
    private val drafts by lazy { PhotoDraftStore(this) }
    private var photoResult: MethodChannel.Result? = null
    private var healthResult: MethodChannel.Result? = null
    private var exportResult: MethodChannel.Result? = null
    private var exportBytes: ByteArray? = null
    private var cameraFile: File? = null
    private var cameraUri: Uri? = null
    private val picker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) { photoResult?.success(null); photoResult = null } else loadPhoto(uri)
    }
    private val camera = registerForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        val uri = cameraUri
        if (saved && uri != null) loadPhoto(uri)
        else { photoResult?.success(null); photoResult = null; cameraFile?.delete() }
    }
    private val permissions = registerForActivityResult(PermissionController.createRequestPermissionResultContract()) { granted ->
        if (granted.isEmpty()) { healthResult?.error("PERMISSION_DENIED", "未获得健康数据读取权限", null); healthResult = null }
        else readHealth(granted)
    }
    private val document = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { activity ->
        val reply = exportResult ?: return@registerForActivityResult
        val bytes = exportBytes
        exportResult = null; exportBytes = null
        val uri = activity.data?.data
        if (activity.resultCode != RESULT_OK || uri == null || bytes == null) reply.success(false)
        else boundary(reply) {
            withContext(Dispatchers.IO) {
                val stream = contentResolver.openOutputStream(uri, "wt") ?: error("无法写入选定文件")
                stream.use { it.write(bytes) }
            }
            true
        }
    }
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "nutripulse/device").setMethodCallHandler { call, reply ->
            when (call.method) {
                "settings" -> boundary(reply) { mapOf("url" to prefs.getString("server_url", "http://10.0.2.2:8787"), "token" to tokens.read()) }
                "configure" -> boundary(reply) {
                    prefs.edit().putString("server_url", call.argument<String>("url")!!).apply()
                    tokens.write(call.argument<String>("token")!!); null
                }
                "read" -> boundary(reply) { values.read(call.argument<String>("key")!!) }
                "write" -> boundary(reply) { values.write(call.argument<String>("key")!!, call.argument<String>("value")); null }
                "photoDraft" -> boundary(reply) { drafts.load()?.let { mapOf("bytes" to it.first, "mime" to it.second, "key" to it.third) } }
                "savePhotoDraft" -> boundary(reply) { drafts.save(call.argument<ByteArray>("bytes")!!, "image/jpeg", call.argument<String>("key")!!); null }
                "clearPhotoDraft" -> boundary(reply) { drafts.clear(); null }
                "photo" -> boundaryStart(reply) {
                    check(photoResult == null) { "已有照片选择操作进行中" }
                    photoResult = reply
                    if (call.argument<Boolean>("camera") == true) {
                        cameraFile = File.createTempFile("nutripulse-camera-", ".jpg", cacheDir)
                        cameraUri = FileProvider.getUriForFile(this, "$packageName.fileprovider", cameraFile!!)
                        camera.launch(cameraUri)
                    } else picker.launch("image/*")
                }
                "healthSamples" -> boundaryStart(reply) {
                    check(healthResult == null) { "健康数据同步正在进行" }
                    check(HealthConnectClient.getSdkStatus(this) == HealthConnectClient.SDK_AVAILABLE) { "请先安装或启用 Health Connect，再授权读取数据" }
                    healthResult = reply
                    if (call.argument<Boolean>("requestPermission") != false) permissions.launch(HealthConnectAdapter.permissions)
                    else {
                        healthResult = null
                        boundary(reply) {
                            val granted = HealthConnectClient.getOrCreate(this@MainActivity).permissionController.getGrantedPermissions()
                            check(granted.isNotEmpty()) { "健康读取权限已撤销" }
                            healthData(granted)
                        }
                    }
                }
                "revokeHealth" -> boundary(reply) {
                    if (HealthConnectClient.getSdkStatus(this) == HealthConnectClient.SDK_AVAILABLE)
                        HealthConnectClient.getOrCreate(this).permissionController.revokeAllPermissions()
                    null
                }
                "saveFile" -> boundaryStart(reply) {
                    check(exportResult == null) { "已有文件导出进行中" }
                    exportBytes = call.argument<ByteArray>("bytes")!!
                    exportResult = reply
                    document.launch(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = call.argument<String>("mime")!!
                        putExtra(Intent.EXTRA_TITLE, call.argument<String>("name")!!)
                    })
                }
                "openUrl" -> boundary(reply) {
                    val uri = Uri.parse(call.argument<String>("url")!!)
                    require(uri.scheme == "https" || uri.scheme == "http") { "只支持网页链接" }
                    startActivity(Intent(Intent.ACTION_VIEW, uri)); null
                }
                "clearLocal" -> boundary(reply) {
                    val category = call.argument<String>("category")!!
                    values.clear(category)
                    if (category in setOf("all", "diet", "agent")) drafts.clear()
                    if (category in setOf("all", "fitness", "profile")) prefs.edit().remove("health_auto_sync").apply()
                    if (category == "all") {
                        tokens.write("")
                        prefs.edit().remove("server_url").apply()
                        getSharedPreferences("nutripulse_drafts", MODE_PRIVATE).edit().clear().apply()
                    }
                    null
                }
                else -> reply.notImplemented()
            }
        }
    }
    private fun loadPhoto(uri: Uri) {
        val reply = photoResult ?: return
        photoResult = null
        boundary(reply) {
            withContext(Dispatchers.IO) {
                try {
                    val out = ByteArrayOutputStream()
                    val stream = contentResolver.openInputStream(uri) ?: error("无法读取照片")
                    stream.use { input ->
                        val buffer = ByteArray(8192)
                        while (true) {
                            val count = input.read(buffer)
                            if (count < 0) break
                            out.write(buffer, 0, count)
                            require(out.size() <= 12_000_000) { "照片超过 12 MB，请选择较小图片" }
                        }
                    }
                    PhotoNormalizer.normalize(out.toByteArray()).first
                } finally { cameraFile?.delete(); cameraFile = null; cameraUri = null }
            }
        }
    }
    private fun readHealth(granted: Set<String>) {
        val reply = healthResult ?: return
        healthResult = null
        boundary(reply) { healthData(granted) }
    }
    private suspend fun healthData(granted: Set<String>): Map<String, Any?> {
        val array = withContext(Dispatchers.IO) { HealthConnectAdapter.readRecentSamples(this@MainActivity, granted, UserCalendar.today()) }
        return mapOf("samples" to jsonValue(array), "scopes" to granted.toList(), "energy_allowed" to granted.contains(HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class)))
    }
    private fun jsonValue(value: Any?): Any? = when (value) {
        JSONObject.NULL, null -> null
        is JSONArray -> (0 until value.length()).map { jsonValue(value.get(it)) }
        is JSONObject -> value.keys().asSequence().associateWith { jsonValue(value.get(it)) }
        else -> value
    }
    // The platform entry point is the single exception boundary; original causes are logged.
    private fun boundary(reply: MethodChannel.Result, work: suspend () -> Any?) {
        lifecycleScope.launch {
            try { reply.success(work()) }
            catch (error: Exception) { Log.e("NutriPulseBridge", "Platform request failed", error); reply.error("PLATFORM_ERROR", error.localizedMessage, null) }
        }
    }
    private fun boundaryStart(reply: MethodChannel.Result, work: () -> Unit) {
        try { work() }
        catch (error: Exception) { Log.e("NutriPulseBridge", "Platform action failed", error); reply.error("PLATFORM_ERROR", error.localizedMessage, null) }
    }
}
