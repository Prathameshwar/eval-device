"""Build-time native protection for the manager; installers and UI use bytecode."""

import argparse
import importlib.metadata
import json
import os
import py_compile
import shutil
import sys
import sysconfig
from pathlib import Path

from local_models_package import NATIVE_MODULES

TOOLS = {"Cython": "3.1.8", "setuptools": "80.9.0"}
TREES = (
    "local-models/desktop",
    "local-models/service",
    "local-models/scripts",
    "device/audio-process/src/device_audio",
)
ENTRIES = (
    "local-models/manage_local_models.py",
    "local-models/manage_service.py",
    "start/local_models_check.py",
    "start/local_models_package.py",
)
WRAPPER = """# Portable entry shim; implementation is in adjacent bytecode.
from importlib.machinery import SourcelessFileLoader as _PortableLoader
from pathlib import Path as _PortablePath
exec(_PortableLoader(__name__, str(_PortablePath(__file__).with_suffix('.pyc'))).get_code(__name__))
"""


def protect(destination, work):
    if (
        sys.platform != "win32"
        or sys.version_info[:2] != (3, 12)
        or sysconfig.get_platform() != "win-amd64"
    ):
        raise RuntimeError("Protection requires Windows x64 Python 3.12")
    for name, version in TOOLS.items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError(f"Protection requires {name}=={version}")
    from Cython.Build import cythonize
    from setuptools import Distribution, Extension

    extensions = []
    for name in NATIVE_MODULES:
        source = Path("local-models") / (name.replace(".", "/") + ".py")
        if not (destination / source).is_file():
            raise RuntimeError(f"Missing protected module: {name}")
        extensions.append(Extension(name, [source.as_posix()]))
    extensions = cythonize(
        extensions,
        build_dir=str(work / "generated"),
        compiler_directives={
            "language_level": 3,
            "annotation_typing": False,
            "binding": True,
            "emit_code_comments": False,
        },
    )
    (work / "c").mkdir(parents=True)
    for index, extension in enumerate(extensions):
        generated = work / "c" / f"module{index}.c"
        shutil.copy2(extension.sources[0], generated)
        extension.sources = [f"c/module{index}.c"]
    distribution = Distribution({"ext_modules": extensions})
    command = distribution.get_command_obj("build_ext")
    command.build_lib = str(work / "native")
    command.build_temp = str(work / "objects")
    previous = Path.cwd()
    try:
        os.chdir(work)
        distribution.run_command("build_ext")
    finally:
        os.chdir(previous)
    native = {}
    for name in NATIVE_MODULES:
        source = destination / "local-models" / (name.replace(".", "/") + ".py")
        output = Path(command.get_ext_fullpath(name))
        if not output.is_file():
            raise RuntimeError(f"Native compilation failed: {name}")
        target = source.parent / output.name
        shutil.copy2(output, target)
        source.unlink()
        native[name] = target.relative_to(destination).as_posix()
    bytecode, wrappers = [], []
    sources = [
        source for tree in TREES for source in (destination / tree).rglob("*.py")
    ]
    sources.extend(destination / name for name in ENTRIES)
    for source in sorted(sources):
        relative = source.relative_to(destination).as_posix()
        py_compile.compile(
            str(source),
            cfile=str(source.with_suffix(".pyc")),
            dfile=relative,
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        bytecode.append(source.with_suffix(".pyc").relative_to(destination).as_posix())
        if (
            source.parent.name == "scripts"
            or relative in ENTRIES
            or source.name in {"daemon.py", "worker.py", "install_adapter.py"}
        ):
            source.write_text(WRAPPER, encoding="utf-8")
            wrappers.append(relative)
        else:
            source.unlink()
    (destination / "protection-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "cython",
                "tools": TOOLS,
                "native": native,
                "bytecode": bytecode,
                "entry_shims": wrappers,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    protect(args.destination.resolve(), args.work.resolve())
