"""Check the measured native DSR executable revision without executing it."""
from pathlib import Path
import hashlib

from .audit import is_within

# All seven were compared against the original installed source and both private
# copies on 2026-10-02. A Steam update needs an explicit compatibility review.
RUNTIME_HASHES = {
    "DarkSoulsRemastered.exe": "a45aaa36dd2f6cc151670a639ea5547043cf38ea79ff4178b963c6ed71f98d7b",
    "binkw64.dll": "dd76c2d48969a77bf98e51568eda0b774e3e47296585ada5d0d0c9583ed5feb5",
    "fmod_event64.dll": "27008d07df0ccfa5ad66ca6820e34fe378388515fecb0c22c48daeb26379c314",
    "fmod_event_net64.dll": "a82cbf50eedd842ec8b2ea5098a33c134e43bc25fe34f1c8009684d66a9a7dd7",
    "fmodex64.dll": "3cfda68e1488c1ba7171b218da27f2feded47b958352a9240a5ce78831794468",
    "steam_api64.dll": "a0a5ac6dcd3d9255bb9c71bae3a71b6bf90c56f4fce46ff0d65533d7ef89b8d8",
    "xinput1_3.dll": "756cad002e1553cfa1a91ebe8c1b9380ffabe0b4b1916c4a4db802396ddfbef8",
}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def check(root: Path, *, input_trial: bool = False) -> list[str]:
    reasons = []
    try:
        hashes = RUNTIME_HASHES
        if input_trial:
            from tools.native_input_trial import expected
            hashes = expected()
        actual = {p.name for p in root.iterdir() if p.suffix.lower() in {".dll", ".exe"}}
        if actual != set(hashes):
            reasons.append("Private DSR runtime binary set changed: " + root.name)
        for name, expected_hash in hashes.items():
            path = root / name
            if path.is_symlink() or not is_within(path, root) or digest(path) != expected_hash:
                reasons.append("Private DSR runtime revision changed: " + root.name + "/" + name)
    except (OSError, ValueError, KeyError) as exc:
        reasons.append("Private DSR runtime check failed: " + str(exc))
    return reasons
