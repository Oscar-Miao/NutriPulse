package com.example.appdemo

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.example.appdemo.core.files.PhotoNormalizer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.File

@RunWith(AndroidJUnit4::class)
class PhotoNormalizerInstrumentedTest {
    @Test fun smallPhotoIsReencodedWithoutGpsAndWithAppliedOrientation() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val original = File.createTempFile("scan_exif_", ".jpg", context.cacheDir)
        try {
            val bitmap = Bitmap.createBitmap(120, 60, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(Color.RED)
            original.outputStream().use { bitmap.compress(Bitmap.CompressFormat.JPEG, 90, it) }
            bitmap.recycle()
            ExifInterface(original.absolutePath).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION,
                    ExifInterface.ORIENTATION_ROTATE_90.toString())
                setAttribute(ExifInterface.TAG_GPS_LATITUDE, "37/1,25/1,0/1")
                setAttribute(ExifInterface.TAG_GPS_LATITUDE_REF, "N")
                setAttribute(ExifInterface.TAG_MAKE, "private-device")
                saveAttributes()
            }
            val source = original.readBytes()
            assertTrue(source.size < 3_500_000)
            val (clean, mime) = PhotoNormalizer.normalize(source)
            assertEquals("image/jpeg", mime)
            assertTrue(clean.size <= 3_500_000)
            assertFalse(source.contentEquals(clean))
            val decoded = BitmapFactory.decodeByteArray(clean, 0, clean.size)
            assertEquals(60, decoded.width)
            assertEquals(120, decoded.height)
            decoded.recycle()
            val metadata = ExifInterface(ByteArrayInputStream(clean))
            assertNull(metadata.getAttribute(ExifInterface.TAG_GPS_LATITUDE))
            assertNull(metadata.getAttribute(ExifInterface.TAG_MAKE))
            val outputOrientation = metadata.getAttributeInt(ExifInterface.TAG_ORIENTATION,
                ExifInterface.ORIENTATION_UNDEFINED)
            assertTrue(outputOrientation == ExifInterface.ORIENTATION_UNDEFINED ||
                outputOrientation == ExifInterface.ORIENTATION_NORMAL)
        } finally {
            original.delete()
        }
    }
}
