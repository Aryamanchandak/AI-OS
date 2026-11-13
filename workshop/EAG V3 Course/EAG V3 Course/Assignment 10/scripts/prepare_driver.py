"""Prepare the pinned local driver bundle without launching it or changing macOS settings."""
from __future__ import annotations
import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from computer.backend import ARCHIVE_SHA256, LOCAL_APP, RELEASE


def prepare(archive=None):
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    name = f"cua-driver-rs-{RELEASE}-darwin-universal.tar.gz"
    with tempfile.TemporaryDirectory(prefix="cua-download-", dir=tools) as temporary:
        package = Path(archive).resolve() if archive else Path(temporary) / name
        if archive is None:
            url = f"https://github.com/trycua/cua/releases/download/cua-driver-rs-v{RELEASE}/{name}"
            urllib.request.urlretrieve(url, package)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        if digest != ARCHIVE_SHA256:
            raise ValueError("Driver archive checksum mismatch; nothing extracted")
        print(f"SHA256 verified: {digest}")
        # The standard library's data filter rejects path escapes and unsafe links.
        with tarfile.open(package) as bundle:
            bundle.extractall(temporary, filter="data")
        unpacked = Path(temporary) / f"cua-driver-rs-{RELEASE}-darwin-universal"
        destination = tools / unpacked.name
        if not destination.exists():
            shutil.move(str(unpacked), str(destination))
    binary = LOCAL_APP / "Contents/MacOS/cua-driver"
    version = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=True)
    print(f"Release {RELEASE}; binary reports: {version.stdout.strip()}")
    print("Prepared only: no daemon, permission dialogs, or desktop actions started")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded release archive")
    args = parser.parse_args()
    try:
        prepare(args.archive)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        print(f"Preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
