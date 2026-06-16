"""
Split an FBX mesh plus matching FBX animation clips into Mesh2Motion assets.

Run headlessly via Blender:
  blender --background --python scripts/split_fbx_animation_pack.py -- \
      --mesh "C:/path/Mesh/SK_Animal_01.fbx" \
      --animations-dir "C:/path/Animations" \
      --slug animal \
      --project-root "C:/repo/mesh2motion-app"
"""

import argparse
import re
import sys
from pathlib import Path

import bmesh
import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Split an FBX or Blend animation pack into GLB rig/model/animation files.")
    parser.add_argument("--mesh", required=True, help="Base skinned mesh FBX or Blend file")
    parser.add_argument("--animations-dir", help="Directory containing animation FBX files")
    parser.add_argument("--embedded-actions", action="store_true", help="Use all actions embedded in --mesh")
    parser.add_argument("--skip-transform-apply", action="store_true", help="Preserve imported FBX object transforms")
    parser.add_argument(
        "--exclude-actions",
        default="",
        help="Comma-separated action names to skip after cleaning, e.g. Rat_Attack,Wasp_Death",
    )
    parser.add_argument("--slug", required=True, help="Output slug, e.g. animal")
    parser.add_argument("--project-root", default=None, help="Project root; defaults to script parent.parent")
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_fbx(path: Path) -> None:
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True)


def load_source(path: Path) -> None:
    if path.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
        return
    reset_scene()
    import_fbx(path)


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
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in bpy.data.objects:
        obj.select_set(False)
    for obj in objs:
        obj.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def apply_object_transforms(objs) -> None:
    select_only_many(objs)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def make_materials_opaque() -> None:
    for material in bpy.data.materials:
        material.blend_method = "OPAQUE"
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
        if bsdf is not None and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = 1.0
        material.diffuse_color[3] = 1.0


def move_vertex_group_weights(mesh, source_name: str, target_name: str) -> None:
    source_group = mesh.vertex_groups.get(source_name)
    target_group = mesh.vertex_groups.get(target_name)
    if source_group is None or target_group is None:
        return

    source_index = source_group.index
    target_weights = []
    cleared_vertices = []
    for vertex in mesh.data.vertices:
        for group in vertex.groups:
            if group.group == source_index and group.weight > 0:
                target_weights.append((vertex.index, group.weight))
                cleared_vertices.append(vertex.index)
                break

    if not target_weights:
        return

    for vertex_index, weight in target_weights:
        target_group.add([vertex_index], weight, "ADD")
    source_group.remove(cleared_vertices)


def delete_vertices_for_group(mesh, group_name: str) -> None:
    vertex_group = mesh.vertex_groups.get(group_name)
    if vertex_group is None:
        return

    group_index = vertex_group.index
    vertex_indices = {
        vertex.index
        for vertex in mesh.data.vertices
        for group in vertex.groups
        if group.group == group_index and group.weight > 0
    }
    if not vertex_indices:
        return

    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(
        bm,
        geom=[bm.verts[index] for index in vertex_indices if index < len(bm.verts)],
        context="VERTS",
    )
    bm.to_mesh(mesh.data)
    bm.free()
    mesh.data.update()
    mesh.vertex_groups.remove(vertex_group)


def fix_rat_ik_target_weights(meshes, armature) -> None:
    """Rat paw meshes are weighted to IK target bones; move those weights to lower legs."""
    remaps = {
        "FrontFoot.R": "FrontLowLeg.R",
        "BackFoot.R": "BackLowLeg.R",
        "FrontFoot.L": "FrontLowLeg.L",
        "BackFoot.L": "BackLowLeg.L",
    }

    for mesh in meshes:
        for source_name, target_name in remaps.items():
            move_vertex_group_weights(mesh, source_name, target_name)

    for source_name in remaps:
        bone = armature.data.bones.get(source_name)
        if bone is not None:
            bone.use_deform = False


def remove_rat_ik_target_bones(meshes, armature) -> None:
    target_bones = ["FrontFoot.R", "BackFoot.R", "FrontFoot.L", "BackFoot.L"]

    for mesh in meshes:
        for bone_name in target_bones:
            vertex_group = mesh.vertex_groups.get(bone_name)
            if vertex_group is not None:
                mesh.vertex_groups.remove(vertex_group)

    select_only_many([armature])
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name in target_bones:
        edit_bone = armature.data.edit_bones.get(bone_name)
        if edit_bone is not None:
            armature.data.edit_bones.remove(edit_bone)
    bpy.ops.object.mode_set(mode="OBJECT")


def fix_wasp_stinger_weights(meshes, armature) -> None:
    """Remove the stinger tip; its source bone does not play well after export."""
    for mesh in meshes:
        delete_vertices_for_group(mesh, "Sting")

    select_only_many([armature])
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bone = armature.data.edit_bones.get("Sting")
    if edit_bone is not None:
        armature.data.edit_bones.remove(edit_bone)
    bpy.ops.object.mode_set(mode="OBJECT")


def clean_clip_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"^1 type[_ ]*", "", name)
    name = re.sub(r"_?v\d+(?: test)?$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return name or path.stem


def clean_action_name(name: str) -> str:
    name = name.split("|")[-1]
    name = re.sub(r"[._]\d{3}$", "", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return name or "Action"


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


def bake_visual_actions(armature):
    """Bake constraint-driven pose results into ordinary keyed actions."""
    original_actions = list(bpy.data.actions)
    baked_actions = []
    select_only_many([armature])

    for action in original_actions:
        if armature.animation_data is None:
            armature.animation_data_create()
        armature.animation_data.action = action

        start, end = [int(value) for value in action.frame_range]
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.nla.bake(
            frame_start=start,
            frame_end=end,
            step=1,
            only_selected=False,
            visual_keying=True,
            clear_constraints=False,
            clear_parents=False,
            use_current_action=False,
            bake_types={"POSE"},
        )
        bpy.ops.object.mode_set(mode="OBJECT")

        baked_action = armature.animation_data.action
        baked_action.name = action.name
        baked_actions.append(baked_action)

    for action in original_actions:
        if action.users == 0 or action not in baked_actions:
            bpy.data.actions.remove(action)

    armature.animation_data.action = None
    return baked_actions


def clear_pose_constraints(armature) -> None:
    for pose_bone in armature.pose.bones:
        for constraint in list(pose_bone.constraints):
            pose_bone.constraints.remove(constraint)


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
        export_force_sampling=export_animations,
        export_frame_step=1,
    )


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve() if args.project_root else Path(__file__).resolve().parent.parent
    mesh_path = Path(args.mesh).resolve()
    animations_dir = Path(args.animations_dir).resolve() if args.animations_dir else None
    slug = args.slug.lower()
    excluded_actions = {
        action.strip().lower()
        for action in args.exclude_actions.split(",")
        if action.strip()
    }

    if not mesh_path.exists():
        print(f"ERROR: mesh not found: {mesh_path}", file=sys.stderr)
        return 1
    if not args.embedded_actions and animations_dir is None:
        print("ERROR: --animations-dir is required unless --embedded-actions is set", file=sys.stderr)
        return 1
    if animations_dir is not None and not animations_dir.exists():
        print(f"ERROR: animations dir not found: {animations_dir}", file=sys.stderr)
        return 1

    print(f"[{slug}] Importing base mesh: {mesh_path}")
    load_source(mesh_path)
    armature = first_armature()
    if armature is None:
        print("ERROR: no armature found in base mesh", file=sys.stderr)
        return 2
    meshes = skinned_meshes_for(armature)
    print(f"[{slug}] Armature: {armature.name} ({len(armature.data.bones)} bones)")
    print(f"[{slug}] Meshes: {', '.join(mesh.name for mesh in meshes)}")
    make_materials_opaque()
    if slug == "rat":
        fix_rat_ik_target_weights(meshes, armature)
        bake_visual_actions(armature)
        clear_pose_constraints(armature)
        remove_rat_ik_target_bones(meshes, armature)
    if slug == "wasp":
        fix_wasp_stinger_weights(meshes, armature)
    if not args.skip_transform_apply:
        apply_object_transforms([armature, *meshes])

    rig_out = project_root / "static" / "rigs" / f"rig-{slug}.glb"
    model_out = project_root / "static" / "models" / f"model-{slug}.glb"
    anims_out = project_root / "static" / "animations" / f"{slug}-animations.glb"

    export_glb(rig_out, [armature], export_animations=False, export_materials="NONE", export_apply=True)
    print(f"[{slug}] Wrote rig: {rig_out.relative_to(project_root)}")

    export_glb(model_out, [armature, *meshes], export_animations=False, export_materials="EXPORT", export_apply=True)
    print(f"[{slug}] Wrote model: {model_out.relative_to(project_root)}")

    if args.embedded_actions:
        if armature.animation_data is None:
            armature.animation_data_create()
        for track in list(armature.animation_data.nla_tracks):
            armature.animation_data.nla_tracks.remove(track)

        embedded_actions = list(bpy.data.actions)
        if not embedded_actions:
            print("ERROR: no embedded actions found", file=sys.stderr)
            return 3

        for action in embedded_actions:
            action.name = clean_action_name(action.name)
            if action.name.lower() in excluded_actions:
                print(f"[{slug}] Skipping embedded action: {action.name}")
                bpy.data.actions.remove(action)
                continue
            add_action_to_nla(armature, action)
            print(f"[{slug}] Added embedded action: {action.name}")

        export_glb(anims_out, [armature], export_animations=True, export_materials="NONE", export_apply=True)
        exported_actions = [track for track in armature.animation_data.nla_tracks]
        print(f"[{slug}] Wrote animations: {anims_out.relative_to(project_root)} ({len(exported_actions)} actions)")
        return 0

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
