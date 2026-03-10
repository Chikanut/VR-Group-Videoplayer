package com.vrclassroom.controlpanel

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.WebSettings
import android.webkit.WebView
import android.widget.Button
import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var debugOverlay: View
    private lateinit var debugLogText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        startService(Intent(this, ServerService::class.java))

        webView = findViewById(R.id.webview)
        debugOverlay = findViewById(R.id.debugOverlay)
        debugLogText = findViewById(R.id.debugLogText)

        val webSettings = webView.settings
        webSettings.javaScriptEnabled = true
        webSettings.domStorageEnabled = true
        webSettings.cacheMode = WebSettings.LOAD_DEFAULT

        Handler(Looper.getMainLooper()).postDelayed({
            webView.loadUrl("http://127.0.0.1:8000")
            appendLog("WebView loaded: http://127.0.0.1:8000")
        }, 2500)

        findViewById<ImageButton>(R.id.toggleDebugOverlayButton).setOnClickListener {
            val isVisible = debugOverlay.visibility == View.VISIBLE
            debugOverlay.visibility = if (isVisible) View.GONE else View.VISIBLE
            appendLog(if (isVisible) "Overlay hidden" else "Overlay opened")
        }

        findViewById<Button>(R.id.reloadWebviewButton).setOnClickListener {
            webView.reload()
            appendLog("WebView reloaded")
        }

        findViewById<Button>(R.id.restartServerButton).setOnClickListener {
            restartServer()
        }
    }

    private fun restartServer() {
        stopService(Intent(this, ServerService::class.java))
        startService(Intent(this, ServerService::class.java))
        appendLog("Server restart requested")

        Handler(Looper.getMainLooper()).postDelayed({
            webView.reload()
            appendLog("WebView reloaded after server restart")
        }, 1500)
    }

    private fun appendLog(message: String) {
        val ts = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val current = debugLogText.text?.toString().orEmpty()
        val next = if (current.isBlank()) "[$ts] $message" else "$current\n[$ts] $message"
        debugLogText.text = next.lines().takeLast(8).joinToString("\n")
    }

    override fun onDestroy() {
        stopService(Intent(this, ServerService::class.java))
        super.onDestroy()
    }
}
