# PyTox

A cross-platform Tox chat client for desktop (Linux, macOS, Windows) and Android,
built with [Kivy](https://kivy.org/) on top of `py_toxcore_c` from this repository.

- `pytox_client`: the single-threaded Tox engine (`ToxClient`), the SQLite store
  (`chats.db`, schema-compatible with `kTox`), platform adapters (`DesktopPlatform`,
  `AndroidPlatform`), Unix-socket IPC (`service_ipc.py`), QR helper (`segno`), and
  responsive Material-3-inspired UI (`ui/`). On wide windows (`>= 720dp`) it shows
  the chat list alongside the active chat or detail page; on narrow/phone screens
  it displays one page at a time.
- Group chats (NGC), like kTox: start private or public groups, join public ones by
  chat ID, accept friends' invites, and chat with per-sender names. Founders and
  moderators can set the topic, change roles, remove people, and (founders) set
  privacy, topic lock, password and peer limit. Groups we found keep their founder
  key across restarts (`experimental_groups_persistence`).
- Calls, like kTox: one at a time, audio or video, over toxav (`calls.py`), with
  the friend's video and ours on a page of their own and a note in the chat when
  a call ends. Sound and pictures go between threads as plain bytes (`media.py`);
  the GPU turns pictures into colours (`ui/video.py`). Desktops use PortAudio
  (`sounddevice`) and V4L2 cameras (`media_desktop.py`).
- Emoji: Kivy draws text in one font, with no fallback, so `assets/fonts/make_fonts.py`
  (fontTools) copies Noto Emoji's outlines into Kivy's Roboto. It runs at build time,
  like Go Tox's emoji font; the fonts aren't in git. Without them, emoji show as boxes.
- `main.py`: entry point used on both desktop and Android (`buildozer`).
- `android_support/`: the `python-for-android` foreground service (`service.py`),
  local NDK recipes (`libsodium`, `opus`, `libvpx`, `ctoxcore`, `pytox`), and
  `aar/`: a small support library with the `FileProvider`, its paths, the
  receivers, and the Java side of calls (sound, cameras, notifications).

## Running with Bazel

```sh
bazel run //py_toxcore_c/apps/client:client
bazel run //py_toxcore_c/apps/client:client -- --profile /tmp/pytox-dev
bazel run //py_toxcore_c/apps/client:client -- --theme dark
bazel test //py_toxcore_c/apps/client/...
```

## Running standalone (outside Bazel)

With `py_toxcore_c` installed in your Python environment:

```sh
pip install -e py_toxcore_c/apps/client
pytox --profile /tmp/pytox-dev
```

On desktop, the default profile directory is:

- Linux: `$XDG_DATA_HOME/pytox` (default `~/.local/share/pytox`)
- macOS: `~/Library/Application Support/PyTox`
- Windows: `%LOCALAPPDATA%\PyTox`

It has the profiles, in `profiles/1`, `profiles/2` and so on, all online at
once; the menu switches between them. Each stores `profile.tox` (toxcore save
data), `chats.db` (history, friend cache, requests, settings), `files/`,
`avatars/`, and `avatar.png`. A profile from before there were several moves
into `profiles/1`.

## Android APK (Buildozer / python-for-android)

Needs Python Buildozer (`pip install buildozer`, not Bazel's `buildozer`), a JDK,
autotools and CMake. Buildozer downloads the Android SDK and NDK into `~/.buildozer`.
From `py_toxcore_c/apps/client`:

```sh
# Fonts with emoji (needs fontTools).
python3 assets/fonts/make_fonts.py

# The FileProvider and boot receiver, which python-for-android can't put in the
# manifest itself, come from a small AAR that Gradle merges in.
python3 android_support/aar/build_aar.py \
    --android-jar "$ANDROID_HOME/platforms/android-36/android.jar"

export TOXCORE_SRC=/path/to/c-toxcore   # optional; clones TokTok/c-toxcore otherwise
export PYTOX_SRC=/path/to/py_toxcore_c  # optional; defaults to ../..
APP_ANDROID_ARCHS=arm64-v8a buildozer android debug   # one ABI is faster
adb install -r bin/pytox-*-arm64-v8a-debug.apk
```

`BUILDOZER_BUILD_DIR` and `BUILDOZER_BIN_DIR` move the build and the APK out of the
source tree. libsodium is the same commit as the Bazel build; Cython is 3.2.4, also
as in Bazel.

While "Stay connected" is on, the `p4a` foreground service `Tox`
(`android_support/service.py`) runs every profile's Tox in its own process, so
they stay connected when the UI is closed, and serves the UI over a private
`AF_UNIX` socket (`pytox.sock`) in each profile's directory. While it's off, the UI runs Tox
itself. `HandoverClient` (`handover.py`) moves Tox between the two when the setting
changes: one closes the profile before the other opens it. The service stops itself
when the setting goes off, and the UI starts it again if Android stops it.

Calls run where Tox runs. In the service, the microphone and camera keep going
with the screen off: its foreground types gain them for the call, as far as the
user has allowed them. The call's pictures reach the UI on a second socket
(`pytox-video.sock`), newest only. While "Stay connected" is off, a call goes on
only while PyTox is on screen.

## Bootstrap nodes

PyTox starts from the bundled nodes in `pytox_client/nodes.py` and never fetches a
node list at runtime. Run `./tools/update-nodes` before each release to refresh it.
