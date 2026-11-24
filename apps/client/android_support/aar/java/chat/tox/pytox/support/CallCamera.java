// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 The TokTok team
package chat.tox.pytox.support;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.OutputConfiguration;
import android.hardware.camera2.params.SessionConfiguration;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.hardware.display.DisplayManager;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;
import android.util.Range;
import android.util.Size;
import android.view.Display;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Executor;

/**
 * A Camera2 camera filming upright pictures in I420 for calls.
 *
 * <p>PyTox takes the newest one with {@link #take} on a thread of its own: each is 8 bytes of width and height
 * (big-endian) and then the Y, U and V planes, packed.
 */
public final class CallCamera {
    private static final String TAG = "PyTox";

    /** What cameras are asked for: phones turn it to 480 × 640. */
    private static final int WIDTH = 640;

    private static final int HEIGHT = 480;
    private static final int MAX_FPS = 30;

    /** At most this many pictures a second go out: each one takes the Tox thread a while to encode. */
    private static final long INTERVAL_NS = 1_000_000_000L / 24;

    private final Context context;
    private final boolean front;
    private final int sensor;
    private final HandlerThread thread = new HandlerThread("camera");
    private final Handler handler;
    private final Executor executor;
    private ImageReader reader;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private volatile boolean closed;

    /** The camera thread's copies of the planes, used again for each picture. */
    private final byte[][] planes = new byte[3][];

    private final byte[][] packed = new byte[3][];
    private boolean gateStarted;
    private long gate;

    private final Object lock = new Object();
    private byte[] newest;

    private CallCamera(Context context, boolean front, int sensor) {
        this.context = context.getApplicationContext();
        this.front = front;
        this.sensor = sensor;
        thread.start();
        handler = new Handler(thread.getLooper());
        executor = handler::post;
    }

    /** How many cameras face the user or away: phones have a front and a back one. */
    public static int count(Context context) {
        CameraManager manager = context.getSystemService(CameraManager.class);
        List<Integer> facings = new ArrayList<>();
        try {
            for (String id : manager.getCameraIdList()) {
                Integer facing = manager.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING);
                if (facing != null
                        && (facing == CameraCharacteristics.LENS_FACING_FRONT
                                || facing == CameraCharacteristics.LENS_FACING_BACK)
                        && !facings.contains(facing)) {
                    facings.add(facing);
                }
            }
        } catch (CameraAccessException e) {
            Log.w(TAG, "no cameras", e);
        }
        return facings.size();
    }

    /** Starts the front or the back camera: null if it can't. */
    public static CallCamera open(Context context, boolean front) {
        if (context.checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            return null;
        }
        CameraManager manager = context.getSystemService(CameraManager.class);
        try {
            int wanted = front ? CameraCharacteristics.LENS_FACING_FRONT : CameraCharacteristics.LENS_FACING_BACK;
            String id = null;
            for (String each : manager.getCameraIdList()) {
                Integer facing = manager.getCameraCharacteristics(each).get(CameraCharacteristics.LENS_FACING);
                if (id == null || (facing != null && facing == wanted)) {
                    id = each;
                }
                if (facing != null && facing == wanted) {
                    break;
                }
            }
            if (id == null) {
                return null;
            }
            CameraCharacteristics characteristics = manager.getCameraCharacteristics(id);
            StreamConfigurationMap map =
                    characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map == null) {
                return null;
            }
            // The size nearest to 640 × 480, 4:3 if the camera has one.
            Size[] sizes = map.getOutputSizes(ImageFormat.YUV_420_888);
            if (sizes == null || sizes.length == 0) {
                return null;
            }
            Size size = null;
            long best = Long.MAX_VALUE;
            for (Size s : sizes) {
                long score =
                        Math.abs((long) s.getWidth() * s.getHeight() - WIDTH * HEIGHT)
                                + (s.getWidth() * 3 == s.getHeight() * 4 ? 0 : WIDTH * HEIGHT);
                if (score < best) {
                    best = score;
                    size = s;
                }
            }
            if (size == null) {
                return null;
            }
            // Up to 30 a second, fewer where it's dark.
            Range<Integer> fps = null;
            Range<Integer>[] ranges = characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES);
            if (ranges != null) {
                for (Range<Integer> r : ranges) {
                    if (r.getUpper() <= MAX_FPS
                            && (fps == null
                                    || r.getUpper() > fps.getUpper()
                                    || (r.getUpper().equals(fps.getUpper()) && r.getLower() < fps.getLower()))) {
                        fps = r;
                    }
                }
            }
            Integer facing = characteristics.get(CameraCharacteristics.LENS_FACING);
            Integer sensor = characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION);
            CallCamera camera =
                    new CallCamera(
                            context,
                            facing != null && facing == CameraCharacteristics.LENS_FACING_FRONT,
                            sensor != null ? sensor : 0);
            try {
                camera.start(manager, id, size, fps);
            } catch (CameraAccessException | RuntimeException e) {
                camera.close();
                throw e;
            }
            return camera;
        } catch (CameraAccessException | SecurityException e) {
            Log.w(TAG, "no camera", e);
            return null;
        }
    }

    private void start(CameraManager manager, String id, Size size, Range<Integer> fps)
            throws CameraAccessException {
        ImageReader r = ImageReader.newInstance(size.getWidth(), size.getHeight(), ImageFormat.YUV_420_888, 3);
        reader = r;
        r.setOnImageAvailableListener(
                ir -> {
                    Image image = ir.acquireLatestImage();
                    if (image == null) {
                        return;
                    }
                    try {
                        long now = System.nanoTime();
                        if (!closed && (!gateStarted || now - gate >= 0L)) {
                            gate = !gateStarted ? now + INTERVAL_NS : gate + INTERVAL_NS;
                            if (now - gate >= 0L) {
                                gate = now + INTERVAL_NS;
                            }
                            gateStarted = true;
                            hand(convert(image));
                        }
                    } finally {
                        image.close();
                    }
                },
                handler);
        // Dispatch callbacks directly so onOpened() can still close late devices after the handler thread quits.
        Executor callbackExec = command -> {
            if (!handler.post(command)) {
                command.run();
            }
        };
        manager.openCamera(
                id,
                callbackExec,
                new CameraDevice.StateCallback() {
                    @Override
                    public void onOpened(CameraDevice device) {
                        if (closed) {
                            device.close();
                            return;
                        }
                        camera = device;
                        capture(device, r, fps);
                    }

                    @Override
                    public void onDisconnected(CameraDevice device) {
                        device.close();
                        markFailed();
                    }

                    @Override
                    public void onError(CameraDevice device, int error) {
                        Log.w(TAG, "camera error " + error);
                        device.close();
                        markFailed();
                    }
                });
    }

    private void markFailed() {
        synchronized (lock) {
            closed = true;
            newest = null;
            lock.notifyAll();
        }
    }

    private void capture(CameraDevice device, ImageReader r, Range<Integer> fps) {
        try {
            CaptureRequest.Builder request = device.createCaptureRequest(CameraDevice.TEMPLATE_RECORD);
            request.addTarget(r.getSurface());
            if (fps != null) {
                request.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, fps);
            }
            device.createCaptureSession(
                    new SessionConfiguration(
                            SessionConfiguration.SESSION_REGULAR,
                            Collections.singletonList(new OutputConfiguration(r.getSurface())),
                            executor,
                            new CameraCaptureSession.StateCallback() {
                                @Override
                                public void onConfigured(CameraCaptureSession s) {
                                    if (closed) {
                                        return;
                                    }
                                    session = s;
                                    try {
                                        s.setRepeatingRequest(request.build(), null, handler);
                                    } catch (CameraAccessException | IllegalStateException e) {
                                        Log.w(TAG, "camera stopped", e);
                                    }
                                }

                                @Override
                                public void onConfigureFailed(CameraCaptureSession s) {
                                    Log.w(TAG, "camera session failed");
                                    markFailed();
                                }
                            }));
        } catch (CameraAccessException | IllegalStateException e) {
            Log.w(TAG, "camera stopped", e);
            markFailed();
        }
    }

    /** The newest picture, waiting for one: null once closed. */
    public byte[] take() throws InterruptedException {
        synchronized (lock) {
            while (newest == null && !closed) {
                lock.wait();
            }
            byte[] picture = newest;
            newest = null;
            return closed ? null : picture;
        }
    }

    private void hand(byte[] picture) {
        synchronized (lock) {
            newest = picture;
            lock.notifyAll();
        }
    }

    /** How far to turn the camera's pictures clockwise to make them upright, as the phone is held now. */
    private int rotation() {
        Display display = context.getSystemService(DisplayManager.class).getDisplay(Display.DEFAULT_DISPLAY);
        int screen = (display != null ? display.getRotation() : 0) * 90;
        return front ? (sensor + screen) % 360 : (sensor - screen + 360) % 360;
    }

    /** The camera's picture, upright, in a dedicated buffer so readers never see overwritten bytes. */
    private byte[] convert(Image image) {
        int width = image.getWidth() & ~1;
        int height = image.getHeight() & ~1;
        int degrees = rotation();
        boolean turned = degrees == 90 || degrees == 270;
        int outWidth = turned ? height : width;
        int outHeight = turned ? width : height;
        int luma = width * height;
        int size = 8 + luma + luma / 2;
        byte[] out = new byte[size];
        putInt(out, 0, outWidth);
        putInt(out, 4, outHeight);
        Image.Plane[] imagePlanes = image.getPlanes();
        int offset = 8;
        for (int i = 0; i < 3; i++) {
            int w = i == 0 ? width : width / 2;
            int h = i == 0 ? height : height / 2;
            Image.Plane plane = imagePlanes[i];
            ByteBuffer buffer = plane.getBuffer();
            int row = plane.getRowStride();
            byte[] data = planes[i];
            if (data == null || data.length < row * h) {
                data = new byte[row * h];
                planes[i] = data;
            }
            buffer.get(data, 0, Math.min(buffer.remaining(), data.length));
            if (plane.getPixelStride() == 1) {
                rotatePlane(data, w, h, row, degrees, out, offset);
            } else {
                // Chroma samples of interleaved planes are every pixelStride bytes: pack them first.
                int step = plane.getPixelStride();
                byte[] tight = packed[i];
                if (tight == null || tight.length != w * h) {
                    tight = new byte[w * h];
                    packed[i] = tight;
                }
                for (int j = 0; j < h; j++) {
                    for (int k = 0; k < w; k++) {
                        tight[j * w + k] = data[j * row + k * step];
                    }
                }
                rotatePlane(tight, w, h, w, degrees, out, offset);
            }
            offset += w * h;
        }
        return out;
    }

    private static void putInt(byte[] out, int at, int value) {
        out[at] = (byte) (value >>> 24);
        out[at + 1] = (byte) (value >>> 16);
        out[at + 2] = (byte) (value >>> 8);
        out[at + 3] = (byte) value;
    }

    /** Turns a plane of width × height samples (in rows of stride) by degrees clockwise, into out at offset. */
    static void rotatePlane(byte[] plane, int width, int height, int stride, int degrees, byte[] out, int offset) {
        switch (degrees) {
            case 90:
                for (int j = 0; j < height; j++) {
                    for (int i = 0; i < width; i++) {
                        out[offset + i * height + (height - 1 - j)] = plane[j * stride + i];
                    }
                }
                break;
            case 180:
                for (int j = 0; j < height; j++) {
                    for (int i = 0; i < width; i++) {
                        out[offset + (height - 1 - j) * width + (width - 1 - i)] = plane[j * stride + i];
                    }
                }
                break;
            case 270:
                for (int j = 0; j < height; j++) {
                    for (int i = 0; i < width; i++) {
                        out[offset + (width - 1 - i) * height + j] = plane[j * stride + i];
                    }
                }
                break;
            default:
                for (int j = 0; j < height; j++) {
                    System.arraycopy(plane, j * stride, out, offset + j * width, width);
                }
        }
    }

    /** Stops filming: {@link #take} returns null from now on. */
    public void close() {
        closed = true;
        synchronized (lock) {
            lock.notifyAll();
        }
        // Closing waits for the camera thread's last picture.
        handler.post(
                () -> {
                    if (session != null) {
                        session.close();
                    }
                    if (camera != null) {
                        camera.close();
                    }
                    if (reader != null) {
                        reader.close();
                    }
                });
        thread.quitSafely();
        try {
            thread.join();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
