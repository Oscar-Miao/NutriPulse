package com.example.appdemo

import com.example.appdemo.features.analytics.PeriodRange
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalDate

class PeriodRangeTest {
    private val end = LocalDate.of(2026, 10, 2)

    @Test fun weekIsSevenDaysInclusive() {
        assertEquals(LocalDate.of(2026, 9, 26), PeriodRange.forIndex(1, end).first)
    }

    @Test fun monthAndYearStartAtCalendarBoundary() {
        assertEquals(LocalDate.of(2026, 10, 1), PeriodRange.forIndex(2, end).first)
        assertEquals(LocalDate.of(2026, 1, 1), PeriodRange.forIndex(3, end).first)
    }
}
