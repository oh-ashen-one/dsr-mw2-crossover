"""List matching original MW2 IWD entries without exporting retail content."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile


def inventory(main_dir: Path, pattern: str = "m9|beretta") -> list[dict]:
    needle = re.compile(pattern, re.IGNORECASE)
    matches: list[dict] = []
    for archive in sorted(main_dir.glob("*.iwd")):
        try:
            with ZipFile(archive) as package:
                for member in package.infolist():
                    if member.is_dir() or not needle.search(member.filename):
                        continue
                    matches.append({
                        "archive": archive.name,
                        "entry": member.filename,
                        "size": member.file_size,
                        "crc32": f"{member.CRC:08x}",
                    })
        except BadZipFile as exc:
            raise ValueError(f"Invalid IWD archive: {archive}") from exc
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_dir", type=Path, help="Read-only path to owned MW2 2009 main/ archives")
    parser.add_argument("--pattern", default="m9|beretta")
    args = parser.parse_args()
    matches = inventory(args.main_dir, args.pattern)
    print(json.dumps(matches, indent=2))
    return 0 if matches else 2


if __name__ == "__main__":
    raise SystemExit(main())
