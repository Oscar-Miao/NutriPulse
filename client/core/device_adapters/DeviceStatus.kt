package com.example.appdemo.core.device_adapters

/** Device integrations implement this contract and normalize samples before upload. */
data class DeviceStatus(val provider: String, val connected: Boolean, val lastSyncedAt: String?)
