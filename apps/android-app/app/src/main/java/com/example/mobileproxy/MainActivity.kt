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

        findViewById<TextView>(R.id.proxySummary).text = ProxySummary.text()
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
