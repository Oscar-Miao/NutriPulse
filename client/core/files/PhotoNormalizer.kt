package com.example.appdemo.core.files

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.media.ExifInterface
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

/** Re-encoding strips source EXIF before any image leaves the phone. */
object PhotoNormalizer {
    private const val MAX_DIMENSION = 1600
    private const val MAX_UPLOAD_BYTES = 3_500_000

    fun normalize(bytes: ByteArray): Pair<ByteArray, String> {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        require(bounds.outWidth > 0 && bounds.outHeight > 0) { "无法解码这张照片" }
        var sample = 1
        while (bounds.outWidth / sample > MAX_DIMENSION || bounds.outHeight / sample > MAX_DIMENSION)
            sample *= 2
        val orientation = try {
            ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(
                ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        } catch (_: Exception) { ExifInterface.ORIENTATION_NORMAL }
        val source = BitmapFactory.decodeByteArray(bytes, 0, bytes.size,
            BitmapFactory.Options().apply { inSampleSize = sample })
            ?: throw IllegalArgumentException("无法解码这张照片")
        var working = source
        try {
            val transform = orientationMatrix(orientation)
            if (transform != null) {
                working = Bitmap.createBitmap(source, 0, 0, source.width, source.height, transform, true)
                if (working !== source) source.recycle()
            }
            if (working.hasAlpha()) {
                val opaque = Bitmap.createBitmap(working.width, working.height, Bitmap.Config.ARGB_8888)
                Canvas(opaque).apply {
                    drawColor(Color.WHITE)
                    drawBitmap(working, 0f, 0f, null)
                }
                working.recycle()
                working = opaque
            }
            for (quality in listOf(85, 70, 55, 40)) {
                val output = ByteArrayOutputStream()
                if (!working.compress(Bitmap.CompressFormat.JPEG, quality, output))
                    throw IllegalArgumentException("照片压缩失败")
                if (output.size() <= MAX_UPLOAD_BYTES) return output.toByteArray() to "image/jpeg"
            }
            throw IllegalArgumentException("图片压缩后仍过大，请重新拍摄")
        } finally {
            if (!working.isRecycled) working.recycle()
            if (source !== working && !source.isRecycled) source.recycle()
        }
    }

    private fun orientationMatrix(orientation: Int): Matrix? = Matrix().apply {
        when (orientation) {
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
            ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
            ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(270f); postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(270f)
            else -> return null
        }
    }
}
