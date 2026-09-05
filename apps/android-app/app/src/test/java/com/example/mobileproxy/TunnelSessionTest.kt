package com.example.mobileproxy

import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TunnelSessionTest {
    @Test
    fun validConfigTransitionsBackendUp() {
        val backend = RecordingBackend()

        val transition = TunnelSession(backend).start(VALID_CONFIG)

        assertTrue(transition is TunnelTransition.Applied)
        assertEquals(Tunnel.State.UP, (transition as TunnelTransition.Applied).state)
        assertEquals(Tunnel.State.UP, backend.lastState)
        assertNotNull(backend.lastConfig)
    }

    @Test
    fun malformedConfigFailsBeforeBackendMutation() {
        val backend = RecordingBackend()

        val transition = TunnelSession(backend).start("not-a-wireguard-config")

        assertTrue(transition is TunnelTransition.Failed)
        assertFalse(backend.called)
    }

    @Test
    fun backendFailureBecomesObservableFailedTransition() {
        val backend = RecordingBackend(failure = IllegalStateException("backend exploded"))

        val transition = TunnelSession(backend).start(VALID_CONFIG)

        assertTrue(transition is TunnelTransition.Failed)
        assertTrue((transition as TunnelTransition.Failed).error.contains("backend exploded"))
    }

    @Test
    fun stopTransitionsBackendDownWithoutConfig() {
        val backend = RecordingBackend()

        val transition = TunnelSession(backend).stop()

        assertTrue(transition is TunnelTransition.Applied)
        assertEquals(Tunnel.State.DOWN, (transition as TunnelTransition.Applied).state)
        assertEquals(Tunnel.State.DOWN, backend.lastState)
        assertNull(backend.lastConfig)
    }

    private class RecordingBackend(
        private val failure: Exception? = null,
    ) : TunnelBackend {
        var called = false
        var lastState: Tunnel.State? = null
        var lastConfig: Config? = null

        override fun setState(state: Tunnel.State, config: Config?): Tunnel.State {
            called = true
            lastState = state
            lastConfig = config
            failure?.let { throw it }
            return state
        }
    }

    private companion object {
        val VALID_CONFIG = """
            [Interface]
            PrivateKey = AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=
            Address = 10.0.0.2/32

            [Peer]
            PublicKey = AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=
            AllowedIPs = 0.0.0.0/0
            Endpoint = 127.0.0.1:51820
        """.trimIndent()
    }
}
