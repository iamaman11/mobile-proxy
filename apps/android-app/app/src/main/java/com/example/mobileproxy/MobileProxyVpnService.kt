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
    private var session: TunnelSession? = null

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
            recordTransition(TunnelTransition.Failed("vpn consent is required"))
            return
        }

        val configText = TunnelState.getConfig(this)
        if (configText.isNullOrBlank()) {
            recordTransition(TunnelTransition.Failed("wireguard config is missing"))
            return
        }

        val transition = try {
            val currentSession = session
                ?: TunnelSession(GoTunnelBackend(applicationContext, tunnel)).also { session = it }
            currentSession.start(configText)
        } catch (error: Exception) {
            TunnelTransition.Failed(errorMessage(error))
        }
        recordTransition(transition)
    }

    private fun stopTunnel() {
        val transition = session?.stop() ?: TunnelTransition.Applied(Tunnel.State.DOWN)
        recordTransition(transition)
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun recordTransition(transition: TunnelTransition) {
        when (transition) {
            is TunnelTransition.Applied -> {
                TunnelState.setLastState(this, transition.state.name)
                TunnelState.setLastError(this, null)
            }
            is TunnelTransition.Failed -> TunnelState.setLastError(this, transition.error)
        }
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

internal fun interface TunnelBackend {
    fun setState(state: Tunnel.State, config: Config?): Tunnel.State
}

private class GoTunnelBackend(
    context: Context,
    private val tunnel: Tunnel,
) : TunnelBackend {
    private val backend = GoBackend(context)

    override fun setState(state: Tunnel.State, config: Config?): Tunnel.State =
        backend.setState(tunnel, state, config)
}

internal sealed interface TunnelTransition {
    data class Applied(val state: Tunnel.State) : TunnelTransition
    data class Failed(val error: String) : TunnelTransition
}

internal class TunnelSession(private val backend: TunnelBackend) {
    fun start(configText: String): TunnelTransition = try {
        val parsed = Config.parse(ByteArrayInputStream(configText.toByteArray(Charsets.UTF_8)))
        TunnelTransition.Applied(backend.setState(Tunnel.State.UP, parsed))
    } catch (error: Exception) {
        TunnelTransition.Failed(errorMessage(error))
    }

    fun stop(): TunnelTransition = try {
        backend.setState(Tunnel.State.DOWN, null)
        TunnelTransition.Applied(Tunnel.State.DOWN)
    } catch (error: Exception) {
        TunnelTransition.Failed(errorMessage(error))
    }
}

private fun errorMessage(error: Exception): String =
    error.message ?: error.javaClass.name

private class MobileProxyTunnel : Tunnel {
    override fun getName(): String = "mobile-proxy"

    override fun onStateChange(newState: Tunnel.State) = Unit
}
