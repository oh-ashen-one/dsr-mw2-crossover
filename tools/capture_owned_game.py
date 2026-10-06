"""Record only the verified disposable game; no prompt, microphone or input."""
import argparse
import hashlib
from pathlib import Path
import subprocess
from dsr_mw2.validation_session import require_active
from dsr_mw2.launch import game_processes
from tools.inspect_dsr_window import windows
from tools.owned_dsr_input import foreground_pid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/capture_owned_game.swift'
BINARY = ROOT / 'tooling-local/native-input/capture-owned-game'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--seconds', type=int, default=25)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    stamp = BINARY.with_suffix('.sha256')
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if args.build:
        subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(SOURCE), '-o', str(BINARY)], check=True)
        stamp.write_text(source_hash + '\n')
        return
    require_active()
    if not 1 <= args.seconds <= 60 or args.output is None:
        raise ValueError('A bounded duration and output are required')
    output = args.output.absolute()
    if output.exists() or not output.resolve().is_relative_to(ROOT / 'evidence/raw') or output.suffix != '.mp4':
        raise ValueError('Capture must be a fresh ignored evidence/raw MP4')
    if stamp.read_text().strip() != source_hash:
        raise ValueError('Capture helper needs rebuilding')
    games = game_processes()
    if len(games) != 1 or foreground_pid() != games[0]:
        raise ValueError('One owned foreground native game is required')
    matches = [w for w in windows() if w.get('kCGWindowOwnerPID') == games[0]
               and w.get('kCGWindowName') == 'DARK SOULS™: REMASTERED'
               and w.get('kCGWindowBounds', {}).get('Width', 0) > 100]
    if len(matches) != 1:
        raise ValueError('Ambiguous owned game window')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(BINARY), str(games[0]), str(matches[0]['kCGWindowNumber']),
                    str(args.seconds), str(output)], check=True, timeout=args.seconds + 30)


if __name__ == '__main__':
    main()
