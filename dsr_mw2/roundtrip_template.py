"""Verify DSR's weapon FLVER can round-trip offline before replacing its mesh."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from .soulstruct_tools import configure


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    configure()
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.flver import FLVER

    source = root / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx"
    binder = Binder.from_path(source)
    original = [(e.entry_id, e.path, e.flags, e.data) for e in binder.entries]
    entry = next(e for e in binder.entries if e.path.endswith(".flver"))
    model = FLVER.from_bytes(entry.get_uncompressed_data())
    encoded = bytes(model)
    reloaded = FLVER.from_bytes(encoded)
    errors = []
    for mesh, check in zip(model.meshes, reloaded.meshes, strict=True):
        if mesh.material != check.material or not np.array_equal(mesh.bone_indices, check.bone_indices):
            raise ValueError("Mesh material/rig mismatch")
        for array, checked_array in zip(mesh.vertex_arrays, check.vertex_arrays, strict=True):
            for field in array.array.dtype.names:
                error = float(np.max(np.abs(array.array[field].astype(float) - checked_array.array[field].astype(float))))
                errors.append({"mesh": mesh.index, "field": field, "max_error": error})
                if error > 1e-5:
                    raise ValueError(f"Vertex data changed: {field} {error}")
        for faces, checked_faces in zip(mesh.face_sets, check.face_sets, strict=True):
            if not np.array_equal(faces.vertex_indices, checked_faces.vertex_indices):
                raise ValueError("Faces changed")
    for bone, check in zip(model.bones, reloaded.bones, strict=True):
        for field in ("name", "usage_flags", "parent_bone_index", "child_bone_index", "next_sibling_bone_index", "previous_sibling_bone_index"):
            if getattr(bone, field) != getattr(check, field):
                raise ValueError(f"Bone field changed: {field}")
        for field in ("translate", "rotate", "scale"):
            if not np.allclose(tuple(getattr(bone, field)), tuple(getattr(check, field)), atol=1e-7, rtol=0):
                raise ValueError(f"Bone transform changed: {field}")
        for field in ("min", "max"):
            if not np.allclose(tuple(getattr(bone.bounding_box, field)), tuple(getattr(check.bounding_box, field)), atol=1e-7, rtol=0):
                raise ValueError("Bone bounds changed")
    for dummy, check in zip(model.dummies, reloaded.dummies, strict=True):
        for field in ("translate", "forward", "upward", "color"):
            if not np.allclose(tuple(getattr(dummy, field)), tuple(getattr(check, field)), atol=1e-7, rtol=0):
                raise ValueError(f"Dummy vector changed: {field}")
        for field in ("reference_id", "parent_bone_index", "attach_bone_index", "follows_attach_bone", "use_upward_vector", "unk_x30", "unk_x34"):
            if getattr(dummy, field) != getattr(check, field):
                raise ValueError(f"Dummy field changed: {field}")
    entry.set_uncompressed_data(encoded)
    target = root / "converted/dsr/template-roundtrip/parts/WP_A_1401.partsbnd.dcx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes(binder))
    checked_binder = Binder.from_path(target)
    unchanged = []
    for old, checked in zip(original, checked_binder.entries, strict=True):
        if old[:3] != (checked.entry_id, checked.path, checked.flags):
            raise ValueError("Binder metadata changed")
        if not checked.path.endswith(".flver"):
            if old[3] != checked.data:
                raise ValueError("Texture/animation entry changed")
            unchanged.append(checked.entry_id)
    report = {
        "soulstruct_commit": "12b69189a2ccebbc623a1b6565be89a18d6c9958",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "meshes": model.mesh_count, "bones": model.bone_count, "dummies": model.dummy_count,
        "vertices": sum(len(m.vertex_arrays[0].array) for m in model.meshes), "field_errors": errors,
        "materials_rig_dummies_faces_verified": True, "unchanged_texture_animation_entries": unchanged,
        "activated": False, "runtime_verified": False,
    }
    (root / "evidence/flver-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "field_errors"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
