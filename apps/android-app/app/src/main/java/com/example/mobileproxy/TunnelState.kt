package com.example.mobileproxy

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.core.content.edit
import java.io.File
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

object TunnelState {
    private const val PREFS = "mobile_proxy_tunnel"
    private const val DESIRED = "desired"
    private const val LEGACY_CONFIG = "config"
    private const val CONFIG_CIPHERTEXT = "config_ciphertext"
    private const val CONFIG_IV = "config_iv"
    private const val LAST_STATE = "last_state"
    private const val LAST_ERROR = "last_error"
    private const val LOCAL_CONTROL_TOKEN_CIPHERTEXT = "local_control_token_ciphertext"
    private const val LOCAL_CONTROL_TOKEN_IV = "local_control_token_iv"
    private const val LOCAL_CONTROL_KEY_ALIAS = "mobile_proxy_local_control_v1"

    data class EgressConfig(val port: Int, val username: String, val password: String)

    private fun storageContext(context: Context): Context =
        context.createDeviceProtectedStorageContext()

    private fun prefs(context: Context) =
        storageContext(context).getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun setDesired(context: Context, desired: Boolean) {
        prefs(context).edit(commit = true) {
            putBoolean(DESIRED, desired)
        }
    }

    fun isDesired(context: Context): Boolean =
        prefs(context)
            .getBoolean(DESIRED, false)

    fun setConfig(context: Context, config: String) {
        setConfig(context, config) { localControlKey() }
    }

    internal fun setConfig(context: Context, config: String, keyProvider: () -> SecretKey) {
        val store = prefs(context)
        purgeLegacyConfig(store)
        val encrypted = AesGcmSecretCodec.encrypt(config, keyProvider())
        store.edit(commit = true) {
            putString(CONFIG_CIPHERTEXT, encrypted.ciphertext)
            putString(CONFIG_IV, encrypted.iv)
        }
    }

    fun getConfig(context: Context): String? =
        getConfig(context) { localControlKey() }

    internal fun getConfig(context: Context, keyProvider: () -> SecretKey): String? {
        val store = prefs(context)
        purgeLegacyConfig(store)
        val ciphertext = store.getString(CONFIG_CIPHERTEXT, null) ?: return null
        val iv = store.getString(CONFIG_IV, null) ?: return null
        val key = runCatching { keyProvider() }.getOrNull() ?: return null
        return AesGcmSecretCodec.decrypt(ciphertext, iv, key)
    }

    private fun purgeLegacyConfig(store: SharedPreferences) {
        if (store.contains(LEGACY_CONFIG)) {
            store.edit(commit = true) {
                remove(LEGACY_CONFIG)
            }
        }
    }

    fun setLastState(context: Context, state: String) {
        prefs(context).edit(commit = true) {
            putString(LAST_STATE, state)
        }
    }

    fun setLastError(context: Context, error: String?) {
        prefs(context).edit(commit = true) {
            putString(LAST_ERROR, error)
        }
    }

    fun setLocalControlToken(context: Context, token: String) {
        val encrypted = AesGcmSecretCodec.encrypt(token, localControlKey())
        prefs(context).edit(commit = true) {
            putString(LOCAL_CONTROL_TOKEN_CIPHERTEXT, encrypted.ciphertext)
            putString(LOCAL_CONTROL_TOKEN_IV, encrypted.iv)
        }
    }

    fun getLocalControlToken(context: Context): String? {
        val store = prefs(context)
        val ciphertext = store.getString(LOCAL_CONTROL_TOKEN_CIPHERTEXT, null) ?: return null
        val iv = store.getString(LOCAL_CONTROL_TOKEN_IV, null) ?: return null
        val key = runCatching { localControlKey() }.getOrNull() ?: return null
        return AesGcmSecretCodec.decrypt(ciphertext, iv, key)
    }

    fun setEgressConfig(context: Context, port: Int, username: String, password: String) {
        require(port in 1024..65535) { "egress port must be unprivileged" }
        require(username.isNotBlank() && username.length <= 256) { "egress username is invalid" }
        require(password.length >= 16) { "egress password is too short" }
        val encrypted = AesGcmSecretCodec.encrypt(password, localControlKey())
        prefs(context).edit(commit = true) {
            putInt("egress_port", port)
            putString("egress_username", username)
            putString("egress_password_ciphertext", encrypted.ciphertext)
            putString("egress_password_iv", encrypted.iv)
        }
    }

    fun getEgressConfig(context: Context): EgressConfig? {
        val store = prefs(context)
        val port = store.getInt("egress_port", -1)
        val username = store.getString("egress_username", null)
        val ciphertext = store.getString("egress_password_ciphertext", null)
        val iv = store.getString("egress_password_iv", null)
        if (port !in 1024..65535 || username.isNullOrBlank() || ciphertext == null || iv == null) return null
        val key = runCatching { localControlKey() }.getOrNull() ?: return null
        val password = AesGcmSecretCodec.decrypt(ciphertext, iv, key) ?: return null
        return EgressConfig(port, username, password)
    }

    /** Consumes the root-provisioned one-time file from this app's private DE storage. */
    fun consumeProvisionedEgressConfig(context: Context): EgressConfig? {
        val file = File(storageContext(context).filesDir, "cellular-egress.json")
        val raw = runCatching { file.readText(Charsets.UTF_8) }.getOrNull() ?: return null
        return runCatching {
            val json = org.json.JSONObject(raw)
            val config = EgressConfig(
                json.getInt("port"),
                json.getString("username"),
                json.getString("password"),
            )
            setEgressConfig(context, config.port, config.username, config.password)
            config
        }.also { file.delete() }.getOrNull()
    }

    internal fun secretKeySpec(alias: String = LOCAL_CONTROL_KEY_ALIAS): KeyGenParameterSpec {
        val builder = KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setUserAuthenticationRequired(false)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            builder.setUnlockedDeviceRequired(false)
        }
        return builder.build()
    }

    private fun localControlKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(LOCAL_CONTROL_KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(secretKeySpec())
        return generator.generateKey()
    }
}
