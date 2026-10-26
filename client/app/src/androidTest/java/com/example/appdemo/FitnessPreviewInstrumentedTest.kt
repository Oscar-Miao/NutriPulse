package com.example.appdemo

import android.content.Intent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class FitnessPreviewInstrumentedTest {
    @Test
    fun quickWorkoutDialogOffersIntensityAndEstimateBeforeSave() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val activity = instrumentation.startActivitySync(
            Intent(instrumentation.targetContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            instrumentation.waitForIdleSync()
            clickText("健身")
            instrumentation.waitForIdleSync()
            assertNotNull(findText("设备与手工运动时间冲突"))
            clickText("+ 快速记录运动")
            instrumentation.waitForIdleSync()
            assertNotNull(findText("中等强度"))
            assertNotNull(findText("先估算活动消耗"))
        } finally {
            instrumentation.runOnMainSync { activity.finish() }
        }
    }

    private fun findText(text: String): AccessibilityNodeInfo? {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        repeat(10) {
            val match = automation.rootInActiveWindow?.findAccessibilityNodeInfosByText(text)
                ?.firstOrNull { node -> node.text?.toString() == text }
            if (match != null) return match
            Thread.sleep(100)
        }
        return null
    }

    private fun clickText(text: String) {
        var node = findText(text)
        assertNotNull("未找到：$text", node)
        while (node != null && !node.isClickable) node = node.parent
        assertTrue("无法点击：$text", node?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true)
    }
}
