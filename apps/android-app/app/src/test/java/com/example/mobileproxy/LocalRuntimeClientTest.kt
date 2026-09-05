package com.example.mobileproxy

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class LocalRuntimeClientTest {
    @Test
    fun missingBearerTokenRefusesBeforeOpeningHttpConnection() {
        var connectionOpened = false
        val transport = HttpRuntimeTransport(
            tokenProvider = { null },
            connectionFactory = {
                connectionOpened = true
                throw AssertionError("connection must not be opened without a token")
            },
        )

        val failure = runCatching {
            transport.request("/v1/ui/status", "GET")
        }.exceptionOrNull()

        assertTrue(failure is IOException)
        assertTrue(failure?.message?.contains("local control is not ready") == true)
        assertFalse(connectionOpened)
    }

    @Test
    fun unauthorizedStatusIsTerminalAndIsNotRetried() {
        var calls = 0
        val transport = RuntimeTransport { _, method ->
            calls += 1
            if (method == "POST") {
                "{}"
            } else {
                throw RuntimeRequestException(401, "unauthorized")
            }
        }
        val client = LocalRuntimeClient(transport, FakeTiming())

        val result = awaitRotation(client, issueCommand = true)
        client.close()

        assertTrue(result.exceptionOrNull() is RuntimeRequestException)
        assertEquals(2, calls)
    }

    @Test
    fun transientStatusLossRetriesThenReturnsSuccessfulRotation() {
        var statusCalls = 0
        val timing = FakeTiming()
        val transport = RuntimeTransport { _, _ ->
            statusCalls += 1
            if (statusCalls == 1) {
                throw IOException("runtime temporarily unavailable")
            }
            READY_CHANGED_STATUS
        }
        val client = LocalRuntimeClient(transport, timing)

        val result = awaitRotation(client, issueCommand = false)
        client.close()

        assertTrue(result.getOrNull() is RotationDecision.Succeeded)
        assertEquals(2, statusCalls)
        assertEquals(listOf(2_000L), timing.sleeps)
    }

    @Test
    fun persistentStatusLossStopsAtBoundedTimeout() {
        val timing = FakeTiming()
        val transport = RuntimeTransport { _, _ ->
            throw IOException("runtime unavailable")
        }
        val client = LocalRuntimeClient(transport, timing)

        val result = awaitRotation(client, issueCommand = false)
        client.close()

        val failure = result.exceptionOrNull()
        assertTrue(failure is IOException)
        assertTrue(failure?.message?.contains("until timeout") == true)
        assertEquals(RotationTracker.TIMEOUT_MILLIS, timing.now)
    }

    private fun awaitRotation(
        client: LocalRuntimeClient,
        issueCommand: Boolean,
    ): Result<RotationDecision> {
        val latch = CountDownLatch(1)
        var captured: Result<RotationDecision>? = null
        client.rotateAndMonitor(
            oldIp = "198.51.100.10",
            issueCommand = issueCommand,
            onStatus = {},
            callback = {
                captured = it
                latch.countDown()
            },
        )
        assertTrue("rotation callback did not complete", latch.await(2, TimeUnit.SECONDS))
        return requireNotNull(captured)
    }

    private class FakeTiming : RuntimeTiming {
        var now = 0L
        val sleeps = mutableListOf<Long>()

        override fun nowMillis(): Long = now

        override fun sleep(millis: Long) {
            sleeps += millis
            now += millis
        }
    }

    private companion object {
        const val READY_CHANGED_STATUS = """
            {
              "public_ip": "203.0.113.20",
              "readiness": "ready",
              "serving": true,
              "rotation_in_progress": false,
              "tunnel_owner": "wireguard"
            }
        """
    }
}
