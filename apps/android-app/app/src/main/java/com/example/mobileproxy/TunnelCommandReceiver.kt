package com.example.mobileproxy

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.util.Base64

class TunnelCommandReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_SET_CONFIG -> {
                val config = intent.getStringExtra(EXTRA_CONFIG)
                    ?: intent.getStringExtra(EXTRA_CONFIG_B64)?.let(::decodeConfig)
                if (!config.isNullOrBlank()) {
                    runCatching { TunnelState.setConfig(context, config) }
                        .onFailure {
                            TunnelState.setLastError(
                                context,
                                "secure wireguard config storage is unavailable",
                            )
                        }
                }
            }
            ACTION_START -> startTunnel(context)
            ACTION_STOP -> {
                TunnelState.setDesired(context, false)
                context.startService(MobileProxyVpnService.stopIntent(context))
            }
            ACTION_SET_LOCAL_CONTROL_TOKEN -> {
                intent.getStringExtra(EXTRA_CONTROL_TOKEN)
                    ?.takeIf { it.isNotBlank() }
                    ?.let { TunnelState.setLocalControlToken(context, it) }
            }
            ACTION_SET_EGRESS_CONFIG -> {
                val username = intent.getStringExtra(EXTRA_EGRESS_USERNAME)
                val password = intent.getStringExtra(EXTRA_EGRESS_PASSWORD)
                val port = intent.getIntExtra(EXTRA_EGRESS_PORT, -1)
                if (!username.isNullOrBlank() && !password.isNullOrBlank()) {
                    runCatching { TunnelState.setEgressConfig(context, port, username, password) }
                }
            }
            ACTION_START_EGRESS -> startEgress(context)
            ACTION_STOP_EGRESS -> context.startService(CellularEgressService.stopIntent(context))
        }
    }

    private fun startTunnel(context: Context) {
        if (VpnService.prepare(context) != null) {
            return
        }
        TunnelState.setDesired(context, true)
        startTunnelService(context)
    }

    private fun startEgress(context: Context) {
        val serviceIntent = CellularEgressService.startIntent(context)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }

    companion object {
        const val ACTION_START = "com.example.mobileproxy.action.START_TUNNEL"
        const val ACTION_STOP = "com.example.mobileproxy.action.STOP_TUNNEL"
        const val ACTION_SET_CONFIG = "com.example.mobileproxy.action.SET_TUNNEL_CONFIG"
        const val ACTION_SET_LOCAL_CONTROL_TOKEN = "com.example.mobileproxy.action.SET_LOCAL_CONTROL_TOKEN"
        const val EXTRA_CONFIG = "config"
        const val EXTRA_CONFIG_B64 = "config_b64"
        const val EXTRA_CONTROL_TOKEN = "control_token"
        const val ACTION_SET_EGRESS_CONFIG = "com.example.mobileproxy.action.SET_EGRESS_CONFIG"
        const val ACTION_START_EGRESS = "com.example.mobileproxy.action.START_CELLULAR_EGRESS"
        const val ACTION_STOP_EGRESS = "com.example.mobileproxy.action.STOP_CELLULAR_EGRESS"
        const val EXTRA_EGRESS_PORT = "egress_port"
        const val EXTRA_EGRESS_USERNAME = "egress_username"
        const val EXTRA_EGRESS_PASSWORD = "egress_password"

        private fun decodeConfig(raw: String): String =
            String(Base64.decode(raw, Base64.DEFAULT), Charsets.UTF_8)
    }
}
