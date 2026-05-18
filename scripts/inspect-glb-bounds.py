from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_glb(path: Path) -> None:
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()


def object_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    clear_scene()
    import_glb(args.path)
    print(args.path)
    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "ARMATURE"}:
            continue
        if obj.type == "MESH":
            low, high = object_bounds(obj)
            size = high - low
            print(f"MESH {obj.name} loc={tuple(round(v, 4) for v in obj.location)} scale={tuple(round(v, 4) for v in obj.scale)} size={tuple(round(v, 4) for v in size)}")
        else:
            bones = list(obj.data.bones)
            points = [(obj.matrix_world @ bone.head_local) for bone in bones] + [(obj.matrix_world @ bone.tail_local) for bone in bones]
            low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
            high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
            size = high - low
            print(f"ARMATURE {obj.name} loc={tuple(round(v, 4) for v in obj.location)} scale={tuple(round(v, 4) for v in obj.scale)} bones={len(bones)} size={tuple(round(v, 4) for v in size)}")


if __name__ == "__main__":
    main()
