package com.example.appdemo.features.analytics

import com.example.appdemo.core.time.UserCalendar
import java.time.LocalDate

object PeriodRange {
    fun forIndex(index: Int, end: LocalDate = UserCalendar.today()): Pair<LocalDate, LocalDate> {
        val start = when (index) {
            0 -> end
            1 -> end.minusDays(6)
            2 -> end.withDayOfMonth(1)
            3 -> end.withDayOfYear(1)
            else -> throw IllegalArgumentException("Unknown period: $index")
        }
        return start to end
    }
}
