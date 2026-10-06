"""Verify local native M9 containers without a game, renderer or retail writes."""

from pathlib import Path
import json

from dsr_mw2.soulstruct_tools import WORKSPACE, configure
from dsr_mw2.model_candidate import read, PARTS
from dsr_mw2.status import package_status


def main():
    configure()
    import numpy as np
    from soulstruct.containers import Binder, TPF
    from soulstruct.flver import FLVER

    original = Binder.from_path(WORKSPACE / "profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered" / PARTS)
    models = []
    for folder_name in ("m9-model-candidate", "m9-suppressed-model-candidate"):
        report, data = read(WORKSPACE / "converted/dsr" / folder_name)
        binder = Binder.from_bytes(data)
        for before, after in zip(original.entries, binder.entries, strict=True):
            assert (before.entry_id, before.path, before.flags) == (after.entry_id, after.path, after.flags)
            if not before.path.endswith((".flver", ".tpf")):
                assert before.data == after.data, "Untouched native binder member changed"
        flver = FLVER.from_bytes(next(e for e in binder.entries if e.path.endswith(".flver")).get_uncompressed_data())
        tpf = TPF.from_bytes(next(e for e in binder.entries if e.path.endswith(".tpf")).get_uncompressed_data())
        stems = {texture.stem.lower() for texture in tpf.textures}
        triangles = 0
        for mesh in flver.meshes:
            vertices = mesh.vertex_arrays[0].array
            assert np.isfinite(vertices["position"]).all()
            assert np.isfinite(vertices["normal"]).all()
            assert np.isfinite(vertices["tangent_0"]).all()
            assert np.allclose(np.linalg.norm(vertices["normal"], axis=1), 1, atol=.02)
            assert np.allclose(vertices["bone_weights"].sum(axis=1), 1, atol=.02)
            for texture in mesh.material.textures:
                if texture.path:
                    stem = Path(texture.path.replace("\\", "/")).stem.lower()
                    assert stem in stems, f"Missing native texture binding: {stem}"
            faces = mesh.face_sets[0].vertex_indices
            assert faces.size and int(faces.max()) < len(vertices)
            triangles += len(faces)
        assert flver.mesh_count == (2 if folder_name.startswith("m9-suppressed") else 1)
        models.append({"name": folder_name, "binder_sha256": report["output_sha256"], "meshes": flver.mesh_count,
                       "vertices": report["vertices"], "triangles": triangles, "textures": len(tpf.textures),
                       "mip_levels": sum(texture.mipmap_count for texture in tpf.textures),
                       "native_texture_bindings_verified": True, "untouched_binder_members_verified": True})
    packages = []
    for name in ("m9-sidearm", "m9-low-damage", "m9-sidearm-suppressed", "m9-low-damage-suppressed"):
        check = package_status(WORKSPACE / "converted/packages" / name)
        assert check["files_hash_verified"] and check["config_disabled"] and check["authentic_model_candidate_included"]
        packages.append({"name": name, "files_hash_verified": True, "override_disabled": True})
    evidence = {"models": models, "packages": packages, "game_launched": False,
                "runtime_verified": False, "ready_to_play_crossover": False}
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
