// Analytiq Android SDK
// Kotlin 1.9+  |  Android API 21+ (Android 5.0+)
//
// Usage:
//   // Initialize once in Application.onCreate()
//   Analytiq.configure(context, apiKey = "YOUR_API_KEY", host = "https://your-domain.com")
//
//   // Track
//   Analytiq.track("button_tapped", mapOf("screen" to "home"))
//
//   // Identify
//   Analytiq.identify("user-123", mapOf("email" to "alice@example.com", "plan" to "pro"))
//
//   // Page/screen
//   Analytiq.screen("Settings")

package io.analytiq.sdk

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

object Analytiq {

    private const val PREFS_NAME = "analytiq_prefs"
    private const val ANON_KEY   = "anonymous_id"

    private var apiKey:      String = ""
    private var host:        String = "https://app.analytiq.io"
    private var userId:      String? = null
    private var anonymousId: String = UUID.randomUUID().toString()

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // ── Configuration ──────────────────────────────────────────────────────

    fun configure(context: Context, apiKey: String, host: String = "https://app.analytiq.io") {
        this.apiKey = apiKey
        this.host   = host.trimEnd('/')

        val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        anonymousId = prefs.getString(ANON_KEY, null) ?: run {
            val id = UUID.randomUUID().toString()
            prefs.edit().putString(ANON_KEY, id).apply()
            id
        }
    }

    // ── Public API ─────────────────────────────────────────────────────────

    fun identify(userId: String, traits: Map<String, Any> = emptyMap()) {
        this.userId = userId
        enqueue("identify", null, userId, traits)
    }

    fun track(event: String, properties: Map<String, Any> = emptyMap()) {
        enqueue("track", event, userId, properties)
    }

    fun screen(name: String, properties: Map<String, Any> = emptyMap()) {
        val props = properties.toMutableMap().apply { put("name", name) }
        enqueue("page", name, userId, props)
    }

    fun reset() {
        userId = null
    }

    // ── Internal ───────────────────────────────────────────────────────────

    private fun enqueue(
        type:       String,
        event:      String?,
        userId:     String?,
        properties: Map<String, Any>,
    ) {
        scope.launch {
            try {
                val body = JSONObject().apply {
                    put("type",        type)
                    put("anonymousId", anonymousId)
                    put("properties",  JSONObject(properties))
                    event?.let  { put("event",  it) }
                    userId?.let { put("userId", it) }
                }
                post("$host/api/ingest/$apiKey", body.toString())
            } catch (e: Exception) {
                System.err.println("[Analytiq] ingest error: ${e.message}")
            }
        }
    }

    private fun post(url: String, json: String) {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.doOutput = true
            conn.connectTimeout = 10_000
            conn.readTimeout    = 10_000
            OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(json) }
            conn.responseCode  // trigger the request
        } finally {
            conn.disconnect()
        }
    }
}
