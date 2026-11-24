#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
# Runs headless Kivy UI tests under Xvfb with Nix's software Mesa (llvmpipe).
set -eu

xvfb=$PWD/$1
libgl_dir=$(dirname "$(readlink -f "$PWD/$2")")
mesa_json=$(readlink -f "$PWD/$3")
mesa_root=$(dirname "$(dirname "$(dirname "$(dirname "$mesa_json")")")")
test_bin=$PWD/$4
shift 4

export LIBGL_ALWAYS_SOFTWARE=1
export __GLX_VENDOR_LIBRARY_NAME=mesa
export LIBGL_DRIVERS_PATH="$mesa_root/lib/dri"
export __EGL_VENDOR_LIBRARY_FILENAMES="$mesa_json"
export LD_LIBRARY_PATH="$libgl_dir:$mesa_root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export SDL_VIDEODRIVER=x11
export XDG_RUNTIME_DIR="${TEST_TMPDIR:-/tmp}/xdg-runtime"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
export PYTHONDONTWRITEBYTECODE=1

display_file="${TEST_TMPDIR:-/tmp}/xvfb-display"
xvfb_log="${TEST_TMPDIR:-/tmp}/xvfb.log"
rm -f "$display_file" "$xvfb_log"

"$xvfb" -displayfd 3 -screen 0 1280x1024x24 -nolisten tcp -noreset \
    3>"$display_file" 2>"$xvfb_log" &
xvfb_pid=$!
cleanup() {
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT

display=""
for _ in $(seq 1 100); do
    if [ -s "$display_file" ]; then
        read -r display <"$display_file" || true
        if [ -n "$display" ]; then
            break
        fi
    fi
    if ! kill -0 "$xvfb_pid" 2>/dev/null; then
        cat "$xvfb_log" >&2
        exit 1
    fi
    sleep 0.05
done
if [ -z "$display" ]; then
    echo "Xvfb did not become ready" >&2
    cat "$xvfb_log" >&2
    exit 1
fi

DISPLAY=":$display" "$test_bin" -v "$@"
