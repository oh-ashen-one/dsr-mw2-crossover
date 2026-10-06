"""Prepare a rigid M9 mesh candidate inside DSR's native weapon binder.

No renderer is used. Source model, materials and attachment points are checked.
This converter retains DSR's attachment skeleton and animations; it does not
retarget MW2 slide/magazine or player animations. Placement requires owner QA.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from .audit import is_within
from .obj_geometry import parse
from .soulstruct_tools import configure
from .pack_textures import pack
from .asset_provenance import verify

WORKSPACE = Path(__file__).resolve().parents[1]


def make_meshes(model, geometry: dict, scale: float = .0254, *, include_suppressor: bool = False, grip=(0., 0., 0.), material_stems=None):
    import numpy as np
    from soulstruct.flver.face_set import FaceSet
    from soulstruct.flver.vertex_array import VertexArray
    if not .005 <= scale <= .05:
        raise ValueError("Scale outside the expected CoD inches to DSR meters conversion")
    source = model.meshes[0]
    if len(source.vertex_arrays) != 1:
        raise ValueError("Unexpected DSR weapon template vertex layout")
    meshes = []
    # Match the native crossbow's -X forward axis and anchor the measured
    # MW2 pistol grip to the retained DSR weapon root. Owner QA remains needed.
    transform = np.diag([-scale, scale, scale])
    for material_name, faces in geometry["groups"].items():
        suppressor = material_name == "mc/mtl_weapon_suppressor_b"
        if suppressor and not include_suppressor:
            continue
        if material_stems is not None and material_name not in material_stems:
            raise ValueError('Unverified source material: '+material_name)
        if material_stems is None and material_name not in ("mc/mtl_weapon_beretta", "mtl_weapon_beretta", "mc/mtl_weapon_suppressor_b"):
            raise ValueError(f"Unverified M9 material association: {material_name}")
        mapping, vertices, triangles = {}, [], []
        for face in faces:
            triangle = []
            for indices in face:
                if indices not in mapping:
                    mapping[indices] = len(vertices)
                    vertices.append(indices)
                triangle.append(mapping[indices])
            # This OBJ export + reflected basis already yields DSR's clockwise
            # facing. Reversing again makes every face oppose the native weapon
            # convention (measured against the unmodified crossbow normals).
            triangles.append(tuple(triangle))
        if len(vertices) > 65534:
            raise ValueError("Mesh exceeds DSR's 16-bit vertex budget")
        mesh = copy.deepcopy(source)
        array = np.zeros(len(vertices), dtype=source.vertex_arrays[0].array.dtype)
        for i, (p, uv, n) in enumerate(vertices):
            array["position"][i] = transform @ (np.asarray(geometry["positions"][p]) - np.asarray(grip))
            normal = np.asarray(geometry["normals"][n]) * [-1, 1, 1]
            length = np.linalg.norm(normal)
            if length < 1e-6:
                raise ValueError("Zero source normal")
            array["normal"][i] = normal / length
            u, v = geometry["uvs"][uv]
            array["uv_0"][i] = u, 1.0 - v  # undo OBJ's V flip for FLVER
        array["bone_indices"] = 0
        array["bone_weights"][:, 0] = 1.0
        array["color_0"] = 1.0
        tangents = np.zeros((len(vertices), 3))
        bitangents = np.zeros((len(vertices), 3))
        for triangle in triangles:
            a, b, c = triangle
            p, q = array["position"][b] - array["position"][a], array["position"][c] - array["position"][a]
            uv, st = array["uv_0"][b] - array["uv_0"][a], array["uv_0"][c] - array["uv_0"][a]
            determinant = uv[0] * st[1] - uv[1] * st[0]
            if abs(determinant) > 1e-8:
                tangent = (p * st[1] - q * uv[1]) / determinant
                bitangent = (q * uv[0] - p * st[0]) / determinant
                tangents[list(triangle)] += tangent
                bitangents[list(triangle)] += bitangent
        for i in range(len(vertices)):
            normal = array["normal"][i]
            tangent = tangents[i] - normal * np.dot(normal, tangents[i])
            if np.linalg.norm(tangent) < 1e-6:
                tangent = np.cross(normal, [0, 1, 0] if abs(normal[1]) < .9 else [1, 0, 0])
            array["tangent_0"][i, :3] = tangent / np.linalg.norm(tangent)
            array["tangent_0"][i, 3] = -1.0 if np.dot(np.cross(normal, tangent), bitangents[i]) < 0 else 1.0
        mesh.vertex_arrays = [VertexArray(array, copy.deepcopy(source.vertex_arrays[0].layout))]
        mesh.default_bone_index = 0
        mesh.bone_indices = np.array([0], dtype=np.int32)
        mesh.material.name = "MW2 M9 candidate"
        if suppressor:
            mesh.material.name = "MW2 M9 original suppressor"
            for texture in mesh.material.textures:
                if texture.path:
                    suffix = "_n" if texture.texture_type == "g_Bumpmap" else "_s" if texture.texture_type == "g_Specular" else ""
                    texture.path = "WP_A_1401_suppressor" + suffix + ".tga"
        if material_stems is not None:
            mesh.material.name=material_name
            for texture in mesh.material.textures:
                if texture.path:
                    suffix='_n' if texture.texture_type=='g_Bumpmap' else '_s' if texture.texture_type=='g_Specular' else ''
                    texture.path=material_stems[material_name]+suffix+'.tga'
        mesh.face_sets = [FaceSet(s.flags, False, s.use_backface_culling, s.unk_x06, np.asarray(triangles, dtype=np.uint32)) for s in source.face_sets]
        meshes.append(mesh)
    model.meshes = meshes
    model.refresh_mesh_indices()
    model.refresh_bounding_boxes()
    model.refresh_bone_bounding_boxes()
    return model


def build(obj: Path, provenance: Path, output: Path, include_suppressor: bool = False) -> dict:
    if not is_within(obj, WORKSPACE / "converted") or not is_within(output, WORKSPACE / "converted"):
        raise ValueError("Use only this task's converted source/output folders")
    proof = json.loads(provenance.read_text())
    proof = verify(obj, proof)
    points = proof.get("attachment_points")
    if not points:
        raise ValueError("Authentic M9 grip/muzzle bone export is required")
    raw_obj = obj.read_bytes()
    if len(raw_obj) > 64 * 1024 * 1024:
        raise ValueError("Oversized OBJ export")
    configure()
    import numpy as np
    from soulstruct.containers import Binder, TPF
    from soulstruct.flver import FLVER
    source = WORKSPACE / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx"
    binder = Binder.from_path(source)
    animation = next(e for e in binder.entries if e.path.endswith(".anibnd"))
    animation_hash = hashlib.sha256(animation.data).hexdigest()
    entry = next(e for e in binder.entries if e.path.endswith(".flver"))
    model = make_meshes(FLVER.from_bytes(entry.get_uncompressed_data()), parse(raw_obj.decode("utf-8")), include_suppressor=include_suppressor, grip=points["grip_obj"])
    encoded = bytes(model)
    check = FLVER.from_bytes(encoded)
    for mesh, reloaded in zip(model.meshes, check.meshes, strict=True):
        if not np.allclose(mesh.vertex_arrays[0].array["position"], reloaded.vertex_arrays[0].array["position"], atol=1e-6):
            raise ValueError("Converted mesh positions differ after reload")
        for faces, reloaded_faces in zip(mesh.face_sets, reloaded.face_sets, strict=True):
            if not np.array_equal(faces.vertex_indices, reloaded_faces.vertex_indices):
                raise ValueError("Converted faces differ after reload")
    entry.set_uncompressed_data(encoded)
    tpf_entry = next(e for e in binder.entries if e.path.endswith(".tpf"))
    tpf = TPF.from_bytes(tpf_entry.get_uncompressed_data())
    texture_root = WORKSPACE / "converted/mw2-2009/m9/dds"
    texture_bytes, texture_report = pack(tpf, texture_root, include_suppressor)
    tpf_entry.set_uncompressed_data(texture_bytes)
    target = output / "parts/WP_A_1401.partsbnd.dcx"
    if any(not is_within(p, output) for p in (target, output / "model-report.json")):
        raise ValueError("Model output contains an external symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes(binder))
    reloaded = Binder.from_path(target)
    if hashlib.sha256(next(e for e in reloaded.entries if e.path.endswith(".anibnd")).data).hexdigest() != animation_hash:
        raise ValueError("Native animation entry changed")
    report = {
        "source": proof, "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "authentic_asset_provenance_verified": True,
        "export_obj_relative_path": str(obj.resolve().relative_to((WORKSPACE / "converted").resolve())),
        "meshes": check.mesh_count, "vertices": sum(len(m.vertex_arrays[0].array) for m in check.meshes),
        "native_animation_sha256": animation_hash, "mw2_animation_retargeted": False,
        "texture_container": texture_report,
        "attachment": "original suppressor" if include_suppressor else "base M9; original suppressor surface omitted",
        "placement": "inch scale 0.0254, reflected X, measured MW2 pistol grip anchored to native root; owner grip/muzzle QA required",
        "native_dummy_retained": True, "muzzle_alignment_runtime_verified": False,
        "normal_mapping_verified": False, "runtime_verified": False, "activated": False,
    }
    (output / "model-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obj", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=WORKSPACE / "converted/dsr/m9-model-candidate")
    parser.add_argument("--include-suppressor", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.obj, args.provenance, args.output, args.include_suppressor), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
