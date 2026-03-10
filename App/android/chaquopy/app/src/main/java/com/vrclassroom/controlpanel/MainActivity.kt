package com.vrclassroom.controlpanel

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private val handler = Handler(Looper.getMainLooper())
    private var loadAttempts = 0

    private val loadRunnable = object : Runnable {
        override fun run() {
            loadAttempts += 1
            webView.loadUrl("http://127.0.0.1:8000")
            if (loadAttempts < 30) {
                handler.postDelayed(this, 1000)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        startService(Intent(this, ServerService::class.java))

        webView = findViewById(R.id.webview)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.cacheMode = WebSettings.LOAD_DEFAULT
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                handler.removeCallbacks(loadRunnable)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                handler.postDelayed(loadRunnable, 1000)
            }
        }

        handler.postDelayed(loadRunnable, 500)
    }

    override fun onResume() {
        super.onResume()
        startService(Intent(this, ServerService::class.java))
        loadAttempts = 0
        handler.postDelayed(loadRunnable, 300)
    }

    override fun onDestroy() {
        handler.removeCallbacks(loadRunnable)
        super.onDestroy()
    }
}
