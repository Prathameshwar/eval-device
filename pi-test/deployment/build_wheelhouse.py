"""Build versioned application wheels and a hash-locked ARM64 dependency bundle."""

import argparse
import hashlib
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python-version", choices=("312", "313"), default="313")
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Choose an empty wheelhouse directory")
    for package in ("shared/training-contracts", "local-models/client", "shared/training-client", "pi-test"):
        subprocess.run(["uv", "build", "--wheel", "--out-dir", str(output), str(ROOT / package)], check=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--dest",
            str(output),
            "--require-hashes",
            "--no-deps",
            "--only-binary=:all:",
            "--platform",
            "manylinux_2_28_aarch64",
            "--platform",
            "manylinux_2_17_aarch64",
            "--platform",
            "manylinux2014_aarch64",
            "--implementation",
            "cp",
            "--python-version",
            args.python_version,
            "--abi",
            "cp" + args.python_version,
            "-r",
            str(Path(__file__).with_name("requirements.lock")),
        ],
        check=True,
    )
    requirements = []
    for wheel in sorted(output.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            metadata = BytesParser().parsebytes(archive.read(name))
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        requirements.append(f"{metadata['Name']}=={metadata['Version']} --hash=sha256:{digest}")
    (output / "release-requirements.txt").write_text("\n".join(requirements) + "\n", encoding="utf-8")
    print(f"Built {len(requirements)} wheels for CPython {args.python_version} ARM64; hardware not exercised")


if __name__ == "__main__":
    main()
