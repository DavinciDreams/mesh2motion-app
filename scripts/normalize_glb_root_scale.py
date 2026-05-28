"""Bake a uniform root-node scale into node translations in a GLB.

This is useful for FBX-imported armature-only GLBs where the root object keeps
an FBX unit scale such as 0.01. Mesh2Motion's skeleton loading step replaces
the root scale with its UI scale, so rig files need the armature root at scale 1.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


GLB_HEADER = struct.Struct("<4sII")
CHUNK_HEADER = struct.Struct("<I4s")
FLOAT_COMPONENT = 5126
VEC3 = "VEC3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake root scale into GLB armature translations.")
    parser.add_argument("paths", nargs="+", help="GLB files to patch in place")
    parser.add_argument("--root", default=None, help="Optional root node name to patch")
    return parser.parse_args()


def read_glb(path: Path) -> tuple[dict, bytearray]:
    data = path.read_bytes()
    magic, version, _length = GLB_HEADER.unpack_from(data, 0)
    if magic != b"glTF" or version != 2:
      raise ValueError(f"{path} is not a GLB v2 file")

    json_chunk: dict | None = None
    bin_chunk = bytearray()
    offset = GLB_HEADER.size
    while offset < len(data):
        chunk_length, chunk_type = CHUNK_HEADER.unpack_from(data, offset)
        offset += CHUNK_HEADER.size
        chunk = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_type == b"JSON":
            json_chunk = json.loads(chunk.decode("utf-8"))
        elif chunk_type == b"BIN\0":
            bin_chunk = bytearray(chunk)

    if json_chunk is None:
        raise ValueError(f"{path} has no JSON chunk")
    return json_chunk, bin_chunk


def write_glb(path: Path, gltf: dict, bin_chunk: bytearray) -> None:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_padding = (-len(json_bytes)) % 4
    json_bytes += b" " * json_padding

    bin_padding = (-len(bin_chunk)) % 4
    bin_bytes = bytes(bin_chunk) + (b"\0" * bin_padding)

    chunks = [
        CHUNK_HEADER.pack(len(json_bytes), b"JSON") + json_bytes,
    ]
    if bin_bytes:
        chunks.append(CHUNK_HEADER.pack(len(bin_bytes), b"BIN\0") + bin_bytes)

    total_length = GLB_HEADER.size + sum(len(chunk) for chunk in chunks)
    path.write_bytes(GLB_HEADER.pack(b"glTF", 2, total_length) + b"".join(chunks))


def accessor_byte_offset(gltf: dict, accessor_index: int) -> int:
    accessor = gltf["accessors"][accessor_index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    return int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))


def scale_vec3_accessor(gltf: dict, bin_chunk: bytearray, accessor_index: int, scale: float) -> None:
    accessor = gltf["accessors"][accessor_index]
    if accessor.get("componentType") != FLOAT_COMPONENT or accessor.get("type") != VEC3:
        return
    if "sparse" in accessor:
        raise ValueError("Sparse VEC3 accessors are not supported by this patcher")

    view = gltf["bufferViews"][accessor["bufferView"]]
    stride = int(view.get("byteStride", 12))
    offset = accessor_byte_offset(gltf, accessor_index)
    count = int(accessor["count"])
    for index in range(count):
        item_offset = offset + index * stride
        x, y, z = struct.unpack_from("<fff", bin_chunk, item_offset)
        struct.pack_into("<fff", bin_chunk, item_offset, x * scale, y * scale, z * scale)

    if "min" in accessor:
        accessor["min"] = [value * scale for value in accessor["min"]]
    if "max" in accessor:
        accessor["max"] = [value * scale for value in accessor["max"]]


def bake_node_translations(gltf: dict, node_index: int, scale: float) -> None:
    node = gltf["nodes"][node_index]
    if "translation" in node:
        node["translation"] = [value * scale for value in node["translation"]]
    for child_index in node.get("children", []):
        bake_node_translations(gltf, child_index, scale)


def patch_path(path: Path, root_name: str | None) -> None:
    gltf, bin_chunk = read_glb(path)
    scene_index = int(gltf.get("scene", 0))
    scene_roots = gltf.get("scenes", [{}])[scene_index].get("nodes", [])
    if not scene_roots:
        return

    root_index = scene_roots[0]
    if root_name is not None:
        matches = [idx for idx, node in enumerate(gltf["nodes"]) if node.get("name") == root_name]
        if not matches:
            raise ValueError(f"{path}: root node {root_name!r} not found")
        root_index = matches[0]

    root = gltf["nodes"][root_index]
    scale_values = root.get("scale")
    if not scale_values:
        print(f"{path}: no root scale to bake")
        return
    if max(scale_values) - min(scale_values) > 1e-6:
        raise ValueError(f"{path}: non-uniform root scale is not supported: {scale_values}")

    scale = float(scale_values[0])
    if abs(scale - 1.0) < 1e-6:
        print(f"{path}: root scale already normalized")
        return

    for child_index in root.get("children", []):
        bake_node_translations(gltf, child_index, scale)

    for animation in gltf.get("animations", []):
        for channel in animation.get("channels", []):
            if channel.get("target", {}).get("path") != "translation":
                continue
            sampler = animation["samplers"][channel["sampler"]]
            scale_vec3_accessor(gltf, bin_chunk, sampler["output"], scale)

    root["scale"] = [1, 1, 1]
    write_glb(path, gltf, bin_chunk)
    print(f"{path}: baked root scale {scale:g}")


def main() -> int:
    args = parse_args()
    for raw_path in args.paths:
        patch_path(Path(raw_path), args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
