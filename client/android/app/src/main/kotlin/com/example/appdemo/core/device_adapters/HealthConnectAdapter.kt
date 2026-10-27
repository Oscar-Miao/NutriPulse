package com.example.appdemo.core.device_adapters

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregateMetric
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.BodyFatRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.example.appdemo.core.time.UserCalendar
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

object HealthConnectAdapter {
    val permissions = setOf(
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(WeightRecord::class),
        HealthPermission.getReadPermission(BodyFatRecord::class),
    )

    suspend fun readRecentSamples(context: Context, granted: Set<String>,
                                  anchorDay: LocalDate): JSONArray {
        val client = HealthConnectClient.getOrCreate(context)
        val zone = UserCalendar.zone
        val today = anchorDay
        val result = JSONArray()
        val energyAllowed = granted.contains(HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class))
        val stepsAllowed = granted.contains(HealthPermission.getReadPermission(StepsRecord::class))
        val metrics = mutableSetOf<AggregateMetric<*>>()
        if (stepsAllowed) metrics.add(StepsRecord.COUNT_TOTAL)
        for (offset in 6 downTo 0) {
            val day = today.minusDays(offset.toLong())
            val start = day.atStartOfDay(zone).toInstant()
            val end = day.plusDays(1).atStartOfDay(zone).toInstant()
            if (metrics.isNotEmpty()) {
                val aggregate = client.aggregate(AggregateRequest(
                    metrics = metrics, timeRangeFilter = TimeRangeFilter.between(start, end)))
                if (stepsAllowed) aggregate[StepsRecord.COUNT_TOTAL]?.let { steps ->
                    result.put(sample("hc-steps-$day", "steps", day, steps.toDouble(), start.toString()))
                }
            }
        }
        val start = today.minusDays(6).atStartOfDay(zone).toInstant()
        val end = today.plusDays(1).atStartOfDay(zone).toInstant()
        if (energyAllowed) {
            var token: String? = null
            var pages = 0
            do {
                val page = client.readRecords(ReadRecordsRequest(ActiveCaloriesBurnedRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(start, end), pageSize = 500,
                    pageToken = token))
                for (record in page.records) {
                    val clippedStart = maxOf(record.startTime, start)
                    val clippedEnd = minOf(record.endTime, end)
                    if (clippedEnd <= clippedStart || record.energy.inKilocalories < 0) continue
                    val originalMillis = java.time.Duration.between(record.startTime, record.endTime)
                        .toMillis().toDouble().coerceAtLeast(1.0)
                    var cursor = clippedStart
                    while (cursor < clippedEnd) {
                        val day = cursor.atZone(zone).toLocalDate()
                        val nextDay = day.plusDays(1).atStartOfDay(zone).toInstant()
                        val segmentEnd = minOf(clippedEnd, nextDay)
                        val segmentMillis = java.time.Duration.between(cursor, segmentEnd).toMillis().toDouble()
                        val energy = record.energy.inKilocalories * segmentMillis / originalMillis
                        if (energy > 0) result.put(sample(
                            "hc-energy-${record.metadata.id}-$day", "active_energy", day,
                            energy, cursor.toString(), segmentEnd.toString()))
                        cursor = segmentEnd
                    }
                }
                token = page.pageToken
                pages++
                if (pages > 100) throw IllegalStateException("健康数据超过单次可同步上限，请缩短时间范围")
            } while (!token.isNullOrBlank())
        }
        if (granted.contains(HealthPermission.getReadPermission(WeightRecord::class))) {
            val weights = client.readRecords(ReadRecordsRequest(WeightRecord::class,
                timeRangeFilter = TimeRangeFilter.between(start, end), pageSize = 1000))
            for (record in weights.records.groupBy { it.time.atZone(zone).toLocalDate() }
                    .values.mapNotNull { daily -> daily.maxByOrNull { it.time } }) {
                val day = record.time.atZone(zone).toLocalDate()
                result.put(sample("hc-weight-${record.metadata.id}", "body_weight", day,
                    record.weight.inKilograms, record.time.toString()))
            }
        }
        if (granted.contains(HealthPermission.getReadPermission(BodyFatRecord::class))) {
            val bodyFats = client.readRecords(ReadRecordsRequest(BodyFatRecord::class,
                timeRangeFilter = TimeRangeFilter.between(start, end), pageSize = 1000))
            for (record in bodyFats.records.groupBy { it.time.atZone(zone).toLocalDate() }
                    .values.mapNotNull { daily -> daily.maxByOrNull { it.time } }) {
                val day = record.time.atZone(zone).toLocalDate()
                result.put(sample("hc-fat-${record.metadata.id}", "body_fat", day,
                    record.percentage.value, record.time.toString()))
            }
        }
        if (granted.contains(HealthPermission.getReadPermission(HeartRateRecord::class))) {
            val heartRates = client.readRecords(ReadRecordsRequest(HeartRateRecord::class,
                timeRangeFilter = TimeRangeFilter.between(java.time.Instant.now().minusSeconds(7200),
                    java.time.Instant.now()), pageSize = 1000))
            val recent = heartRates.records.flatMap { it.samples }.maxByOrNull { it.time }
            if (recent != null) {
                val day = recent.time.atZone(zone).toLocalDate()
                result.put(sample("hc-heart-$day", "heart_rate", day,
                    recent.beatsPerMinute.toDouble(), recent.time.toString()))
            }
        }
        return result
    }

    private fun sample(id: String, type: String, date: LocalDate, value: Double,
                       time: String, endTime: String? = null) =
        JSONObject().put("external_id", id).put("sample_type", type)
            .put("local_date", date.toString()).put("start_at", time).put("value", value).apply {
                if (endTime != null) put("end_at", endTime)
            }
}
