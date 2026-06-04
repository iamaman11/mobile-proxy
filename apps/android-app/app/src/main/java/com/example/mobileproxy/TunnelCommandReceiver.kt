package com.example.mobileproxy

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build

class TunnelCommandReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_START -> startTunnel(context)
            ACTION_STOP -> {
                TunnelState.setDesired(context, false)
                context.startService(MobileProxyVpnService.stopIntent(context))
            }
        }
    }

    private fun startTunnel(context: Context) {
        if (VpnService.prepare(context) != null) {
            return
        }
        TunnelState.setDesired(context, true)
        val serviceIntent = MobileProxyVpnService.startIntent(context)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }

    companion object {
        const val ACTION_START = "com.example.mobileproxy.action.START_TUNNEL"
        const val ACTION_STOP = "com.example.mobileproxy.action.STOP_TUNNEL"
    }
}
