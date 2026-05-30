"""Compare two skeletons side-by-side to help plan a bone-rename mapping.

Usage:
  blender --background --python scripts/blender/compare_skeleton_to_canonical.py -- \
      --source path/to/new-rig.glb --canonical path/to/rig-husky.glb
"""
import argparse
import sys
from pathlib import Path

import bpy


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--canonical", required=True)
    return p.parse_args(argv)


def load_armature(path: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def bone_summary(arm):
    """Return a list of (depth, name, head_world, tail_world) for each bone."""
    out = []
    name_to_depth = {}
    for b in arm.data.bones:
        depth = 0
        cur = b.parent
        while cur is not None:
            depth += 1
            cur = cur.parent
        name_to_depth[b.name] = depth
    for b in arm.data.bones:
        # rest-pose world position
        head = arm.matrix_world @ b.head_local
        tail = arm.matrix_world @ b.tail_local
        out.append((name_to_depth[b.name], b.name, head, tail))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def main():
    args = parse_args()
    print("\n=== CANONICAL ===")
    arm = load_armature(Path(args.canonical))
    if arm is None:
        print("no canonical armature")
        return 1
    can = bone_summary(arm)
    for depth, name, head, _ in can:
        print(f"  {'  '*depth}{name:<32}  head=({head.x:+.2f},{head.y:+.2f},{head.z:+.2f})")
    print(f"  TOTAL: {len(can)} bones\n")

    print("=== SOURCE ===")
    arm = load_armature(Path(args.source))
    if arm is None:
        print("no source armature")
        return 1
    src = bone_summary(arm)
    for depth, name, head, _ in src:
        print(f"  {'  '*depth}{name:<48}  head=({head.x:+.2f},{head.y:+.2f},{head.z:+.2f})")
    print(f"  TOTAL: {len(src)} bones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
