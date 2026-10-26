package com.example.appdemo.core.design_system

import android.content.Context
import com.example.appdemo.core.networking.ApiClient

interface ScreenHost {
    val screenContext: Context
    val api: ApiClient
    fun navigate(tab: Int)
    fun refresh()
    fun message(text: String)
    fun undoableMessage(text: String, undo: () -> Unit)
    fun choosePhoto(done: (ByteArray, String) -> Unit)
    fun syncHealthConnect()
    fun revokeDeviceConnection(connectionId: String, provider: String, deleteHistory: Boolean)
    fun exportPersonalData(category: String)
    fun exportDiagnosticLogs()
    fun exportAnalyticsPdf(period: String, end: String)
    fun beginPersonalDataDeletion(category: String): Boolean
    fun cancelPersonalDataDeletion(category: String)
    fun personalDataDeleted(category: String)
}
