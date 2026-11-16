package com.vrclass.player;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.util.Log;

import java.io.File;

/**
 * Restarts the player process. Runs in its own process (":restart" in the manifest):
 * it kills the player process, then launches the player again from a clean process.
 *
 * Used after the headset wakes from sleep during an 8K video: Unity's video pipeline
 * leaks gigabytes of GPU memory across sleep/wake, which only a process restart frees.
 */
public class RestartActivity extends Activity {
    private static final String TAG = "VRPlayerRestart";
    private static final long RELAUNCH_DELAY_MS = 800;
    private static final long POLL_MS = 100;
    private static final int MAX_POLLS = 50; // 5s

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        final int pid = getIntent().getIntExtra("pid", -1);
        Log.i(TAG, "Restarting player, killing pid " + pid);
        if (pid > 0 && pid != Process.myPid()) {
            Process.killProcess(pid);
        }

        // Relaunch only after the old process is really gone (plus a moment for its GPU memory
        // to be returned): two players alive at once do not fit into the headset's memory.
        final Handler handler = new Handler(Looper.getMainLooper());
        final File oldProcess = new File("/proc/" + pid);
        handler.postDelayed(new Runnable() {
            private int polls;
            private boolean gone;

            @Override
            public void run() {
                if (!gone) {
                    gone = pid <= 0 || !oldProcess.exists() || ++polls >= MAX_POLLS;
                    handler.postDelayed(this, gone ? RELAUNCH_DELAY_MS : POLL_MS);
                    return;
                }
                try {
                    Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
                    if (launch != null) {
                        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
                        startActivity(launch);
                        Log.i(TAG, "Player relaunched");
                    } else {
                        Log.e(TAG, "No launch intent for " + getPackageName());
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Relaunch failed", e);
                }
                finish();
                Process.killProcess(Process.myPid());
            }
        }, POLL_MS);
    }
}
