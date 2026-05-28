"""
Apply the first frame of a named animation clip from one GLB to matching nodes
in a rig GLB.

This keeps a display-friendly rig export while borrowing a source-authored pose
such as HorseALL_TPOSE.
"""

import argparse
import json
import struct
from pathlib import Path


COMPONENT_FORMAT = {
    5126: ("f", 4),
}

TYPE_COUNTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT4": 16,
}


def parse_glb(path: Path):
    data = path.read_bytes()
    magic, version, _ = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2:
        raise ValueError(f"Not a GLB v2 file: {path}")

    offset = 12
    json_chunk = None
    bin_chunk = b""
    chunks = []
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_data = data[offset:offset + chunk_length]
        offset += chunk_length
        chunks.append((chunk_type, chunk_data))
        if chunk_type == 0x4E4F534A:
            json_chunk = chunk_data
        elif chunk_type == 0x004E4942:
            bin_chunk = chunk_data

    if json_chunk is None:
        raise ValueError(f"Missing JSON chunk: {path}")
    gltf = json.loads(json_chunk.decode("utf-8").rstrip(" \t\r\n\0"))
    return gltf, bin_chunk


def read_accessor_first(gltf, bin_chunk: bytes, accessor_index: int):
    accessor = gltf["accessors"][accessor_index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    component_format, component_size = COMPONENT_FORMAT[accessor["componentType"]]
    count = TYPE_COUNTS[accessor["type"]]
    byte_offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", count * component_size)
    del stride  # first element starts at byte_offset regardless of stride
    fmt = "<" + component_format * count
    return list(struct.unpack_from(fmt, bin_chunk, byte_offset))


def write_glb(path: Path, gltf, bin_chunk: bytes):
    json_bytes = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_bytes = bin_chunk + b"\0" * ((4 - len(bin_chunk) % 4) % 4)

    body = (
        struct.pack("<II", len(json_bytes), 0x4E4F534A)
        + json_bytes
        + struct.pack("<II", len(bin_bytes), 0x004E4942)
        + bin_bytes
    )
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--rig", required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--root-rotation", default=None, help="Comma-separated quaternion for rig scene root")
    args = parser.parse_args()

    source_gltf, source_bin = parse_glb(Path(args.source))
    rig_gltf, rig_bin = parse_glb(Path(args.rig))

    clip = next((anim for anim in source_gltf.get("animations", []) if anim.get("name") == args.clip), None)
    if clip is None:
        raise ValueError(f"Clip not found: {args.clip}")

    rig_nodes_by_name = {
        node.get("name"): node
        for node in rig_gltf.get("nodes", [])
        if node.get("name") is not None
    }

    applied = 0
    for channel in clip["channels"]:
        source_node = source_gltf["nodes"][channel["target"]["node"]]
        target_node = rig_nodes_by_name.get(source_node.get("name"))
        if target_node is None:
            continue
        target_path = channel["target"]["path"]
        value = read_accessor_first(source_gltf, source_bin, clip["samplers"][channel["sampler"]]["output"])
        if target_path == "translation":
            target_node["translation"] = value
        elif target_path == "rotation":
            target_node["rotation"] = value
        elif target_path == "scale":
            target_node["scale"] = value
        else:
            continue
        applied += 1

    if args.root_rotation is not None:
        root_index = rig_gltf["scenes"][0]["nodes"][0]
        rig_gltf["nodes"][root_index]["rotation"] = [float(v) for v in args.root_rotation.split(",")]

    write_glb(Path(args.output), rig_gltf, rig_bin)
    print(f"Applied {applied} channel transforms from {args.clip} to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
