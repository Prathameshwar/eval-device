"""Build the Human-test Windows desktop client with its private Python runtime."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from human_test_package import APP_SCRIPTS, START_FILES, validate_client_path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ("human-test",)
SOURCE_PREFIXES = ("human-test/src/",)
SOURCE_FILES = {
    *("human-test/scripts/" + name for name in APP_SCRIPTS),
    *("start/" + name for name in START_FILES),
    "human-test/.env.example",
    "docs/human-test-portable.md",
}
CLIENT_DEPENDENCIES = {
    "training_client": "shared/training-client/src/training_client",
    "local_model_client": "local-models/client/src/local_model_client",
    "training_contracts": "shared/training-contracts/src/training_contracts",
}


def included(relative):
    path = Path(relative)
    if relative == "human-test/.env.example":
        return True
    if any(
        part.startswith(".") or part in {"__pycache__", "tests"} for part in path.parts
    ):
        return False
    if relative in SOURCE_FILES:
        return True
    return relative.startswith(SOURCE_PREFIXES) and path.suffix.lower() == ".py"


def run(command, **kwargs):
    return subprocess.run([str(part) for part in command], check=True, **kwargs)


def checked_build_file(root, path):
    """Reject links/junctions at every level, including linked source directories."""
    root = root.resolve()
    if not path.resolve().is_relative_to(root):
        raise RuntimeError("Distribution file escapes its root")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise RuntimeError("Linked paths are not allowed in a distribution")
        if part == root:
            break
    return path


def copy_sources(destination):
    # Explicit source trees: never walk private state, credentials, recordings or models.
    paths = set(SOURCE_FILES)
    for prefix in SOURCE_PREFIXES:
        paths.update(
            path.relative_to(ROOT).as_posix() for path in (ROOT / prefix).rglob("*")
        )
    for relative in sorted(paths):
        source = ROOT / relative
        if not source.is_file() or not included(relative):
            continue
        checked_build_file(ROOT, source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def copy_client_dependencies(library):
    """Install local client libraries as ordinary runtime dependencies, not apps."""
    for package, relative in CLIENT_DEPENDENCIES.items():
        source_root = ROOT / relative
        if not source_root.is_dir():
            raise RuntimeError(f"Missing client dependency: {package}")
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or any(
                part.startswith(".") or part in {"tests", "__pycache__"}
                for part in source.relative_to(source_root).parts
            ):
                continue
            if source.suffix != ".py" and source.name not in {
                "input-ignore.json",
                "manifest.json",
                "phrases.json",
                "pronunciation.json",
                "instructions.txt",
            }:
                continue
            checked_build_file(ROOT, source)
            target = library / package / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def remove_dependency_models(library):
    # OpenCV's camera wheel also ships pretrained cascade detectors, unused here.
    # Keep cv2/data/__init__.py so imports retain the wheel's expected layout.
    for path in (library / "cv2/data").glob("*.xml"):
        checked_build_file(library, path)
        path.unlink()


def remove_dependency_tests(library):
    # Wheel test suites are not imported by the desktop runtime.
    for path in sorted(
        library.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_dir() and path.name.lower() in {"test", "tests"}:
            checked_build_file(library, path)
            shutil.rmtree(path)


def private_python(base, target):
    target.mkdir(parents=True)
    for name in ("Lib", "DLLs", "tcl"):
        shutil.copytree(
            base / name,
            target / name,
            ignore=shutil.ignore_patterns(
                "site-packages", "__pycache__", "*.pyc", "test", "tests"
            ),
        )
    for source in base.iterdir():
        if source.is_file() and (
            source.suffix.lower() in {".dll", ".exe"} or source.name == "LICENSE.txt"
        ):
            shutil.copy2(source, target / source.name)
    library = target / "Lib/site-packages"
    library.mkdir()
    paths = [
        ".",
        "Lib",
        "DLLs",
        "Lib/site-packages",
        "../../src",
        "../../scripts",
        "../../../start",
        "import site",
        "",
    ]
    (
        target / f"python{sys.version_info.major}{sys.version_info.minor}._pth"
    ).write_text("\n".join(paths), encoding="utf-8")
    return library


def find_vc_runtime(explicit=None):
    if explicit is not None:
        candidates = [explicit]
    else:
        candidates = list(
            Path(os.environ.get("ProgramFiles", "C:/Program Files")).glob(
                "Microsoft Visual Studio/*/*/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT"
            )
        )
    candidates = [path for path in candidates if (path / "msvcp140.dll").is_file()]
    if not candidates:
        raise RuntimeError(
            "Build needs Visual Studio x64 CRT redistribution files; use --vc-runtime PATH"
        )
    return max(
        candidates,
        key=lambda path: tuple(
            int(part) for part in path.parents[1].name.split(".") if part.isdecimal()
        ),
    )


def copy_vc_runtime(source, target):
    for name in (
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "msvcp140_codecvt_ids.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "vcruntime140_threads.dll",
        "concrt140.dll",
        "vccorlib140.dll",
    ):
        if (source / name).is_file():
            shutil.copy2(source / name, target / name)


def protect_sources(destination, uv, online, python=None):
    if python is None:
        directory = ROOT / "start/.build-tools/protection"
        python = directory / "Scripts/python.exe"
        if not python.is_file():
            run([uv, "venv", directory, "--python", sys.executable])
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                python,
                "--no-build",
                *([] if online else ["--offline"]),
                "Cython==3.1.8",
                "setuptools==80.9.0",
            ]
        )
    python = python.resolve()
    if not python.is_file():
        raise RuntimeError("Protection build interpreter does not exist")
    with tempfile.TemporaryDirectory(prefix="human-test-native-") as directory:
        run(
            [python, ROOT / "start/protect_human_test.py", destination, directory],
            cwd=destination,
        )


def validate_protection(destination):
    from human_test_package import native_module_path
    from protect_human_test import NATIVE_MODULES, SOURCE_TREES, WRAPPER

    manifest = json.loads((destination / "protection-manifest.json").read_text())
    expected = {name for modules in NATIVE_MODULES.values() for name in modules}
    if manifest.get("mode") != "cython" or set(manifest["native"]) != expected:
        raise RuntimeError("Incomplete native protection")
    for tree, modules in NATIVE_MODULES.items():
        for name in modules:
            source = destination / tree / (name.replace(".", "/") + ".py")
            native = destination / manifest["native"][name]
            if (
                native != destination / native_module_path(name)
                or not native.is_file()
                or native.suffix != ".pyd"
                or source.exists()
                or source.with_suffix(".pyc").exists()
                or list((source.parent / "__pycache__").glob(source.stem + ".*.pyc"))
            ):
                raise RuntimeError(f"Unprotected native module: {name}")
    allowed = set(manifest["entry_shims"])
    for relative in manifest["bytecode"]:
        path = destination / relative
        if not path.resolve().is_relative_to(destination) or not path.is_file():
            raise RuntimeError("Missing protected application bytecode")
    for relative in allowed:
        path = destination / relative
        if (
            not path.resolve().is_relative_to(destination)
            or not path.is_file()
            or path.read_text(encoding="utf-8") != WRAPPER
            or not path.with_suffix(".pyc").is_file()
        ):
            raise RuntimeError("Invalid protected entry shim")
    bytecode = set()
    shims = set()
    for tree in SOURCE_TREES:
        for path in (destination / tree).rglob("*"):
            if not path.is_file():
                continue
            checked_build_file(destination, path)
            relative = path.relative_to(destination).as_posix()
            suffix = path.suffix.lower()
            if suffix in {
                ".c",
                ".cpp",
                ".cxx",
                ".h",
                ".hpp",
                ".pyx",
                ".pxd",
                ".pyi",
                ".pdb",
                ".obj",
                ".exp",
                ".lib",
            }:
                raise RuntimeError("Compiler artifacts leaked into distribution")
            if suffix == ".pyc" and "__pycache__" not in path.parts:
                bytecode.add(relative)
            if suffix == ".py":
                shims.add(relative)
            if suffix == ".py" and (
                relative not in allowed or path.read_text(encoding="utf-8") != WRAPPER
            ):
                raise RuntimeError(
                    "Readable application source leaked into distribution"
                )
    if bytecode != set(manifest["bytecode"]) or shims != allowed:
        raise RuntimeError("Protection inventory does not match application files")


def clean_build_caches(destination):
    # Import checks create bytecode containing the build machine's absolute paths.
    for cache in sorted(destination.rglob("__pycache__"), reverse=True):
        checked_build_file(destination, cache)
        if cache.is_dir():
            for path in cache.rglob("*"):
                checked_build_file(destination, path)
            # The resolved target is verified inside this fresh build before deletion.
            shutil.rmtree(cache)


def release_package(destination, release, no_zip=False, verify_release=None):
    """Only expose finished names after all checks, ZIP writes and hashing succeed."""
    files = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            checked_build_file(destination, path)
            relative = path.relative_to(destination).as_posix()
            try:
                validate_client_path(relative)
            except ValueError as error:
                raise RuntimeError(str(error)) from None
            with path.open("rb") as stream:
                files[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps(files, indent=2), encoding="utf-8")
    archive = release.with_suffix(".zip")
    partial = archive.with_suffix(".zip.partial")
    checksum = archive.with_suffix(".zip.sha256")
    partial_checksum = checksum.with_suffix(".sha256.partial")
    if release.exists() or archive.exists() or checksum.exists():
        raise RuntimeError("Refusing to replace an existing release")
    if not no_zip:
        folder_name = "Desktop-App"
        expected = {
            **files,
            "manifest.json": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
        with zipfile.ZipFile(
            partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3
        ) as bundle:
            for index, (relative, digest) in enumerate(expected.items(), start=1):
                path = checked_build_file(destination, destination / relative)
                if index % 2000 == 0:
                    print(f"Packing {index}/{len(expected)}: {relative}", flush=True)
                # Hash exactly the bytes written, so a changed file aborts the release.
                actual = hashlib.sha256()
                with (
                    path.open("rb") as source,
                    bundle.open(
                        folder_name + "/" + relative, "w", force_zip64=True
                    ) as target,
                ):
                    while block := source.read(1024 * 1024):
                        actual.update(block)
                        target.write(block)
                if actual.hexdigest() != digest:
                    raise RuntimeError("Distribution changed while writing the archive")
        with partial.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        partial_checksum.write_text(
            digest + "  " + archive.name + "\n", encoding="ascii"
        )
    destination.rename(release)
    if verify_release is not None:
        try:
            verify_release(release)
        except BaseException:
            release.rename(destination)
            partial.unlink(missing_ok=True)
            partial_checksum.unlink(missing_ok=True)
            raise
    if not no_zip:
        partial.rename(archive)
        partial_checksum.rename(checksum)
        print(f"Portable archive: {archive}", flush=True)
    print(f"Portable executable: {release / 'Human-test.exe'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online", action="store_true", help="Allow fetching missing locked wheels"
    )
    parser.add_argument("--no-zip", action="store_true")
    parser.add_argument(
        "--protection",
        choices=("cython", "none"),
        default="cython",
        help="Native compilation plus bytecode (default); none is for debugging only",
    )
    parser.add_argument(
        "--protection-python",
        type=Path,
        help="Optional build-only Python 3.12 with pinned Cython/setuptools",
    )
    parser.add_argument(
        "--vc-runtime", type=Path, help="Visual Studio x64 Microsoft.VC*.CRT directory"
    )
    args = parser.parse_args()
    if (
        sys.platform != "win32"
        or sys.maxsize <= 2**32
        or sys.version_info[:2] != (3, 12)
        or sysconfig.get_platform() != "win-amd64"
    ):
        parser.error("Build with Windows x64 Python 3.12 (human-test's environment)")
    uv = shutil.which("uv")
    compiler = (
        Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    if not uv or not compiler.is_file():
        parser.error("Build requires uv and the Windows .NET Framework C# compiler")
    vc_runtime = find_vc_runtime(args.vc_runtime)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    edition = "runtime" + (
        "-protected" if args.protection == "cython" else "-debug-source"
    )
    release = ROOT / "start/dist" / f"Human-test-windows-x64-{edition}-{stamp}"
    destination = release.with_name(".building-" + release.name)
    destination.mkdir(parents=True)
    copy_sources(destination)
    # Source allowlist deliberately excludes local .env/.local/.state even on an enrolled builder.
    (destination / "portable-runtime.json").write_text(
        json.dumps(
            {
                "version": 2,
                "application": "human-test",
                "role": "client",
                "python": sys.version.split()[0],
                "protection": args.protection,
            }
        ),
        encoding="utf-8",
    )
    base = Path(sys.base_prefix)
    environment = {**os.environ, "UV_PYTHON_DOWNLOADS": "never"}
    for project in PROJECTS:
        target = destination / project / ".venv/Scripts"
        library = private_python(base, target)
        copy_vc_runtime(vc_runtime, target)
        requirements = destination / project / "portable-requirements.txt"
        run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-local",
                "--no-header",
                "--output-file",
                requirements,
            ],
            cwd=ROOT / project,
            env=environment,
            stdout=subprocess.DEVNULL,
        )
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                target / "python.exe",
                "--target",
                library,
                "--require-hashes",
                "--no-deps",
                "--no-build",
                "--link-mode",
                "copy",
                *([] if args.online else ["--offline"]),
                "-r",
                requirements,
            ],
            env=environment,
        )
        remove_dependency_models(library)
        remove_dependency_tests(library)
    copy_client_dependencies(library)
    if args.protection == "cython":
        protect_sources(destination, uv, args.online, args.protection_python)
    run(
        [
            compiler,
            "/nologo",
            "/target:exe",
            "/platform:x64",
            f"/out:{destination / 'Human-test.exe'}",
            ROOT / "start/portable/HumanTest.cs",
        ]
    )
    clean_build_caches(destination)
    if args.protection == "cython":
        validate_protection(destination)
    release_package(
        destination,
        release,
        args.no_zip,
        verify_release=lambda finished: run(
            [finished / "Human-test.exe", "--self-test"], cwd=finished
        ),
    )


if __name__ == "__main__":
    main()
