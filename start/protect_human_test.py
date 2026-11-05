"""Build-time protection; no compiler or protection dependency ships to clients."""

import argparse
import importlib.metadata
import json
import os
import py_compile
import shutil
import sys
import sysconfig
from pathlib import Path

from human_test_package import APP_NATIVE_MODULES

# Preserve protection of extracted application logic in the desktop distribution.
# The shared wheel remains portable Python for other hosts.
CLIENT_LIBRARY = "human-test/.venv/Scripts/Lib/site-packages"
NATIVE_MODULES = {
    "human-test/src": tuple(
        name for name in APP_NATIVE_MODULES if name.startswith("human_test.")
    ),
    CLIENT_LIBRARY: tuple(
        name for name in APP_NATIVE_MODULES if name.startswith("training_client.")
    ),
}
TOOL_VERSIONS = {"Cython": "3.1.8", "setuptools": "80.9.0"}
SOURCE_TREES = (
    "human-test/src",
    "human-test/scripts",
    CLIENT_LIBRARY + "/training_client",
    "start",
)
WRAPPER = """# Portable entry shim; implementation is in adjacent bytecode.
from importlib.machinery import SourcelessFileLoader as _PortableLoader
from pathlib import Path as _PortablePath
exec(_PortableLoader(__name__, str(_PortablePath(__file__).with_suffix(".pyc"))).get_code(__name__))
"""


def bytecode_sources(destination):
    bytecode, wrappers = [], []
    for tree in SOURCE_TREES:
        for source in sorted((destination / tree).rglob("*.py")):
            relative = source.relative_to(destination).as_posix()
            py_compile.compile(
                str(source),
                cfile=str(source.with_suffix(".pyc")),
                dfile=relative,
                doraise=True,
                optimize=0,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            )
            bytecode.append(
                source.with_suffix(".pyc").relative_to(destination).as_posix()
            )
            if tree.endswith("scripts") or tree == "start":
                # These paths are executed directly AND imported by the launcher.
                source.write_text(WRAPPER, encoding="utf-8")
                wrappers.append(relative)
            else:
                source.unlink()
    return bytecode, wrappers


def protect(destination, work):
    if (
        sys.platform != "win32"
        or sys.version_info[:2] != (3, 12)
        or sys.maxsize <= 2**32
        or sysconfig.get_platform() != "win-amd64"
    ):
        raise RuntimeError("Protection tools must use Windows x64 Python 3.12")
    for package, version in TOOL_VERSIONS.items():
        if importlib.metadata.version(package) != version:
            raise RuntimeError(f"Protection requires {package}=={version}")
    from Cython.Build import cythonize
    from setuptools import Distribution, Extension

    extensions = []
    for tree, modules in NATIVE_MODULES.items():
        for module in modules:
            source = Path(tree) / (module.replace(".", "/") + ".py")
            if not (destination / source).is_file():
                raise RuntimeError(f"Missing protected module: {module}")
            extensions.append(Extension(module, [source.as_posix()]))
    # Called with cwd=destination so embedded filenames are relative.
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
    # Flatten generated paths: MSVC's linker still has legacy path length limits.
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
    for tree, modules in NATIVE_MODULES.items():
        for module in modules:
            source = destination / tree / (module.replace(".", "/") + ".py")
            output = Path(command.get_ext_fullpath(module))
            if not output.is_file():
                raise RuntimeError(f"Native compilation failed: {module}")
            target = source.parent / output.name
            target.write_bytes(output.read_bytes())
            source.unlink()
            native[module] = target.relative_to(destination).as_posix()
    bytecode, wrappers = bytecode_sources(destination)
    manifest = {
        "version": 1,
        "mode": "cython",
        "tools": TOOL_VERSIONS,
        "native": native,
        "bytecode": bytecode,
        "entry_shims": wrappers,
        "limitations": "Raises inspection cost; bytecode and native strings remain recoverable.",
    }
    (destination / "protection-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    protect(args.destination.resolve(), args.work.resolve())
