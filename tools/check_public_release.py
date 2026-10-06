"""Audit publishable files without reading ignored games, saves or credentials."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOTS = {'retail','converted','profiles','tooling-local','.venv','private'}
TEXT_SUFFIXES = {'.py','.cpp','.hpp','.h','.S','.swift','.def','.patch','.md','.txt','.json','.toml','.command','.yml','.yaml','.sb'}
TEXT_NAMES = {'LICENSE','NOTICE','.gitignore','.gitattributes','Makefile'}
SAFE_EVIDENCE = {'native-gun-trial-runtime.json','native-player-reference-runtime.json','native-type-table-runtime.json'}
PATTERNS = [
    re.compile(r'/(?:Users|home)/[^ /\n]+'),
    re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    re.compile(r'(?:libfile|file)_[a-f0-9]{24,}'),
    re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
]


def main():
    files = sorted(set(subprocess.check_output(
        ['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT
    ).decode().rstrip('\0').split('\0')) - {''})
    failures = []
    for name in files:
        relative = Path(name)
        file = ROOT / relative
        if relative.parts[0] in FORBIDDEN_ROOTS or (relative.parts[0]=='evidence' and relative.name not in SAFE_EVIDENCE):
            failures.append({'file':name,'reason':'private output path'})
            continue
        if file.is_symlink() or not file.is_file():
            failures.append({'file':name,'reason':'nonphysical file'})
            continue
        if relative.suffix not in TEXT_SUFFIXES and relative.name not in TEXT_NAMES:
            failures.append({'file':name,'reason':'unexpected non-source extension'})
            continue
        if file.stat().st_size > 512*1024:
            failures.append({'file':name,'reason':'oversized source file'})
            continue
        try:
            data = file.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            failures.append({'file':name,'reason':'binary content'})
            continue
        if '\0' in data or any(p.search(data) for p in PATTERNS):
            failures.append({'file':name,'reason':'private-path, credential or binary signature'})
    print(json.dumps({'files_checked':len(files),'failures':failures,
                      'scope':'Tracked and unignored text only; ignored local data was not inspected'},indent=2))
    return 1 if failures or not files else 0


if __name__ == '__main__': raise SystemExit(main())
