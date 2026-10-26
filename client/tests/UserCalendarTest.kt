package com.example.appdemo

import com.example.appdemo.core.time.UserCalendar
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant
import java.time.LocalDate

class UserCalendarTest {
    @Test fun shanghaiDateDoesNotFollowDeviceUtcDateNearMidnight() {
        assertEquals(LocalDate.of(2026, 10, 4),
            UserCalendar.today(Instant.parse("2026-10-03T16:30:00Z")))
        assertEquals(LocalDate.of(2026, 10, 3),
            UserCalendar.today(Instant.parse("2026-10-03T15:59:59Z")))
    }
}
