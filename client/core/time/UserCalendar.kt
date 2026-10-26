package com.example.appdemo.core.time

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** The local Demo currently stores every profile in Asia/Shanghai. */
object UserCalendar {
    val zone: ZoneId = ZoneId.of("Asia/Shanghai")

    fun today(instant: Instant = Instant.now()): LocalDate = instant.atZone(zone).toLocalDate()
}
