"""Dump bone hierarchy + action list from one or more GLB files.

Usage:
  blender --background --python scripts/blender/inspect_skeleton.py -- \
      file1.glb file2.glb ...
"""
import sys
from pathlib import Path

import bpy


def parse_args():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1:]
    return []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def first_armature():
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def print_bone_tree(bone, indent=0):
    print("  " * indent + bone.name)
    for child in bone.children:
        print_bone_tree(child, indent + 1)


def inspect(path: Path):
    print("\n" + "=" * 72)
    print(f"FILE: {path}")
    print("=" * 72)
    reset()
    try:
        bpy.ops.import_scene.gltf(filepath=str(path))
    except Exception as exc:
        print(f"  IMPORT FAILED: {exc}")
        return

    arm = first_armature()
    if arm is None:
        print("  NO ARMATURE")
        return

    print(f"  Armature object: {arm.name!r}")
    print(f"  Armature scale: {tuple(round(v, 4) for v in arm.scale)}")
    print(f"  Bone count: {len(arm.data.bones)}")
    print("  Bone hierarchy:")
    roots = [b for b in arm.data.bones if b.parent is None]
    for r in roots:
        print_bone_tree(r, indent=2)

    actions = list(bpy.data.actions)
    print(f"  Actions ({len(actions)}):")
    for a in actions:
        fr = a.frame_range
        print(f"    - {a.name!r}  frames {int(fr[0])}..{int(fr[1])}")

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    print(f"  Meshes ({len(meshes)}):")
    for m in meshes:
        print(f"    - {m.name!r}  verts={len(m.data.vertices)}")


def main():
    files = parse_args()
    if not files:
        print("ERROR: pass at least one .glb path after --", file=sys.stderr)
        return 1
    for f in files:
        inspect(Path(f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
