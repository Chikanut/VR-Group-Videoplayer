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
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

/**
 * Keeps the player on screen: every few seconds, if the player is not visible (after
 * boot, a crash, an update, a quit, or the user went to Quest Home), it launches it again.
 * Also hosts the headset agent (Agent.java), the headset's only link to the instructor server.
 *
 * Runs in its own process (":watchdog" in the manifest) so it survives player crashes.
 * Launching from the background is allowed only with the "display over other apps"
 * permission (tools/quest_deploy.py: appops SYSTEM_ALERT_WINDOW allow). While a Quest
 * system dialog is showing, launches are dropped, so it simply keeps retrying.
 * To stop it until the next boot: Settings > Apps > VR Player > Force stop.
 *
 * HTTP on port 8081 (works while the headset sleeps or the player is closed):
 *   POST /wake                   wake the headset (Quest freezes and kills the player in a long sleep)
 *   POST /autostart/off|on       switch relaunching; GET /autostart
 *   POST /server?address=ip:port the server's discovery tells the agent where it is
 *   GET  /status                 the agent's last status JSON
 */
public class WatchdogService extends Service {
    private static final String TAG = "VRPlayerWatchdog";
    private static final String CHANNEL_ID = "watchdog";
    private static final long CHECK_INTERVAL_MS = 10000;
    private static final int FOREGROUND_SERVICE_TYPE_SPECIAL_USE = 1 << 30; // ServiceInfo, API 34
    private static final int WAKE_PORT = 8081;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean started;
    private Agent agent;

    private final BroadcastReceiver screenOn = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            // Bring the player back soon after wake instead of waiting for the next 10s tick.
            handler.removeCallbacks(check);
            handler.postDelayed(check, 2000);
            agent.onScreenOn();
        }
    };

    private final Runnable check = new Runnable() {
        @Override
        public void run() {
            // Not while the headset sleeps: a launch then resumes and pauses Unity every 10s for
            // the whole sleep (seen in logcat), keeping a 1.7 GB GL context churning.
            if (!autostartOff(WatchdogService.this).exists() && !agent.holdRelaunch()
                    && getSystemService(PowerManager.class).isInteractive() && !isPlayerRunning()) {
                Log.i(TAG, "Player not visible");
                Agent.launchPlayer(WatchdogService.this);
            }
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
            agent = Agent.start(this);
            handler.postDelayed(check, CHECK_INTERVAL_MS);
            registerReceiver(screenOn, new IntentFilter(Intent.ACTION_SCREEN_ON), Context.RECEIVER_NOT_EXPORTED);
            startWakeListener();
        }
        return START_STICKY;
    }

    // Instructor switch "POST /autostart/off|on" (port 8081). A marker file: survives reboots and
    // app updates, and needs no sync between this process and the player.
    static File autostartOff(Context context) {
        return new File(context.getFilesDir(), "autostart_off");
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
                            String[] parts = line == null ? new String[0] : line.split(" ");
                            String request = parts.length >= 2 ? parts[0] + " " + parts[1] : "";
                            String body = handle(request);
                            byte[] bytes = (body == null ? "{\"error\":\"not found\"}" : body).getBytes(StandardCharsets.UTF_8);
                            OutputStream out = socket.getOutputStream();
                            out.write(("HTTP/1.1 " + (body != null ? "200 OK" : "404 Not Found")
                                    + "\r\nContent-Type: application/json\r\nContent-Length: " + bytes.length
                                    + "\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                            out.write(bytes);
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

    /** "METHOD /path?query" -> JSON body, or null for 404. */
    private String handle(String request) throws Exception {
        String autostart = "{\"ok\":true,\"autostart\":";
        if (request.startsWith("POST /wake")) {
            agent.remoteWake();
            return "{\"ok\":true}";
        }
        if (request.startsWith("POST /autostart/off")) {
            autostartOff(this).createNewFile();
            Log.i(TAG, request + " -> autostart off");
            return autostart + "false}";
        }
        if (request.startsWith("POST /autostart/on")) {
            autostartOff(this).delete();
            Log.i(TAG, request + " -> autostart on");
            return autostart + "true}";
        }
        if (request.startsWith("GET /autostart")) return autostart + !autostartOff(this).exists() + "}";
        if (request.startsWith("POST /server?address=")) {
            agent.setServerAddress(URLDecoder.decode(request.substring(request.indexOf('=') + 1), "UTF-8"));
            return "{\"ok\":true}";
        }
        if (request.startsWith("GET /status")) return agent.statusJson();
        return null;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
