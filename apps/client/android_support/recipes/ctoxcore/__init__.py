# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""python-for-android recipe for c-toxcore."""
import os
import shutil
import subprocess
from os.path import join

from pythonforandroid.recipe import Recipe
from pythonforandroid.util import current_directory


class CToxcoreRecipe(Recipe):  # type: ignore[misc]
    """Cross-compile c-toxcore (static) via CMake and the NDK toolchain.

    Uses the checkout in $TOXCORE_SRC (e.g. this repo's c-toxcore, with its
    third_party/cmp submodule), else clones TokTok/c-toxcore master.
    """

    name = "ctoxcore"
    version = "master"
    depends = ["libsodium", "opus", "libvpx"]
    url = None

    def get_install_dir(self, arch: object) -> str:
        return join(self.get_build_dir(arch.arch), "_install")  # type: ignore[attr-defined]

    def build_arch(self, arch: object) -> None:
        build_dir = self.get_build_dir(arch.arch)  # type: ignore[attr-defined]
        os.makedirs(build_dir, exist_ok=True)
        src_dir = join(build_dir, "src")
        install_dir = self.get_install_dir(arch)
        local_src = os.environ.get("TOXCORE_SRC", "")
        if local_src and os.path.isdir(local_src):
            if os.path.exists(src_dir):
                shutil.rmtree(src_dir)
            shutil.copytree(
                local_src,
                src_dir,
                ignore=shutil.ignore_patterns(
                    ".git", "_build", "build", "bazel-*"),
            )
        elif not os.path.exists(src_dir):
            subprocess.check_call([
                "git", "clone", "--depth=1", "--recursive",
                "https://github.com/TokTok/c-toxcore.git", src_dir,
            ])

        prefixes = [
            Recipe.get_recipe(name, self.ctx).get_install_dir(arch)
            for name in ("libsodium", "opus", "libvpx")
        ]
        toolchain = join(self.ctx.ndk_dir, "build/cmake/android.toolchain.cmake")
        out_build = join(build_dir, "_cmake")
        jobs = str(os.cpu_count() or 4)
        env = self.get_recipe_env(arch)
        env["PKG_CONFIG_LIBDIR"] = os.pathsep.join(
            join(prefix, "lib", "pkgconfig") for prefix in prefixes)
        env["PKG_CONFIG_PATH"] = env["PKG_CONFIG_LIBDIR"]

        with current_directory(build_dir):
            subprocess.check_call([
                "cmake",
                "-S", src_dir,
                "-B", out_build,
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
                f"-DANDROID_ABI={arch.arch}",  # type: ignore[attr-defined]
                f"-DANDROID_PLATFORM=android-{self.ctx.ndk_api}",
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DCMAKE_INSTALL_PREFIX={install_dir}",
                f"-DCMAKE_PREFIX_PATH={';'.join(prefixes)}",
                "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
                "-DENABLE_SHARED=OFF",
                "-DENABLE_STATIC=ON",
                "-DBOOTSTRAP_DAEMON=OFF",
                "-DDHT_BOOTSTRAP=OFF",
                "-DMUST_BUILD_TOXAV=ON",
                "-DBUILD_TOXAV=ON",
                "-DEXPERIMENTAL_API=ON",
                "-DUNITTEST=OFF",
                "-DAUTOTEST=OFF",
            ], env=env)
            subprocess.check_call([
                "cmake", "--build", out_build, f"-j{jobs}",
                "--target", "install",
            ], env=env)


recipe = CToxcoreRecipe()
