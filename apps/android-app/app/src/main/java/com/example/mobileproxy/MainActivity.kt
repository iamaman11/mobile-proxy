package com.example.mobileproxy

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.edit
import com.google.android.material.progressindicator.CircularProgressIndicator
import java.text.DateFormat
import java.util.Date

class MainActivity : AppCompatActivity() {
    private lateinit var statusText: TextView
    private lateinit var currentIpText: TextView
    private lateinit var refreshButton: Button
    private lateinit var rotateButton: Button
    private lateinit var stateBadge: TextView
    private lateinit var lastUpdatedText: TextView
    private lateinit var progress: CircularProgressIndicator
    private lateinit var runtimeClient: LocalRuntimeClient
    private var latestStatus: LocalRuntimeStatus? = null
    private var monitoringRotation = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusText = findViewById(R.id.statusText)
        currentIpText = findViewById(R.id.currentIpText)
        refreshButton = findViewById(R.id.refreshRuntimeButton)
        rotateButton = findViewById(R.id.rotateIpButton)
        stateBadge = findViewById(R.id.stateBadge)
        lastUpdatedText = findViewById(R.id.lastUpdatedText)
        progress = findViewById(R.id.progressIndicator)
        runtimeClient = LocalRuntimeClient(this)

        findViewById<TextView>(R.id.proxySummary).text = ProxySummary.text()
        refreshButton.setOnClickListener { refreshRuntimeStatus() }
        rotateButton.setOnClickListener { rotateIp() }
    }

    override fun onResume() {
        super.onResume()
        refreshRuntimeStatus()
    }

    override fun onDestroy() {
        runtimeClient.close()
        super.onDestroy()
    }

    private fun refreshRuntimeStatus() {
        refreshButton.isEnabled = false
        progress.visibility = View.VISIBLE
        if (!monitoringRotation) statusText.setText(R.string.status_checking)
        runtimeClient.fetchStatus { result ->
            runOnUiThread {
                refreshButton.isEnabled = true
                progress.visibility = View.GONE
                result.onSuccess { status ->
                    if (monitoringRotation) {
                        renderRotationStatus(status)
                    } else {
                        renderStatus(status)
                        pendingOldIp()?.let { resumeRotation(it) }
                    }
                }.onFailure(::renderError)
            }
        }
    }

    private fun rotateIp() {
        val oldIp = latestStatus?.publicIp
        if (oldIp.isNullOrBlank()) {
            renderError(IllegalStateException(getString(R.string.error_ip_unknown)))
            return
        }
        preferences().edit(commit = true) { putString(PENDING_OLD_IP, oldIp) }
        monitorRotation(oldIp, issueCommand = true)
    }

    private fun resumeRotation(oldIp: String) {
        if (!monitoringRotation) monitorRotation(oldIp, issueCommand = false)
    }

    private fun monitorRotation(oldIp: String, issueCommand: Boolean) {
        monitoringRotation = true
        rotateButton.isEnabled = false
        refreshButton.isEnabled = true
        progress.visibility = View.VISIBLE
        stateBadge.setText(R.string.state_rotating)
        statusText.setText(
            if (issueCommand) R.string.status_rotation_queued else R.string.status_rotation_in_progress,
        )
        runtimeClient.rotateAndMonitor(
            oldIp = oldIp,
            issueCommand = issueCommand,
            onStatus = { status -> runOnUiThread { renderRotationStatus(status) } },
        ) { result ->
            runOnUiThread {
                monitoringRotation = false
                progress.visibility = View.GONE
                refreshButton.isEnabled = true
                result.onSuccess { decision ->
                    preferences().edit(commit = true) { remove(PENDING_OLD_IP) }
                    when (decision) {
                        is RotationDecision.Succeeded -> {
                            currentIpText.text = decision.newIp
                            stateBadge.setText(R.string.state_ready)
                            statusText.text = getString(
                                R.string.status_rotation_succeeded,
                                decision.oldIp,
                                decision.newIp,
                            )
                        }
                        is RotationDecision.Failed -> {
                            stateBadge.setText(R.string.state_error)
                            statusText.text = getString(
                                R.string.status_rotation_failed,
                                decision.reason,
                            )
                        }
                        RotationDecision.Waiting -> Unit
                    }
                    refreshRuntimeStatus()
                }.onFailure {
                    preferences().edit(commit = true) { remove(PENDING_OLD_IP) }
                    renderError(it)
                }
            }
        }
    }

    private fun renderStatus(status: LocalRuntimeStatus) {
        latestStatus = status
        currentIpText.text = status.publicIp ?: getString(R.string.ip_unknown)
        rotateButton.isEnabled = status.serving && !status.rotationInProgress
        stateBadge.setText(
            when {
                status.rotationInProgress -> R.string.state_rotating
                status.serving -> R.string.state_ready
                else -> R.string.state_error
            },
        )
        statusText.text = when {
            status.rotationInProgress -> getString(R.string.status_rotation_in_progress)
            status.serving -> getString(
                R.string.status_ready,
                status.tunnelOwner ?: status.readiness,
            )
            else -> getString(R.string.status_not_ready, status.readiness)
        }
        lastUpdatedText.text = getString(
            R.string.last_updated,
            DateFormat.getTimeInstance(DateFormat.SHORT).format(Date()),
        )
    }

    private fun renderRotationStatus(status: LocalRuntimeStatus) {
        latestStatus = status
        currentIpText.text = status.publicIp ?: getString(R.string.ip_unknown)
        stateBadge.setText(R.string.state_rotating)
        statusText.setText(
            if (status.rotationInProgress) {
                R.string.status_rotation_in_progress
            } else {
                R.string.status_rotation_waiting
            },
        )
    }

    private fun renderError(error: Throwable) {
        progress.visibility = View.GONE
        rotateButton.isEnabled = false
        refreshButton.isEnabled = true
        stateBadge.setText(R.string.state_error)
        val raw = error.message.orEmpty()
        val message = when {
            raw.contains("401") || raw.contains("invalid bearer token") ->
                getString(R.string.error_control_token)
            raw.contains("timed out", ignoreCase = true) ->
                getString(R.string.error_timeout)
            raw.isBlank() -> getString(R.string.error_unknown)
            else -> raw.take(180)
        }
        statusText.text = getString(R.string.status_runtime_unavailable, message)
    }

    private fun preferences() = getSharedPreferences(UI_PREFS, MODE_PRIVATE)
    private fun pendingOldIp(): String? = preferences().getString(PENDING_OLD_IP, null)

    private companion object {
        const val UI_PREFS = "mobile_proxy_ui"
        const val PENDING_OLD_IP = "pending_rotation_old_ip"
    }
}
