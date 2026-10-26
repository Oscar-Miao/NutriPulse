package com.example.appdemo.features.fitness

/** Parses the structured units already present in official plan templates. */
data class PlanPrescription(val name: String, val setCount: Int,
                            val targetAmount: Int, val timed: Boolean)

object PlanPrescriptions {
    private val pattern = Regex("^(.*?)\\s+(\\d+)[×xX](\\d+)(?:[-–]\\d+)?.*$")
    private val secondsSuffix = Regex("\\d+\\s*秒(?:/侧)?$")

    fun parse(text: String): PlanPrescription {
        val match = pattern.find(text)
        val name = match?.groupValues?.get(1)?.trim().takeUnless { it.isNullOrBlank() } ?: text
        val setCount = (match?.groupValues?.get(2)?.toIntOrNull() ?: 1).coerceIn(1, 8)
        val target = match?.groupValues?.get(3)?.toIntOrNull() ?: 8
        return PlanPrescription(name, setCount, target, secondsSuffix.containsMatchIn(text))
    }
}
