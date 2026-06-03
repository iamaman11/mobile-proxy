package com.example.mobileproxy

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val relaySummary = buildString {
            appendLine("Relay IP: 34.118.88.54")
            appendLine("Mixed: 34.118.88.54:1080")
            appendLine("SOCKS5: 34.118.88.54:1081")
            appendLine("HTTP/HTTPS CONNECT: 34.118.88.54:3128")
            appendLine("Runtime credentials are injected from secure env/manifests")
            appendLine("SOCKS5 URL: socks5h://<user>:<pass>@34.118.88.54:1081")
            appendLine("HTTP URL: http://<user>:<pass>@34.118.88.54:3128")
            appendLine()
            appendLine("Test URLs: http://httpbin.org/ip and https://example.com")
            appendLine("Preferred for browsers: SOCKS5 :1081")
            appendLine("Preferred for raw CLI: HTTP CONNECT :3128")
        }

        findViewById<TextView>(R.id.proxySummary).text = relaySummary
    }
}
