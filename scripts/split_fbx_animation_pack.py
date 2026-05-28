"""
Split an FBX mesh plus matching FBX animation clips into Mesh2Motion assets.

Run headlessly via Blender:
  blender --background --python scripts/split_fbx_animation_pack.py -- \
      --mesh "C:/path/Mesh/SK_GermanShepherd_01.fbx" \
      --animations-dir "C:/path/Animations" \
      --slug german-shepherd \
      --project-root "C:/repo/mesh2motion-app"
"""

import argparse
import re
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Split an FBX animation pack into GLB rig/model/animation files.")
    parser.add_argument("--mesh", required=True, help="Base skinned mesh FBX")
    parser.add_argument("--animations-dir", required=True, help="Directory containing animation FBX files")
    parser.add_argument("--slug", required=True, help="Output slug, e.g. german-shepherd")
    parser.add_argument("--project-root", default=None, help="Project root; defaults to script parent.parent")
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_fbx(path: Path) -> None:
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True)


def first_armature():
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def skinned_meshes_for(armature):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        skinned = any(m.type == "ARMATURE" and m.object == armature for m in obj.modifiers)
        parented = obj.parent == armature
        if skinned or parented:
            meshes.append(obj)
    if meshes:
        return meshes
    return [obj for obj in bpy.data.objects if obj.type == "MESH"]


def select_only_many(objs) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def apply_object_transforms(objs) -> None:
    select_only_many(objs)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def clean_clip_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"^1 type[_ ]*", "", name)
    name = re.sub(r"_?v\d+(?: test)?$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return name or path.stem


def rename_current_action(armature, name: str):
    if armature.animation_data is None or armature.animation_data.action is None:
        return None
    action = armature.animation_data.action
    action.name = name
    return action


def add_action_to_nla(armature, action) -> None:
    if action is None:
        return
    if armature.animation_data is None:
        armature.animation_data_create()
    track = armature.animation_data.nla_tracks.new()
    track.name = action.name
    track.strips.new(action.name, int(action.frame_range[0]), action)


def export_glb(
    path: Path,
    objects,
    export_animations: bool,
    export_materials: str = "EXPORT",
    export_apply: bool = True,
    export_yup: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    select_only_many(objects)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_cameras=False,
        export_lights=False,
        export_apply=export_apply,
        export_yup=export_yup,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials=export_materials,
        export_animations=export_animations,
        export_animation_mode="ACTIONS" if export_animations else "ACTIVE_ACTIONS",
        export_nla_strips=export_animations,
    )


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve() if args.project_root else Path(__file__).resolve().parent.parent
    mesh_path = Path(args.mesh).resolve()
    animations_dir = Path(args.animations_dir).resolve()
    slug = args.slug.lower()

    if not mesh_path.exists():
        print(f"ERROR: mesh not found: {mesh_path}", file=sys.stderr)
        return 1
    if not animations_dir.exists():
        print(f"ERROR: animations dir not found: {animations_dir}", file=sys.stderr)
        return 1

    reset_scene()
    print(f"[{slug}] Importing base mesh: {mesh_path}")
    import_fbx(mesh_path)
    armature = first_armature()
    if armature is None:
        print("ERROR: no armature found in base mesh", file=sys.stderr)
        return 2
    meshes = skinned_meshes_for(armature)
    print(f"[{slug}] Armature: {armature.name} ({len(armature.data.bones)} bones)")
    print(f"[{slug}] Meshes: {', '.join(mesh.name for mesh in meshes)}")
    apply_object_transforms([armature, *meshes])

    rig_out = project_root / "static" / "rigs" / f"rig-{slug}.glb"
    model_out = project_root / "static" / "models" / f"model-{slug}.glb"
    anims_out = project_root / "static" / "animations" / f"{slug}-animations.glb"

    export_glb(rig_out, [armature], export_animations=False, export_materials="NONE", export_apply=True)
    print(f"[{slug}] Wrote rig: {rig_out.relative_to(project_root)}")

    export_glb(model_out, [armature, *meshes], export_animations=False, export_materials="EXPORT", export_apply=True)
    print(f"[{slug}] Wrote model: {model_out.relative_to(project_root)}")

    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = None
    for track in list(armature.animation_data.nla_tracks):
        armature.animation_data.nla_tracks.remove(track)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)

    animation_files = sorted(animations_dir.glob("*.fbx"))
    if not animation_files:
        print("ERROR: no animation FBX files found", file=sys.stderr)
        return 3

    imported_actions = []
    base_bone_names = {bone.name for bone in armature.data.bones}
    for anim_path in animation_files:
        before_objects = set(bpy.data.objects)
        before_actions = set(bpy.data.actions)
        import_fbx(anim_path)
        imported_armatures = [obj for obj in set(bpy.data.objects) - before_objects if obj.type == "ARMATURE"]
        source_armature = imported_armatures[0] if imported_armatures else first_armature()
        source_action = None
        if source_armature is not None and source_armature.animation_data is not None:
            source_action = source_armature.animation_data.action
        if source_action is None:
            new_actions = [action for action in bpy.data.actions if action not in before_actions]
            source_action = new_actions[0] if new_actions else None
        if source_action is None:
            print(f"[{slug}] Skipping animation with no action: {anim_path.name}")
        else:
            source_names = {bone.name for bone in source_armature.data.bones} if source_armature is not None else set()
            if source_names and base_bone_names != source_names:
                print(f"[{slug}] Warning: bone names differ for {anim_path.name}")
            action = source_action.copy()
            action.name = clean_clip_name(anim_path)
            imported_actions.append(action)
            add_action_to_nla(armature, action)
            print(f"[{slug}] Added action: {action.name}")

        for obj in list(set(bpy.data.objects) - before_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for action in list(bpy.data.actions):
            if action not in imported_actions:
                bpy.data.actions.remove(action)

    export_glb(anims_out, [armature], export_animations=True, export_materials="NONE", export_apply=True)
    print(f"[{slug}] Wrote animations: {anims_out.relative_to(project_root)} ({len(imported_actions)} actions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
