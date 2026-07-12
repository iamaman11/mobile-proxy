package com.example.mobileproxy

object ProxySummary {
    const val RELAY_HOST = "34.118.88.54"

    fun text(): String = buildString {
        appendLine("Relay IP: $RELAY_HOST")
        appendLine("Mixed: $RELAY_HOST:1080")
        appendLine("SOCKS5: $RELAY_HOST:1081")
        appendLine("HTTP/HTTPS CONNECT: $RELAY_HOST:3128")
        appendLine("Runtime credentials are injected from secure env/manifests")
        appendLine("SOCKS5 URL: socks5h://<user>:<pass>@$RELAY_HOST:1081")
        appendLine("HTTP URL: http://<user>:<pass>@$RELAY_HOST:3128")
        appendLine()
        appendLine("Test URLs: http://httpbin.org/ip and https://example.com")
        appendLine("Preferred transport: QUIC/UDP (TLS/TCP is fallback only)")
        appendLine("Preferred for browsers: SOCKS5 :1081")
        appendLine("Preferred for raw CLI: HTTP CONNECT :3128")
    }
}
