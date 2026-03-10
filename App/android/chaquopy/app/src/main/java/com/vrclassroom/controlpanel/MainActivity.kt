package com.vrclassroom.controlpanel

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        startService(Intent(this, ServerService::class.java))

        val webView = findViewById<WebView>(R.id.webview)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.cacheMode = WebSettings.LOAD_DEFAULT
        Handler(Looper.getMainLooper()).postDelayed({ webView.loadUrl("http://127.0.0.1:8000") }, 2500)
    }

    override fun onDestroy() {
        stopService(Intent(this, ServerService::class.java))
        super.onDestroy()
    }
}
