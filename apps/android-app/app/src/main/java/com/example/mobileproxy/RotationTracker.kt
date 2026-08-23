package com.example.mobileproxy

sealed interface RotationDecision {
    data object Waiting : RotationDecision
    data class Succeeded(val oldIp: String, val newIp: String) : RotationDecision
    data class Failed(val reason: String) : RotationDecision
}

object RotationTracker {
    const val TIMEOUT_MILLIS = 240_000L

    fun evaluate(oldIp: String?, status: LocalRuntimeStatus, elapsedMillis: Long): RotationDecision {
        val newIp = status.publicIp
        if (!oldIp.isNullOrBlank() && !newIp.isNullOrBlank() && oldIp != newIp && status.serving) {
            return RotationDecision.Succeeded(oldIp, newIp)
        }
        if (elapsedMillis >= TIMEOUT_MILLIS) {
            val reason = when {
                newIp.isNullOrBlank() -> "сервер не подтвердил внешний IP"
                oldIp == newIp -> "оператор не выдал новый IP"
                !status.serving -> "прокси не восстановился после смены сети"
                else -> "сервер не подтвердил завершение команды"
            }
            return RotationDecision.Failed(reason)
        }
        return RotationDecision.Waiting
    }
}
