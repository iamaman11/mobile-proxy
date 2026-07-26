package com.example.mobileproxy

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProxySummaryTest {
    @Test
    fun summaryDocumentsPublicEndpointsWithoutEmbeddingCredentials() {
        val summary = ProxySummary.text()

        assertTrue(summary.contains(ProxySummary.RELAY_HOST))
        assertTrue(summary.contains(":1080"))
        assertTrue(summary.contains(":1081"))
        assertTrue(summary.contains(":3128"))
        assertTrue(summary.contains("не отображаются"))
        assertFalse(summary.contains("<user>:<pass>"))
    }
}
