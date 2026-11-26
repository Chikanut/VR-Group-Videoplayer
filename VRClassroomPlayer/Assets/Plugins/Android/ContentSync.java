package com.vrclass.player;

import android.content.Context;
import android.media.MediaScannerConnection;
import android.os.SystemClock;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * Downloads from the instructor server, one at a time, on its own thread:
 *  - videos into /sdcard/Movies ("sync_content"): a file is skipped when one with the same
 *    name and size is there. Downloads go to ".partial-<name>" and resume after a dropped
 *    connection (HTTP Range); they pause while the player is playing, so a class video never
 *    competes with a download for Wi-Fi and storage.
 *  - the player APK ("update"): skipped when the installed APK has that sha256, then
 *    installed silently by PlayerSystem.installUpdate.
 * Progress goes into every agent status ("content", "update", "files", "storageFreeMb").
 */
final class ContentSync {
    private static final String TAG = "VRPlayerContent";
    private static final String PARTIAL_PREFIX = ".partial-";
    private static final long KEEP_FREE_BYTES = 500L * 1024 * 1024;
    private static final int ATTEMPTS = 6;

    private final Context context;
    private final Agent agent;
    private final LinkedBlockingQueue<Runnable> jobs = new LinkedBlockingQueue<>();

    // Progress, read by Agent.buildStatus on another thread.
    private volatile String state = "idle";     // idle | downloading | waiting | error
    private volatile String currentFile = "";
    private volatile long done;
    private volatile long total;
    private volatile int queued;
    private volatile String lastError = "";
    private volatile String updateState = "";   // "", downloading N%, installing, up to date, failed: ...
    private volatile boolean cancelled;

    ContentSync(Context context, Agent agent) {
        this.context = context;
        this.agent = agent;
        Agent.startThread("agent-content", this::worker);
    }

    private void worker() {
        while (true) {
            try {
                Runnable job = jobs.take();
                job.run();
            } catch (InterruptedException e) {
                return;
            } catch (Throwable t) {
                Log.e(TAG, "Job failed", t);
            }
        }
    }

    // ─── Commands ───────────────────────────────────────────────────────────────

    /** files: [{"name": "a.mp4", "size": 123, "url": "/api/content/files/a.mp4"}, ...] */
    void sync(JSONArray files) {
        if (files == null) return;
        cancelled = false;
        lastError = "";
        List<JSONObject> wanted = new ArrayList<>();
        for (int i = 0; i < files.length(); i++) {
            JSONObject file = files.optJSONObject(i);
            if (file != null && safeName(file.optString("name")) != null) wanted.add(file);
        }
        queued += wanted.size();
        jobs.add(() -> {
            state = "idle";
            for (JSONObject file : wanted) {
                queued = Math.max(0, queued - 1);
                if (cancelled) continue;
                downloadVideo(file.optString("name"), file.optLong("size", -1), agent.serverUrl(file.optString("url")));
            }
            if (!"error".equals(state)) state = "idle";
            currentFile = "";
            agent.onContentChanged();
        });
    }

    void cancel() {
        cancelled = true;
        Log.i(TAG, "Downloads cancelled");
    }

    void delete(JSONArray names) {
        if (names == null) return;
        for (int i = 0; i < names.length(); i++) {
            String name = safeName(names.optString(i));
            if (name == null) continue;
            File file = new File(Agent.moviesDir(), name);
            boolean deleted = file.delete();
            new File(Agent.moviesDir(), PARTIAL_PREFIX + name).delete();
            Log.i(TAG, "Delete " + name + ": " + deleted);
            if (deleted) scan(file);
        }
    }

    void update(String url, String sha256) {
        String expected = sha256 == null ? "" : sha256.trim().toLowerCase();
        if (url == null || url.isEmpty() || expected.isEmpty()) {
            Log.w(TAG, "update ignored: url or sha256 missing");
            return;
        }
        jobs.add(() -> {
            File apk = new File(context.getCacheDir(), "player-update.apk");
            try {
                if (expected.equals(PlayerSystem.sha256Of(new File(context.getApplicationInfo().sourceDir)))) {
                    updateState = "up to date";
                    Log.i(TAG, "Update skipped: installed APK already matches");
                    return;
                }
                apk.delete();
                updateState = "downloading";
                download(url, apk, -1, false, true);
                updateState = "installing";
                agent.onContentChanged();
                PlayerSystem.installUpdate(context, apk.getAbsolutePath(), expected); // the app restarts when installed
            } catch (Exception e) {
                updateState = "failed: " + e.getMessage();
                Log.e(TAG, "Update failed: " + e);
            } finally {
                agent.onContentChanged();
            }
        });
    }

    // ─── Status ─────────────────────────────────────────────────────────────────

    void putStatus(JSONObject s) throws Exception {
        JSONArray files = new JSONArray();
        File[] list = Agent.moviesDir().listFiles();
        if (list != null) {
            for (File file : list) {
                if (!file.isFile() || file.getName().startsWith(".")) continue;
                files.put(new JSONObject().put("name", file.getName()).put("size", file.length()));
            }
        }
        s.put("files", files);
        s.put("storageFreeMb", Agent.moviesDir().getUsableSpace() / (1024 * 1024));
        s.put("content", new JSONObject()
                .put("state", state)
                .put("file", currentFile)
                .put("done", done)
                .put("total", total)
                .put("queued", queued)
                .put("error", lastError));
        s.put("update", updateState);
    }

    // ─── Downloads ──────────────────────────────────────────────────────────────

    private void downloadVideo(String name, long size, String url) {
        File target = new File(Agent.moviesDir(), name);
        if (size >= 0 && target.isFile() && target.length() == size) return;
        File partial = new File(Agent.moviesDir(), PARTIAL_PREFIX + name);
        currentFile = name;
        Log.i(TAG, "Download " + name + " (" + size + " bytes) from " + url);
        try {
            long needed = size - (partial.isFile() ? partial.length() : 0);
            if (size > 0 && needed > Agent.moviesDir().getUsableSpace() - KEEP_FREE_BYTES) {
                throw new IOException("not enough space (" + (needed >> 20) + " MB needed)");
            }
            download(url, partial, size, true, false);
            if (cancelled) return;
            if (target.exists() && !target.delete()) throw new IOException("cannot replace the old " + name);
            if (!partial.renameTo(target)) throw new IOException("cannot rename the download");
            scan(target);
            Log.i(TAG, "Downloaded " + name);
        } catch (Exception e) {
            state = "error";
            lastError = name + ": " + e.getMessage();
            Log.e(TAG, "Download " + name + " failed: " + e);
        }
    }

    /**
     * GET url into file, resuming what is already there. size < 0 = unknown (taken from the
     * response). Retries dropped connections with backoff.
     */
    private void download(String url, File file, long size, boolean pauseWhilePlaying, boolean isUpdate) throws Exception {
        IOException last = null;
        for (int attempt = 1; attempt <= ATTEMPTS && !cancelled; attempt++) {
            try {
                downloadOnce(url, file, size, pauseWhilePlaying, isUpdate);
                return;
            } catch (IOException e) {
                last = e;
                Log.w(TAG, "Download attempt " + attempt + " failed: " + e.getMessage());
                state = "waiting";
                SystemClock.sleep(5000L * attempt);
            }
        }
        if (cancelled) return;
        throw last != null ? last : new IOException("download failed");
    }

    private void downloadOnce(String url, File file, long size, boolean pauseWhilePlaying, boolean isUpdate) throws IOException {
        long have = file.isFile() ? file.length() : 0;
        if (size >= 0 && have > size) {
            file.delete();
            have = 0;
        }
        if (size >= 0 && have == size) return;

        AgentHttp response = AgentHttp.get(url, have, 5000, 30000);
        try {
            int code = response.status;
            if (code == 200) {
                have = 0; // server ignored the range: start over
            } else if (code != 206) {
                throw new IOException("HTTP " + code);
            }
            long length = response.contentLength;
            long expected = size >= 0 ? size : (length >= 0 ? have + length : -1);
            total = expected;
            done = have;
            state = "downloading";

            byte[] buffer = new byte[1 << 18];
            long lastReport = 0;
            try (InputStream in = response.body;
                 OutputStream out = new FileOutputStream(file, have > 0)) {
                for (int n; (n = in.read(buffer)) > 0; ) {
                    out.write(buffer, 0, n);
                    done += n;
                    if (isUpdate && expected > 0) updateState = "downloading " + (done * 100 / expected) + "%";
                    if (cancelled) return;
                    while (pauseWhilePlaying && agent.playerPlaying() && !cancelled) {
                        state = "waiting";
                        SystemClock.sleep(2000);
                    }
                    state = "downloading";
                    long now = SystemClock.elapsedRealtime();
                    if (now - lastReport > 2000) {
                        lastReport = now;
                        agent.onContentChanged();
                    }
                }
            }
            if (expected >= 0 && file.length() != expected) {
                throw new IOException("incomplete: " + file.length() + " of " + expected);
            }
        } finally {
            response.close();
        }
    }

    private void scan(File file) {
        MediaScannerConnection.scanFile(context, new String[]{file.getAbsolutePath()}, null, null);
    }

    /** A bare file name inside Movies, or null: never a path the server could point anywhere else. */
    static String safeName(String name) {
        if (name == null) return null;
        String trimmed = name.trim();
        if (trimmed.isEmpty() || trimmed.startsWith(".") || trimmed.contains("/") || trimmed.contains("\\")) return null;
        return trimmed;
    }
}
