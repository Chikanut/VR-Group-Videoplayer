package com.vrclass.player;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/** Starts the watchdog after the headset boots and after a self-update replaced the app. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Log.i("VRPlayerWatchdog", "Received " + intent.getAction());
        PlayerSystem.startWatchdog(context);
    }
}
