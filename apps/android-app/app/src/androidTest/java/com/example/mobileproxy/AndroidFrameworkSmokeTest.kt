package com.example.mobileproxy

import android.content.Context
import android.content.Intent
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AndroidFrameworkSmokeTest {
    @Test
    fun keystoreDeviceProtectedReceiverAndServiceLifecycleWorkTogether() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val storage = context.createDeviceProtectedStorageContext()
        val store = storage.getSharedPreferences("mobile_proxy_tunnel", Context.MODE_PRIVATE)
        store.edit().clear().commit()

        val config = "[Interface]\nPrivateKey = instrumentation-secret-material"
        val setConfig = Intent(context, TunnelCommandReceiver::class.java)
            .setAction(TunnelCommandReceiver.ACTION_SET_CONFIG)
            .putExtra(TunnelCommandReceiver.EXTRA_CONFIG, config)
        context.sendBroadcast(setConfig)

        assertTrue(
            "manifest receiver did not persist encrypted config",
            awaitCondition { TunnelState.getConfig(context) == config },
        )
        assertTrue(storage.isDeviceProtectedStorage)
        assertFalse(store.contains("config"))
        assertTrue(store.contains("config_ciphertext"))
        assertTrue(store.contains("config_iv"))
        assertEquals(config, TunnelState.getConfig(context))

        context.startService(MobileProxyVpnService.stopIntent(context))
        assertTrue(
            "service stop lifecycle did not publish DOWN",
            awaitCondition { store.getString("last_state", null) == "DOWN" },
        )
    }

    private fun awaitCondition(condition: () -> Boolean): Boolean {
        val deadline = SystemClock.elapsedRealtime() + 5_000L
        while (SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return true
            SystemClock.sleep(50L)
        }
        return condition()
    }
}
