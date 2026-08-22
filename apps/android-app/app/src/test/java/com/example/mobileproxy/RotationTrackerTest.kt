package com.example.mobileproxy

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RotationTrackerTest {
    @Test
    fun succeedsOnlyAfterIpChangedAndProxyRecovered() {
        val decision = RotationTracker.evaluate("1.1.1.1", status("2.2.2.2", true), 10_000)
        assertEquals(RotationDecision.Succeeded("1.1.1.1", "2.2.2.2"), decision)
    }

    @Test
    fun keepsWaitingWhileProxyIsRecovering() {
        val decision = RotationTracker.evaluate("1.1.1.1", status("2.2.2.2", false), 10_000)
        assertTrue(decision is RotationDecision.Waiting)
    }

    @Test
    fun reportsUnchangedIpAtTimeout() {
        val decision = RotationTracker.evaluate(
            "1.1.1.1",
            status("1.1.1.1", true),
            RotationTracker.TIMEOUT_MILLIS,
        )
        assertEquals(RotationDecision.Failed("оператор не выдал новый IP"), decision)
    }

    private fun status(ip: String?, serving: Boolean) = LocalRuntimeStatus(
        publicIp = ip,
        readiness = if (serving) "healthy" else "waiting_cellular",
        serving = serving,
        rotationInProgress = !serving,
        tunnelOwner = "first_party_android_egress",
    )
}
