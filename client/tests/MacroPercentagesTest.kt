package com.example.appdemo

import com.example.appdemo.features.analytics.MacroPercentages
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MacroPercentagesTest {
    @Test fun largestRemaindersMakeDisplayedTotalExactlyOneHundred() {
        assertEquals(listOf(29, 28, 43), MacroPercentages.fromEnergy(listOf(2.0, 2.0, 3.0)))
        assertEquals(listOf(34, 33, 33), MacroPercentages.fromEnergy(listOf(1.0, 1.0, 1.0)))
        assertEquals(listOf(17, 33, 50), MacroPercentages.fromEnergy(listOf(1.0, 2.0, 3.0)))
    }

    @Test fun zeroAndInvalidEnergyHaveNoFabricatedShare() {
        assertEquals(listOf(0, 0, 100), MacroPercentages.fromEnergy(listOf(0.0, 0.0, 9.0)))
        assertNull(MacroPercentages.fromEnergy(listOf(0.0, 0.0, 0.0)))
        assertNull(MacroPercentages.fromEnergy(listOf(4.0, Double.NaN, 9.0)))
        assertNull(MacroPercentages.fromEnergy(listOf(4.0, -1.0, 9.0)))
    }
}
