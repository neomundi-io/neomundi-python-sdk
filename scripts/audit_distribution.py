"""Offline audit of PyPI distribution archives; no upload and no network.

Checks file paths, expected metadata, licence, and public SDK package membership.
This is NOT a complete secrets scanner or a legal rights audit.
"""
from __future__ import annotations

import io
import re
import tarfile
import zipfile
from pathlib import Path

BANNED_PARTS = {
    ".env", ".git", ".venv", "govern-v3", "portal", "alembic",
    "captured", "validation", "__pycache__", ".pytest_cache",
}
BANNED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".pyc"}
BANNED_NAMES = {"credentials.json", "secrets.json", ".netrc", ".npmrc"}
MAX_FILE_SIZE = 5 * 1024 * 1024


def check_name(name: str) -> None:
    parts = Path(name).parts
    assert parts and not Path(name).is_absolute(), f"Absolute archive path: {name}"
    assert ".." not in parts, f"Archive path traversal: {name}"
    assert not BANNED_PARTS.intersection(parts), f"Excluded directory in dist: {name}"
    leaf = Path(name).name
    assert leaf not in BANNED_NAMES, f"Sensitive file name in dist: {name}"
    assert not leaf.startswith(".env"), f"Environment file in dist: {name}"
    assert Path(leaf).suffix not in BANNED_SUFFIXES, f"Sensitive file suffix: {name}"


def check_archive(path: Path) -> None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as z:
            names = [i.filename for i in z.infolist() if not i.is_dir()]
            for item in z.infolist():
                if not item.is_dir():
                    assert item.file_size < MAX_FILE_SIZE, f"Oversized file: {item.filename}"
                    check_name(item.filename)
            license_files = [n for n in names if n.endswith(".dist-info/licenses/LICENSE")]
            metadata_files = [n for n in names if n.endswith(".dist-info/METADATA")]
            assert len(license_files) == 1, "Apache-2.0 licence not embedded in wheel"
            assert len(metadata_files) == 1, "Wheel metadata not found"
            metadata = z.read(metadata_files[0]).decode("utf-8")
            assert re.search(r"^Name: neomundi$", metadata, re.M), "Distribution name mismatch"
            assert re.search(r"^License-Expression: Apache-2.0$", metadata, re.M), "Licence mismatch"
            assert any(n == "neomundi/__init__.py" for n in names), "SDK module missing"
            assert all(n.startswith(("neomundi/", "neomundi-")) for n in names), (
                "Unexpected non-SDK path in wheel"
            )
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                check_name(member.name)
                assert member.isfile() or member.isdir(), f"Archive link/device: {member.name}"
                if member.isfile():
                    assert member.size < MAX_FILE_SIZE, f"Oversized file: {member.name}"
            names = [m.name for m in members]
            assert any(n.endswith("/LICENSE") for n in names), "Licence missing from sdist"
            assert any(n.endswith("/src/neomundi/__init__.py") for n in names), "SDK missing from sdist"
    else:
        raise AssertionError(f"Unexpected distribution file: {path}")
    print(f"PASS: {path.name} (file paths, licence and SDK package checked)")


def main() -> None:
    files = sorted(p for p in Path("dist").iterdir() if p.is_file())
    assert len(files) == 2, f"Expected exactly wheel + sdist: {[str(p) for p in files]}"
    assert sum(p.suffix == ".whl" for p in files) == 1
    assert sum(p.name.endswith(".tar.gz") for p in files) == 1
    for path in files:
        check_archive(path)
    print("PASS: offline distribution structural audit; no PyPI publication")


if __name__ == "__main__":
    main()
