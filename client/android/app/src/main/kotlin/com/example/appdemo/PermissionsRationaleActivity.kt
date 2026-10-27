package com.example.appdemo

import android.os.Bundle
import android.widget.TextView
import android.app.Activity

class PermissionsRationaleActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            textSize = 17f
            setPadding(36, 48, 36, 36)
            text = "NutriPulse 健康数据使用说明\n\n" +
                "在你授权并主动首次同步后，读取 Health Connect 中的活动热量、步数、心率、体重和体脂率；" +
                "健身页打开期间每分钟尝试刷新，离开页面后停止。" +
                "数据会发送到你在应用中设置的本地电脑服务，用于健身日记、能量统计和代谢目标校准。" +
                "我们不读取其他健康数据，也不把数据发送给资讯源。" +
                "你可以随时在 Health Connect 中撤销权限；撤销后停止新的读取。" +
                "本地服务历史记录需在本地电脑中自行删除。"
        })
    }
}
