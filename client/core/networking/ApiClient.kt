package com.example.appdemo.core.networking

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.example.appdemo.core.database.SecureTokenStore
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

class ApiClient(private val context: Context) {
    companion object {
        fun isSafeServerUrl(value: String): Boolean = try {
            val url = URL(value.trimEnd('/'))
            if (url.userInfo != null || url.query != null || url.ref != null ||
                (url.path.isNotEmpty() && url.path != "/")) false
            else if (url.protocol == "https") true
            else if (url.protocol != "http") false
            else {
                val host = url.host.lowercase()
                val octets = host.split('.').mapNotNull { it.toIntOrNull() }
                host in setOf("localhost", "127.0.0.1", "[::1]") ||
                    (octets.size == 4 && octets.all { it in 0..255 } &&
                        (octets[0] == 10 || (octets[0] == 192 && octets[1] == 168) ||
                            (octets[0] == 172 && octets[1] in 16..31)))
            }
        } catch (_: Exception) { false }
    }
    private val main = Handler(Looper.getMainLooper())
    private val preferences = context.getSharedPreferences("nutripulse", Context.MODE_PRIVATE)
    private val tokenStore = SecureTokenStore(context)

    var baseUrl: String
        get() = preferences.getString("server_url", "http://10.0.2.2:8787") ?: "http://10.0.2.2:8787"
        set(value) { preferences.edit().putString("server_url", value.trimEnd('/')).apply() }

    var token: String
        get() = tokenStore.read()
        set(value) { tokenStore.write(value) }

    fun get(path: String, done: (JSONObject?, String?) -> Unit) = request("GET", path, null, done)
    fun post(path: String, data: JSONObject, done: (JSONObject?, String?) -> Unit) =
        request("POST", path, data, done)
    fun post(path: String, data: JSONObject, idempotencyKey: String,
             done: (JSONObject?, String?) -> Unit) =
        request("POST", path, data, done, idempotencyKey)
    fun put(path: String, data: JSONObject, done: (JSONObject?, String?) -> Unit) =
        request("PUT", path, data, done)
    fun patch(path: String, data: JSONObject, done: (JSONObject?, String?) -> Unit) =
        request("PATCH", path, data, done)
    fun delete(path: String, done: (JSONObject?, String?) -> Unit) =
        request("DELETE", path, null, done)

    fun pair(serverUrl: String, code: String, done: (JSONObject?, String?) -> Unit) {
        Thread {
            var connection: HttpURLConnection? = null
            try {
                val normalizedUrl = serverUrl.trim().trimEnd('/')
                if (!isSafeServerUrl(normalizedUrl))
                    throw IllegalArgumentException("服务地址必须为 HTTPS 或本机/局域网 HTTP")
                if (code.isBlank()) throw IllegalArgumentException("请填写电脑屏幕显示的一次性配对码")
                connection = (URL("$normalizedUrl/api/v1/auth/pair").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 4000
                    readTimeout = 12_000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    setRequestProperty("Accept", "application/json")
                }
                connection.outputStream.use { it.write(JSONObject().put("code", code.trim()).toString().toByteArray(Charsets.UTF_8)) }
                val responseText = (if (connection.responseCode < 400) connection.inputStream
                                    else connection.errorStream).bufferedReader(Charsets.UTF_8).use { it.readText() }
                val response = JSONObject(responseText)
                if (connection.responseCode >= 400) {
                    main.post { done(null, response.optString("message", "配对失败")) }
                    return@Thread
                }
                val data = response.optJSONObject("data") ?: throw IllegalArgumentException("配对响应格式无效")
                val accessToken = data.optString("access_token")
                if (accessToken.isBlank()) throw IllegalArgumentException("配对响应缺少访问凭据")
                baseUrl = normalizedUrl
                token = accessToken
                main.post { done(JSONObject().put("expires_at", data.optString("expires_at")), null) }
            } catch (error: Exception) {
                val message = when (error) {
                    is IllegalArgumentException -> error.localizedMessage ?: "配对参数无效"
                    is java.net.SocketTimeoutException -> "配对超时，请检查电脑服务与网络"
                    is java.io.IOException -> "无法连接电脑服务，请检查地址、网络和配对码有效期"
                    else -> "配对失败，请稍后重试"
                }
                main.post { done(null, message) }
            } finally { connection?.disconnect() }
        }.start()
    }

    fun downloadReport(period: String, end: String, done: (ByteArray?, String?) -> Unit) {
        Thread {
            var connection: HttpURLConnection? = null
            try {
                if (!isSafeServerUrl(baseUrl)) throw IllegalArgumentException("服务地址必须为 HTTPS 或本机/局域网 HTTP")
                connection = (URL(baseUrl + "/api/v1/reports").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 4000
                    readTimeout = 65_000
                    doOutput = true
                    setRequestProperty("Accept", "application/pdf")
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer $token")
                }
                val payload = JSONObject().put("period", period).put("end", end)
                connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
                if (connection.responseCode >= 400) {
                    val error = connection.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                    val message = try { JSONObject(error ?: "{}").optString("message", "报告生成失败") }
                        catch (_: Exception) { "报告生成失败" }
                    main.post { done(null, message) }
                    return@Thread
                }
                if (!connection.contentType.orEmpty().startsWith("application/pdf")) {
                    main.post { done(null, "服务端未返回 PDF 文件") }
                    return@Thread
                }
                val bytes = connection.inputStream.use { input ->
                    val output = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(8192)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        output.write(buffer, 0, count)
                        if (output.size() > 10_000_000) throw IllegalArgumentException("报告超过 10 MB，已停止下载")
                    }
                    output.toByteArray()
                }
                if (bytes.size < 5 || !bytes.copyOfRange(0, 5).contentEquals("%PDF-".toByteArray()))
                    throw IllegalArgumentException("下载的文件不是有效 PDF")
                main.post { done(bytes, null) }
            } catch (error: Exception) {
                val message = when (error) {
                    is IllegalArgumentException -> error.localizedMessage ?: "报告参数无效"
                    is java.net.SocketTimeoutException -> "生成报告超时，请检查本地服务"
                    is java.io.IOException -> "本地服务连接中断，请检查电脑服务、地址与端口"
                    else -> "报告下载失败，请稍后重试"
                }
                main.post { done(null, message) }
            } finally { connection?.disconnect() }
        }.start()
    }

    private fun request(method: String, path: String, data: JSONObject?,
                        done: (JSONObject?, String?) -> Unit, idempotencyKey: String? = null) {
        Thread {
            var connection: HttpURLConnection? = null
            try {
                if (!isSafeServerUrl(baseUrl)) throw IllegalArgumentException("服务地址必须为 HTTPS 或本机/局域网 HTTP")
                val url = URL(baseUrl + "/api/v1" + path)
                connection = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = method
                    connectTimeout = 4000
                    readTimeout = if (path.startsWith("/food-scans") || path.startsWith("/agent/chats") ||
                        path.startsWith("/recommendations") || path.startsWith("/analytics/diagnostics")) 65_000 else 12_000
                    setRequestProperty("Accept", "application/json")
                    if (token.isNotBlank()) setRequestProperty("Authorization", "Bearer $token")
                    if (data != null) {
                        doOutput = true
                        setRequestProperty("Content-Type", "application/json; charset=utf-8")
                        setRequestProperty("Idempotency-Key", idempotencyKey ?: UUID.randomUUID().toString())
                    }
                }
                if (data != null) connection.outputStream.use { it.write(data.toString().toByteArray(Charsets.UTF_8)) }
                val responseText = (if (connection.responseCode < 400) connection.inputStream
                                    else connection.errorStream).bufferedReader(Charsets.UTF_8).use { it.readText() }
                val response = JSONObject(responseText)
                val error = if (connection.responseCode >= 400) response.optString("message", "请求失败") else null
                main.post { done(if (error == null) response.optJSONObject("data") ?: JSONObject().put("items", response.optJSONArray("data")) else null, error) }
            } catch (error: Exception) {
                val message = when (error) {
                    is IllegalArgumentException -> error.localizedMessage ?: "服务地址无效"
                    is java.net.SocketTimeoutException -> "连接本地电脑超时，请检查服务和网络"
                    is java.io.IOException -> "本地服务连接中断，请检查电脑服务、地址与端口"
                    else -> "请求失败，请稍后重试"
                }
                main.post { done(null, message) }
            } finally { connection?.disconnect() }
        }.start()
    }
}
