// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 The TokTok team
package chat.tox.pytox.support;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/** Starts the PyTox foreground service after boot, if stay-connected is on. */
public class BootReceiver extends BroadcastReceiver {
    private static final String PREFS_NAME = "pytox";
    private static final String KEY_STAY_CONNECTED = "stay_connected";
    private static final String FLAG_FILE = ".stay_connected";

    private static boolean shouldStayConnected(Context context) {
        File flag = new File(context.getFilesDir(), FLAG_FILE);
        if (flag.isFile()) {
            try {
                String value = new String(Files.readAllBytes(flag.toPath()), StandardCharsets.UTF_8).trim();
                return "1".equals(value);
            } catch (IOException ignored) {
                // Fall back to SharedPreferences below.
            }
        }
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        // Default false on a fresh install before the user opens PyTox.
        return prefs.getBoolean(KEY_STAY_CONNECTED, false);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        if (!shouldStayConnected(context)) {
            return;
        }
        try {
            // python-for-android generates <package>.ServiceTox in the app, so
            // this library finds it at run time.
            Class<?> service = Class.forName(context.getPackageName() + ".ServiceTox");
            service.getMethod("start", Context.class, String.class).invoke(null, context, "");
        } catch (ReflectiveOperationException e) {
            // Android said no this time: PyTox connects when it's next opened.
        }
    }
}
