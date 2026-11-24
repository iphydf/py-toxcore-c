// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 The TokTok team
package chat.tox.pytox.support;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Person;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;
import android.util.Log;

/** A call outside the app: ringing, and going on in the background service. */
public final class CallNotices {
    private static final String TAG = "PyTox";
    /** Rings, with the phone's ringtone. */
    private static final String CHANNEL_RINGING = "ringing";

    /** A call going on: quiet. */
    private static final String CHANNEL_CALL = "call";

    private static final int RINGING_ID = 101;

    /** What the activity does when a notification opens it. */
    public static final String EXTRA_CALL = "pytox_call";

    public static final String SHOW = "show";
    public static final String ANSWER = "answer";
    public static final String ANSWER_VIDEO = "answer_video";

    private CallNotices() {}

    private static NotificationManager manager(Context context) {
        NotificationManager nm = context.getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CHANNEL_RINGING) == null) {
            NotificationChannel ringing =
                    new NotificationChannel(CHANNEL_RINGING, "Incoming calls", NotificationManager.IMPORTANCE_HIGH);
            ringing.setSound(
                    RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
                    new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                            .build());
            ringing.enableVibration(true);
            nm.createNotificationChannel(ringing);
        }
        if (nm.getNotificationChannel(CHANNEL_CALL) == null) {
            NotificationChannel call =
                    new NotificationChannel(CHANNEL_CALL, "Calls going on", NotificationManager.IMPORTANCE_LOW);
            nm.createNotificationChannel(call);
        }
        return nm;
    }

    private static PendingIntent openApp(Context context, String what, int code) {
        Intent intent = new Intent();
        intent.setClassName(context, "org.kivy.android.PythonActivity");
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        intent.putExtra(EXTRA_CALL, what);
        return PendingIntent.getActivity(
                context, code, intent, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private static PendingIntent hangUp(Context context, String socket) {
        Intent intent = new Intent(context, CallReceiver.class);
        intent.setAction(CallReceiver.HANG_UP);
        intent.putExtra(CallReceiver.EXTRA_SOCKET, socket);
        return PendingIntent.getBroadcast(
                context, 0, intent, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private static Notification.Builder builder(Context context, String channel, String name) {
        return new Notification.Builder(context, channel)
                .setSmallIcon(context.getApplicationInfo().icon)
                .setContentTitle(name)
                .setCategory(Notification.CATEGORY_CALL)
                .setOngoing(true);
    }

    private static Notification.Action action(Context context, String label, PendingIntent intent) {
        return new Notification.Action.Builder(
                        Icon.createWithResource(context, context.getApplicationInfo().icon), label, intent)
                .build();
    }

    private static String safeName(String name) {
        return (name == null || name.isBlank()) ? "Unknown" : name;
    }

    /** A call from a friend rings, until it's answered or ends. */
    public static void ring(Context context, String name, boolean video, String socket) {
        String label = safeName(name);
        NotificationManager nm = manager(context);
        PendingIntent show = openApp(context, SHOW, 1);
        PendingIntent answer = openApp(context, video ? ANSWER_VIDEO : ANSWER, video ? 3 : 2);
        PendingIntent decline = hangUp(context, socket);
        Notification.Builder b =
                builder(context, CHANNEL_RINGING, label)
                        .setContentText(video ? "Incoming video call" : "Incoming call")
                        .setContentIntent(show)
                        .setFullScreenIntent(show, true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            Person caller = new Person.Builder().setName(label).setImportant(true).build();
            b.setStyle(Notification.CallStyle.forIncomingCall(caller, decline, answer).setIsVideo(video));
        } else {
            b.addAction(action(context, "Decline", decline));
            b.addAction(action(context, "Answer", answer));
        }
        Notification n = b.build();
        n.flags |= Notification.FLAG_INSISTENT;
        nm.notify(RINGING_ID, n);
    }

    public static void stopRinging(Context context) {
        context.getSystemService(NotificationManager.class).cancel(RINGING_ID);
    }

    /** A call going on, with a way to hang up. */
    public static Notification ongoing(Context context, String name, boolean video, long startedMs, String socket) {
        String label = safeName(name);
        manager(context);
        PendingIntent show = openApp(context, SHOW, 1);
        PendingIntent hangUp = hangUp(context, socket);
        Notification.Builder b =
                builder(context, CHANNEL_CALL, label)
                        .setContentText(video ? "Video call" : "Call")
                        .setContentIntent(show);
        if (startedMs > 0L) {
            b.setWhen(startedMs).setShowWhen(true).setUsesChronometer(true);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            Person friend = new Person.Builder().setName(label).setImportant(true).build();
            b.setStyle(Notification.CallStyle.forOngoingCall(friend, hangUp).setIsVideo(video));
        } else {
            b.addAction(action(context, "Hang up", hangUp));
        }
        return b.build();
    }

    /**
     * Shows the service's notification, keeping it in the foreground: during a call it may use the microphone and
     * (only when sending video) camera, as far as the user lets it.
     */
    public static void foreground(Service service, int id, Notification n, boolean mic, boolean camera) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            int types = 0;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                if (mic && granted(service, Manifest.permission.RECORD_AUDIO)) {
                    types |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE;
                }
                if (camera && granted(service, Manifest.permission.CAMERA)) {
                    types |= ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA;
                }
            }
            if (types == 0) {
                service.startForeground(id, n);
            } else {
                service.startForeground(id, n, types);
            }
            return;
        }
        int types = ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING;
        if (mic && granted(service, Manifest.permission.RECORD_AUDIO)) {
            types |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE;
        }
        if (camera && granted(service, Manifest.permission.CAMERA)) {
            types |= ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA;
        }
        try {
            service.startForeground(id, n, types);
        } catch (SecurityException e) {
            // Android 14+ refuses mic/camera FGS types when promoted from the background.
            Log.w(TAG, "falling back to remoteMessaging foreground service type", e);
            service.startForeground(id, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING);
        }
    }

    private static boolean granted(Context context, String permission) {
        return context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
    }
}
