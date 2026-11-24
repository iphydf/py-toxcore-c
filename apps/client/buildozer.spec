[app]
title = PyTox
package.name = pytox
package.domain = chat.tox
source.dir = .
source.include_exts = py,png,svg,kv,ttf,txt
source.exclude_dirs = tests,tools,android_support/recipes,android_support/aar,.buildozer,bin,build
# Run at build time: the app has its fonts.
source.exclude_patterns = assets/fonts/make_fonts.py
version = 0.1.0

requirements = python3,kivy==2.3.1,pillow,segno,pyjnius,android,libsodium,ctoxcore,pytox

orientation = all
fullscreen = 0
icon.filename = %(source.dir)s/assets/icon.png
# Launchers shrink a plain icon into a white circle. The icon is full-bleed, so
# it's both layers of the adaptive one.
icon.adaptive_foreground.filename = %(source.dir)s/assets/icon.png
icon.adaptive_background.filename = %(source.dir)s/assets/icon.png

# Background Tox foreground service keeping the client connected when closed.
# The service goes to the foreground itself, with types: python-for-android
# would do it with all of them, and the microphone and camera are only allowed
# during calls the user let PyTox have them for.
services = Tox:android_support/service.py:sticky:foregroundServiceType=remoteMessaging|microphone|camera

# Android (python-for-android). SDK levels match kTox's androidApp.
android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_REMOTE_MESSAGING,RECEIVE_BOOT_COMPLETED,RECORD_AUDIO,CAMERA,MODIFY_AUDIO_SETTINGS,FOREGROUND_SERVICE_MICROPHONE,FOREGROUND_SERVICE_CAMERA,USE_FULL_SCREEN_INTENT,WAKE_LOCK
android.api = 36
android.minapi = 29
android.ndk = 28c
android.archs = arm64-v8a, x86_64
android.accept_sdk_license = True
android.allow_backup = False
android.enable_androidx = True
android.gradle_dependencies = androidx.core:core:1.13.1
# FileProvider, boot receiver and BootReceiver.class: build it first with
# android_support/aar/build_aar.py (see README).
android.add_aars = android_support/aar/build/pytox-android-support.aar
# Back goes to the page before through OnBackInvokedCallback (Android 16 sends
# apps targeting it nothing else); Android 13 to 15 use it only when asked to.
android.extra_manifest_application_arguments = android_support/application_attributes.xml
# python-for-android copies AARs into libs/ and references them by name, but
# its Gradle template doesn't declare that directory as a repository.
android.add_gradle_repositories = flatDir { dirs 'libs' }

p4a.branch = v2026.05.09
p4a.bootstrap = sdl2
p4a.local_recipes = ./android_support/recipes

[buildozer]
log_level = 2
warn_on_root = 1
# Defaults; listed so BUILDOZER_BUILD_DIR / BUILDOZER_BIN_DIR can override them
# (buildozer only applies environment overrides to keys present here).
build_dir = ./.buildozer
bin_dir = ./bin
