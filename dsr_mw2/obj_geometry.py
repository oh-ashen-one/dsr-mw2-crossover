"""Read the narrow triangle OBJ dialect emitted by OpenAssetTools, without file imports."""

from __future__ import annotations

import math


def parse(text: str) -> dict:
    positions, uvs, normals = [], [], []
    groups: dict[str, list] = {}
    material = ""
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        kind = fields[0]
        if kind in ("v", "vt", "vn"):
            count = 2 if kind == "vt" else 3
            if len(fields) != count + 1:
                raise ValueError("Unexpected OBJ vector dimensions")
            values = tuple(float(x) for x in fields[1:])
            if not all(math.isfinite(x) for x in values):
                raise ValueError("Nonfinite OBJ coordinates")
            {"v": positions, "vt": uvs, "vn": normals}[kind].append(values)
        elif kind == "usemtl":
            if len(fields) != 2:
                raise ValueError("Invalid OBJ material")
            material = fields[1]
        elif kind == "f":
            if len(fields) != 4 or not material:
                raise ValueError("Expected material-assigned OBJ triangles")
            face = []
            for token in fields[1:]:
                parts = token.split("/")
                if len(parts) != 3 or any(not x for x in parts):
                    raise ValueError("Expected complete position/UV/normal indices")
                indices = tuple(int(x) - 1 for x in parts)
                if any(not 0 <= i < len(values) for i, values in zip(indices, (positions, uvs, normals), strict=True)):
                    raise ValueError("OBJ index outside its data")
                face.append(indices)
            groups.setdefault(material, []).append(tuple(face))
        elif kind not in ("o", "g", "mtllib", "s"):
            raise ValueError(f"Unsupported OBJ statement: {kind}")
        # mtllib is recorded by the exporter but is never opened/executed here.
    if not positions or not groups or sum(len(faces) for faces in groups.values()) > 100000:
        raise ValueError("Empty or oversized OBJ geometry")
    return {"positions": positions, "uvs": uvs, "normals": normals, "groups": groups}
