"""Bind a reviewed local OAT source build to its exact pinned patch. Never executes it.

Run only after building the source yourself. This cannot prove who built an
arbitrary downloaded executable; do not use it to bless one.
"""
import argparse
import json
from pathlib import Path
import subprocess

from dsr_mw2.asset_provenance import (
    WORKSPACE, SOURCE_COMMIT, SOURCE_PATCH_SHA, EXTRACTOR, digest,
)
import hashlib


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    args = p.parse_args()
    source = args.source.resolve()
    if not source.is_relative_to(WORKSPACE / 'tooling-local/sources'):
        raise ValueError('OAT source must be in tooling-local/sources')
    head = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    diff = subprocess.check_output(['git','-C',str(source),'diff','--no-ext-diff','--no-textconv','--binary','--abbrev=7','--src-prefix=a/','--dst-prefix=b/','-U0','HEAD','--'])
    if head != SOURCE_COMMIT or hashlib.sha256(diff).hexdigest() != SOURCE_PATCH_SHA:
        raise ValueError('Source tree must contain exactly the pinned native64 patch; preserve and inspect any difference')
    if digest(WORKSPACE / 'tools/oat-mw2-native64.patch') != SOURCE_PATCH_SHA:
        raise ValueError('Published patch identity changed')
    if EXTRACTOR.is_symlink() or not EXTRACTOR.is_file():
        raise ValueError('Place your locally built Unlinker at the documented physical path')
    receipt = WORKSPACE / 'tooling-local/extractor-build.json'
    data = {'source_commit':head,'patch_sha256':SOURCE_PATCH_SHA,
            'source_diff_sha256':hashlib.sha256(diff).hexdigest(),
            'binary_sha256':digest(EXTRACTOR),'binary_executed':False}
    if receipt.exists():
        if json.loads(receipt.read_text()) != data:
            raise ValueError('Preserving previous extractor build receipt')
    else:
        with receipt.open('x') as file:
            json.dump(data,file,indent=2)
            file.write('\n')
    print(json.dumps(data,indent=2))


if __name__ == '__main__': main()
