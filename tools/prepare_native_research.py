"""Prepare local static-analysis inputs; never launch DSR or a new analysis tool.

Only the already-used MinGW objdump runs. Retail bytes and disassembly stay in
the ignored task cache. A changed image, destination or tool fails closed.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from dsr_mw2.native_interfaces import inspect
from dsr_mw2.pe_image import PEImage
from dsr_mw2.runtime_paths import bottle_path

ROOT = Path(__file__).resolve().parents[1]
OBJDUMP = Path('/opt/homebrew/bin/x86_64-w64-mingw32-objdump')
# Seeds are questions for an analyst, not callable API declarations. In
# particular, consuming ammo does not establish a projectile collision callback.
SEEDS = {
    'player_frame': (0x15ce90, 'Existing bounded frame hook; establish render/update ordering.'),
    'input_update': (0x396860, 'Existing pad hook; preserve DSR movement, menus and interactions.'),
    'ammo_delta': (0x749310, 'Existing observed ammo delta; do not use as proof of enemy impact.'),
    'native_shot_caller': (0x35b149, 'Observed shot return site; follow callers/callees to native projectile creation.'),
    'aim_camera': (0x231620, 'Qualified camera entry; identify actual camera and weapon transforms.'),
    'projection_inputs': (0x2472d0, 'Measured FOV/aspect/near/far inputs; distinguish world and viewmodel projection.'),
    'projection_builder': (0x93fd0, 'Trace matrix convention before any separate weapon draw pass.'),
    'projection_math': (0x7c1c0, 'Measured perspective math; no unmeasured offsets or lens changes.'),
    'hud_update': (0x67bb20, 'Existing scoped reticle hook; find correct draw ordering beneath native HUD.'),
    'hud_find_child': (0xed6020, 'Existing named HUD child lookup; no global HUD suppression.'),
    'hud_visibility': (0xedbdb0, 'Existing visibility setter contract; restore prior state.'),
    'parts_loader_candidate': (0x20a280, 'Upstream DSR reference only; identify model ownership/lifetime, not yet qualified.'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def preserve(path, data):
    """Never replace an existing result or follow a destination link."""
    if path.is_symlink():
        raise ValueError('Research output cannot be a symlink: ' + str(path))
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError('Differing research output preserved: ' + str(path))
        return
    with path.open('xb') as output:
        output.write(data)
    path.chmod(0o400)


def main():
    source = bottle_path() / 'drive_c/Games/Dark Souls Remastered/DarkSoulsRemastered.exe'
    if source.is_symlink():
        raise ValueError('Private baseline must be a regular file')
    data = source.read_bytes()
    identity = inspect(data)
    pe = PEImage(data)
    optional = struct.unpack_from('<I', data, 0x3c)[0] + 24
    clr = struct.unpack_from('<II', data, optional + 112 + 14 * 8)
    if clr != (0, 0):
        raise ValueError('Unexpected managed CLR directory')
    cache = ROOT / 'tooling-local/native-research' / identity['exe_sha256']
    if cache.resolve() != cache:
        raise ValueError('Research cache path is redirected')
    cache.mkdir(parents=True, exist_ok=True)
    snapshot = cache / source.name
    preserve(snapshot, data)
    if not OBJDUMP.is_file():
        raise ValueError('Existing MinGW objdump unavailable; no installation attempted')
    tool_hash = digest(OBJDUMP.read_bytes())
    version = subprocess.check_output([str(OBJDUMP), '--version'], text=True).splitlines()[0]
    headers = subprocess.check_output([str(OBJDUMP), '-p', str(snapshot)])
    preserve(cache / 'pe-headers.txt', headers)
    records = {}
    for name, (address, question) in SEEDS.items():
        matches = [f for f in pe.functions() if f[0] <= address < f[1]]
        if not matches:
            # Leaf routines may have no unwind entry. Do not invent a function
            # extent or decode arbitrary trailing bytes as instructions.
            if not pe.section_at(address, 32).executable:
                raise ValueError('Research seed is not executable code')
            records[name] = {
                'seed_rva': hex(address), 'seed_va': hex(pe.image_base + address),
                'prefix_32_sha256': digest(pe.at(address, 32)), 'question': question,
                'unwind_fragment': None, 'assembly_local': None,
                'limit': 'No unwind entry; decompiler must establish instruction/function boundaries.',
                'new_runtime_contract_verified': False,
            }
            continue
        if len(matches) != 1:
            raise ValueError('Ambiguous native function range')
        begin, end, unwind = matches[0]
        if end - begin > 0x10000:
            raise ValueError('Unexpectedly large function fragment')
        assembly = subprocess.check_output([
            str(OBJDUMP), '-d', '-Mintel',
            '--start-address=' + hex(pe.image_base + begin),
            '--stop-address=' + hex(pe.image_base + end), str(snapshot),
        ])
        destination = cache / (name + '.asm')
        preserve(destination, assembly)
        records[name] = {
            'seed_rva': hex(address), 'seed_va': hex(pe.image_base + address),
            'fragment_start_rva': hex(begin), 'fragment_end_rva_exclusive': hex(end),
            'fragment_sha256': digest(pe.at(begin, end - begin)), 'unwind_rva': hex(unwind),
            'question': question, 'assembly_local': str(destination.relative_to(ROOT)),
            'assembly_sha256': digest(assembly), 'new_runtime_contract_verified': False,
        }
    if digest(source.read_bytes()) != identity['exe_sha256'] or digest(snapshot.read_bytes()) != identity['exe_sha256']:
        raise ValueError('Source or snapshot changed during review')
    report = {
        'at': datetime.now(timezone.utc).isoformat(),
        'status': 'Static investigation inputs prepared; no decompiler or game executed',
        'image_sha256': identity['exe_sha256'], 'image_base': hex(pe.image_base),
        'format': 'x86-64 PE32+, no CLR directory',
        'import_dlls': re.findall(r'DLL Name: ([^\r\n]+)', headers.decode()),
        'snapshot_local': str(snapshot.relative_to(ROOT)), 'snapshot_mode': oct(snapshot.stat().st_mode & 0o777),
        'objdump': {'version': version, 'sha256': tool_hash},
        'functions': records, 'source_unchanged': True,
        'game_launched': False, 'new_downloaded_tools_executed': False,
        'profile_or_save_changed': False, 'runtime_readiness': 'unverified',
        'limits': [
            'Unwind fragments can be smaller than a logical function; follow xrefs in the decompiler.',
            'Names are investigation labels, not recovered retail symbols.',
            'The shot return site proves native ammunition consumption only, not boss damage.',
            'The parts-loader candidate is an upstream address lead, not a verified ABI.',
        ],
    }
    (ROOT / 'evidence/native-research-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'targets': len(records),
                      'image_sha256': report['image_sha256'], 'source_unchanged': True,
                      'receipt': 'evidence/native-research-preparation.json'}))


if __name__ == '__main__':
    main()
