package com.example.appdemo

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.appdemo.core.database.PhotoDraftStore
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PhotoDraftStoreInstrumentedTest {
    @Test
    fun encryptedDraftPreservesItsScanRetryKey() {
        // Separate device-protected files from any real user photo draft in credential storage.
        val context = InstrumentationRegistry.getInstrumentation().targetContext
            .createDeviceProtectedStorageContext()
        context.filesDir.mkdirs()
        val draft = PhotoDraftStore(context)
        val image = ByteArray(1_200) { (it % 251).toByte() }
        try {
            draft.save(image, "image/jpeg", "original-scan-operation")
            val restored = draft.load()
            assertNotNull(restored)
            assertArrayEquals(image, restored!!.first)
            assertEquals("image/jpeg", restored.second)
            assertEquals("original-scan-operation", restored.third)
            val onDisk = context.getFileStreamPath("nutripulse_scan_draft.enc").readBytes()
            assertFalse(onDisk.contentEquals(image))
        } finally {
            draft.clear()
        }
    }
}
