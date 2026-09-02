#!/usr/bin/env python3
"""Fetch the MODFLOW and PEST++ executables the tutorials need into ./bin.

Run it with ``pixi run get-exes``. Everything lands in a single ``bin``
directory at the repo root, which is gitignored - the binaries are not
vendored into the repo any more.

MODFLOW comes from MODFLOW-ORG/executables via flopy's ``get-modflow``.
PEST++ comes from the usgs/pestpp releases via pyemu's ``get-pestpp``.

Note on PESTPP_RELEASE below: every usgs/pestpp release since 5.2.16 is
flagged as a GitHub "prerelease", and the /releases/latest endpoint that
``get-pestpp`` queries for "latest" skips those. Asking for "latest" would
therefore install 5.2.16 (December 2024), not the newest build. The release
is pinned explicitly instead.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"

# MODFLOW-ORG/executables distribution
# mf5to6 is in the distribution but nothing in tutorials/ calls it
MODFLOW_SUBSET = ["mf6", "mp7", "zbud6"]

# usgs/pestpp - see the module docstring for why this is pinned
PESTPP_RELEASE = "5.2.27"
PESTPP_SUBSET = [
    "pestpp-glm",
    "pestpp-ies",
    "pestpp-sen",
    "pestpp-opt",
    "pestpp-da",
    "pestpp-mou",
    "pestpp-sqp",
    "pestpp-swp",
]

EXPECTED = MODFLOW_SUBSET + PESTPP_SUBSET


def _exe(name: str) -> Path:
    return BIN_DIR / (name + ".exe" if sys.platform.startswith("win") else name)


def check() -> int:
    missing = [n for n in EXPECTED if not _exe(n).exists()]
    if missing:
        print(f"missing from {BIN_DIR}: {', '.join(missing)}")
        print("run 'pixi run get-exes'")
        return 1
    print(f"all {len(EXPECTED)} executables present in {BIN_DIR}")
    return 0


def fetch(force: bool = False) -> int:
    BIN_DIR.mkdir(exist_ok=True)

    cmds = [
        (
            "MODFLOW",
            [
                sys.executable, "-m", "flopy.utils.get_modflow",
                str(BIN_DIR),
                "--subset", ",".join(MODFLOW_SUBSET),
            ],
        ),
        (
            f"PEST++ {PESTPP_RELEASE}",
            [
                sys.executable, "-m", "pyemu.utils.get_pestpp",
                str(BIN_DIR),
                "--release-id", PESTPP_RELEASE,
                "--subset", ",".join(PESTPP_SUBSET),
            ],
        ),
    ]
    for label, cmd in cmds:
        if force:
            cmd.append("--force")
        print(f"\n=== fetching {label}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"FAILED: {label}", file=sys.stderr)
            return result.returncode

    print()
    return check()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true",
                   help="only report what is present, download nothing")
    p.add_argument("--force", action="store_true",
                   help="re-download even if the archives are cached")
    args = p.parse_args()
    return check() if args.check else fetch(force=args.force)


if __name__ == "__main__":
    sys.exit(main())
