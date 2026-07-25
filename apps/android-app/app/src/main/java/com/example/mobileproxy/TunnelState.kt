package com.example.mobileproxy

import android.content.Context
import androidx.core.content.edit

object TunnelState {
    private const val PREFS = "mobile_proxy_tunnel"
    private const val DESIRED = "desired"
    private const val CONFIG = "config"
    private const val LAST_STATE = "last_state"
    private const val LAST_ERROR = "last_error"

    private fun storageContext(context: Context): Context =
        context.createDeviceProtectedStorageContext()

    private fun prefs(context: Context) =
        storageContext(context).getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun setDesired(context: Context, desired: Boolean) {
        prefs(context).edit {
            putBoolean(DESIRED, desired)
        }
    }

    fun isDesired(context: Context): Boolean =
        prefs(context)
            .getBoolean(DESIRED, false)

    fun setConfig(context: Context, config: String) {
        prefs(context).edit {
            putString(CONFIG, config)
        }
    }

    fun getConfig(context: Context): String? =
        prefs(context)
            .getString(CONFIG, null)

    fun setLastState(context: Context, state: String) {
        prefs(context).edit {
            putString(LAST_STATE, state)
        }
    }

    fun setLastError(context: Context, error: String?) {
        prefs(context).edit {
            putString(LAST_ERROR, error)
        }
    }
}
