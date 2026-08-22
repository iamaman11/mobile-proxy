package com.example.mobileproxy

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

data class LocalRuntimeStatus(
    val publicIp: String?,
    val readiness: String,
    val serving: Boolean,
    val rotationInProgress: Boolean,
    val tunnelOwner: String?,
)

class LocalRuntimeClient(private val context: Context) {
    private val executor = Executors.newSingleThreadExecutor()
    private val closed = AtomicBoolean(false)

    fun close() {
        closed.set(true)
        executor.shutdownNow()
    }

    fun fetchStatus(callback: (Result<LocalRuntimeStatus>) -> Unit) {
        executor.execute {
            callback(runCatching { parseStatus(request("/v1/ui/status", "GET")) })
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
                if (issueCommand) request("/v1/ui/ip/rotate", "POST")
                val startedAt = System.currentTimeMillis()
                while (!closed.get()) {
                    val elapsed = System.currentTimeMillis() - startedAt
                    val status = try {
                        parseStatus(request("/v1/ui/status", "GET"))
                    } catch (error: RuntimeRequestException) {
                        if (error.statusCode == 401) throw error
                        if (elapsed >= RotationTracker.TIMEOUT_MILLIS) {
                            throw IOException(
                                "rotation status was unavailable until timeout",
                                error,
                            )
                        }
                        Thread.sleep(POLL_INTERVAL_MILLIS)
                        continue
                    } catch (error: IOException) {
                        if (elapsed >= RotationTracker.TIMEOUT_MILLIS) {
                            throw IOException(
                                "rotation status was unavailable until timeout",
                                error,
                            )
                        }
                        Thread.sleep(POLL_INTERVAL_MILLIS)
                        continue
                    }
                    onStatus(status)
                    val decision = RotationTracker.evaluate(
                        oldIp,
                        status,
                        elapsed,
                    )
                    if (decision !is RotationDecision.Waiting) return@runCatching decision
                    Thread.sleep(POLL_INTERVAL_MILLIS)
                }
                throw IOException("operation cancelled")
            }
            if (!closed.get()) callback(result)
        }
    }

    private fun request(path: String, method: String): String {
        val token = TunnelState.getLocalControlToken(context)
            ?.takeIf { it.isNotBlank() }
            ?: throw IOException("local control is not ready")
        val connection = (URL("http://localhost:8088$path").openConnection() as HttpURLConnection)
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

private class RuntimeRequestException(
    val statusCode: Int,
    message: String,
) : IOException(message)

private fun JSONObject.optNullableString(name: String): String? =
    if (isNull(name)) null else optString(name).takeIf { it.isNotBlank() }
