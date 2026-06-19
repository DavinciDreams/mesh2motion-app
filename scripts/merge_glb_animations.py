"""
Merge same-rig animal GLB animation clips into one animated GLB.

Typical use:
  blender --background --python scripts/merge_glb_animations.py -- \
      --input-dir "C:/Users/lmwat/Downloads/rigged animals" \
      --all

Or one animal:
  blender --background --python scripts/merge_glb_animations.py -- \
      --input-dir "C:/Users/lmwat/Downloads/rigged animals" \
      --animal crocodile

The script expects files named like crocodile-idle.glb and crocodile-walk.glb.
It keeps one base mesh/armature, copies animation actions from matching GLBs,
adds those actions as NLA tracks on the base armature, and exports one GLB.
"""

import argparse
import re
import sys
from pathlib import Path

import bpy


KNOWN_CLIPS = [
    "idle",
    "walk",
    "trot",
    "canter",
    "gallop",
    "hop",
    "head-turn",
    "run",
    "jump",
    "attack",
    "death",
]

DUPLICATE_SUFFIX_RE = re.compile(r"\s+\(\d+\)$")


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Merge same-rig GLB animation clips into combined GLBs.")
    parser.add_argument("--input-dir", required=True, help="Directory containing animal-action.glb files")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to <input-dir>/merged")
    parser.add_argument("--animal", default=None, help="Merge one animal slug, e.g. crocodile")
    parser.add_argument("--all", action="store_true", help="Merge every detected animal group with 2+ clips")
    parser.add_argument("--base-clip", default="idle", help="Preferred base mesh clip; defaults to idle")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing merged GLBs")
    parser.add_argument("--preserve-axis", action="store_true", help="Do not force glTF Y-up conversion on export")
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_gltf(path: Path) -> set[str]:
    before = {obj.name for obj in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=str(path))
    after = {obj.name for obj in bpy.data.objects}
    return after - before


def first_armature(objects=None):
    search = objects if objects is not None else bpy.data.objects
    for obj in search:
        if obj.type == "ARMATURE":
            return obj
    return None


def skinned_meshes_for(armature):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        skinned = any(mod.type == "ARMATURE" and mod.object == armature for mod in obj.modifiers)
        parented = obj.parent == armature
        if skinned or parented:
            meshes.append(obj)
    return meshes or [obj for obj in bpy.data.objects if obj.type == "MESH"]


def select_only_many(objs) -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def clean_clip_name(name: str) -> str:
    return DUPLICATE_SUFFIX_RE.sub("", name)


def detect_clip(path: Path):
    stem = clean_clip_name(path.stem)
    for clip in sorted(KNOWN_CLIPS, key=len, reverse=True):
        suffix = f"-{clip}"
        if stem.endswith(suffix):
            animal = stem[: -len(suffix)]
            if animal:
                return animal, clip
    return None


def discover_groups(input_dir: Path) -> dict[str, dict[str, Path]]:
    groups: dict[str, dict[str, Path]] = {}
    for path in sorted(input_dir.glob("*.glb")):
        parsed = detect_clip(path)
        if parsed is None:
            continue
        animal, clip = parsed
        groups.setdefault(animal, {})
        # Prefer the original download over duplicate " (1)" files.
        if clip not in groups[animal] or " (" not in path.stem:
            groups[animal][clip] = path
    return groups


def action_for_armature(armature):
    if armature.animation_data is None:
        return None
    if armature.animation_data.action is not None:
        return armature.animation_data.action
    for track in armature.animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action is not None:
                return strip.action
    return None


def base_bone_names(armature) -> set[str]:
    return {bone.name for bone in armature.data.bones}


def remove_objects(objects) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.ops.object.delete()


def prune_unused_data() -> None:
    for collection in [
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.textures,
    ]:
        for item in list(collection):
            if item.users == 0:
                collection.remove(item)


def remove_unmerged_actions(keep_actions: set[bpy.types.Action]) -> None:
    for action in list(bpy.data.actions):
        if action not in keep_actions:
            bpy.data.actions.remove(action)


def add_action_to_nla(armature, action) -> None:
    if armature.animation_data is None:
        armature.animation_data_create()
    track = armature.animation_data.nla_tracks.new()
    track.name = action.name
    start = int(action.frame_range[0])
    track.strips.new(action.name, start, action)


def export_combined(out_path: Path, armature, meshes, export_yup: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    select_only_many([armature, *meshes])
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_apply=False,
        export_yup=export_yup,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_nla_strips=True,
    )


def merge_group(animal: str, clips: dict[str, Path], out_dir: Path, base_clip: str, overwrite: bool, export_yup: bool):
    base_name = base_clip if base_clip in clips else sorted(clips)[0]
    out_path = out_dir / f"{animal}-combined.glb"
    if out_path.exists() and not overwrite:
        print(f"SKIP {animal}: output exists ({out_path})")
        return {"animal": animal, "status": "skipped", "clips": len(clips), "output": out_path}

    reset_scene()
    import_gltf(clips[base_name])
    base_armature = first_armature()
    if base_armature is None:
        raise RuntimeError(f"{animal}: no armature found in base file {clips[base_name]}")

    base_meshes = skinned_meshes_for(base_armature)
    if not base_meshes:
        raise RuntimeError(f"{animal}: no mesh found in base file {clips[base_name]}")

    if base_armature.animation_data is not None:
        for track in list(base_armature.animation_data.nla_tracks):
            base_armature.animation_data.nla_tracks.remove(track)

    base_bones = base_bone_names(base_armature)
    merged_actions = []
    warnings = []

    for clip_name in sorted(clips, key=lambda name: (name != base_name, KNOWN_CLIPS.index(name) if name in KNOWN_CLIPS else 99, name)):
        source_path = clips[clip_name]
        before_actions = set(bpy.data.actions)

        if clip_name == base_name:
            source_armature = base_armature
            source_action = action_for_armature(source_armature)
            if source_action is None:
                warnings.append(f"{clip_name}: no animation action")
                continue
            merged_action = source_action.copy()
        else:
            imported_names = import_gltf(source_path)
            imported_objects = [bpy.data.objects[name] for name in imported_names if name in bpy.data.objects]
            source_armature = first_armature(imported_objects)
            if source_armature is None:
                warnings.append(f"{clip_name}: no armature")
                remove_objects(imported_objects)
                continue

            source_bones = base_bone_names(source_armature)
            missing = sorted(source_bones.symmetric_difference(base_bones))
            if missing:
                warnings.append(f"{clip_name}: bone mismatch ({len(missing)} differing names)")

            source_action = action_for_armature(source_armature)
            if source_action is None:
                warnings.append(f"{clip_name}: no animation action")
                remove_objects(imported_objects)
                continue

            merged_action = source_action.copy()
            remove_objects(imported_objects)

        merged_action.name = clip_name
        merged_action.use_fake_user = True
        merged_actions.append(merged_action)

        imported_actions = set(bpy.data.actions) - before_actions
        for action in imported_actions:
            if action != merged_action and action.users == 0:
                bpy.data.actions.remove(action)

    if not merged_actions:
        raise RuntimeError(f"{animal}: no animation actions were merged")

    if base_armature.animation_data is None:
        base_armature.animation_data_create()
    base_armature.animation_data.action = None
    for track in list(base_armature.animation_data.nla_tracks):
        base_armature.animation_data.nla_tracks.remove(track)

    keep = set(merged_actions)
    remove_unmerged_actions(keep)
    for action in merged_actions:
        add_action_to_nla(base_armature, action)

    prune_unused_data()
    export_combined(out_path, base_armature, base_meshes, export_yup)
    size = out_path.stat().st_size if out_path.exists() else 0
    print(f"MERGED {animal}: {len(merged_actions)} clips -> {out_path} ({size} bytes)")
    for warning in warnings:
        print(f"WARNING {animal}: {warning}")
    return {"animal": animal, "status": "merged", "clips": len(merged_actions), "output": out_path, "warnings": warnings}


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else input_dir / "merged"

    if not input_dir.exists():
        print(f"Input directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    groups = discover_groups(input_dir)
    if args.animal:
        if args.animal not in groups:
            print(f"No detected clips for animal: {args.animal}", file=sys.stderr)
            return 2
        selected = {args.animal: groups[args.animal]}
    elif args.all:
        selected = {animal: clips for animal, clips in groups.items() if len(clips) >= 2}
    else:
        print("Pass --animal <slug> or --all.", file=sys.stderr)
        return 2

    if not selected:
        print("No mergeable groups found.", file=sys.stderr)
        return 2

    failures = 0
    for animal, clips in sorted(selected.items()):
        try:
            merge_group(
                animal,
                clips,
                output_dir,
                args.base_clip,
                args.overwrite,
                export_yup=not args.preserve_axis,
            )
        except Exception as exc:
            failures += 1
            print(f"FAILED {animal}: {exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
