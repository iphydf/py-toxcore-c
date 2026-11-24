# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""python-for-android recipe for the ``pytox`` bindings (toxcore, toxav)."""
from __future__ import annotations

import os
import shutil
from os.path import abspath
from os.path import dirname
from os.path import join

import sh
from pythonforandroid.logger import shprint
from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe
from pythonforandroid.recipe import Recipe

# Same Cython as the Bazel build (MODULE.bazel: bazel_dep cython 3.2.4).
_CYTHON = "Cython==3.2.4"

_ANDROID_SETUP_PY = '''\
from setuptools import Extension
from setuptools import setup

setup(
    name="py-toxcore-c",
    version="0.2.20",
    py_modules=["pytox.common", "pytox.toxcore.events", "pytox.toxav.events"],
    ext_modules=[
        Extension(
            "pytox.toxcore.tox",
            ["pytox/toxcore/tox.cpp"],
            language="c++",
            extra_compile_args=["-funsigned-char"],
            libraries=["toxcore", "sodium"],
        ),
        Extension(
            "pytox.toxav.toxav",
            ["pytox/toxav/toxav.cpp"],
            language="c++",
            extra_compile_args=["-funsigned-char"],
            libraries=["toxcore", "sodium", "opus", "vpx"],
        ),
    ],
)
'''


class PyToxRecipe(CppCompiledComponentsPythonRecipe):  # type: ignore[misc]
    """Build py_toxcore_c's toxcore and toxav extensions for Android.

    PyTox doesn't use toxencryptsave, so that module isn't built.
    """

    name = "pytox"
    version = "0.2.20"
    url = None
    depends = ["python3", "setuptools", "libsodium", "opus", "libvpx",
               "ctoxcore"]
    site_packages_name = "pytox"
    hostpython_prerequisites = ["setuptools", _CYTHON]

    def _source_root(self) -> str:
        override = os.environ.get("PYTOX_SRC", "")
        if override and os.path.isdir(override):
            return abspath(override)
        # android_support/recipes/pytox -> py_toxcore_c
        return abspath(join(dirname(__file__), "..", "..", "..", "..", ".."))

    def unpack(self, arch: str) -> None:
        """Stage a clean copy of pytox/ (never builds in the checkout).

        python-for-android passes the ABI name here, not an Arch.
        """
        build_dir = self.get_build_dir(arch)
        os.makedirs(build_dir, exist_ok=True)
        pkg_dst = join(build_dir, "pytox")
        for stale in (pkg_dst, join(build_dir, "build")):
            if os.path.exists(stale):
                shutil.rmtree(stale)
        shutil.copytree(
            join(self._source_root(), "pytox"),
            pkg_dst,
            ignore=shutil.ignore_patterns(
                "*.so", "*.cpp", "*.c", "__pycache__"),
        )
        with open(join(build_dir, "setup.py"), "w", encoding="utf-8") as fh:
            fh.write(_ANDROID_SETUP_PY)

    def get_recipe_env(
        self,
        arch: object,
        with_flags_in_cc: bool = True,
    ) -> dict[str, str]:
        env = super().get_recipe_env(arch, with_flags_in_cc=with_flags_in_cc)
        prefixes = [
            Recipe.get_recipe(name, self.ctx).get_install_dir(arch)
            for name in ("ctoxcore", "libsodium", "opus", "libvpx")
        ]
        inc = "".join(f" -I{join(prefix, 'include')}" for prefix in prefixes)
        env["CFLAGS"] = env.get("CFLAGS", "") + inc
        env["CXXFLAGS"] = env.get("CXXFLAGS", "") + inc
        env["CPPFLAGS"] = env.get("CPPFLAGS", "") + inc
        env["LDFLAGS"] = env.get("LDFLAGS", "") + "".join(
            f" -L{join(prefix, 'lib')}" for prefix in prefixes)
        return env  # type: ignore[no-any-return]

    def build_compiled_components(self, arch: object) -> None:
        build_dir = self.get_build_dir(arch.arch)  # type: ignore[attr-defined]
        # Cythonize with hostpython's pinned Cython, like Bazel: C++ output.
        hostpython = sh.Command(self.real_hostpython_location)
        for module in ("toxcore/tox", "toxav/toxav"):
            source = join(build_dir, "pytox", module)
            shprint(
                hostpython, "-m", "cython", "--cplus", "-I", build_dir,
                f"{source}.pyx", "-o", f"{source}.cpp",
                _env=self.get_hostrecipe_env(arch),
            )
        super().build_compiled_components(arch)


recipe = PyToxRecipe()
