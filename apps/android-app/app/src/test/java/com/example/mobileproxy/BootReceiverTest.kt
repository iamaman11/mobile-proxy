package com.example.mobileproxy

import android.content.Context
import android.content.Intent
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class BootReceiverTest {
    private lateinit var context: Context

    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        devicePrefs().edit().clear().commit()
    }

    @After
    fun tearDown() {
        devicePrefs().edit().clear().commit()
    }

    @Test
    fun desiredFalseDoesNotProbeConsentOrStartService() {
        TunnelState.setDesired(context, false)
        var consentProbed = false
        var started = false

        BootReceiver().restoreFromBoot(
            context,
            Intent.ACTION_BOOT_COMPLETED,
            prepareVpn = {
                consentProbed = true
                null
            },
            startTunnel = { started = true },
        )

        assertFalse(consentProbed)
        assertFalse(started)
    }

    @Test
    fun desiredTrueWithAdmittedVpnRestoresTunnelAtLockedBoot() {
        TunnelState.setDesired(context, true)
        var started = false

        BootReceiver().restoreFromBoot(
            context,
            Intent.ACTION_LOCKED_BOOT_COMPLETED,
            prepareVpn = { null },
            startTunnel = { started = true },
        )

        assertTrue(started)
    }

    @Test
    fun vpnConsentRequirementFailsClosedWithoutStartingTunnel() {
        TunnelState.setDesired(context, true)
        var started = false

        BootReceiver().restoreFromBoot(
            context,
            Intent.ACTION_BOOT_COMPLETED,
            prepareVpn = { Intent("vpn-consent-required") },
            startTunnel = { started = true },
        )

        assertFalse(started)
    }

    private fun devicePrefs() =
        context.createDeviceProtectedStorageContext()
            .getSharedPreferences("mobile_proxy_tunnel", Context.MODE_PRIVATE)
}
