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
            appendLine("HTTP/HTTPS CONNECT: 34.118.26.142:3128")
            appendLine("Proxy login: relay4855cb91")
            appendLine("Proxy password: 4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9")
            appendLine("Mixed URL: http://relay4855cb91:4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9@34.118.26.142:1080")
            appendLine("SOCKS5 URL: socks5h://relay4855cb91:4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9@34.118.26.142:1081")
            appendLine("HTTP URL: http://relay4855cb91:4gKDPTqhCtFwSvy5FlsDJO91e7A4r3t9@34.118.26.142:3128")
            appendLine()
            appendLine("Test URLs: http://httpbin.org/ip and https://httpbin.org/ip")
            appendLine("Preferred for browsers: SOCKS5 :1081")
            appendLine("Preferred for raw CLI: HTTP CONNECT :3128")
        }

        findViewById<TextView>(R.id.proxySummary).text = relaySummary
    }
}
