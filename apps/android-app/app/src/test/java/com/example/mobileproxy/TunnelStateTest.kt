package com.example.mobileproxy

import android.content.Context
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class TunnelStateTest {
    private lateinit var context: Context
    private lateinit var key: SecretKey

    @Before
    fun setUp() {
        context = RuntimeEnvironment.getApplication()
        devicePrefs().edit().clear().commit()
        key = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
    }

    @After
    fun tearDown() {
        devicePrefs().edit().clear().commit()
    }

    @Test
    fun configPersistsOnlyAsEncryptedDeviceProtectedState() {
        val config = """
            [Interface]
            PrivateKey = private-key-material
            Address = 10.0.0.2/32
        """.trimIndent()

        TunnelState.setConfig(context, config, key)

        val storage = context.createDeviceProtectedStorageContext()
        assertTrue(storage.isDeviceProtectedStorage)
        val store = devicePrefs()
        assertFalse(store.contains("config"))
        val ciphertext = store.getString("config_ciphertext", null)
        val iv = store.getString("config_iv", null)
        assertNotNull(ciphertext)
        assertNotNull(iv)
        assertFalse(ciphertext!!.contains("private-key-material"))
        assertEquals(config, TunnelState.getConfig(context) { key })
    }

    @Test
    fun corruptEncryptedStateNeverFallsBackToLegacyPlaintext() {
        val config = "[Interface]\nPrivateKey = legacy-private-key"
        TunnelState.setConfig(context, config, key)
        devicePrefs().edit()
            .putString("config", config)
            .putString("config_ciphertext", "not-valid-base64")
            .commit()

        assertNull(TunnelState.getConfig(context) { key })
        assertFalse(devicePrefs().contains("config"))
    }

    @Test
    fun unavailableKeyFailsClosedAndLockedBootKeySpecNeedsNoUnlock() {
        TunnelState.setConfig(context, "[Interface]\nPrivateKey = encrypted", key)

        assertNull(
            TunnelState.getConfig(context) {
                throw IllegalStateException("keystore unavailable")
            },
        )

        val spec = TunnelState.secretKeySpec("mobile_proxy_test_direct_boot")
        assertFalse(spec.isUnlockedDeviceRequired)
        assertFalse(spec.isUserAuthenticationRequired)
    }

    private fun devicePrefs() =
        context.createDeviceProtectedStorageContext()
            .getSharedPreferences("mobile_proxy_tunnel", Context.MODE_PRIVATE)
}
