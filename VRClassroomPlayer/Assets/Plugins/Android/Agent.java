package com.vrclass.player;

import android.app.ActivityManager;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Environment;
import android.os.PowerManager;
import android.os.Process;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * The headset agent: the only link between this headset and the instructor server.
 * Lives in the ":watchdog" process (WatchdogService), so it is up whenever the headset is,
 * with or without the player.
 *
 *   server  <-- WebSocket /ws/agent -->  agent  <-- 127.0.0.1:8082, one JSON per line -->  player (Unity)
 *
 * Server -> agent: the same {"type":"command","action":...} messages the player used to get.
 * Actions about the headset (wake, sleep, launch/close/restart_player, autostart, set_name,
 * apply_settings, update, sync_content, cancel_content, delete_content) are handled here;
 * everything else (open, play, pause, stop, seek, ...) is passed to the player.
 * Agent -> server: "register" then "status" every 5s and whenever the player reports: the
 * player's last status merged with what the agent knows (battery, name, files, downloads,
 * playerRunning, autostart). Without a player the state is "closed".
 *
 * All state lives on one thread (exec); the socket readers only post to it.
 */
final class Agent {
    static final String TAG = "VRPlayerAgent";
    private static final int SERVER_PORT = 8000;
    static final int PLAYER_LINK_PORT = 8082;
    private static final long STATUS_INTERVAL_MS = 5000;
    private static final long KEEP_AWAKE_RELEASE_MS = 60000;
    private static final long WAKE_DISCOVERY_HOLD_MS = 30000;
    private static final long REMOTE_WAKE_WINDOW_MS = 60000;
    private static final int FAILURES_BEFORE_DISCOVERY = 3;

    private static volatile Agent instance;

    private final Context context;
    private final SharedPreferences prefs;
    private final ScheduledExecutorService exec = Executors.newSingleThreadScheduledExecutor();
    private final ExecutorService discoveryPool = Executors.newFixedThreadPool(32);
    private final Semaphore uplinkWake = new Semaphore(0);
    private final ContentSync content;
    private final String deviceId;
    private final String version;

    // Uplink (server). ws is written by the uplink thread only.
    private volatile AgentWs ws;
    private volatile boolean connected;
    private volatile String serverAddress;      // "ip:port"
    private volatile long discoveryHoldUntil;   // elapsedRealtime

    // Player link (exec thread only, except the socket itself).
    private Socket playerSocket;
    private OutputStream playerOut;
    private JSONObject playerStatus;
    private volatile String playerState = "closed";

    // Headset state (exec thread).
    private boolean keepAwake;
    private boolean sleepRequested;
    private long disconnectedSince = -1;
    private volatile long remoteWakeAt = -REMOTE_WAKE_WINDOW_MS;
    private volatile boolean holdRelaunch;      // instructor closed the player: watchdog must not reopen it
    private String settingsProfile = "";
    private long lastStatusSentAt;
    private final AtomicReference<String> statusJson = new AtomicReference<>("{}");

    static Agent get() {
        return instance;
    }

    static synchronized Agent start(Context context) {
        if (instance == null) {
            instance = new Agent(context.getApplicationContext());
            instance.begin();
        }
        return instance;
    }

    private Agent(Context context) {
        this.context = context;
        this.prefs = context.getSharedPreferences("agent", Context.MODE_PRIVATE);
        this.deviceId = readDeviceId(context);
        this.version = readVersion(context);
        this.content = new ContentSync(context, this);
        migrateFromPlayerPrefs();
        serverAddress = prefs.getString("server", "");
    }

    private void begin() {
        Log.i(TAG, "Agent " + version + " starting, device " + deviceId + ", server '" + serverAddress + "'");
        exec.scheduleWithFixedDelay(this::tick, STATUS_INTERVAL_MS, STATUS_INTERVAL_MS, TimeUnit.MILLISECONDS);
        startThread("agent-uplink", this::uplinkLoop);
        startThread("agent-player-link", this::playerLinkLoop);
    }

    // ─── Facts for WatchdogService ─────────────────────────────────────────────

    boolean holdRelaunch() {
        return holdRelaunch;
    }

    String statusJson() {
        return statusJson.get();
    }

    boolean playerPlaying() {
        String state = playerState;
        return "playing".equals(state) || "loading".equals(state);
    }

    /** POST :8081/wake - also counts as "we woke it ourselves" for the screen-on handler. */
    void remoteWake() {
        remoteWakeAt = SystemClock.elapsedRealtime();
        context.sendBroadcast(new Intent("com.oculus.vrpowermanager.prox_close"));
        Log.i(TAG, "Remote wake");
    }

    /** POST :8081/server?address=ip:port (the server's discovery found us). */
    void setServerAddress(String address) {
        String normalized = address == null ? "" : address.trim();
        if (normalized.isEmpty() || normalized.equals(serverAddress)) return;
        Log.i(TAG, "Server address pushed: '" + serverAddress + "' -> '" + normalized + "'");
        saveServerAddress(normalized);
        AgentWs current = ws;
        if (current != null) current.close();
        uplinkWake.release();
    }

    void onScreenOn() {
        exec.execute(() -> {
            sleepRequested = false;
            keepAwake = false; // unknown after a sleep: re-asserted by updateKeepAwake if wanted
            discoveryHoldUntil = SystemClock.elapsedRealtime() + WAKE_DISCOVERY_HOLD_MS;
            boolean remote = SystemClock.elapsedRealtime() - remoteWakeAt < REMOTE_WAKE_WINDOW_MS;
            if (!wantKeepAwake() && !remote) {
                // After an instructor "sleep" the virtual proximity sensor stays FAR: hand it
                // back, or a headset woken with the power button falls asleep again.
                context.sendBroadcast(new Intent("com.oculus.vrpowermanager.automation_disable"));
                Log.i(TAG, "Screen on: proximity sensor back to automatic");
            }
            updateKeepAwake();
            uplinkWake.release(); // reconnect now instead of after the retry delay
        });
    }

    void onContentChanged() {
        exec.execute(this::sendStatus);
    }

    // ─── Periodic tick (exec) ───────────────────────────────────────────────────

    private void tick() {
        try {
            updateKeepAwake();
            if (SystemClock.elapsedRealtime() - lastStatusSentAt >= STATUS_INTERVAL_MS - 500) sendStatus();
            else statusJson.set(buildStatus("status").toString());
        } catch (Throwable t) {
            Log.e(TAG, "Tick failed", t);
        }
    }

    private boolean wantKeepAwake() {
        return connected && !sleepRequested && !WatchdogService.autostartOff(context).exists();
    }

    /**
     * While the server is connected (and autostart is on) the headset must not fall asleep:
     * sleep leaks video memory and drops the class. Released only after a longer outage, so
     * short Wi-Fi blips do not toggle it. With autostart off the headset is in normal use.
     */
    private void updateKeepAwake() {
        if (sleepRequested) {
            keepAwake = false; // prox_far is in effect; automation_disable would undo it
            return;
        }
        if (wantKeepAwake()) {
            disconnectedSince = -1;
            if (keepAwake) return;
            keepAwake = true;
            context.sendBroadcast(new Intent("com.oculus.vrpowermanager.prox_close"));
            Log.i(TAG, "Keep awake on");
            return;
        }
        if (!keepAwake) return;
        if (!connected) {
            long now = SystemClock.elapsedRealtime();
            if (disconnectedSince < 0) disconnectedSince = now;
            if (now - disconnectedSince < KEEP_AWAKE_RELEASE_MS) return;
        }
        keepAwake = false;
        context.sendBroadcast(new Intent("com.oculus.vrpowermanager.automation_disable"));
        Log.i(TAG, "Keep awake off");
    }

    // ─── Status ─────────────────────────────────────────────────────────────────

    private JSONObject buildStatus(String type) {
        JSONObject s = new JSONObject();
        try {
            boolean linked = playerOut != null && playerStatus != null;
            if (linked) s = new JSONObject(playerStatus.toString());
            s.put("type", type);
            if (!linked) {
                s.put("state", "closed");
                s.put("file", "");
                s.put("time", 0);
                s.put("duration", 0);
            }
            s.put("agent", true);
            s.put("agentVersion", version);
            if (!s.has("playerVersion") || s.optString("playerVersion").isEmpty()) s.put("playerVersion", version);
            s.put("deviceId", deviceId);
            s.put("androidId", deviceId);
            s.put("deviceName", prefs.getString("deviceName", ""));
            s.put("deviceModel", Build.MODEL);
            s.put("ip", localIp());
            s.put("playerRunning", linked);
            s.put("autostart", !WatchdogService.autostartOff(context).exists());
            s.put("settingsProfile", settingsProfile);
            Intent battery = context.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (battery != null) {
                int level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = battery.getIntExtra(BatteryManager.EXTRA_SCALE, 100);
                s.put("battery", level < 0 || scale <= 0 ? -1 : level * 100 / scale);
                s.put("batteryCharging", battery.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0);
            }
            content.putStatus(s);
        } catch (Exception e) {
            Log.w(TAG, "Status build failed: " + e);
        }
        return s;
    }

    private void sendStatus() {
        JSONObject status = buildStatus("status");
        String text = status.toString();
        statusJson.set(text);
        lastStatusSentAt = SystemClock.elapsedRealtime();
        sendToServer(text);
    }

    private void sendToServer(String text) {
        AgentWs current = ws;
        if (current == null || !connected) return;
        try {
            current.sendText(text);
        } catch (IOException e) {
            Log.w(TAG, "Send failed: " + e.getMessage());
            current.close(); // the uplink loop reconnects
        }
    }

    // ─── Uplink: WebSocket to the server ───────────────────────────────────────

    private void uplinkLoop() {
        int failures = 0;
        while (true) {
            try {
                String address = serverAddress;
                if (address.isEmpty()) {
                    address = discoveryAllowed() ? discoverServer() : null;
                    if (address == null) {
                        waitForWake(10000);
                        continue;
                    }
                    saveServerAddress(address);
                }

                try {
                    runSession(address);
                    failures = 0; // the server closed the socket normally (restart, replaced)
                } catch (IOException e) {
                    failures++;
                    Log.w(TAG, "Server " + address + " failed (" + failures + "): " + e.getMessage());
                }

                if (failures >= FAILURES_BEFORE_DISCOVERY && discoveryAllowed()) {
                    // Keep the saved address unless something else answers: a short server
                    // restart must not force every headset into a full scan.
                    failures = 0;
                    String found = discoverServer();
                    if (found != null && !found.equals(serverAddress)) saveServerAddress(found);
                }
                // Asleep, Wi-Fi is usually down: retry rarely; screen-on wakes the loop at once.
                waitForWake(context.getSystemService(PowerManager.class).isInteractive() ? 3000 : 15000);
            } catch (Throwable t) {
                Log.e(TAG, "Uplink loop error", t);
                waitForWake(5000);
            }
        }
    }

    private void runSession(String address) throws IOException {
        int colon = address.lastIndexOf(':');
        String host = colon > 0 ? address.substring(0, colon) : address;
        int port = colon > 0 ? Integer.parseInt(address.substring(colon + 1)) : SERVER_PORT;
        AgentWs session = AgentWs.connect(host, port, "/ws/agent", 3000, 45000);
        ws = session;
        try {
            Log.i(TAG, "Connected to server " + address);
            exec.execute(() -> {
                connected = true;
                sendToServer(buildStatus("register").toString());
                sendStatus();
                updateKeepAwake();
            });
            while (true) {
                String message = session.readText();
                exec.execute(() -> handleServerMessage(message));
            }
        } finally {
            session.close();
            if (ws == session) ws = null;
            exec.execute(() -> {
                if (ws == null) connected = false;
                updateKeepAwake();
            });
            Log.i(TAG, "Disconnected from server " + address);
        }
    }

    private boolean discoveryAllowed() {
        boolean awake = context.getSystemService(PowerManager.class).isInteractive();
        return awake && SystemClock.elapsedRealtime() >= discoveryHoldUntil;
    }

    private void waitForWake(long ms) {
        try {
            uplinkWake.tryAcquire(ms, TimeUnit.MILLISECONDS);
            uplinkWake.drainPermits();
        } catch (InterruptedException ignored) { }
    }

    private void saveServerAddress(String address) {
        serverAddress = address;
        prefs.edit().putString("server", address).apply();
    }

    /** Scans the local /24 for the instructor server (port 8000, GET /api/server-info). */
    private String discoverServer() {
        String ip = localIp();
        int dot = ip.lastIndexOf('.');
        if (ip.equals("0.0.0.0") || dot < 0) return null;
        String subnet = ip.substring(0, dot + 1);
        Log.i(TAG, "Scanning " + subnet + "0/24 for the server");
        AtomicReference<String> found = new AtomicReference<>();
        java.util.List<java.util.concurrent.Future<?>> probes = new java.util.ArrayList<>();
        for (int i = 1; i <= 254; i++) {
            String host = subnet + i;
            probes.add(discoveryPool.submit(() -> {
                if (found.get() == null && isServer(host)) found.compareAndSet(null, host + ":" + SERVER_PORT);
            }));
        }
        for (java.util.concurrent.Future<?> probe : probes) {
            try { probe.get(); } catch (Exception ignored) { }
        }
        Log.i(TAG, "Scan done: " + found.get());
        return found.get();
    }

    private static boolean isServer(String host) {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, SERVER_PORT), 1500);
        } catch (IOException e) {
            return false;
        }
        AgentHttp response = null;
        try {
            response = AgentHttp.get("http://" + host + ":" + SERVER_PORT + "/api/server-info", 0, 2000, 2000);
            if (response.status != 200) return false;
            JSONObject info = new JSONObject(response.readText(4096));
            return info.has("ip") && info.has("port");
        } catch (Exception e) {
            return false;
        } finally {
            if (response != null) response.close();
        }
    }

    /** Absolute URL for a server path ("/api/..."): the server never has to guess its own IP. */
    String serverUrl(String pathOrUrl) {
        if (pathOrUrl == null || !pathOrUrl.startsWith("/")) return pathOrUrl;
        String address = serverAddress;
        if (!address.contains(":")) address += ":" + SERVER_PORT;
        return "http://" + address + pathOrUrl;
    }

    // ─── Server commands (exec) ────────────────────────────────────────────────

    private void handleServerMessage(String raw) {
        JSONObject command;
        try {
            command = new JSONObject(raw);
        } catch (Exception e) {
            Log.w(TAG, "Bad message from server: " + e.getMessage());
            return;
        }
        if (!"command".equals(command.optString("type"))) return;
        String action = command.optString("action").toLowerCase();
        Log.i(TAG, "Command " + action);
        try {
            switch (action) {
                case "set_name": {
                    if (!command.has("name")) break;
                    String name = command.optString("name").trim();
                    prefs.edit().putString("deviceName", name).apply();
                    sendToPlayer(command); // the HUD shows it
                    sendStatus();
                    break;
                }
                case "wake":
                    remoteWake();
                    break;
                case "sleep":
                    sendToPlayer(command); // stops the video
                    sleepRequested = true;
                    keepAwake = false;
                    context.sendBroadcast(new Intent("com.oculus.vrpowermanager.prox_far"));
                    Log.i(TAG, "Sleep requested");
                    break;
                case "launch_player":
                    holdRelaunch = false;
                    launchPlayer(context);
                    break;
                case "close_player":
                    holdRelaunch = true;
                    killPlayer();
                    break;
                case "restart_player":
                    holdRelaunch = false;
                    killPlayer();
                    exec.schedule(() -> launchPlayer(context), 1500, TimeUnit.MILLISECONDS);
                    break;
                case "autostart": {
                    File marker = WatchdogService.autostartOff(context);
                    if (command.optBoolean("enabled", true)) marker.delete();
                    else marker.createNewFile();
                    updateKeepAwake();
                    sendStatus();
                    break;
                }
                case "apply_settings":
                    if (!command.has("settings")) break;
                    settingsProfile = PlayerSystem.applySettings(context, command.optString("settings"));
                    sendStatus();
                    break;
                case "update":
                    content.update(serverUrl(command.optString("url")), command.optString("sha256"));
                    break;
                case "sync_content":
                    content.sync(command.optJSONArray("files"));
                    break;
                case "cancel_content":
                    content.cancel();
                    break;
                case "set_environment":
                    content.environment(command.optJSONObject("environment"), serverUrl(command.optString("logoUrl")));
                    break;
                case "delete_content":
                    content.delete(command.optJSONArray("files"));
                    sendStatus();
                    break;
                default:
                    if (!sendToPlayer(command)) Log.w(TAG, action + " dropped: player not running");
                    break;
            }
        } catch (Exception e) {
            Log.e(TAG, "Command " + action + " failed", e);
        }
    }

    static void launchPlayer(Context context) {
        try {
            Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
            if (launch == null) return;
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launch);
            Log.i(TAG, "Player launch requested");
        } catch (Exception e) {
            Log.e(TAG, "Launch failed: " + e);
        }
    }

    /** Same app, same uid: the agent may end the player's process. */
    private void killPlayer() {
        ActivityManager am = context.getSystemService(ActivityManager.class);
        if (am.getRunningAppProcesses() == null) return;
        for (ActivityManager.RunningAppProcessInfo p : am.getRunningAppProcesses()) {
            if (context.getPackageName().equals(p.processName)) {
                Log.i(TAG, "Closing player pid " + p.pid);
                Process.killProcess(p.pid);
            }
        }
    }

    // ─── Player link: 127.0.0.1:8082, one JSON object per line ─────────────────

    private void playerLinkLoop() {
        while (true) {
            try (ServerSocket server = new ServerSocket()) {
                server.setReuseAddress(true);
                server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), PLAYER_LINK_PORT));
                Log.i(TAG, "Player link on 127.0.0.1:" + PLAYER_LINK_PORT);
                while (true) {
                    Socket client = server.accept();
                    client.setTcpNoDelay(true);
                    startThread("agent-player-reader", () -> readPlayer(client));
                }
            } catch (Throwable t) {
                Log.e(TAG, "Player link stopped, restarting: " + t);
                SystemClock.sleep(2000);
            }
        }
    }

    private void readPlayer(Socket client) {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(client.getInputStream(), StandardCharsets.UTF_8))) {
            OutputStream out = client.getOutputStream();
            exec.execute(() -> attachPlayer(client, out));
            for (String line; (line = reader.readLine()) != null; ) {
                String message = line;
                exec.execute(() -> handlePlayerMessage(client, message));
            }
        } catch (IOException e) {
            Log.i(TAG, "Player link closed: " + e.getMessage());
        } finally {
            try { client.close(); } catch (IOException ignored) { }
            exec.execute(() -> detachPlayer(client));
        }
    }

    private void attachPlayer(Socket client, OutputStream out) {
        if (playerSocket != null && playerSocket != client) {
            try { playerSocket.close(); } catch (IOException ignored) { } // a newer player instance wins
        }
        playerSocket = client;
        playerOut = out;
        playerStatus = null;
        Log.i(TAG, "Player connected");
        sendEnvironmentToPlayer();
        // The agent owns the name: hand it to a fresh player (its HUD shows it).
        if (prefs.contains("deviceName")) {
            try {
                sendToPlayer(new JSONObject().put("type", "command").put("action", "set_name")
                        .put("name", prefs.getString("deviceName", "")));
            } catch (Exception ignored) { }
        }
    }

    private void detachPlayer(Socket client) {
        if (playerSocket != client) return;
        playerSocket = null;
        playerOut = null;
        playerStatus = null;
        playerState = "closed";
        Log.i(TAG, "Player disconnected");
        sendStatus();
    }

    private void handlePlayerMessage(Socket client, String line) {
        if (playerSocket != client) return;
        JSONObject message;
        try {
            message = new JSONObject(line);
        } catch (Exception e) {
            Log.w(TAG, "Bad message from player: " + e.getMessage());
            return;
        }
        String type = message.optString("type");
        if (!"register".equals(type) && !"status".equals(type)) return;
        message.remove("type");
        if (!prefs.contains("deviceName") && !message.optString("deviceName").isEmpty()) {
            // First run after updating from a player-only build: adopt the player's name.
            prefs.edit().putString("deviceName", message.optString("deviceName").trim()).apply();
        }
        boolean first = playerStatus == null;
        playerStatus = message;
        playerState = message.optString("state", "idle");
        if (first) Log.i(TAG, "Player registered, state " + playerState);
        sendStatus();
    }

    /** The stored waiting-room look (ContentSync.environment) for the player; default when none. */
    void sendEnvironmentToPlayer() {
        try {
            File file = content.environmentFile();
            JSONObject env = file.isFile()
                    ? new JSONObject(new String(java.nio.file.Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8))
                    : new JSONObject().put("custom", false);
            File logo = content.environmentLogo();
            sendToPlayer(new JSONObject().put("type", "command").put("action", "apply_environment")
                    .put("environment", env).put("logoPath", logo.isFile() ? logo.getAbsolutePath() : ""));
        } catch (Exception e) {
            Log.w(TAG, "Environment to player failed: " + e);
        }
    }

    private synchronized boolean sendToPlayer(JSONObject command) {
        if (playerOut == null) return false;
        try {
            playerOut.write((command.toString() + "\n").getBytes(StandardCharsets.UTF_8));
            playerOut.flush();
            return true;
        } catch (IOException e) {
            Log.w(TAG, "Send to player failed: " + e.getMessage());
            try { playerSocket.close(); } catch (Exception ignored) { }
            return false;
        }
    }

    // ─── Helpers ────────────────────────────────────────────────────────────────

    /** One-time carry-over of what the player kept in Unity PlayerPrefs before the agent existed. */
    private void migrateFromPlayerPrefs() {
        if (prefs.getBoolean("migrated", false)) return;
        SharedPreferences unity = context.getSharedPreferences(context.getPackageName() + ".v2.playerprefs", Context.MODE_PRIVATE);
        SharedPreferences.Editor edit = prefs.edit().putBoolean("migrated", true);
        String server = unityString(unity, "instructor_ip");
        if (!server.isEmpty()) edit.putString("server", server.contains(":") ? server : server + ":" + SERVER_PORT);
        String name = unityString(unity, "device_name");
        if (!name.isEmpty()) edit.putString("deviceName", name);
        edit.apply();
        Log.i(TAG, "Migrated from player prefs: server '" + server + "', name '" + name + "'");
    }

    private static String unityString(SharedPreferences unity, String key) {
        try {
            String value = unity.getString(key, "");
            return value == null ? "" : URLDecoder.decode(value, "UTF-8").trim(); // Unity URL-encodes strings
        } catch (Exception e) {
            return "";
        }
    }

    static String readDeviceId(Context context) {
        String id = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
        return id == null ? "unknown" : id;
    }

    private static String readVersion(Context context) {
        try {
            return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "";
        }
    }

    static String localIp() {
        try {
            for (NetworkInterface nif : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!nif.isUp() || nif.isLoopback()) continue;
                for (InetAddress address : Collections.list(nif.getInetAddresses())) {
                    if (address instanceof Inet4Address && !address.isLoopbackAddress()) return address.getHostAddress();
                }
            }
        } catch (Exception ignored) { }
        return "0.0.0.0";
    }

    static File moviesDir() {
        return Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES);
    }

    static void startThread(String name, Runnable body) {
        Thread thread = new Thread(body, name);
        thread.setDaemon(true);
        thread.start();
    }
}
