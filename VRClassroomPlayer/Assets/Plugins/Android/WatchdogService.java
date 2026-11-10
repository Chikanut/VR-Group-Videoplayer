package com.vrclass.player;

import android.app.ActivityManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

/**
 * Keeps the player on screen: every few seconds, if the player is not visible (after
 * boot, a crash, an update, a quit, or the user went to Quest Home), it launches it again.
 *
 * Runs in its own process (":watchdog" in the manifest) so it survives player crashes.
 * Launching from the background is allowed only with the "display over other apps"
 * permission (tools/quest_deploy.py: appops SYSTEM_ALERT_WINDOW allow). While a Quest
 * system dialog is showing, launches are dropped, so it simply keeps retrying.
 * To stop it until the next boot: Settings > Apps > VR Player > Force stop.
 */
public class WatchdogService extends Service {
    private static final String TAG = "VRPlayerWatchdog";
    private static final String CHANNEL_ID = "watchdog";
    private static final long CHECK_INTERVAL_MS = 10000;
    private static final int FOREGROUND_SERVICE_TYPE_SPECIAL_USE = 1 << 30; // ServiceInfo, API 34

    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean started;

    private final Runnable check = new Runnable() {
        @Override
        public void run() {
            if (!isPlayerRunning()) launchPlayer();
            handler.postDelayed(this, CHECK_INTERVAL_MS);
        }
    };

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL_ID, "Player watchdog", NotificationManager.IMPORTANCE_MIN));
        Notification notification = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_popup_sync)
                .setContentTitle("VR Player")
                .build();
        startForeground(1, notification, FOREGROUND_SERVICE_TYPE_SPECIAL_USE);

        if (!started) {
            started = true;
            Log.i(TAG, "Watchdog started");
            handler.postDelayed(check, CHECK_INTERVAL_MS);
        }
        return START_STICKY;
    }

    private boolean isPlayerRunning() {
        ActivityManager am = getSystemService(ActivityManager.class);
        if (am.getRunningAppProcesses() == null) return false;
        for (ActivityManager.RunningAppProcessInfo p : am.getRunningAppProcesses()) {
            // The process alone is not enough: Quest may close the player window on unlock and
            // keep an empty process. Only a visible activity counts; relaunching an existing
            // activity just brings it back to front (singleTask).
            if (getPackageName().equals(p.processName)
                    && p.importance <= ActivityManager.RunningAppProcessInfo.IMPORTANCE_VISIBLE) return true;
        }
        return false;
    }

    private void launchPlayer() {
        try {
            Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
            if (launch == null) return;
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(launch);
            Log.i(TAG, "Player not visible, launch requested");
        } catch (Exception e) {
            Log.e(TAG, "Launch failed: " + e);
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
