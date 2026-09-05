package com.example.mobileproxy

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CellularEgressServiceTest {
    @Test
    fun validCredentialsReachValidatedCellularGateAndFailNetworkUnreachable() {
        val response = exercise(
            username = "proxy-user",
            password = "correct-password-123",
            expectedPassword = "correct-password-123",
        )

        assertArrayEquals(
            byteArrayOf(5, 2, 1, 0, 5, 3, 0, 1, 0, 0, 0, 0, 0, 0),
            response,
        )
    }

    @Test
    fun invalidPasswordIsRejectedBeforeCellularNetworkSelection() {
        var networkRequested = false
        val response = exercise(
            username = "proxy-user",
            password = "wrong-password",
            expectedPassword = "correct-password-123",
            onNetworkRequest = { networkRequested = true },
        )

        assertArrayEquals(byteArrayOf(5, 2, 1, 1), response)
        assertFalse(networkRequested)
    }

    private fun exercise(
        username: String,
        password: String,
        expectedPassword: String,
        onNetworkRequest: () -> Unit = {},
    ): ByteArray {
        val service = Robolectric.buildService(CellularEgressService::class.java).create().get()
        val config = TunnelState.EgressConfig(
            port = 1080,
            username = "proxy-user",
            password = expectedPassword,
        )
        ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { listener ->
            Socket("127.0.0.1", listener.localPort).use { client ->
                val server = listener.accept()
                client.getOutputStream().apply {
                    write(socksRequest(username, password))
                    flush()
                }
                server.use {
                    service.handleClient(it, config) {
                        onNetworkRequest()
                        null
                    }
                }
                return client.getInputStream().readBytes()
            }
        }
    }

    private fun socksRequest(username: String, password: String): ByteArray =
        ByteArrayOutputStream().apply {
            write(byteArrayOf(5, 1, 2))
            write(1)
            write(username.toByteArray().size)
            write(username.toByteArray())
            write(password.toByteArray().size)
            write(password.toByteArray())
            write(byteArrayOf(5, 1, 0, 1, 8, 8, 8, 8, 0, 53))
        }.toByteArray()
}
