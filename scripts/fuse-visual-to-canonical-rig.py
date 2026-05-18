from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_glb(path: Path) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [obj for obj in bpy.data.objects if obj not in before]


def mesh_objects(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    return [obj for obj in objects if obj.type == "MESH"]


def find_armature(objects: list[bpy.types.Object]) -> bpy.types.Object:
    for obj in objects:
        if obj.type == "ARMATURE":
            return obj
    raise RuntimeError("No armature found in canonical source")


def find_source_mesh(objects: list[bpy.types.Object]) -> bpy.types.Object:
    candidates = [obj for obj in mesh_objects(objects) if obj.vertex_groups]
    if not candidates:
        raise RuntimeError("No skinned source mesh with vertex groups found")
    return max(candidates, key=lambda obj: len(obj.data.vertices))


def largest_mesh(objects: list[bpy.types.Object]) -> bpy.types.Object:
    candidates = mesh_objects(objects)
    if not candidates:
        raise RuntimeError("No mesh found")
    return max(candidates, key=lambda obj: len(obj.data.vertices))


def remove_meshes_except(keep: set[bpy.types.Object]) -> None:
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)


def world_bbox(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points: list[Vector] = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj.update_from_editmode()
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        raise RuntimeError("Cannot compute bounds for empty mesh list")
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


def align_targets_to_source(source_mesh: bpy.types.Object, targets: list[bpy.types.Object]) -> None:
    source_min, source_max = world_bbox([source_mesh])
    target_min, target_max = world_bbox(targets)
    source_size = source_max - source_min
    target_size = target_max - target_min

    # For quadrupeds the longest axis is usually the body length. Matching that
    # keeps the canonical skeleton from becoming huge compared with the visual.
    scale = max(source_size.x, source_size.y, source_size.z) / max(
        max(target_size.x, target_size.y, target_size.z),
        1e-6,
    )

    source_center = (source_min + source_max) * 0.5
    target_center = (target_min + target_max) * 0.5
    source_bottom = source_min.z

    for obj in targets:
        obj.location = source_center + (obj.location - target_center) * scale
        obj.scale = obj.scale * scale

    bpy.context.view_layer.update()
    aligned_min, _ = world_bbox(targets)
    z_delta = source_bottom - aligned_min.z
    for obj in targets:
        obj.location.z += z_delta

    bpy.context.view_layer.update()


def source_vertex_weights(source: bpy.types.Object) -> list[list[tuple[str, float]]]:
    group_names = {group.index: group.name for group in source.vertex_groups}
    weights: list[list[tuple[str, float]]] = []
    for vertex in source.data.vertices:
        entries: list[tuple[str, float]] = []
        for group in vertex.groups:
            name = group_names.get(group.group)
            if name is not None and group.weight > 0:
                entries.append((name, group.weight))
        weights.append(entries)
    return weights


def build_source_kdtree(source: bpy.types.Object) -> KDTree:
    tree = KDTree(len(source.data.vertices))
    matrix = source.matrix_world.copy()
    for index, vertex in enumerate(source.data.vertices):
        tree.insert(matrix @ vertex.co, index)
    tree.balance()
    return tree


def prepare_target_mesh(target: bpy.types.Object) -> None:
    for modifier in list(target.modifiers):
        if modifier.type == "ARMATURE":
            target.modifiers.remove(modifier)
    while target.vertex_groups:
        target.vertex_groups.remove(target.vertex_groups[0])
    target.parent = None


def ensure_target_groups(
    target: bpy.types.Object,
    bone_names: list[str],
) -> dict[str, bpy.types.VertexGroup]:
    groups: dict[str, bpy.types.VertexGroup] = {}
    for name in bone_names:
        groups[name] = target.vertex_groups.new(name=name)
    return groups


def transfer_weights(
    source: bpy.types.Object,
    target: bpy.types.Object,
    armature: bpy.types.Object,
) -> None:
    prepare_target_mesh(target)
    source_weights = source_vertex_weights(source)
    tree = build_source_kdtree(source)
    bone_names = [bone.name for bone in armature.data.bones]
    target_groups = ensure_target_groups(target, bone_names)
    target_matrix = target.matrix_world.copy()

    for vertex in target.data.vertices:
        world_position = target_matrix @ vertex.co
        _, nearest_index, _ = tree.find(world_position)
        for name, weight in source_weights[nearest_index]:
            group = target_groups.get(name)
            if group is not None:
                group.add([vertex.index], float(weight), "REPLACE")

    modifier = target.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature
    target.parent = armature


def remove_visual_armatures(visual_objects: list[bpy.types.Object]) -> None:
    for obj in list(visual_objects):
        if obj.type == "ARMATURE":
            bpy.data.objects.remove(obj, do_unlink=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path, help="Canonical rigged mesh GLB")
    parser.add_argument("--visual", required=True, type=Path, help="High quality visual mesh GLB")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--no-align", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    clear_scene()
    source_objects = import_glb(args.source)
    armature = find_armature(source_objects)
    source_mesh = find_source_mesh(source_objects)

    visual_objects = import_glb(args.visual)
    target = largest_mesh(visual_objects)
    targets = [target]

    remove_visual_armatures(visual_objects)
    remove_meshes_except({source_mesh, target})
    if not args.no_align:
        align_targets_to_source(source_mesh, targets)

    for target in targets:
        transfer_weights(source_mesh, target, armature)

    remove_meshes_except({target})
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.type in {"ARMATURE", "MESH"}:
            obj.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=str(args.out),
        export_format="GLB",
        use_selection=True,
        export_materials="EXPORT",
        export_apply=False,
        export_skins=True,
        export_animations=False,
    )
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
