package com.example.mobileproxy

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.core.content.edit
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

object TunnelState {
    private const val PREFS = "mobile_proxy_tunnel"
    private const val DESIRED = "desired"
    private const val CONFIG = "config"
    private const val LAST_STATE = "last_state"
    private const val LAST_ERROR = "last_error"
    private const val LOCAL_CONTROL_TOKEN_CIPHERTEXT = "local_control_token_ciphertext"
    private const val LOCAL_CONTROL_TOKEN_IV = "local_control_token_iv"
    private const val LOCAL_CONTROL_KEY_ALIAS = "mobile_proxy_local_control_v1"
    private const val GCM_TAG_BITS = 128

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
        prefs(context).edit(commit = true) {
            putString(CONFIG, config)
        }
    }

    fun getConfig(context: Context): String? =
        prefs(context)
            .getString(CONFIG, null)

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
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, localControlKey())
        val ciphertext = cipher.doFinal(token.toByteArray(StandardCharsets.UTF_8))
        prefs(context).edit(commit = true) {
            putString(LOCAL_CONTROL_TOKEN_CIPHERTEXT, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
            putString(LOCAL_CONTROL_TOKEN_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
        }
    }

    fun getLocalControlToken(context: Context): String? {
        val ciphertext = prefs(context).getString(LOCAL_CONTROL_TOKEN_CIPHERTEXT, null) ?: return null
        val iv = prefs(context).getString(LOCAL_CONTROL_TOKEN_IV, null) ?: return null
        return runCatching {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                localControlKey(),
                GCMParameterSpec(GCM_TAG_BITS, Base64.decode(iv, Base64.NO_WRAP)),
            )
            String(cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)), StandardCharsets.UTF_8)
        }.getOrNull()
    }

    private fun localControlKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(LOCAL_CONTROL_KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        val builder = KeyGenParameterSpec.Builder(
            LOCAL_CONTROL_KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            builder.setUnlockedDeviceRequired(false)
        }
        generator.init(builder.build())
        return generator.generateKey()
    }
}
