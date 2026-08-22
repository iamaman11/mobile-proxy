package com.example.mobileproxy

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

data class LocalRuntimeStatus(
    val publicIp: String?,
    val readiness: String,
    val serving: Boolean,
    val rotationInProgress: Boolean,
)

data class LocalRotationJob(
    val status: String,
    val oldPublicIp: String?,
    val newPublicIp: String?,
    val changed: Boolean?,
)

class LocalRuntimeClient(private val context: Context) {
    private val executor = Executors.newSingleThreadExecutor()

    fun close() {
        executor.shutdownNow()
    }

    fun fetchStatus(callback: (Result<LocalRuntimeStatus>) -> Unit) {
        executor.execute {
            callback(runCatching { parseStatus(request("/v1/ui/status", "GET")) })
        }
    }

    fun rotate(callback: (Result<LocalRotationJob>) -> Unit) {
        executor.execute {
            callback(runCatching {
                // The VM owns command scheduling.  The accepted id is a
                // control-plane command id, not a phone-local rotation job;
                // polling /v1/ui/jobs here would therefore report a false
                // failure before the phone receives the command.
                request("/v1/ui/ip/rotate", "POST")
                LocalRotationJob("queued", null, null, null)
            })
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
                throw IOException("runtime request failed (${connection.responseCode}): ${body.take(120)}")
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
        )
    }

    private fun parseJob(body: String): LocalRotationJob {
        val json = JSONObject(body)
        return LocalRotationJob(
            status = json.optString("status", "failed"),
            oldPublicIp = json.optNullableString("old_public_ip"),
            newPublicIp = json.optNullableString("new_public_ip"),
            changed = if (json.isNull("changed")) null else json.optBoolean("changed"),
        )
    }
}

private fun JSONObject.optNullableString(name: String): String? =
    if (isNull(name)) null else optString(name).takeIf { it.isNotBlank() }
