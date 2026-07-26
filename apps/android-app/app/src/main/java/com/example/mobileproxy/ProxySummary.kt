package com.example.mobileproxy

object ProxySummary {
    const val RELAY_HOST = "34.118.88.54"

    fun text(): String = buildString {
        appendLine("Релей: $RELAY_HOST")
        appendLine("SOCKS5: :1081  •  HTTP/HTTPS: :3128")
        appendLine("Смешанный порт: :1080")
        append("Учётные данные защищены и не отображаются")
    }
}
