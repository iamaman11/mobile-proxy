package com.example.mobileproxy

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import java.io.ByteArrayInputStream

class MobileProxyVpnService : Service() {
    private val tunnel = MobileProxyTunnel()
    private var backend: GoBackend? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> stopTunnel()
            else -> startTunnel()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopTunnel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startTunnel() {
        startForeground(NOTIFICATION_ID, buildNotification())
        if (VpnService.prepare(this) != null) {
            TunnelState.setLastError(this, "vpn consent is required")
            return
        }

        val configText = TunnelState.getConfig(this)
        if (configText.isNullOrBlank()) {
            TunnelState.setLastError(this, "wireguard config is missing")
            return
        }

        try {
            val parsed = Config.parse(ByteArrayInputStream(configText.toByteArray(Charsets.UTF_8)))
            val currentBackend = backend ?: GoBackend(applicationContext).also { backend = it }
            val state = currentBackend.setState(tunnel, Tunnel.State.UP, parsed)
            TunnelState.setLastState(this, state.name)
            TunnelState.setLastError(this, null)
        } catch (error: Exception) {
            TunnelState.setLastError(this, error.message ?: error.javaClass.name)
        }
    }

    private fun stopTunnel() {
        try {
            backend?.setState(tunnel, Tunnel.State.DOWN, null)
            TunnelState.setLastState(this, Tunnel.State.DOWN.name)
            TunnelState.setLastError(this, null)
        } catch (error: Exception) {
            TunnelState.setLastError(this, error.message ?: error.javaClass.name)
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun buildNotification(): Notification {
        ensureNotificationChannel()
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle(getString(R.string.vpn_notification_title))
            .setContentText(getString(R.string.vpn_notification_text))
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }
        val manager = getSystemService(NotificationManager::class.java)
        val existing = manager.getNotificationChannel(CHANNEL_ID)
        if (existing != null) {
            return
        }
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                getString(R.string.vpn_notification_channel),
                NotificationManager.IMPORTANCE_LOW
            )
        )
    }

    companion object {
        private const val ACTION_START = "com.example.mobileproxy.service.START"
        private const val ACTION_STOP = "com.example.mobileproxy.service.STOP"
        private const val CHANNEL_ID = "mobile_proxy_tunnel"
        private const val NOTIFICATION_ID = 4201

        fun startIntent(context: Context): Intent =
            Intent(context, MobileProxyVpnService::class.java).setAction(ACTION_START)

        fun stopIntent(context: Context): Intent =
            Intent(context, MobileProxyVpnService::class.java).setAction(ACTION_STOP)
    }
}

private class MobileProxyTunnel : Tunnel {
    override fun getName(): String = "mobile-proxy"

    override fun onStateChange(newState: Tunnel.State) = Unit
}
