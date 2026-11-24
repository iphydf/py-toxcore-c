// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 The TokTok team
package chat.tox.pytox.support;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.util.Log;
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * Declining or hanging up from a call's notification, without opening PyTox.
 *
 * <p>The app's process says so to its client while PyTox is running ({@link #setListener}); otherwise only the
 * background service has Tox, and it hears it on its socket.
 */
public final class CallReceiver extends BroadcastReceiver {
    private static final String TAG = "PyTox";
    public static final String HANG_UP = "chat.tox.pytox.HANG_UP";

    /** The service's socket, for when PyTox isn't running. */
    public static final String EXTRA_SOCKET = "socket";

    /** PyTox's client, in the app's process. */
    public interface Listener {
        void onHangUp();
    }

    private static volatile Listener listener;

    public static void setListener(Listener l) {
        listener = l;
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !HANG_UP.equals(intent.getAction())) {
            return;
        }
        Listener l = listener;
        if (l != null) {
            try {
                l.onHangUp();
                return;
            } catch (RuntimeException e) {
                Log.w(TAG, "hang-up listener failed", e);
            }
        }
        String socket = intent.getStringExtra(EXTRA_SOCKET);
        if (socket == null) {
            return;
        }
        PendingResult result = goAsync();
        new Thread(
                        () -> {
                            try (LocalSocket s = new LocalSocket()) {
                                s.connect(new LocalSocketAddress(socket, LocalSocketAddress.Namespace.FILESYSTEM));
                                s.setSoTimeout(5000);
                                // The service sends its state first, and reads once that's gone.
                                InputStream in = new BufferedInputStream(s.getInputStream());
                                int c;
                                do {
                                    c = in.read();
                                } while (c != -1 && c != '\n');
                                OutputStream out = s.getOutputStream();
                                out.write("{\"cmd\":\"hang_up\"}\n".getBytes(StandardCharsets.UTF_8));
                                out.flush();
                            } catch (IOException e) {
                                Log.w(TAG, "couldn't reach the service to hang up", e);
                            } finally {
                                result.finish();
                            }
                        },
                        "hang-up")
                .start();
    }
}
