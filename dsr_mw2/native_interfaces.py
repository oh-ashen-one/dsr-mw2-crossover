"""Exact-build, static evidence for the experimental native handling adapter.

Matching bytes establish where code lives, not that a runtime ABI is safe.
There is intentionally no install/launch action in this module.
"""
import hashlib
from .native_runtime import RUNTIME_HASHES
from .pe_image import PEImage

POINTERS = {
    "world_chr_man": {
        "pattern": "48 8B 05 ? ? ? ? 48 8B 48 68 48 85 C9 0F 84 ? ? ? ? 48 39 5E 10 0F 84 ? ? ? ? 48",
        "instruction_rva": 0x7c4626, "target_rva": 0x1c77e50,
    },
    "game_data_man": {
        "pattern": "48 8B 05 ? ? ? ? 48 85 C0 ? ? F3 0F 58 80 AC 00 00 00",
        "instruction_rva": 0x758cf0, "target_rva": 0x1c8a530,
    },
}
FUNCTIONS = {
    "aim_camera_update": (0x231620, "48 8b c4 55 53 56 57 41 56 48 8d a8 18 ff ff ff 48 81 ec c0 01 00 00 48 c7 44 24 50 fe ff ff ff"),
    "frame_entry": (0x15ce90, "48 8b c4 57 48 83 ec 70 48 c7 40 a8 fe ff ff ff 48 89 58 08 0f 29 70 e8"),
    "pad_step": (0x396860, "48 8b c4 55 56 57 41 54 41 55 41 56 41 57 48 8d a8 28 ff ff ff 48 81 ec a0 01 00 00"),
    "item_get": (0x7479e0, "48 89 5c 24 18 89 54 24 10 55 56 57 41 54 41 55 41 56 41 57 48 8d 6c 24 f9"),
    "item_set_quantity_candidate": (0x747ed0, "48 89 5c 24 08 48 89 6c 24 10 48 89 74 24 18 57 41 56 41 57 48 83 ec 40"),
    "item_delta_candidate": (0x749310, "40 53 56 57 41 56 48 81 ec 88 00 00 00 48 63 da 41 0f b6 f9"),
    "inventory_set_quantity_candidate": (0x74f2d0, "48 83 ec 28 48 89 5c 24 30 48 8b d9 48 89 6c 24 38 41 8b e8"),
}


def inspect(data: bytes) -> dict:
    sha = hashlib.sha256(data).hexdigest()
    if sha != RUNTIME_HASHES["DarkSoulsRemastered.exe"]:
        raise ValueError("Native interface review only supports the measured DSR executable")
    pe = PEImage(data)
    pointers = {}
    for name, item in POINTERS.items():
        instruction = pe.unique(item["pattern"])
        target = pe.rip_target(instruction, 3, 7)
        if instruction != item["instruction_rva"] or target != item["target_rva"]:
            raise ValueError("Native pointer signature disagrees: " + name)
        section = pe.section_at(target, 8)
        if section.executable or not section.flags & 0x80000000:
            raise ValueError("Native global is not in a writable data section")
        pointers[name] = {"instruction_rva": hex(instruction), "target_rva": hex(target), "unique_pattern": True}
    functions = {}
    for name, (rva, signature) in FUNCTIONS.items():
        expected = bytes.fromhex(signature)
        if pe.at(rva, len(expected)) != expected:
            raise ValueError("Native entry bytes disagree: " + name)
        fragment = pe.function_at(rva)
        if fragment[0] != rva:
            raise ValueError("Native entry is not a runtime-function boundary: " + name)
        functions[name] = {"rva": hex(rva), "prefix_length": len(expected),
                           "runtime_function_fragment_end": hex(fragment[1]),
                           "runtime_abi_verified": False}
    # These independently corroborate the table stride, two backing-list paths,
    # and quantity +8 observed in upstream source. No machine code is emitted.
    checks = {
        "aim_camera_angular_stage": (0x231a99, "0f 28 8b b0 00 00 00 0f 28 93 c0 00 00 00 0f 5c d1 f3 0f 10 06 0f c6 c0 00 0f 59 d0 0f 58 d1"),
        "aim_camera_zoom_stage": (0x231795, "48 8d b3 3c 01 00 00 f3 0f 59 83 44 01 00 00 f3 0f 58 06 f3 0f 11 06"),
        "quantity_load": (0x74f291, "41 8b 41 08"),
        "quantity_store": (0x74f2a8, "41 89 41 08"),
        "entry_stride": (0x74f27b, "4c 6b cb 1c"),
        "list_boundary": (0x74f282, "3b 5f 20"),
        "list_one": (0x74f287, "4c 03 4f 30"),
        "list_two": (0x74f28d, "4c 03 4f 38"),
    }
    for name, (rva, signature) in checks.items():
        if pe.at(rva, len(bytes.fromhex(signature))) != bytes.fromhex(signature):
            raise ValueError("Native instruction evidence disagrees: " + name)
    return {"exe_sha256": sha, "image_timestamp": hex(pe.timestamp),
            "image_base": hex(pe.image_base), "pointers": pointers, "functions": functions,
            "inventory_layout_checks": {k: hex(v[0]) for k, v in checks.items() if not k.startswith('aim_camera')},
            "camera_instruction_checks": {k: hex(v[0]) for k, v in checks.items() if k.startswith('aim_camera')},
            "status": "static matches only; no native code executed",
            "runtime_verified": False}
