package com.vrclassroom.controlpanel

import android.content.ContentValues
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebChromeClient.FileChooserParams
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    companion object {
        private const val SERVER_URL = "http://127.0.0.1:8000"
        private const val HEALTH_URL = "$SERVER_URL/api/health"
        private const val STARTUP_TIMEOUT_MS = 20000L
        private const val HEALTH_POLL_INTERVAL_MS = 1000L
    }

    private lateinit var webView: WebView
    private lateinit var startupOverlay: View
    private lateinit var startupStatusText: TextView
    private lateinit var startupDetailText: TextView
    private lateinit var startupProgress: ProgressBar
    private lateinit var startupRestartButton: Button
    private lateinit var debugOverlay: View
    private lateinit var debugLogText: TextView
    private val mainHandler = Handler(Looper.getMainLooper())
    private val backgroundExecutor = Executors.newSingleThreadExecutor()
    private val healthPollRunnable = object : Runnable {
        override fun run() {
            pollServerStartup()
        }
    }
    private var startupStartedAt = 0L
    private var startupSessionId = 0
    private var inFlightHealthSessionId = -1
    private var webViewLoaded = false
    private var lastLoggedStatus = ""
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private val fileChooserLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val callback = fileChooserCallback
        fileChooserCallback = null

        if (callback == null) {
            return@registerForActivityResult
        }

        val uris = WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
        callback.onReceiveValue(uris ?: emptyArray())
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webview)
        startupOverlay = findViewById(R.id.startupOverlay)
        startupStatusText = findViewById(R.id.startupStatusText)
        startupDetailText = findViewById(R.id.startupDetailText)
        startupProgress = findViewById(R.id.startupProgress)
        startupRestartButton = findViewById(R.id.startupRestartButton)
        debugOverlay = findViewById(R.id.debugOverlay)
        debugLogText = findViewById(R.id.debugLogText)

        configureWebView()
        startupRestartButton.setOnClickListener {
            restartServer()
        }

        findViewById<ImageButton>(R.id.toggleDebugOverlayButton).setOnClickListener {
            val isVisible = debugOverlay.visibility == View.VISIBLE
            debugOverlay.visibility = if (isVisible) View.GONE else View.VISIBLE
            appendLog(if (isVisible) "Overlay hidden" else "Overlay opened")
        }

        findViewById<Button>(R.id.reloadWebviewButton).setOnClickListener {
            if (webViewLoaded) {
                webView.reload()
                appendLog("WebView reloaded")
            } else {
                beginServerStartupMonitoring("Manual reload requested before backend was ready")
            }
        }

        findViewById<Button>(R.id.restartServerButton).setOnClickListener {
            restartServer()
        }

        startService(Intent(this, ServerService::class.java))
        beginServerStartupMonitoring("Server service start requested")
    }

    private fun restartServer() {
        mainHandler.removeCallbacks(healthPollRunnable)
        stopService(Intent(this, ServerService::class.java))
        startService(Intent(this, ServerService::class.java))
        appendLog("Server restart requested")
        beginServerStartupMonitoring("Waiting for backend after server restart")
    }

    private fun configureWebView() {
        val webSettings = webView.settings
        webSettings.javaScriptEnabled = true
        webSettings.domStorageEnabled = true
        webSettings.cacheMode = WebSettings.LOAD_DEFAULT
        webSettings.allowFileAccess = true
        webSettings.allowContentAccess = true
        webView.addJavascriptInterface(AndroidWebBridge(), "AndroidBridge")
        webView.setDownloadListener { url, _, _, _, _ ->
            if (!url.isNullOrBlank()) {
                appendLog("WebView download requested: $url")
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                if (!url.isNullOrBlank() && url != "about:blank") {
                    appendLog("WebView finished loading: $url")
                }
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                if (request == null || request.isForMainFrame) {
                    val errorText = error?.description?.toString()?.trim().orEmpty()
                    if (errorText.isNotEmpty()) {
                        appendLog("WebView error: $errorText")
                    }
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback

                return try {
                    val chooserIntent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                    }
                    fileChooserLauncher.launch(chooserIntent)
                    appendLog("Opening Android file picker")
                    true
                } catch (exc: Exception) {
                    appendLog("Failed to open file picker: ${exc.message.orEmpty()}")
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = null
                    false
                }
            }
        }
    }

    private fun beginServerStartupMonitoring(reason: String) {
        mainHandler.removeCallbacks(healthPollRunnable)
        startupStartedAt = System.currentTimeMillis()
        startupSessionId += 1
        inFlightHealthSessionId = -1
        webViewLoaded = false
        lastLoggedStatus = ""
        webView.loadUrl("about:blank")
        showStartupOverlay(
            title = getString(R.string.server_starting_title),
            detail = getString(R.string.server_starting_detail),
            isError = false,
        )
        appendLog(reason)
        mainHandler.post(healthPollRunnable)
    }

    private fun pollServerStartup() {
        val status = getEmbeddedServerStatus()
        logStatusIfChanged(status)

        if (status.state == "failed") {
            mainHandler.removeCallbacks(healthPollRunnable)
            showStartupOverlay(
                title = getString(R.string.server_failed_title),
                detail = status.detail.ifBlank { getString(R.string.server_failed_fallback_detail) },
                isError = true,
            )
            return
        }

        val elapsedMs = System.currentTimeMillis() - startupStartedAt
        if (elapsedMs >= STARTUP_TIMEOUT_MS) {
            mainHandler.removeCallbacks(healthPollRunnable)
            val timeoutDetail = if (status.detail.isNotBlank()) {
                status.detail
            } else {
                getString(R.string.server_timeout_detail, STARTUP_TIMEOUT_MS / 1000L)
            }
            showStartupOverlay(
                title = getString(R.string.server_timeout_title),
                detail = timeoutDetail,
                isError = true,
            )
            appendLog("Embedded server startup timed out")
            return
        }

        showStartupOverlay(
            title = getString(R.string.server_starting_title),
            detail = buildStartupDetail(status),
            isError = false,
        )

        if (inFlightHealthSessionId == startupSessionId) {
            return
        }

        val sessionId = startupSessionId
        inFlightHealthSessionId = sessionId
        backgroundExecutor.execute {
            val ready = isServerHealthy()
            runOnUiThread {
                if (inFlightHealthSessionId == sessionId) {
                    inFlightHealthSessionId = -1
                }
                if (isDestroyed || isFinishing) {
                    return@runOnUiThread
                }
                if (sessionId != startupSessionId) {
                    return@runOnUiThread
                }

                if (ready) {
                    onServerReady()
                } else {
                    mainHandler.postDelayed(healthPollRunnable, HEALTH_POLL_INTERVAL_MS)
                }
            }
        }
    }

    private fun onServerReady() {
        mainHandler.removeCallbacks(healthPollRunnable)
        showStartupOverlay("", "", false, visible = false)
        if (!webViewLoaded) {
            webViewLoaded = true
            webView.loadUrl(SERVER_URL)
            appendLog("Backend ready; loading WebView: $SERVER_URL")
        }
    }

    private fun buildStartupDetail(status: EmbeddedServerStatus): String {
        return when (status.state) {
            "running" -> getString(R.string.server_running_detail)
            "starting" -> status.message.ifBlank { getString(R.string.server_starting_detail) }
            "stopped" -> getString(R.string.server_stopped_detail)
            else -> status.message.ifBlank { getString(R.string.server_starting_detail) }
        }
    }

    private fun showStartupOverlay(title: String, detail: String, isError: Boolean, visible: Boolean = true) {
        startupOverlay.visibility = if (visible) View.VISIBLE else View.GONE
        startupStatusText.text = title
        startupStatusText.setTextColor(if (isError) Color.parseColor("#FFB4AB") else Color.WHITE)
        startupDetailText.text = detail
        startupProgress.visibility = if (isError) View.GONE else View.VISIBLE
        startupRestartButton.visibility = if (isError) View.VISIBLE else View.GONE
    }

    private fun logStatusIfChanged(status: EmbeddedServerStatus) {
        val signature = listOf(status.state, status.message, status.traceback).joinToString("|")
        if (signature == lastLoggedStatus) {
            return
        }
        lastLoggedStatus = signature

        val summary = buildString {
            append("Embedded server status: ")
            append(status.state)
            if (status.message.isNotBlank()) {
                append(" (")
                append(status.message)
                append(")")
            }
        }
        appendLog(summary)
    }

    private fun getEmbeddedServerStatus(): EmbeddedServerStatus {
        return try {
            if (!Python.isStarted()) {
                return EmbeddedServerStatus("idle", "Python runtime is not started yet", "")
            }

            val module = Python.getInstance().getModule("android_service")
            val rawStatus = module.callAttr("get_status").toJava(String::class.java)
            val json = JSONObject(rawStatus)
            EmbeddedServerStatus(
                state = json.optString("state", "idle"),
                message = json.optString("message", ""),
                traceback = json.optString("traceback", ""),
            )
        } catch (exc: Exception) {
            EmbeddedServerStatus(
                state = "failed",
                message = "Failed to read embedded server status",
                traceback = exc.message.orEmpty(),
            )
        }
    }

    private fun isServerHealthy(): Boolean {
        var connection: HttpURLConnection? = null
        return try {
            connection = (URL(HEALTH_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 1000
                readTimeout = 1000
                requestMethod = "GET"
            }
            connection.connect()
            connection.responseCode == HttpURLConnection.HTTP_OK
        } catch (_: Exception) {
            false
        } finally {
            connection?.disconnect()
        }
    }

    private fun appendLog(message: String) {
        val ts = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val current = debugLogText.text?.toString().orEmpty()
        val next = if (current.isBlank()) "[$ts] $message" else "$current\n[$ts] $message"
        debugLogText.text = next.lines().takeLast(8).joinToString("\n")
    }

    override fun onDestroy() {
        mainHandler.removeCallbacks(healthPollRunnable)
        fileChooserCallback?.onReceiveValue(null)
        fileChooserCallback = null
        backgroundExecutor.shutdownNow()
        stopService(Intent(this, ServerService::class.java))
        super.onDestroy()
    }

    private inner class AndroidWebBridge {
        @JavascriptInterface
        fun saveJsonFile(filename: String, jsonContent: String): Boolean {
            val safeName = filename.trim().ifBlank { "export.json" }
            val finalName = if (safeName.endsWith(".json", ignoreCase = true)) safeName else "$safeName.json"

            return try {
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, finalName)
                    put(MediaStore.Downloads.MIME_TYPE, "application/json")
                    put(MediaStore.Downloads.RELATIVE_PATH, "Download/VRClassroom")
                }

                val resolver = contentResolver
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: throw IOException("Failed to create download entry")

                resolver.openOutputStream(uri)?.use { stream ->
                    stream.write(jsonContent.toByteArray(Charsets.UTF_8))
                } ?: throw IOException("Failed to open output stream")

                runOnUiThread {
                    appendLog("Saved export to Downloads/VRClassroom/$finalName")
                    Toast.makeText(
                        this@MainActivity,
                        getString(R.string.export_saved_message, finalName),
                        Toast.LENGTH_SHORT,
                    ).show()
                }
                true
            } catch (exc: Exception) {
                runOnUiThread {
                    appendLog("Failed to save export: ${exc.message.orEmpty()}")
                    Toast.makeText(
                        this@MainActivity,
                        getString(R.string.export_failed_message),
                        Toast.LENGTH_SHORT,
                    ).show()
                }
                false
            }
        }
    }

    private data class EmbeddedServerStatus(
        val state: String,
        val message: String,
        val traceback: String,
    ) {
        val detail: String
            get() = listOf(message, traceback).filter { it.isNotBlank() }.joinToString("\n")
    }
}
