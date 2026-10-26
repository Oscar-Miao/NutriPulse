package com.example.appdemo

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.appdemo.core.networking.ApiClient
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.net.ServerSocket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class ApiIdempotencyInstrumentedTest {
    @Test
    fun repeatedPostCanReuseTheSameIdempotencyKey() {
        val server = ServerSocket(0)
        val keys = mutableListOf<String>()
        val worker = Thread {
            repeat(2) {
                server.accept().use { socket ->
                    socket.soTimeout = 5_000
                    val input = socket.getInputStream()
                    val headerBytes = ByteArrayOutputStream()
                    while (!headerBytes.toByteArray().endsWithHeaders()) {
                        val next = input.read()
                        if (next < 0) break
                        headerBytes.write(next)
                    }
                    val headers = headerBytes.toString("UTF-8")
                    keys.add(Regex("(?im)^Idempotency-Key: ([^\\r\\n]+)").find(headers)?.groupValues?.get(1) ?: "")
                    val length = Regex("(?im)^Content-Length: (\\d+)").find(headers)?.groupValues?.get(1)
                        ?.toIntOrNull() ?: 0
                    repeat(length) { if (input.read() < 0) return@use }
                    val body = "{\"data\":{\"id\":\"same-meal\"}}".toByteArray(Charsets.UTF_8)
                    val response = "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n" +
                        "Content-Length: ${body.size}\r\nConnection: close\r\n\r\n"
                    socket.getOutputStream().write(response.toByteArray(Charsets.US_ASCII))
                    socket.getOutputStream().write(body)
                    socket.getOutputStream().flush()
                }
            }
        }
        worker.start()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val client = ApiClient(context)
        val original = client.baseUrl
        try {
            client.baseUrl = "http://127.0.0.1:${server.localPort}"
            repeat(2) {
                val done = CountDownLatch(1)
                var error: String? = null
                var id: String? = null
                client.post("/meals", JSONObject().put("test", true), "stable-form-operation") { data, failure ->
                    id = data?.optString("id")
                    error = failure
                    done.countDown()
                }
                assertTrue(done.await(8, TimeUnit.SECONDS))
                assertNull(error)
                assertEquals("same-meal", id)
            }
            worker.join(5_000)
            assertEquals(listOf("stable-form-operation", "stable-form-operation"), keys)
        } finally {
            client.baseUrl = original
            server.close()
        }
    }

    private fun ByteArray.endsWithHeaders(): Boolean {
        val n = size
        return n >= 4 && this[n - 4] == 13.toByte() && this[n - 3] == 10.toByte() &&
            this[n - 2] == 13.toByte() && this[n - 1] == 10.toByte()
    }
}
