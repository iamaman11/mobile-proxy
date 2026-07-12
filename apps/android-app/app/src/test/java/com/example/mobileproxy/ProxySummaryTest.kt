package com.example.mobileproxy

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProxySummaryTest {
    @Test
    fun summaryDocumentsEveryPublicEndpointWithoutEmbeddingCredentials() {
        val summary = ProxySummary.text()

        assertTrue(summary.contains("${ProxySummary.RELAY_HOST}:1080"))
        assertTrue(summary.contains("${ProxySummary.RELAY_HOST}:1081"))
        assertTrue(summary.contains("${ProxySummary.RELAY_HOST}:3128"))
        assertTrue(summary.contains("QUIC/UDP"))
        assertTrue(summary.contains("<user>:<pass>"))
        assertFalse(summary.contains("Runtime credentials:"))
    }
}
