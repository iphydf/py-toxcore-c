// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 The TokTok team
package chat.tox.pytox.support;

import android.content.ContentResolver;
import android.net.Uri;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Streams bytes between Android {@link ContentResolver} URIs and local files in Java.
 *
 * <p>Avoids pyjnius byte-array copying issues and whole-file heap allocations on large transfers.
 */
public final class FileHelper {
    private static final int BUFFER_SIZE = 65536;

    private FileHelper() {}

    /** Copies the contents of {@code srcUri} to {@code dstPath}. Returns false if {@code srcUri} cannot be opened. */
    public static boolean copyUriToFile(ContentResolver resolver, Uri srcUri, String dstPath)
            throws IOException {
        try (InputStream in = resolver.openInputStream(srcUri)) {
            if (in == null) {
                return false;
            }
            try (OutputStream out = new FileOutputStream(dstPath)) {
                byte[] buf = new byte[BUFFER_SIZE];
                int n;
                while ((n = in.read(buf)) != -1) {
                    out.write(buf, 0, n);
                }
                out.flush();
            }
        }
        return true;
    }

    /** Copies the contents of {@code srcPath} to {@code dstUri}. Returns false if {@code dstUri} cannot be opened. */
    public static boolean copyFileToUri(ContentResolver resolver, String srcPath, Uri dstUri)
            throws IOException {
        try (OutputStream out = resolver.openOutputStream(dstUri)) {
            if (out == null) {
                return false;
            }
            try (InputStream in = new FileInputStream(srcPath)) {
                byte[] buf = new byte[BUFFER_SIZE];
                int n;
                while ((n = in.read(buf)) != -1) {
                    out.write(buf, 0, n);
                }
                out.flush();
            }
        }
        return true;
    }
}
