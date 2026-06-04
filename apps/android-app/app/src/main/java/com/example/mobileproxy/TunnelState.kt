package com.example.mobileproxy

import android.content.Context

object TunnelState {
    private const val PREFS = "mobile_proxy_tunnel"
    private const val DESIRED = "desired"

    fun setDesired(context: Context, desired: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(DESIRED, desired)
            .apply()
    }

    fun isDesired(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(DESIRED, false)
}
