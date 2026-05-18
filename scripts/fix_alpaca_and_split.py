"""
One-off fix for Alpaca.gltf:
The Quaternius Alpaca source has broken right-side IK helper bones
(FF.R, FFB.R, IKFrontLeg.R, IKBackLeg.R) whose rest positions are not mirrors
of the .L counterparts. Other viewers tolerate this; three.js evaluates the
skeleton honestly and the mesh vertices weighted to these bones float.

This script:
  1. Imports Alpaca.gltf
  2. Enters edit mode on the armature and mirrors L-side IK bones to R-side
     (head/tail x flipped, y and z preserved from .L)
  3. Runs the same three-way split as split_animal_asset.py to produce:
     - static/rigs/rig-alpaca.glb
     - static/models/model-alpaca.glb
     - static/animations/alpaca-animations.glb

Run:
  blender --background --python scripts/fix_alpaca_and_split.py
"""

import sys
from pathlib import Path

import bpy

# Import the splitter module so we can reuse its export helpers.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from split_animal_asset import (  # noqa: E402
    reset_scene,
    import_gltf,
    first_armature,
    skinned_mesh_for,
    ensure_actions_on_nla,
    export_rig,
    export_model,
    export_animations,
)


SOURCE_GLTF = Path(r"C:\Users\lmwat\Downloads\glTF-extracted\glTF\Alpaca.gltf")
PROJECT_ROOT = SCRIPT_DIR.parent
SLUG = "alpaca"

# Bones whose .R rest positions are broken in the Quaternius source.
# Mirror from .L: x negated, y/z preserved.
MIRROR_BONES = ["FF", "FFB", "IKFrontLeg", "IKBackLeg"]


def mirror_right_from_left(armature) -> None:
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = armature.data.edit_bones
    for stem in MIRROR_BONES:
        left = edit_bones.get(f"{stem}.L")
        right = edit_bones.get(f"{stem}.R")
        if left is None or right is None:
            print(f"WARN: missing {stem}.L or {stem}.R, skipping")
            continue

        before_head = tuple(right.head)
        before_tail = tuple(right.tail)
        right.head = (-left.head.x, left.head.y, left.head.z)
        right.tail = (-left.tail.x, left.tail.y, left.tail.z)
        right.roll = -left.roll  # mirror twist
        print(
            f"  {stem}.R  head {tuple(round(c, 3) for c in before_head)} -> "
            f"{tuple(round(c, 3) for c in right.head)}"
        )
        print(
            f"  {stem}.R  tail {tuple(round(c, 3) for c in before_tail)} -> "
            f"{tuple(round(c, 3) for c in right.tail)}"
        )

    bpy.ops.object.mode_set(mode="OBJECT")


def main() -> int:
    if not SOURCE_GLTF.exists():
        print(f"ERROR: source not found: {SOURCE_GLTF}", file=sys.stderr)
        return 1

    reset_scene()
    import_gltf(SOURCE_GLTF)

    armature = first_armature()
    mesh = skinned_mesh_for(armature)
    if armature is None or mesh is None:
        print("ERROR: armature or mesh missing after import", file=sys.stderr)
        return 2

    print(f"[alpaca] Armature: {armature.name!r} ({len(armature.data.bones)} bones)")
    print(f"[alpaca] Mesh:     {mesh.name!r} ({len(mesh.data.vertices)} verts)")

    print("[alpaca] Mirroring broken .R IK helper bones from .L ...")
    mirror_right_from_left(armature)

    action_count = ensure_actions_on_nla(armature)
    print(f"[alpaca] Pushed {action_count} action(s) onto NLA tracks for export")

    rig_out = PROJECT_ROOT / "static" / "rigs" / f"rig-{SLUG}.glb"
    model_out = PROJECT_ROOT / "static" / "models" / f"model-{SLUG}.glb"
    anims_out = PROJECT_ROOT / "static" / "animations" / f"{SLUG}-animations.glb"

    export_rig(rig_out, armature)
    print(f"[alpaca] Wrote rig:        {rig_out.relative_to(PROJECT_ROOT)} ({rig_out.stat().st_size // 1024} KB)")

    export_model(model_out, mesh, armature)
    print(f"[alpaca] Wrote model:      {model_out.relative_to(PROJECT_ROOT)} ({model_out.stat().st_size // 1024} KB)")

    export_animations(anims_out, armature)
    print(f"[alpaca] Wrote animations: {anims_out.relative_to(PROJECT_ROOT)} ({anims_out.stat().st_size // 1024} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
