package com.example.appdemo.core.database

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import java.security.KeyStore
import java.util.UUID

/** One encrypted, private photo draft; the original is never kept by the server. */
class PhotoDraftStore(private val context: Context) {
    private val fileName = "nutripulse_scan_draft.enc"
    private val prefs = context.getSharedPreferences("nutripulse_drafts", Context.MODE_PRIVATE)
    private val alias = "nutripulse-photo-draft"

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

    fun exists(): Boolean = context.getFileStreamPath(fileName).exists()

    fun save(image: ByteArray, mime: String, operationKey: String) {
        require(image.size <= 3_500_000 && mime in setOf("image/jpeg", "image/png", "image/webp"))
        require(operationKey.isNotBlank())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        context.openFileOutput(fileName, Context.MODE_PRIVATE).use { output ->
            output.write(cipher.iv + cipher.doFinal(image))
        }
        prefs.edit().putString("photo_mime", mime).putString("scan_operation_key", operationKey).apply()
    }

    fun load(): Triple<ByteArray, String, String>? {
        if (!exists()) return null
        return try {
            val bytes = context.openFileInput(fileName).use { it.readBytes() }
            if (bytes.size <= 12) null
            else {
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
                val operationKey = prefs.getString("scan_operation_key", null)
                    ?: UUID.randomUUID().toString().also {
                        prefs.edit().putString("scan_operation_key", it).apply()
                    }
                Triple(cipher.doFinal(bytes.copyOfRange(12, bytes.size)),
                    prefs.getString("photo_mime", "image/jpeg") ?: "image/jpeg", operationKey)
            }
        } catch (_: Exception) { null }
    }

    fun clear() {
        context.deleteFile(fileName)
        prefs.edit().remove("photo_mime").remove("scan_operation_key").apply()
    }
}
