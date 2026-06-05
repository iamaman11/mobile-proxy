package com.example.mobileproxy

import android.content.Context

object TunnelState {
    private const val PREFS = "mobile_proxy_tunnel"
    private const val DESIRED = "desired"
    private const val CONFIG = "config"
    private const val LAST_STATE = "last_state"
    private const val LAST_ERROR = "last_error"

    fun setDesired(context: Context, desired: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(DESIRED, desired)
            .apply()
    }

    fun isDesired(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(DESIRED, false)

    fun setConfig(context: Context, config: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(CONFIG, config)
            .apply()
    }

    fun getConfig(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(CONFIG, null)

    fun setLastState(context: Context, state: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(LAST_STATE, state)
            .apply()
    }

    fun setLastError(context: Context, error: String?) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(LAST_ERROR, error)
            .apply()
    }
}
