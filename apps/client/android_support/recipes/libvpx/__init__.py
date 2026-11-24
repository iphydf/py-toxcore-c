# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""python-for-android recipe for libvpx, which toxav encodes video with.

It takes the place of python-for-android's own, which is older and builds VP9
too: toxav only uses VP8.
"""
import glob
import os
import re
import subprocess
from os.path import join

from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory

_TARGETS = {
    "armeabi-v7a": "armv7-android-gcc",
    "arm64-v8a": "arm64-android-gcc",
    "x86": "x86-android-gcc",
    "x86_64": "x86_64-android-gcc",
}


class LibvpxRecipe(Recipe):  # type: ignore[misc]
    """A static libvpx with VP8 only, the version kTox's native build has."""

    version = "1.17.0"
    url = ("https://storage.googleapis.com/downloads.webmproject.org/"
           "releases/webm/libvpx-{version}.tar.gz")
    sha512sum = (
        "5a0ebcc1a0ee936db0835438a0d870860f3d5769589b2974096839e918a36bf8"
        "1084515426592a94aee910579d92f483900672cd6724f3b00c859cd175cb48d4"
    )

    def get_install_dir(self, arch: object) -> str:
        return join(self.get_build_dir(arch.arch), "_install")  # type: ignore[attr-defined]

    def build_arch(self, arch: object) -> None:
        env = self.get_recipe_env(arch)
        abi = arch.arch  # type: ignore[attr-defined]
        jobs = str(os.cpu_count() or 4)
        with current_directory(self.get_build_dir(abi)):
            subprocess.check_call(
                [
                    "./configure",
                    f"--prefix={self.get_install_dir(arch)}",
                    f"--target={_TARGETS[abi]}",
                    "--disable-vp9",
                    "--disable-examples",
                    "--disable-tools",
                    "--disable-docs",
                    "--disable-unit-tests",
                    "--enable-pic",
                ],
                env=env,
            )
            # libvpx's Android targets assume GNU as and strip.
            strip = join(self.ctx.ndk.llvm_bin_dir, "llvm-strip")
            for mk in glob.glob("*.mk"):
                with open(mk, encoding="utf-8") as fh:
                    text = fh.read()
                text = re.sub(r"^AS=as$", f"AS={env['CC']} -c", text,
                              flags=re.M)
                text = re.sub(r"^STRIP=strip$", f"STRIP={strip}", text,
                              flags=re.M)
                with open(mk, "w", encoding="utf-8") as fh:
                    fh.write(text)
            subprocess.check_call(["make", f"-j{jobs}", "install"], env=env)


recipe = LibvpxRecipe()
