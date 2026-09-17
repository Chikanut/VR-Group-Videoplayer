package com.vrclass.player;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.util.Log;

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

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        int pid = getIntent().getIntExtra("pid", -1);
        Log.i(TAG, "Restarting player, killing pid " + pid);
        if (pid > 0 && pid != Process.myPid()) {
            Process.killProcess(pid);
        }

        new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
            @Override
            public void run() {
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
        }, RELAUNCH_DELAY_MS);
    }
}
