"""Inactive magazine/reserve data candidate. Never installs or edits a save.

Requires the native controller/writer before gameplay; the ordinary installed
prototype must retain its 99 bolts until runtime integration is verified.
"""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import json
import struct
from pathlib import Path

from .soulstruct_tools import configure, WORKSPACE
from .param_patch import append_fixed_row, patch_row
from .audit import is_within

RESERVE_ID = 9000001
PARAM = Path("param/GameParam/GameParam.parambnd.dcx")
TEXT = Path("msg/ENGLISH/item.msgbnd.dcx")
PARAM_SHA = "6a1051662f7f73db872fbaa995bc40e204d5fbced4f8485bf7e7970003c6fb3a"
TEXT_SHA = "88c30b78a15cc92dd0bcca2d7c46047e6260294ee2a09e7f0f037584be0bbf9d"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def table_map(params):
    return {k.rsplit("\\", 1)[-1]: v for k, v in params.params.items()}


def build() -> dict:
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND
    from soulstruct.darksouls1r.text.fmg import FMG
    param_source = WORKSPACE / "converted/dsr/m9-sidearm/mod" / PARAM
    text_source = WORKSPACE / "converted/dsr/m9-model-candidate/equipment-text" / TEXT
    param_bytes, text_bytes = param_source.read_bytes(), text_source.read_bytes()
    if sha(param_bytes) != PARAM_SHA or sha(text_bytes) != TEXT_SHA:
        raise ValueError("Expected verified base M9 package revision")
    out = WORKSPACE / "converted/dsr/handling-candidate-v1"
    targets = [out / "mod" / PARAM, out / "mod" / TEXT, out / "reserve-report.json"]
    if any(not is_within(p, WORKSPACE / "converted") or not is_within(p, out) for p in targets):
        raise ValueError("Output redirected outside task candidate")
    binder = Binder.from_bytes(param_bytes)
    tables = table_map(GameParamBND.from_bytes(param_bytes))
    old_entries = [(e.entry_id, e.path, e.flags, e.data) for e in binder.entries]
    goods = tables["EquipParamGoods"]
    if RESERVE_ID in goods.rows:
        raise ValueError("Reserve ID already occupied")
    reserve = copy.deepcopy(goods[1000])
    reserve.RawName = b""
    reserve.Name = ""
    for field in dataclasses.fields(reserve):
        if field.name.startswith("Useable"):
            setattr(reserve, field.name, 0)
    edits = {
        "ReferenceID": -1, "AnimationVariationID": -1, "FramptSellValue": -1,
        "GoodToReplace": -1, "Spell": -1, "MaxHoldQuantity": 999,
        "GoodIcon": tables["EquipParamWeapon"][2100000].WeaponIcon,
        "CanBeEquipped": 0, "AutomaticallyEquipped": 0, "ConsumedOnUse": 0,
        "CanBeDropped": 0, "CanBeStored": 0, "IsUpgradeMaterial": 0,
        "DisableMultiplayerShare": 1, "MenuActivated": 0,
        "VagrantItemLot": -1, "VagrantBonusEnemyDropItemLot": -1, "VagrantItemEnemyDropItemLot": -1,
    }
    for field, value in edits.items():
        setattr(reserve, field, value)
    goods_entry = next(e for e in binder.entries if e.path.endswith("\\EquipParamGoods.param"))
    raw_goods = goods_entry.get_uncompressed_data()
    row_size = len(bytes(reserve))
    if struct.unpack_from("<H", raw_goods, 10)[0] != len(goods.rows):
        raise ValueError("Goods source has duplicate IDs")
    goods_entry.set_uncompressed_data(append_fixed_row(raw_goods, RESERVE_ID, bytes(reserve)))
    starts_entry = next(e for e in binder.entries if e.path.endswith("\\CharaInitParam.param"))
    raw_starts = starts_entry.get_uncompressed_data()
    starter_edits = []
    for row_id in range(2000, 2010):
        old = tables["CharaInitParam"][row_id]
        if old.GoodSlot8 != -1 or old.GoodSlot8Count != 0 or old.BoltSlot1 != 2100000 or old.BoltSlot1Count != 99:
            raise ValueError("Expected unused reserve starter slot and existing M9 bolt stack")
        new = copy.deepcopy(old)
        new.GoodSlot8, new.GoodSlot8Count, new.BoltSlot1Count = RESERVE_ID, 84, 15
        raw_starts, _ = patch_row(raw_starts, row_id, bytes(old), bytes(new))
        starter_edits.append(row_id)
    starts_entry.set_uncompressed_data(raw_starts)
    candidate = bytes(binder)
    decoded = table_map(GameParamBND.from_bytes(candidate))
    decoded_binder = Binder.from_bytes(candidate)
    if set(decoded["EquipParamGoods"].rows) != set(goods.rows) | {RESERVE_ID}:
        raise ValueError("Goods row set changed unexpectedly")
    for row_id, before in goods.rows.items():
        after = decoded["EquipParamGoods"][row_id]
        if bytes(after) != bytes(before) or after.RawName != before.RawName:
            raise ValueError("Existing Goods row/name changed")
    if bytes(decoded["EquipParamGoods"][RESERVE_ID]) != bytes(reserve):
        raise ValueError("Reserve row round trip mismatch")
    for row_id, before in tables["CharaInitParam"].rows.items():
        after = decoded["CharaInitParam"][row_id]
        for field in dataclasses.fields(before):
            if row_id in starter_edits and field.name in {"GoodSlot8", "GoodSlot8Count", "BoltSlot1Count"}:
                expected = {"GoodSlot8": RESERVE_ID, "GoodSlot8Count": 84, "BoltSlot1Count": 15}[field.name]
            else:
                expected = getattr(before, field.name)
            if getattr(after, field.name) != expected:
                raise ValueError("Unintended starter/stat/gear field change: " + field.name)
    untouched = []
    for old, new in zip(old_entries, decoded_binder.entries, strict=True):
        if old[:3] != (new.entry_id, new.path, new.flags):
            raise ValueError("Binder metadata changed")
        if not new.path.endswith(("\\EquipParamGoods.param", "\\CharaInitParam.param")):
            if old[3] != new.data:
                raise ValueError("Unrelated parameter table changed")
            untouched.append(new.path.rsplit("\\", 1)[-1])
    text_binder = Binder.from_bytes(text_bytes)
    text_original = [(e.entry_id, e.path, e.flags, e.data) for e in text_binder.entries]
    names = {10: "M9 reserve rounds", 111: "M9 reserve rounds",
             20: "Spare ammunition for the M9 magazine.", 110: "Spare ammunition for the M9 magazine.",
             24: "Reserve rounds for the M9.\nTransferred into its magazine when reloading.\nCannot be used or equipped directly.",
             100: "Reserve rounds for the M9.\nTransferred into its magazine when reloading.\nCannot be used or equipped directly."}
    for entry in text_binder.entries:
        if entry.entry_id in names:
            fmg = FMG.from_bytes(entry.get_uncompressed_data())
            before = dict(fmg.entries)
            if RESERVE_ID in before:
                raise ValueError("Reserve FMG ID already occupied")
            fmg.entries[RESERVE_ID] = names[entry.entry_id]
            encoded = bytes(fmg)
            check = FMG.from_bytes(encoded)
            if check.entries != before | {RESERVE_ID: names[entry.entry_id]}:
                raise ValueError("FMG round trip changed existing text")
            entry.set_uncompressed_data(encoded)
    text_candidate = bytes(text_binder)
    for before, after in zip(text_original, Binder.from_bytes(text_candidate).entries, strict=True):
        if before[:3] != (after.entry_id, after.path, after.flags) or (after.entry_id not in names and before[3] != after.data):
            raise ValueError("Unrelated text entry changed")
    if param_source.read_bytes() != param_bytes or text_source.read_bytes() != text_bytes:
        raise ValueError("Input changed during build")
    report = {"reserve_id": RESERVE_ID, "category": "0x40000000", "magazine_capacity": 15,
              "starter_reserve": 84, "starter_total": 99, "reserve_row_bytes": row_size,
              "existing_goods_rows_preserved": len(goods.rows), "untouched_param_tables": untouched,
              "starter_rows": starter_edits, "unchanged_stats_and_gear": True,
              "source_param_sha256": sha(param_bytes), "output_param_sha256": sha(candidate),
              "source_text_sha256": sha(text_bytes), "output_text_sha256": sha(text_candidate),
              "source_files_unchanged": True, "runtime_verified": False, "installed": False,
              "limitations": ["Native transaction/input driver is not implemented",
                              "Reserve item uses the native Standard Bolt icon; in-game display unverified",
                              "English only; stock shop pickups still need magazine/reserve routing",
                              "Existing characters are not migrated; no replenishment shop configured",
                              "Candidate must not be installed before native writer/zero-stack validation"]}
    for target, payload in zip(targets[:2], (candidate, text_candidate), strict=True):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    targets[2].write_text(json.dumps(report, indent=2) + "\n")
    (WORKSPACE / "evidence/m9-reserve-candidate.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
