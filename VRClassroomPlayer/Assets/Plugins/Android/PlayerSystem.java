package com.vrclass.player;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Headset-level helpers called from C# (ServerConnection):
 *  - keep the headset awake while the server is connected (virtual proximity sensor),
 *  - start the relaunch watchdog,
 *  - silent self-update from the instructor server.
 *
 * Silent update works only when this app is its own "installer of record"
 * (tools/quest_deploy.py installs with `adb install -i com.vrclass.player`); otherwise
 * Android shows a one-time confirmation dialog in the headset.
 */
public class PlayerSystem {
    private static final String TAG = "VRPlayerSystem";
    private static final AtomicBoolean updating = new AtomicBoolean(false);

    public static void setKeepAwake(Context context, boolean keepAwake) {
        // Accepted from any app on Horizon OS; resets on reboot.
        String action = keepAwake
                ? "com.oculus.vrpowermanager.prox_close"
                : "com.oculus.vrpowermanager.automation_disable";
        context.sendBroadcast(new Intent(action));
        Log.i(TAG, "Keep awake " + keepAwake);
    }

    /** Instructor "sleep": virtual proximity FAR, the headset turns off its display and sleeps (~15s). */
    public static void sleep(Context context) {
        context.sendBroadcast(new Intent("com.oculus.vrpowermanager.prox_far"));
        Log.i(TAG, "Sleep requested");
    }

    public static void startWatchdog(Context context) {
        try {
            context.startForegroundService(new Intent(context, WatchdogService.class));
        } catch (Exception e) {
            Log.e(TAG, "Watchdog start failed", e);
        }
    }

    /**
     * Installs a downloaded APK file if its sha256 matches. The download happens in C#:
     * Unity's network security config blocks plain HTTP for Java, not for Mono sockets.
     */
    public static void installUpdate(final Context context, final String apkPath, final String sha256) {
        if (!updating.compareAndSet(false, true)) {
            Log.w(TAG, "Update already in progress");
            return;
        }
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    installUpdateBlocking(context.getApplicationContext(), apkPath, sha256);
                } catch (Exception e) {
                    Log.e(TAG, "Update failed: " + e);
                } finally {
                    updating.set(false);
                }
            }
        }, "PlayerSelfUpdate").start();
    }

    private static void installUpdateBlocking(Context context, String apkPath, String sha256) throws Exception {
        String expected = sha256 == null ? "" : sha256.trim().toLowerCase();
        if (expected.isEmpty()) throw new IllegalArgumentException("sha256 missing");

        Log.i(TAG, "Update install " + apkPath);
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params =
                new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName());
        params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        int sessionId = installer.createSession(params);

        File apk = new File(apkPath);
        try (PackageInstaller.Session session = installer.openSession(sessionId)) {
            String actual;
            try (InputStream in = new FileInputStream(apk);
                 OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
                actual = sha256Of(in, out);
                session.fsync(out);
            }
            // Never install a truncated or wrong file.
            if (!expected.equals(actual)) {
                session.abandon();
                throw new IllegalStateException("sha256 mismatch: got " + actual);
            }
            Intent result = new Intent(context, InstallResultReceiver.class);
            PendingIntent pending = PendingIntent.getBroadcast(context, sessionId, result,
                    PendingIntent.FLAG_MUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            session.commit(pending.getIntentSender());
            Log.i(TAG, "Update committed, the app restarts when it is installed");
        } finally {
            apk.delete(); // the session keeps its own copy
        }
    }

    /** Hex sha256 of the stream; also copies it to out when out is not null. */
    private static String sha256Of(InputStream in, OutputStream out) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[1 << 16];
        int n;
        while ((n = in.read(buffer)) > 0) {
            digest.update(buffer, 0, n);
            if (out != null) out.write(buffer, 0, n);
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : digest.digest()) hex.append(String.format("%02x", b));
        return hex.toString();
    }

    public static class InstallResultReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context context, Intent intent) {
            int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            String message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            Log.i(TAG, "Update install status=" + status + " message=" + message);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                // Not its own installer yet: show the system confirmation in the headset once.
                Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm != null) {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    context.startActivity(confirm);
                }
            }
        }
    }
}
