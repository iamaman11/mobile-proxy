package com.example.mobileproxy

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

data class LocalRuntimeStatus(
    val publicIp: String?,
    val readiness: String,
    val serving: Boolean,
    val rotationInProgress: Boolean,
    val tunnelOwner: String?,
)

internal fun interface RuntimeTransport {
    fun request(path: String, method: String): String
}

internal interface RuntimeTiming {
    fun nowMillis(): Long
    fun sleep(millis: Long)
}

private object SystemRuntimeTiming : RuntimeTiming {
    override fun nowMillis(): Long = System.currentTimeMillis()
    override fun sleep(millis: Long) = Thread.sleep(millis)
}

internal class HttpRuntimeTransport(
    private val tokenProvider: () -> String?,
    private val connectionFactory: (URL) -> HttpURLConnection = {
        it.openConnection() as HttpURLConnection
    },
) : RuntimeTransport {
    override fun request(path: String, method: String): String {
        val token = tokenProvider()
            ?.takeIf { it.isNotBlank() }
            ?: throw IOException("local control is not ready")
        val connection = connectionFactory(URL("http://localhost:8088$path"))
        try {
            connection.requestMethod = method
            connection.connectTimeout = 5_000
            connection.readTimeout = 10_000
            connection.setRequestProperty("Authorization", "Bearer $token")
            if (method == "POST") {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write("{}".toByteArray()) }
            }
            val stream = if (connection.responseCode in 200..299) {
                connection.inputStream
            } else {
                connection.errorStream
            }
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (connection.responseCode !in 200..299) {
                throw RuntimeRequestException(
                    connection.responseCode,
                    "runtime request failed (" + connection.responseCode + "): " + body.take(120),
                )
            }
            return body
        } finally {
            connection.disconnect()
        }
    }
}

class LocalRuntimeClient private constructor(
    private val transport: RuntimeTransport,
    private val timing: RuntimeTiming,
    private val executor: ExecutorService,
) {
    constructor(context: Context) : this(
        HttpRuntimeTransport(
            tokenProvider = { TunnelState.getLocalControlToken(context) },
        ),
        SystemRuntimeTiming,
        Executors.newFixedThreadPool(2),
    )

    internal constructor(transport: RuntimeTransport, timing: RuntimeTiming) : this(
        transport,
        timing,
        Executors.newFixedThreadPool(2),
    )

    private val closed = AtomicBoolean(false)

    fun close() {
        closed.set(true)
        executor.shutdownNow()
    }

    fun fetchStatus(callback: (Result<LocalRuntimeStatus>) -> Unit) {
        executor.execute {
            callback(runCatching { parseStatus(transport.request("/v1/ui/status", "GET")) })
        }
    }

    fun rotateAndMonitor(
        oldIp: String?,
        issueCommand: Boolean,
        onStatus: (LocalRuntimeStatus) -> Unit,
        callback: (Result<RotationDecision>) -> Unit,
    ) {
        executor.execute {
            val result = runCatching {
                if (issueCommand) transport.request("/v1/ui/ip/rotate", "POST")
                val startedAt = timing.nowMillis()
                while (!closed.get()) {
                    val elapsed = timing.nowMillis() - startedAt
                    val status = try {
                        parseStatus(transport.request("/v1/ui/status", "GET"))
                    } catch (error: RuntimeRequestException) {
                        if (error.statusCode == 401) throw error
                        if (elapsed >= RotationTracker.TIMEOUT_MILLIS) {
                            throw IOException(
                                "rotation status was unavailable until timeout",
                                error,
                            )
                        }
                        timing.sleep(POLL_INTERVAL_MILLIS)
                        continue
                    } catch (error: IOException) {
                        if (elapsed >= RotationTracker.TIMEOUT_MILLIS) {
                            throw IOException(
                                "rotation status was unavailable until timeout",
                                error,
                            )
                        }
                        timing.sleep(POLL_INTERVAL_MILLIS)
                        continue
                    }
                    onStatus(status)
                    val decision = RotationTracker.evaluate(
                        oldIp,
                        status,
                        elapsed,
                    )
                    if (decision !is RotationDecision.Waiting) return@runCatching decision
                    timing.sleep(POLL_INTERVAL_MILLIS)
                }
                throw IOException("operation cancelled")
            }
            if (!closed.get()) callback(result)
        }
    }

    private fun parseStatus(body: String): LocalRuntimeStatus {
        val json = JSONObject(body)
        return LocalRuntimeStatus(
            publicIp = json.optNullableString("public_ip"),
            readiness = json.optString("readiness", "unknown"),
            serving = json.optBoolean("serving", false),
            rotationInProgress = json.optBoolean("rotation_in_progress", false),
            tunnelOwner = json.optNullableString("tunnel_owner"),
        )
    }

    private companion object {
        const val POLL_INTERVAL_MILLIS = 2_000L
    }
}

internal class RuntimeRequestException(
    val statusCode: Int,
    message: String,
) : IOException(message)

private fun JSONObject.optNullableString(name: String): String? =
    if (isNull(name)) null else optString(name).takeIf { it.isNotBlank() }
