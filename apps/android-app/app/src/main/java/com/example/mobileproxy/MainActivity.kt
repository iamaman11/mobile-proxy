package com.example.mobileproxy

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private lateinit var statusText: TextView
    private lateinit var currentIpText: TextView
    private lateinit var refreshButton: Button
    private lateinit var rotateButton: Button
    private lateinit var runtimeClient: LocalRuntimeClient

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusText = findViewById(R.id.statusText)
        currentIpText = findViewById(R.id.currentIpText)
        refreshButton = findViewById(R.id.refreshRuntimeButton)
        rotateButton = findViewById(R.id.rotateIpButton)
        runtimeClient = LocalRuntimeClient(this)

        findViewById<TextView>(R.id.proxySummary).text = ProxySummary.text()
        refreshButton.setOnClickListener { refreshRuntimeStatus() }
        rotateButton.setOnClickListener { rotateIp() }
        refreshRuntimeStatus()
    }

    override fun onDestroy() {
        runtimeClient.close()
        super.onDestroy()
    }

    private fun refreshRuntimeStatus() {
        refreshButton.isEnabled = false
        statusText.setText(R.string.status_checking)
        runtimeClient.fetchStatus { result ->
            runOnUiThread {
                refreshButton.isEnabled = true
                result.onSuccess(::renderStatus).onFailure(::renderError)
            }
        }
    }

    private fun rotateIp() {
        rotateButton.isEnabled = false
        refreshButton.isEnabled = false
        statusText.setText(R.string.status_rotating)
        runtimeClient.rotate { result ->
            runOnUiThread {
                refreshButton.isEnabled = true
                result.onSuccess { job ->
                    if (job.status == "succeeded" && job.changed == true) {
                        currentIpText.text = getString(
                            R.string.current_ip,
                            job.newPublicIp ?: getString(R.string.ip_unknown),
                        )
                        statusText.text = getString(
                            R.string.status_rotation_succeeded,
                            job.oldPublicIp ?: getString(R.string.ip_unknown),
                            job.newPublicIp ?: getString(R.string.ip_unknown),
                        )
                    } else {
                        statusText.text = getString(R.string.status_rotation_failed, job.status)
                    }
                    refreshRuntimeStatus()
                }.onFailure(::renderError)
            }
        }
    }

    private fun renderStatus(status: LocalRuntimeStatus) {
        currentIpText.text = getString(
            R.string.current_ip,
            status.publicIp ?: getString(R.string.ip_unknown),
        )
        rotateButton.isEnabled = status.serving && !status.rotationInProgress
        statusText.text = when {
            status.rotationInProgress -> getString(R.string.status_rotation_in_progress)
            status.serving -> getString(R.string.status_ready, status.readiness)
            else -> getString(R.string.status_not_ready, status.readiness)
        }
    }

    private fun renderError(error: Throwable) {
        rotateButton.isEnabled = false
        statusText.text = getString(R.string.status_runtime_unavailable, error.message ?: "unknown error")
    }
}
