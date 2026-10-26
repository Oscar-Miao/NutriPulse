package com.example.appdemo.features.analytics

import kotlin.math.floor

/** Display-only allocation; the recorded gram values are never changed. */
object MacroPercentages {
    fun fromEnergy(energy: List<Double>): List<Int>? {
        if (energy.isEmpty() || energy.any { !it.isFinite() || it < 0.0 }) return null
        val total = energy.sum()
        if (!total.isFinite() || total <= 0.0) return null

        val exact = energy.map { it / total * 100.0 }
        val whole = exact.map { floor(it).toInt() }.toMutableList()
        val order = exact.indices.sortedWith(compareByDescending<Int> { exact[it] - whole[it] }
            .thenBy { it })
        repeat(100 - whole.sum()) { whole[order[it]]++ }
        return whole
    }
}
