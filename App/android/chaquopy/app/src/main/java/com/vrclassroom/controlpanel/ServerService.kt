package com.vrclassroom.controlpanel

import android.app.Service
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class ServerService : Service() {
    private var started = false
    private val handler = Handler(Looper.getMainLooper())

    private val watchdogRunnable = object : Runnable {
        override fun run() {
            try {
                ensureServerRunning()
            } finally {
                handler.postDelayed(this, 5000)
            }
        }
    }

    private fun ensureServerRunning() {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        val py = Python.getInstance()
        if (!started) {
            py.getModule("android_service").callAttr("start_server")
            started = true
        } else {
            py.getModule("android_service").callAttr("ensure_server_running")
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ensureServerRunning()
        handler.removeCallbacks(watchdogRunnable)
        handler.postDelayed(watchdogRunnable, 5000)
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(watchdogRunnable)
        if (Python.isStarted()) {
            Python.getInstance().getModule("android_service").callAttr("stop_server")
        }
        started = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
