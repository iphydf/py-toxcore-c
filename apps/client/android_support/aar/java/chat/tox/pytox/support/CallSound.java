// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 The TokTok team
package chat.tox.pytox.support;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.AudioEffect;
import android.media.audiofx.NoiseSuppressor;
import android.os.Build;
import android.util.Log;
import java.util.ArrayList;
import java.util.List;

/**
 * A call's sound: the microphone with the phone's echo cancelling, and the earpiece or the loudspeaker.
 *
 * <p>PyTox reads the microphone and feeds the speaker from threads of its own, which wait in {@link #record} and
 * {@link #play}. {@link #close} lets them go; {@link #release} frees the rest once they have.
 */
public final class CallSound {
    private static final String TAG = "PyTox";

    /** What calls record: 20 ms frames of 48 kHz mono. */
    public static final int RATE = 48000;

    public static final int FRAME = RATE / 50;

    private final AudioManager audio;
    private final AudioRecord record;
    private final List<AudioEffect> effects = new ArrayList<>();
    private final Object trackLock = new Object();
    private AudioTrack track;
    private int trackRate;
    private int trackChannels;
    private volatile boolean running = true;
    private volatile boolean released;

    public CallSound(Context context) {
        audio = context.getSystemService(AudioManager.class);
        AudioRecord rec = null;
        try {
            if (audio != null) {
                audio.setMode(AudioManager.MODE_IN_COMMUNICATION);
            }
            rec = openRecord(context);
            if (rec != null) {
                if (AcousticEchoCanceler.isAvailable()) {
                    enable(AcousticEchoCanceler.create(rec.getAudioSessionId()));
                }
                if (NoiseSuppressor.isAvailable()) {
                    enable(NoiseSuppressor.create(rec.getAudioSessionId()));
                }
                rec.startRecording();
            }
            record = rec;
        } catch (RuntimeException e) {
            for (AudioEffect effect : effects) {
                try {
                    effect.release();
                } catch (RuntimeException ignored) {
                }
            }
            effects.clear();
            if (rec != null) {
                rec.release();
            }
            if (audio != null) {
                audio.setMode(AudioManager.MODE_NORMAL);
            }
            throw e;
        }
    }

    private void enable(AudioEffect effect) {
        if (effect != null) {
            effect.setEnabled(true);
            effects.add(effect);
        }
    }

    private static AudioRecord openRecord(Context context) {
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            return null;
        }
        int min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        try {
            AudioRecord r =
                    new AudioRecord(
                            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                            RATE,
                            AudioFormat.CHANNEL_IN_MONO,
                            AudioFormat.ENCODING_PCM_16BIT,
                            Math.max(min, FRAME * 2 * 4));
            if (r.getState() == AudioRecord.STATE_INITIALIZED) {
                return r;
            }
            r.release();
        } catch (SecurityException | IllegalArgumentException e) {
            Log.w(TAG, "no microphone", e);
        }
        return null;
    }

    /** Whether there's a microphone the app may use. */
    public boolean hasMicrophone() {
        return record != null;
    }

    /** Whether there's an earpiece as well as the loudspeaker. */
    public static boolean hasEarpiece(Context context) {
        AudioManager audio = context.getSystemService(AudioManager.class);
        for (AudioDeviceInfo device : audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS)) {
            if (device.getType() == AudioDeviceInfo.TYPE_BUILTIN_EARPIECE) {
                return true;
            }
        }
        return false;
    }

    /** The next 20 ms from the microphone, 16-bit little-endian: null once closed. */
    public byte[] record() {
        if (record == null) {
            return null;
        }
        byte[] pcm = new byte[FRAME * 2];
        int got = 0;
        while (got < pcm.length && running) {
            int n = record.read(pcm, got, pcm.length - got, AudioRecord.READ_BLOCKING);
            if (n <= 0) {
                return null;
            }
            got += n;
        }
        return running ? pcm : null;
    }

    /** Plays 16-bit sound, waiting while the speaker is full: its buffer sets the pace. */
    public void play(byte[] pcm, int rate, int channels) {
        if (pcm == null || pcm.length == 0 || rate <= 0 || channels <= 0) {
            return;
        }
        AudioTrack t;
        synchronized (trackLock) {
            if (!running) {
                return;
            }
            if (track == null || rate != trackRate || channels != trackChannels) {
                if (track != null) {
                    track.release();
                }
                trackRate = rate;
                trackChannels = channels;
                track = openTrack(rate, channels);
            }
            t = track;
        }
        if (t == null) {
            sleepFrame(pcm.length, rate, channels);
            return;
        }
        int written = t.write(pcm, 0, pcm.length, AudioTrack.WRITE_BLOCKING);
        if (written < 0) {
            if (running) {
                Log.w(TAG, "AudioTrack.write returned " + written + ", resetting track");
                synchronized (trackLock) {
                    if (track == t) {
                        track.release();
                        track = null;
                        trackRate = 0;
                        trackChannels = 0;
                    }
                }
                sleepFrame(pcm.length, rate, channels);
            }
        }
    }

    private static void sleepFrame(int bytes, int rate, int channels) {
        long ms = Math.max(1L, bytes * 1000L / 2L / channels / rate);
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static AudioTrack openTrack(int rate, int channels) {
        int mask = channels == 2 ? AudioFormat.CHANNEL_OUT_STEREO : AudioFormat.CHANNEL_OUT_MONO;
        int min = AudioTrack.getMinBufferSize(rate, mask, AudioFormat.ENCODING_PCM_16BIT);
        try {
            AudioTrack t =
                    new AudioTrack.Builder()
                            .setAudioAttributes(
                                    new AudioAttributes.Builder()
                                            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                            .build())
                            .setAudioFormat(
                                    new AudioFormat.Builder()
                                            .setSampleRate(rate)
                                            .setChannelMask(mask)
                                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                            .build())
                            .setBufferSizeInBytes(Math.max(min, rate / 50 * channels * 2 * 3))
                            .setTransferMode(AudioTrack.MODE_STREAM)
                            .build();
            t.play();
            return t;
        } catch (UnsupportedOperationException | IllegalArgumentException e) {
            Log.w(TAG, "no speaker for " + rate + " Hz, " + channels + " channels", e);
            return null;
        }
    }

    /** The loudspeaker, or the earpiece held to the ear. */
    @SuppressWarnings("deprecation") // setSpeakerphoneOn, before Android 12
    public void setSpeaker(boolean on) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            AudioDeviceInfo speaker = null;
            for (AudioDeviceInfo device : audio.getAvailableCommunicationDevices()) {
                if (device.getType() == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) {
                    speaker = device;
                }
            }
            if (on && speaker != null) {
                audio.setCommunicationDevice(speaker);
            } else {
                audio.clearCommunicationDevice();
            }
        } else {
            audio.setSpeakerphoneOn(on);
        }
    }

    /** Lets the threads waiting in {@link #record} and {@link #play} go. */
    public void close() {
        running = false;
        if (record != null) {
            try {
                record.stop();
            } catch (IllegalStateException ignored) {
            }
        }
        synchronized (trackLock) {
            if (track != null) {
                try {
                    track.stop();
                    track.flush();
                } catch (IllegalStateException ignored) {
                }
            }
        }
    }

    /** Frees the microphone and speaker, once nothing waits in here. */
    public void release() {
        if (released) {
            return;
        }
        released = true;
        for (AudioEffect effect : effects) {
            try {
                effect.release();
            } catch (RuntimeException ignored) {
            }
        }
        effects.clear();
        if (record != null) {
            record.release();
        }
        synchronized (trackLock) {
            if (track != null) {
                track.release();
                track = null;
            }
        }
        if (audio != null) {
            setSpeaker(false);
            audio.setMode(AudioManager.MODE_NORMAL);
        }
    }
}
