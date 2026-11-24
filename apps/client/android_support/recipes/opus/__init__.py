# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""python-for-android recipe for Opus, which toxav encodes sound with."""
import os
import subprocess
from os.path import join

from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class OpusRecipe(Recipe):  # type: ignore[misc]
    """A static libopus, the version kTox's native build has."""

    version = "1.6.1"
    url = "https://downloads.xiph.org/releases/opus/opus-{version}.tar.gz"
    sha512sum = (
        "93742e86b2eb222808a5055e62627d142e6e7347b3d5aebb4d39b45df78ed7d4"
        "37746c51eb24d724a7c865d064e9d16f4541a4ce6a82fcf7dcc23427d2252e16"
    )

    def get_install_dir(self, arch: object) -> str:
        return join(self.get_build_dir(arch.arch), "_install")  # type: ignore[attr-defined]

    def build_arch(self, arch: object) -> None:
        env = self.get_recipe_env(arch)
        jobs = str(os.cpu_count() or 4)
        with current_directory(self.get_build_dir(arch.arch)):  # type: ignore[attr-defined]
            subprocess.check_call(
                [
                    "./configure",
                    f"--host={arch.command_prefix}",  # type: ignore[attr-defined]
                    f"--prefix={self.get_install_dir(arch)}",
                    "--disable-shared",
                    "--with-pic",
                    "--disable-doc",
                    "--disable-extra-programs",
                ],
                env=env,
            )
            subprocess.check_call(["make", f"-j{jobs}", "install"], env=env)


recipe = OpusRecipe()
