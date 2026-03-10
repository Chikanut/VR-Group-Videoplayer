package com.vrclassroom.controlpanel

import android.app.Service
import android.content.Intent
import android.os.IBinder
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class ServerService : Service() {
    private var started = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        if (!started) {
            started = true
            val py = Python.getInstance()
            py.getModule("android_service").callAttr("start_server")
        }
        return START_STICKY
    }

    override fun onDestroy() {
        if (Python.isStarted()) {
            Python.getInstance().getModule("android_service").callAttr("stop_server")
        }
        started = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
