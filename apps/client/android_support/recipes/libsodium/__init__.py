# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""python-for-android recipe for libsodium."""
import os
import subprocess
from os.path import join

from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class LibsodiumRecipe(Recipe):  # type: ignore[misc]
    """Build libsodium (with unaligned Salsa20 fixes) for Android ABIs.

    Same commit as the Bazel build in tools/workspace/non_module_deps.bzl.
    """

    version = "0a5f2423db76c6fd323c5496b8635bf84b3cf040"
    url = "https://github.com/jedisct1/libsodium/archive/{version}.tar.gz"
    # python-for-android verifies md5sum or sha512sum (it has no sha256sum).
    sha512sum = (
        "1e9cbe9faf993fa06ab877e002002a99555309eab1b5fbd3159d723269e0899c"
        "89853cc85fa84e781a5768f0d65906edc62e1c5a570c2bfb282c822a80206a44"
    )
    built_libraries = {"libsodium.so": "src/libsodium/.libs"}

    def get_install_dir(self, arch: object) -> str:
        return join(self.get_build_dir(arch.arch), "_install")  # type: ignore[attr-defined]

    def build_arch(self, arch: object) -> None:
        env = self.get_recipe_env(arch)
        build_dir = self.get_build_dir(arch.arch)  # type: ignore[attr-defined]
        install_dir = self.get_install_dir(arch)
        host = arch.command_prefix  # type: ignore[attr-defined]
        jobs = str(os.cpu_count() or 4)
        with current_directory(build_dir):
            if not os.path.exists("configure"):
                subprocess.check_call(["autoreconf", "-fi"], env=env)
            subprocess.check_call(
                [
                    "./configure",
                    f"--host={host}",
                    f"--prefix={install_dir}",
                    "--enable-shared",
                    "--enable-static",
                    "--with-pic",
                    "--disable-soname-versions",
                ],
                env=env,
            )
            subprocess.check_call(["make", f"-j{jobs}", "install"], env=env)


recipe = LibsodiumRecipe()
