"""
Split a Quaternius-style animal .gltf into three .glb files:
  - static/rigs/rig-<slug>.glb         (armature only, no mesh, no animations)
  - static/models/model-<slug>.glb     (mesh only, no animations)
  - static/animations/<slug>-animations.glb  (armature + animations, no mesh)

Run headlessly via Blender:
  blender --background --python scripts/split_animal_asset.py -- \
      --input "<absolute path to .gltf>" --slug wolf

The trailing "--" separates Blender's args from this script's args.
"""

import argparse
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    # Blender forwards everything after "--" to the script.
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Split an animal .gltf into rig/model/animation .glb files.")
    parser.add_argument("--input", required=True, help="Absolute path to source .gltf file")
    parser.add_argument("--slug", required=True, help="Lowercase animal slug, e.g. 'wolf' or 'horse_white'")
    parser.add_argument("--project-root", default=None, help="Project root (defaults to script's parent.parent)")
    parser.add_argument("--preserve-axis", action="store_true", help="Do not force glTF Y-up conversion on export")
    parser.add_argument("--skip-animations", action="store_true", help="Only export rig and model")
    return parser.parse_args(argv)


def reset_scene() -> None:
    """Wipe the default scene so each animal starts from an empty Blender."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_gltf(path: Path) -> None:
    bpy.ops.import_scene.gltf(filepath=str(path))


def first_armature():
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def skinned_mesh_for(armature):
    """Return the largest mesh that is skinned to the given armature.

    Prefers meshes with an Armature modifier pointing at this armature, or
    parented to it. Falls back to the mesh with the most vertices to avoid
    picking up small helper meshes (icosphere markers, debug widgets) that
    sometimes ship with source .gltf files.
    """
    candidates = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        skinned = any(m.type == "ARMATURE" and m.object == armature for m in obj.modifiers)
        parented = obj.parent == armature
        candidates.append((skinned or parented, len(obj.data.vertices), obj))

    if not candidates:
        return None

    # Sort: bound-to-this-armature first, then by vertex count descending.
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return candidates[0][2]


def skinned_meshes_for(armature):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        skinned = any(m.type == "ARMATURE" and m.object == armature for m in obj.modifiers)
        parented = obj.parent == armature
        if skinned or parented:
            meshes.append(obj)
    return meshes


def select_only(obj) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def select_only_many(objs) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objs:
        obj.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def apply_object_transforms(objs) -> None:
    select_only_many(objs)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def ensure_actions_on_nla(armature) -> int:
    """Push every action in bpy.data.actions onto NLA tracks of the armature.

    Required because Blender's glTF exporter exports NLA strips when
    export_animations=True and export_nla_strips=True. Otherwise only the
    currently-active action is exported.
    Returns the number of actions added.
    """
    if armature.animation_data is None:
        armature.animation_data_create()

    # Remove pre-existing tracks so we don't double-add on repeat runs.
    for track in list(armature.animation_data.nla_tracks):
        armature.animation_data.nla_tracks.remove(track)

    added = 0
    for action in bpy.data.actions:
        track = armature.animation_data.nla_tracks.new()
        track.name = action.name
        track.strips.new(action.name, int(action.frame_range[0]), action)
        added += 1
    return added


def export_rig(out_path: Path, armature, export_yup: bool = True) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    select_only(armature)
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_texcoords=False,
        export_normals=False,
        export_tangents=False,
        export_materials="NONE",
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=export_yup,
        export_animations=False,
    )


def export_model(out_path: Path, meshes, armature, export_yup: bool = True) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Export both armature and mesh so skin data is preserved; animations excluded.
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
        export_animations=False,
    )


def export_animations(out_path: Path, armature, export_yup: bool = True) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    select_only(armature)
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_texcoords=False,
        export_normals=False,
        export_tangents=False,
        export_materials="NONE",
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=export_yup,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_nla_strips=True,
    )


def main() -> int:
    args = parse_args()

    project_root = (
        Path(args.project_root).resolve()
        if args.project_root is not None
        else Path(__file__).resolve().parent.parent
    )

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return 1

    slug = args.slug.lower()
    rig_out = project_root / "static" / "rigs" / f"rig-{slug}.glb"
    model_out = project_root / "static" / "models" / f"model-{slug}.glb"
    anims_out = project_root / "static" / "animations" / f"{slug}-animations.glb"

    print(f"\n[{slug}] Importing {input_path.name} ...")
    reset_scene()
    import_gltf(input_path)

    armature = first_armature()
    if armature is None:
        print(f"ERROR [{slug}]: no armature found in {input_path}", file=sys.stderr)
        return 2
    mesh = skinned_mesh_for(armature)
    meshes = skinned_meshes_for(armature)

    if mesh is None:
        print(f"ERROR [{slug}]: no mesh found in {input_path}", file=sys.stderr)
        return 3
    if len(meshes) == 0:
        meshes = [mesh]

    print(f"[{slug}] Armature: {armature.name!r} ({len(armature.data.bones)} bones)")
    print(f"[{slug}] Meshes:   {', '.join(f'{m.name} ({len(m.data.vertices)} verts)' for m in meshes)}")
    apply_object_transforms([armature, *meshes])

    action_count = ensure_actions_on_nla(armature)
    print(f"[{slug}] Pushed {action_count} action(s) onto NLA tracks for export")

    export_yup = not args.preserve_axis

    export_rig(rig_out, armature, export_yup=export_yup)
    print(f"[{slug}] Wrote rig:        {rig_out.relative_to(project_root)} ({rig_out.stat().st_size // 1024} KB)")

    export_model(model_out, meshes, armature, export_yup=export_yup)
    print(f"[{slug}] Wrote model:      {model_out.relative_to(project_root)} ({model_out.stat().st_size // 1024} KB)")

    if not args.skip_animations:
        export_animations(anims_out, armature, export_yup=export_yup)
        print(f"[{slug}] Wrote animations: {anims_out.relative_to(project_root)} ({anims_out.stat().st_size // 1024} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
