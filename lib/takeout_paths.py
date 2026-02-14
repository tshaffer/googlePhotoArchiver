from __future__ import annotations

import argparse
import os
from pathlib import Path

from lib.env import optional_env, require_env


def get_takeout_unzipped_root() -> Path:
    """Return the authoritative unzipped root if set; else fall back to legacy default root."""
    override = optional_env("TAKEOUT_UNZIPPED_ROOT", "").strip()
    if override:
        return Path(override)
    photo_archive = require_env("PHOTO_ARCHIVE")
    return Path(photo_archive) / "GOOGLE_TAKEOUT"


def takeout_unzipped_base(account: str) -> Path:
    """
    Resolve the per-account unzipped base.
    - If TAKEOUT_UNZIPPED_ROOT is set, prefer <root>/<account> when it exists;
      otherwise use <root>.
    - Otherwise use the legacy location: <PHOTO_ARCHIVE>/GOOGLE_TAKEOUT/<account>/unzipped
    """
    override = optional_env("TAKEOUT_UNZIPPED_ROOT", "").strip()
    root = get_takeout_unzipped_root()
    if override:
        candidate = root / account
        if candidate.is_dir():
            return candidate
        return root
    return root / account / "unzipped"


def get_google_photos_root(account: str) -> Path:
    """Return the expected Google Photos folder under the resolved unzipped base."""
    return takeout_unzipped_base(account) / "Takeout" / "Google Photos"


def _main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Takeout unzipped paths.")
    parser.add_argument("--account", default="", help="Account name for per-account resolution.")
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print resolved paths for sanity checking.",
    )
    args = parser.parse_args()

    if args.print:
        acct = args.account or "<account>"
        base = takeout_unzipped_base(acct)
        google = get_google_photos_root(acct)
        print(f"TAKEOUT_UNZIPPED_ROOT={optional_env('TAKEOUT_UNZIPPED_ROOT', '').strip()}")
        print(f"resolved_unzipped_base={base}")
        print(f"google_photos_root={google}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
