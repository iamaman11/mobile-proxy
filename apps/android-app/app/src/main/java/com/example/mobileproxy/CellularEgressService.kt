package com.example.mobileproxy

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * A loopback-only SOCKS5 endpoint whose outbound sockets are explicitly bound to a
 * validated cellular [Network].  The listener is intentionally not public: the
 * authenticated native reverse tunnel is its only consumer.
 */
class CellularEgressService : Service() {
    private val workers: ExecutorService = Executors.newCachedThreadPool()
    @Volatile private var server: ServerSocket? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopAgent()
        } else {
            // Provisioning may rotate SOCKS credentials while the process is
            // alive. Rebind so the listener never keeps stale in-memory auth.
            server?.close()
            server = null
            startAgent()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopAgent()
        super.onDestroy()
    }

    private fun startAgent() {
        if (server != null) return
        // Android requires a foreground notification immediately after
        // startForegroundService(), including during first-boot provisioning
        // when private storage may still be unavailable.
        startForeground(NOTIFICATION_ID, notification())
        val config = TunnelState.getEgressConfig(this)
            ?: TunnelState.consumeProvisionedEgressConfig(this)
            ?: run {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return
            }
        val listener = ServerSocket()
        listener.reuseAddress = true
        // The rooted reverse-tunnel client uses an IPv4 loopback target.
        // Android may otherwise choose ::1 here, leaving the authenticated
        // app listener unreachable even though the service is running.
        listener.bind(InetSocketAddress(InetAddress.getByName("127.0.0.1"), config.port))
        server = listener
        workers.execute {
            while (!listener.isClosed) {
                runCatching { listener.accept() }.getOrNull()?.let { socket ->
                    workers.execute { socket.use { handleClient(it, config) } }
                }
            }
        }
    }

    private fun stopAgent() {
        server?.close()
        server = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun handleClient(client: Socket, config: TunnelState.EgressConfig) {
        client.soTimeout = HANDSHAKE_TIMEOUT_MS
        val input = BufferedInputStream(client.getInputStream())
        val output = BufferedOutputStream(client.getOutputStream())
        if (input.read() != SOCKS_VERSION) return
        val methods = input.readExactly(input.read().coerceIn(0, 16)) ?: return
        if (!methods.contains(USERNAME_PASSWORD.toByte())) {
            output.write(byteArrayOf(SOCKS_VERSION.toByte(), NO_ACCEPTABLE.toByte())); output.flush(); return
        }
        output.write(byteArrayOf(SOCKS_VERSION.toByte(), USERNAME_PASSWORD.toByte())); output.flush()
        if (input.read() != AUTH_VERSION) return
        val username = input.readExactly(input.read().coerceIn(0, 255)) ?: return
        val password = input.readExactly(input.read().coerceIn(0, 255)) ?: return
        if (!MessageDigest.isEqual(username, config.username.toByteArray()) ||
            !MessageDigest.isEqual(password, config.password.toByteArray())) {
            output.write(byteArrayOf(AUTH_VERSION.toByte(), 1)); output.flush(); return
        }
        output.write(byteArrayOf(AUTH_VERSION.toByte(), 0)); output.flush()
        if (input.read() != SOCKS_VERSION || input.read() != CONNECT || input.read() != 0) return
        val address = readAddress(input) ?: return
        val port = (input.read() shl 8) or input.read()
        if (port !in 1..65535) return
        val network = validatedCellularNetwork() ?: run { reply(output, NETWORK_UNREACHABLE); return }
        val targets = runCatching { network.getAllByName(address).toList() }.getOrNull()
            ?.distinct()
            ?.take(MAX_TARGET_ADDRESSES)
            .orEmpty()
        if (targets.isEmpty()) {
            reply(output, HOST_UNREACHABLE)
            return
        }
        val upstream = connectUpstream(network, targets, port)
        if (upstream == null) {
            reply(output, HOST_UNREACHABLE)
            return
        }
        try {
            reply(output, SUCCESS)
            client.soTimeout = 0
            bridge(client, upstream)
        } catch (_: Exception) {
            upstream.close()
        }
    }

    private fun connectUpstream(network: Network, targets: List<InetAddress>, port: Int): Socket? {
        for (target in targets) {
            val candidate = Socket()
            try {
                network.bindSocket(candidate)
                candidate.connect(InetSocketAddress(target, port), CONNECT_TIMEOUT_MS)
                return candidate
            } catch (_: Exception) {
                candidate.close()
            }
        }
        return null
    }

    @Suppress("DEPRECATION") // API 24 support needs enumeration; every selected Network is capability-checked.
    private fun validatedCellularNetwork(): Network? {
        val manager = getSystemService(ConnectivityManager::class.java)
        return manager.allNetworks.firstOrNull { network ->
            manager.getNetworkCapabilities(network)?.let { caps ->
                caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) &&
                    caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                    caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            } == true
        }
    }

    private fun bridge(left: Socket, right: Socket) {
        val first = workers.submit { runCatching { left.getInputStream().copyTo(right.getOutputStream()); right.shutdownOutput() } }
        runCatching { right.getInputStream().copyTo(left.getOutputStream()); left.shutdownOutput() }
        first.get()
        right.close()
    }

    private fun readAddress(input: BufferedInputStream): String? = when (input.read()) {
        IPV4 -> input.readExactly(4)?.joinToString(".") { (it.toInt() and 0xff).toString() }
        DOMAIN -> input.readExactly(input.read().coerceIn(1, 253))?.toString(Charsets.UTF_8)
        IPV6 -> input.readExactly(16)?.let { InetAddress.getByAddress(it).hostAddress }
        else -> null
    }

    private fun reply(output: BufferedOutputStream, status: Int) {
        output.write(byteArrayOf(SOCKS_VERSION.toByte(), status.toByte(), 0, IPV4.toByte(), 0, 0, 0, 0, 0, 0))
        output.flush()
    }

    private fun BufferedInputStream.readExactly(count: Int): ByteArray? {
        if (count == 0) return ByteArray(0)
        val bytes = ByteArray(count)
        var offset = 0
        while (offset < count) {
            val read = read(bytes, offset, count - offset)
            if (read < 0) return null
            offset += read
        }
        return bytes
    }

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && manager.getNotificationChannel(CHANNEL_ID) == null) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Mobile Proxy cellular egress", NotificationManager.IMPORTANCE_LOW))
        }
        val activity = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL_ID).setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle("Mobile Proxy cellular egress").setContentText("Validated cellular data-plane active")
            .setContentIntent(activity).setOngoing(true).build()
    }

    companion object {
        private const val ACTION_STOP = "com.example.mobileproxy.service.STOP_CELLULAR_EGRESS"
        private const val CHANNEL_ID = "mobile_proxy_cellular_egress"
        private const val NOTIFICATION_ID = 4202
        private const val SOCKS_VERSION = 5
        private const val AUTH_VERSION = 1
        private const val USERNAME_PASSWORD = 2
        private const val NO_ACCEPTABLE = 255
        private const val CONNECT = 1
        private const val IPV4 = 1
        private const val DOMAIN = 3
        private const val IPV6 = 4
        private const val SUCCESS = 0
        private const val NETWORK_UNREACHABLE = 3
        private const val HOST_UNREACHABLE = 4
        private const val HANDSHAKE_TIMEOUT_MS = 15_000
        private const val CONNECT_TIMEOUT_MS = 15_000
        private const val MAX_TARGET_ADDRESSES = 4

        fun startIntent(context: Context) = Intent(context, CellularEgressService::class.java)
        fun stopIntent(context: Context) = Intent(context, CellularEgressService::class.java).setAction(ACTION_STOP)
    }
}
