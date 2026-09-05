package com.example.mobileproxy

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        restoreFromBoot(context, intent.action)
    }

    internal fun restoreFromBoot(
        context: Context,
        action: String?,
        prepareVpn: (Context) -> Intent? = { VpnService.prepare(it) },
        startTunnel: (Context) -> Unit = ::startTunnelService,
    ) {
        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != Intent.ACTION_LOCKED_BOOT_COMPLETED
        ) {
            return
        }
        if (!TunnelState.isDesired(context)) {
            return
        }
        if (prepareVpn(context) != null) {
            return
        }
        startTunnel(context)
    }
}

internal fun startTunnelService(context: Context) {
    val serviceIntent = MobileProxyVpnService.startIntent(context)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(serviceIntent)
    } else {
        context.startService(serviceIntent)
    }
}
