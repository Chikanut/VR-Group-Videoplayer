package com.vrclass.player;

import android.app.ActivityManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

/**
 * Keeps the player on screen: every few seconds, if the player is not visible (after
 * boot, a crash, an update, a quit, or the user went to Quest Home), it launches it again.
 *
 * Runs in its own process (":watchdog" in the manifest) so it survives player crashes.
 * Launching from the background is allowed only with the "display over other apps"
 * permission (tools/quest_deploy.py: appops SYSTEM_ALERT_WINDOW allow). While a Quest
 * system dialog is showing, launches are dropped, so it simply keeps retrying.
 * To stop it until the next boot: Settings > Apps > VR Player > Force stop.
 * The instructor can switch relaunching off/on: "POST /autostart/off|on" (port 8081).
 *
 * It also wakes the headset on "POST /wake" (port 8081): during a long sleep Quest freezes and
 * kills the player itself, but this foreground-service process stays reachable over Wi-Fi.
 */
public class WatchdogService extends Service {
    private static final String TAG = "VRPlayerWatchdog";
    private static final String CHANNEL_ID = "watchdog";
    private static final long CHECK_INTERVAL_MS = 10000;
    private static final int FOREGROUND_SERVICE_TYPE_SPECIAL_USE = 1 << 30; // ServiceInfo, API 34
    private static final int WAKE_PORT = 8081;
    private static final long REMOTE_WAKE_WINDOW_MS = 60000;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean started;
    private volatile long remoteWakeAt = -REMOTE_WAKE_WINDOW_MS;

    // After an instructor "sleep" the virtual proximity sensor stays FAR, so a headset woken with
    // the power button would fall asleep again. Hand the sensor back unless we woke it ourselves
    // (then the player reconnects and keeps it awake).
    private final BroadcastReceiver screenOn = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            // Bring the player back soon after wake instead of waiting for the next 10s tick.
            handler.removeCallbacks(check);
            handler.postDelayed(check, 2000);
            if (SystemClock.elapsedRealtime() - remoteWakeAt < REMOTE_WAKE_WINDOW_MS) return;
            sendBroadcast(new Intent("com.oculus.vrpowermanager.automation_disable"));
            Log.i(TAG, "Screen on: proximity sensor back to automatic");
        }
    };

    private final Runnable check = new Runnable() {
        @Override
        public void run() {
            // Not while the headset sleeps: a launch then resumes and pauses Unity every 10s for
            // the whole sleep (seen in logcat), keeping a 1.7 GB GL context churning.
            if (!autostartOff().exists() && getSystemService(PowerManager.class).isInteractive()
                    && !isPlayerRunning()) launchPlayer();
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
            registerReceiver(screenOn, new IntentFilter(Intent.ACTION_SCREEN_ON), Context.RECEIVER_NOT_EXPORTED);
            startWakeListener();
        }
        return START_STICKY;
    }

    // Instructor switch "POST /autostart/off|on" (port 8081). A marker file: survives reboots and
    // app updates, and needs no sync between this process and the player.
    private File autostartOff() {
        return new File(getFilesDir(), "autostart_off");
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

    private void startWakeListener() {
        Thread thread = new Thread(new Runnable() {
            @Override
            public void run() {
                try (ServerSocket server = new ServerSocket(WAKE_PORT)) {
                    Log.i(TAG, "Wake listener on port " + WAKE_PORT);
                    while (true) {
                        try (Socket socket = server.accept()) {
                            socket.setSoTimeout(3000);
                            String line = new BufferedReader(new InputStreamReader(
                                    socket.getInputStream(), StandardCharsets.US_ASCII)).readLine();
                            boolean wake = line != null && line.startsWith("POST /wake");
                            if (wake) {
                                remoteWakeAt = SystemClock.elapsedRealtime();
                                sendBroadcast(new Intent("com.oculus.vrpowermanager.prox_close"));
                                Log.i(TAG, "Remote wake");
                            }
                            boolean known = wake;
                            if (line != null && line.startsWith("POST /autostart/off")) {
                                autostartOff().createNewFile();
                                known = true;
                            } else if (line != null && line.startsWith("POST /autostart/on")) {
                                autostartOff().delete();
                                known = true;
                            } else if (line != null && line.startsWith("GET /autostart")) {
                                known = true;
                            }
                            if (known && !wake) Log.i(TAG, line + " -> autostart " + !autostartOff().exists());
                            String body = known
                                    ? "{\"ok\":true,\"autostart\":" + !autostartOff().exists() + "}"
                                    : "{\"error\":\"not found\"}";
                            OutputStream out = socket.getOutputStream();
                            out.write(("HTTP/1.1 " + (known ? "200 OK" : "404 Not Found")
                                    + "\r\nContent-Type: application/json\r\nContent-Length: " + body.length()
                                    + "\r\nConnection: close\r\n\r\n" + body).getBytes(StandardCharsets.US_ASCII));
                            out.flush();
                        } catch (Exception e) {
                            Log.w(TAG, "Wake request failed: " + e);
                        }
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Wake listener stopped: " + e);
                }
            }
        }, "wake-listener");
        thread.setDaemon(true);
        thread.start();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
