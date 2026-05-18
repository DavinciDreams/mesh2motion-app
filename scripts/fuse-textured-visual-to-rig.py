from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
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
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            return obj
    raise RuntimeError("No armature found in rig source")


def find_source_mesh(objects: list[bpy.types.Object]) -> bpy.types.Object:
    candidates = [obj for obj in mesh_objects(objects) if obj.vertex_groups]
    if not candidates:
        raise RuntimeError("No skinned source mesh with vertex groups found")
    return max(candidates, key=lambda obj: len(obj.data.vertices))


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


def ensure_target_groups(
    target: bpy.types.Object,
    bone_names: list[str],
) -> dict[str, bpy.types.VertexGroup]:
    groups: dict[str, bpy.types.VertexGroup] = {}
    for name in bone_names:
        groups[name] = target.vertex_groups.get(name) or target.vertex_groups.new(name=name)
    return groups


def transfer_weights(
    source: bpy.types.Object,
    target: bpy.types.Object,
    armature: bpy.types.Object,
) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rig", required=True, type=Path)
    parser.add_argument("--visual", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)

    clear_scene()
    rig_objects = import_glb(args.rig)
    armature = find_armature(rig_objects)
    source_mesh = find_source_mesh(rig_objects)
    visual_objects = import_glb(args.visual)
    targets = mesh_objects(visual_objects)
    if not targets:
        raise RuntimeError("No visual mesh found")

    for target in targets:
        transfer_weights(source_mesh, target, armature)

    bpy.data.objects.remove(source_mesh, do_unlink=True)
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
