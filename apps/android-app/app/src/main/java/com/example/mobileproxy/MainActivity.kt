package com.example.mobileproxy

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val relaySummary = buildString {
            appendLine("Relay IP: 34.118.26.142")
            appendLine("Mixed: 34.118.26.142:1080")
            appendLine("SOCKS5: 34.118.26.142:1081")
            appendLine("HTTP/HTTPS: 34.118.26.142:3128")
            appendLine()
            appendLine("Use current runtime credentials from operations docs.")
            appendLine("Preferred for browsers: SOCKS5 :1081")
            appendLine("Preferred for raw CLI: HTTP :1080")
        }

        findViewById<TextView>(R.id.proxySummary).text = relaySummary
    }
}
