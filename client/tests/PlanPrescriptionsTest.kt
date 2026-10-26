package com.example.appdemo

import com.example.appdemo.features.fitness.PlanPrescriptions
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlanPrescriptionsTest {
    @Test fun timedPrescriptionKeepsSecondsDistinctFromRepetitions() {
        val plank = PlanPrescriptions.parse("平板支撑 3×20 秒")
        assertEquals("平板支撑", plank.name)
        assertEquals(3, plank.setCount)
        assertEquals(20, plank.targetAmount)
        assertTrue(plank.timed)
        assertTrue(PlanPrescriptions.parse("农夫走 3×30 秒/侧").timed)
    }

    @Test fun repetitionRangesAndPerSideAreNotTimed() {
        val press = PlanPrescriptions.parse("卧推 4×6-8")
        assertEquals("卧推", press.name)
        assertEquals(4, press.setCount)
        assertEquals(6, press.targetAmount)
        assertFalse(press.timed)
        val lunge = PlanPrescriptions.parse("弓步 3×10/侧")
        assertEquals(10, lunge.targetAmount)
        assertFalse(lunge.timed)
    }
}
