"""Select offline mode only in this task's already authenticated Steam client.

Never print, copy or change account identifiers, tokens or remembered credentials.
"""
from __future__ import annotations

import os
from pathlib import Path
import re


def mode_text(text: str, offline: bool) -> str:
    """Preserve the VDF byte-for-byte except its two existing mode flags."""
    for key in ("WantsOfflineMode", "SkipOfflineModeWarning"):
        pattern = re.compile(r'("' + key + r'"\s+")[01](")', re.IGNORECASE)
        if len(pattern.findall(text)) != 1:
            raise ValueError("Private Steam mode flags are ambiguous; preserve account configuration")
        text = pattern.sub(lambda m: m[1] + str(int(offline)) + m[2], text)
    return text


def configure(path: Path, offline: bool) -> None:
    # Called only while the private session lock is held and Steam is stopped.
    raw = path.read_bytes()
    changed = mode_text(raw.decode("utf-8"), offline).encode("utf-8")
    if changed == raw:
        return
    temporary = path.with_name(".dsr-mw2-steam-mode.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(changed)
            stream.flush()
            os.fsync(stream.fileno())
        # Refuse to replace configuration changed by a concurrently started UI.
        if path.read_bytes() != raw:
            raise ValueError("Private Steam configuration changed concurrently")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
