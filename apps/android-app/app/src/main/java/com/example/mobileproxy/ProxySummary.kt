package com.example.mobileproxy

object ProxySummary {
    const val RELAY_HOST = "34.118.88.54"

    fun text(): String = buildString {
        appendLine("Релей: $RELAY_HOST")
        appendLine("SOCKS5: :1081  •  HTTP CONNECT: :3128")
        appendLine("Универсальный SOCKS5/HTTP: :1080")
        appendLine("Маршруты протоколов изолированы")
        append("Учётные данные защищены и не отображаются")
    }
}
