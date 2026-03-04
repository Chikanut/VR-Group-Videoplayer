package com.vrclass.player;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.util.Log;

import com.unity3d.player.UnityPlayer;

import org.json.JSONObject;

public class ADBBridge {
    private static final String TAG = "ADBBridge";
    private static final String ACTION_PREFIX = "com.vrclass.player";
    private static final String LEGACY_ACTION_PREFIX = "com.vrclassroom.player";
    private static final String UNITY_OBJECT = "ADBReceiver";
    private static final String UNITY_METHOD = "OnBroadcastReceived";

    private static BroadcastReceiver receiver;

    private static final String[] COMMANDS = {
        "OPEN",
        "PLAY",
        "PAUSE",
        "STOP",
        "RESTART",
        "RECENTER",
        "SET_MODE",
        "GET_STATUS",
        "SET_LOOP",
        "TOGGLE_DEBUG"
    };

    private static String actionWithPrefix(String prefix, String command) {
        return prefix + "." + command;
    }

    private static String commandFromAction(String fullAction) {
        String primary = ACTION_PREFIX + ".";
        String legacy = LEGACY_ACTION_PREFIX + ".";

        if (fullAction.startsWith(primary)) {
            return fullAction.substring(primary.length());
        }
        if (fullAction.startsWith(legacy)) {
            return fullAction.substring(legacy.length());
        }
        return null;
    }

    public static void initialize() {
        if (receiver != null) {
            Log.w(TAG, "ADBBridge already initialized");
            return;
        }

        final Context context = UnityPlayer.currentActivity;
        if (context == null) {
            Log.e(TAG, "UnityPlayer.currentActivity is null");
            return;
        }

        receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                try {
                    String fullAction = intent.getAction();
                    if (fullAction == null) return;

                    String action = commandFromAction(fullAction);
                    if (action == null) return;

                    JSONObject json = new JSONObject();
                    json.put("action", action);

                    JSONObject extras = new JSONObject();
                    Bundle bundle = intent.getExtras();
                    if (bundle != null) {
                        for (String key : bundle.keySet()) {
                            Object value = bundle.get(key);
                            if (value != null) {
                                extras.put(key, value.toString());
                            }
                        }
                    }
                    json.put("extras", extras);

                    String data = json.toString();
                    Log.i(TAG, "Broadcast received: " + data);

                    UnityPlayer.UnitySendMessage(UNITY_OBJECT, UNITY_METHOD, data);
                } catch (Exception e) {
                    Log.e(TAG, "Error processing broadcast: " + e.getMessage());
                }
            }
        };

        IntentFilter filter = new IntentFilter();
        for (String command : COMMANDS) {
            filter.addAction(actionWithPrefix(ACTION_PREFIX, command));
            filter.addAction(actionWithPrefix(LEGACY_ACTION_PREFIX, command));
        }

        context.registerReceiver(receiver, filter);
        Log.i(TAG, "ADBBridge initialized, listening for broadcasts");
    }

    public static void shutdown() {
        if (receiver != null) {
            try {
                Context context = UnityPlayer.currentActivity;
                if (context != null) {
                    context.unregisterReceiver(receiver);
                }
            } catch (Exception e) {
                Log.w(TAG, "Error unregistering receiver: " + e.getMessage());
            }
            receiver = null;
            Log.i(TAG, "ADBBridge shut down");
        }
    }
}
