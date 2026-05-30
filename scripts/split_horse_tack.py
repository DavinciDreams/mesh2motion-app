"""Split the animated horse tack mesh into reusable mount GLBs.

The source horse GLB ships the horse body and saddle/bridle as two separate
skinned meshes. This exports the tack mesh as a standalone prop for visual
placement on other animals, and optionally exports a horse body without tack.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Split horse tack from the animated horse GLB.")
    parser.add_argument("--input", required=True, help="Source animated horse GLB")
    parser.add_argument("--project-root", default=None, help="Project root; defaults to script parent.parent")
    return parser.parse_args(argv)


def select_only(objects) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def export_glb(path: Path, objects, export_materials: str = "EXPORT") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    select_only(objects)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials=export_materials,
        export_animations=False,
    )


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve() if args.project_root else Path(__file__).resolve().parent.parent
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(input_path))

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    tack_meshes = [
        obj for obj in meshes
        if any(slot.material and "saddle" in slot.material.name.lower() for slot in obj.material_slots)
        or "saddle" in obj.name.lower()
        or "mnt" in obj.name.lower()
    ]
    body_meshes = [
        obj for obj in meshes
        if obj not in tack_meshes and len(obj.data.vertices) > 100
    ]

    if not tack_meshes:
        print("ERROR: no tack/saddle mesh found", file=sys.stderr)
        return 2

    mount_dir = project_root / "static" / "mounts" / "horse-tack"
    export_glb(mount_dir / "horse-saddle-bridle.glb", tack_meshes)
    print(f"Wrote {mount_dir / 'horse-saddle-bridle.glb'}")

    if body_meshes:
        export_glb(project_root / "static" / "models" / "model-animated-horse-body.glb", body_meshes)
        print(f"Wrote {project_root / 'static' / 'models' / 'model-animated-horse-body.glb'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
