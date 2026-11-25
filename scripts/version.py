#!/usr/bin/env python3
"""
Manage the Qjazz version number

The version is defined once in the `VERSION` file at the root of
the repository and propagated to the package manifests that require
a literal version:

- the Rust workspace (`qjazz-server/Cargo.toml`), which also defines the
  version of the `qjazz-rpc` and `qjazz-map` python wheels (maturin);
- the python packages built with `uv_build`;
- the exact pins between workspace packages.

Usage:

    version.py show             Print the version
    version.py set X.Y.Z        Set the version, update manifests and lock files
    version.py sync             Update manifests from the VERSION file
    version.py check [--tag T]  Check that manifests are in sync with the
                                VERSION file and, optionally, that the
                                release tag T (release-X.Y.Z) matches
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION_FILE = ROOT / "VERSION"

# Rust workspace
CARGO_MANIFEST = ROOT / "qjazz-server" / "Cargo.toml"

# Python projects with a static version
PYTHON_PROJECTS = [
    ROOT / "qjazz-contrib" / "pyproject.toml",
    ROOT / "qjazz-processes" / "pyproject.toml",
    ROOT / "qjazz-metapackage" / "pyproject.toml",
]

# Python projects pinning workspace packages
PINNING_PROJECTS = [
    ROOT / "qjazz-processes" / "pyproject.toml",
    ROOT / "qjazz-server" / "qjazz-rpc" / "pyproject.toml",
    ROOT / "qjazz-metapackage" / "pyproject.toml",
]

# Workspace packages that may be pinned
WORKSPACE_PACKAGES = ["qjazz-contrib", "qjazz-processes", "qjazz-rpc", "qjazz-map"]

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-.]?(?:a|b|rc|dev|post)\.?\d+)?$")

RELEASE_TAG_PREFIX = "release-"


def read_version() -> str:
    version = VERSION_FILE.read_text().strip()
    if not VERSION_RE.match(version):
        sys.exit(f"Invalid version in {VERSION_FILE.name}: '{version}'")
    return version


def set_section_version(content: str, section: str, version: str, path: Path) -> str:
    """Set the `version` key of a TOML section"""
    # Match the section up to the next section header
    section_re = re.compile(
        rf"(^\[{re.escape(section)}\]\n(?:(?!^\[).*\n)*?)^version\s*=\s*\"[^\"]*\"",
        re.MULTILINE,
    )
    content, n = section_re.subn(rf'\g<1>version = "{version}"', content, count=1)
    if n != 1:
        sys.exit(f"No 'version' key found in section [{section}] of {path}")
    return content


def set_pins(content: str, version: str) -> str:
    """Set exact pins of workspace packages"""
    names = "|".join(re.escape(name) for name in WORKSPACE_PACKAGES)
    pin_re = re.compile(rf"\"((?:{names})(?:\[[^\]]*\])?)==[^\"]*\"")
    return pin_re.sub(rf'"\g<1>=={version}"', content)


def expected_contents(version: str) -> dict[Path, str]:
    """Compute the expected content of each manifest"""
    contents: dict[Path, str] = {}

    def get(path: Path) -> str:
        if path not in contents:
            contents[path] = path.read_text()
        return contents[path]

    contents[CARGO_MANIFEST] = set_section_version(
        get(CARGO_MANIFEST),
        "workspace.package",
        version,
        CARGO_MANIFEST,
    )
    for path in PYTHON_PROJECTS:
        contents[path] = set_section_version(get(path), "project", version, path)
    for path in PINNING_PROJECTS:
        contents[path] = set_pins(get(path), version)

    return contents


def sync() -> list[Path]:
    """Update manifests, returns the list of modified files"""
    modified = []
    for path, content in expected_contents(read_version()).items():
        if path.read_text() != content:
            path.write_text(content)
            modified.append(path)
    return modified


def update_lock_files():
    subprocess.run(
        ["cargo", "update", "--workspace", "--offline"],
        cwd=ROOT / "qjazz-server",
        check=True,
    )
    subprocess.run(["uv", "lock", "--offline"], cwd=ROOT, check=True)


def check(tag: str | None) -> bool:
    version = read_version()
    ok = True
    for path, content in expected_contents(version).items():
        if path.read_text() != content:
            print(f"{path.relative_to(ROOT)}: not in sync with VERSION ({version})")
            ok = False
    if tag:
        if tag.startswith(RELEASE_TAG_PREFIX):
            tag_version = tag.removeprefix(RELEASE_TAG_PREFIX)
            if tag_version != version:
                print(f"Release tag '{tag}' does not match VERSION ({version})")
                ok = False
        else:
            print(f"Ignoring non-release tag '{tag}'")
    if not ok:
        print("Run 'make set-version V=X.Y.Z' or 'make sync-version' to fix")
    return ok


def main(args: list[str]):
    match args:
        case ["show"]:
            print(read_version())
        case ["set", version]:
            if not VERSION_RE.match(version):
                sys.exit(f"Invalid version: '{version}'")
            VERSION_FILE.write_text(f"{version}\n")
            for path in sync():
                print(f"Updated {path.relative_to(ROOT)}")
            update_lock_files()
        case ["sync"]:
            for path in sync():
                print(f"Updated {path.relative_to(ROOT)}")
        case ["check"]:
            sys.exit(0 if check(None) else 1)
        case ["check", "--tag", tag]:
            sys.exit(0 if check(tag) else 1)
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
