package com.example.appdemo.core.database

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.security.KeyStore

/** Keeps the LAN API token encrypted with a key that never leaves Android Keystore. */
class SecureTokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("nutripulse", Context.MODE_PRIVATE)
    private val alias = "nutripulse-local-api-token"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return generator.generateKey()
    }

    fun read(): String {
        val encrypted = prefs.getString("server_token_cipher", null)
        if (encrypted == null) {
            val legacy = prefs.getString("server_token", "") ?: ""
            if (legacy.isNotEmpty()) write(legacy)
            return legacy
        }
        return try {
            val payload = Base64.decode(encrypted, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, payload.copyOfRange(0, 12)))
            String(cipher.doFinal(payload.copyOfRange(12, payload.size)), Charsets.UTF_8)
        } catch (_: Exception) { "" }
    }

    fun write(value: String) {
        if (value.isEmpty()) {
            prefs.edit().remove("server_token_cipher").remove("server_token").apply()
            return
        }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val payload = cipher.iv + encrypted
        prefs.edit().putString("server_token_cipher", Base64.encodeToString(payload, Base64.NO_WRAP))
            .remove("server_token").apply()
    }
}
