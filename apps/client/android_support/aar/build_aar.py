#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Build PyTox's Android support library (AAR) for buildozer.

The AAR carries manifest entries python-for-android can't add itself (the
FileProvider and the receivers), the FileProvider paths, and PyTox's Java:
the receivers and what calls need (sound, cameras, notifications). Gradle
merges it into the APK via ``android.add_aars``.

Usage: build_aar.py --android-jar SDK/platforms/android-36/android.jar
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "build" / "pytox-android-support.aar"
# Fixed timestamp so the AAR is the same bytes on every build.
_EPOCH = (1980, 1, 1, 0, 0, 0)


def _add(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-jar", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if not args.android_jar.is_file():
        raise SystemExit(f"no android.jar at {args.android_jar}")

    sources = sorted((HERE / "java").rglob("*.java"))
    with tempfile.TemporaryDirectory() as tmp:
        classes = Path(tmp) / "classes"
        subprocess.check_call([
            "javac", "--release", "11", "-classpath", str(args.android_jar),
            "-d", str(classes), *map(str, sources),
        ])
        jar = Path(tmp) / "classes.jar"
        with zipfile.ZipFile(jar, "w") as zf:
            for f in sorted(classes.rglob("*.class")):
                _add(zf, f.relative_to(classes).as_posix(), f.read_bytes())

        args.out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.out, "w") as aar:
            _add(aar, "AndroidManifest.xml",
                 (HERE / "AndroidManifest.xml").read_bytes())
            _add(aar, "classes.jar", jar.read_bytes())
            for res in sorted((HERE / "res").rglob("*")):
                if res.is_file():
                    _add(aar, f"res/{res.relative_to(HERE / 'res').as_posix()}",
                         res.read_bytes())
            # The library's resources, for R class generation.
            _add(aar, "R.txt", b"int xml files 0x0\n")
    print(args.out)


if __name__ == "__main__":
    if shutil.which("javac") is None:
        raise SystemExit("javac is needed to build the AAR")
    main()
