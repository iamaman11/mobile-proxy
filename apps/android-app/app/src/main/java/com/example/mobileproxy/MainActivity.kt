package com.example.mobileproxy

import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.activity.result.contract.ActivityResultContracts

class MainActivity : AppCompatActivity() {
    private lateinit var statusText: TextView

    private val vpnPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) {
        updateVpnStatus()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusText = findViewById(R.id.statusText)

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
        findViewById<Button>(R.id.prepareVpnButton).setOnClickListener {
            requestVpnPermission()
        }
        findViewById<Button>(R.id.startTunnelButton).setOnClickListener {
            sendTunnelCommand(this, TunnelCommandReceiver.ACTION_START)
            statusText.setText(R.string.status_started)
        }
        findViewById<Button>(R.id.stopTunnelButton).setOnClickListener {
            sendTunnelCommand(this, TunnelCommandReceiver.ACTION_STOP)
            statusText.setText(R.string.status_stopped)
        }
        updateVpnStatus()
    }

    private fun requestVpnPermission() {
        val intent = VpnService.prepare(this)
        if (intent == null) {
            statusText.setText(R.string.status_prepared)
        } else {
            vpnPermissionLauncher.launch(intent)
        }
    }

    private fun updateVpnStatus() {
        if (VpnService.prepare(this) == null) {
            statusText.setText(R.string.status_prepared)
        } else {
            statusText.setText(R.string.status_needs_consent)
        }
    }

    private fun sendTunnelCommand(context: Context, action: String) {
        context.sendBroadcast(Intent(action).setPackage(context.packageName))
    }
}
