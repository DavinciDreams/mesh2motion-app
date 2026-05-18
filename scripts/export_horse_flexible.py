"""
Flexible Horse Export Script for Blender
This script automatically finds armatures and meshes and exports all required files.

INSTRUCTIONS:
1. Open your horse blend file in Blender
2. Run export_horse_diagnostic.py FIRST to see object names
3. Update the OBJECT_NAMES section below with the correct names from the diagnostic
4. Run this script to export all assets

WHAT THIS EXPORTS:
- static/rigs/rig-horse.glb (skeleton only, no mesh, no animations)
- static/models/model-horse.glb (mesh only, no animations)
- static/animations/horse-animations.glb (animations only, no mesh)
"""

import bpy
import os
from pathlib import Path

# ============================================================
# CONFIGURATION - UPDATE THESE NAMES BASED ON YOUR DIAGNOSTIC
# ============================================================

OBJECT_NAMES = {
    # Run export_horse_diagnostic.py first, then update these
    # with the actual names from your blend file

    # Common possibilities: "Armature", "Rig", "Horse", "horse", "Object_4", "horse.rig"
    "armature": "Armature",  # <-- UPDATE THIS

    # Common possibilities: "Horse", "horse", "Body", "Mesh"
    "mesh": "Horse",  # <-- UPDATE THIS
}

# Export paths relative to the project root
PROJECT_ROOT = Path(__file__).parent
EXPORT_PATHS = {
    "rig": PROJECT_ROOT / "static" / "rigs" / "rig-horse.glb",
    "model": PROJECT_ROOT / "static" / "models" / "model-horse.glb",
    "animations": PROJECT_ROOT / "static" / "animations" / "horse-animations.glb",
}

# ============================================================
# EXPORT FUNCTIONS
# ============================================================

def clear_selection():
    """Deselect all objects."""
    bpy.ops.object.select_all(action='DESELECT')

def select_object(name):
    """Select an object by name and make it active."""
    clear_selection()
    obj = bpy.data.objects.get(name)
    if obj:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        return obj
    return None

def get_first_armature():
    """Get the first armature in the scene."""
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    return armatures[0] if armatures else None

def get_first_mesh():
    """Get the first mesh in the scene."""
    meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    return meshes[0] if meshes else None

def setup_animations_in_nla(armature):
    """Add all animation actions to NLA tracks for export."""
    if not armature.animation_data:
        print("   No animation data on armature, skipping NLA setup")
        return

    # Get all actions
    actions = bpy.data.actions

    if not actions:
        print("   No actions found in scene")
        return

    # Clear existing NLA tracks
    for track in armature.animation_data.nla_tracks:
        armature.animation_data.nla_tracks.remove(track)

    # Add each action to NLA
    added_count = 0
    for action in actions:
        # Create new NLA track
        track = armature.animation_data.nla_tracks.new()
        track.name = action.name

        # Create strip for this action
        strip = track.strips.new(action.name, 0, action)
        added_count += 1
        print(f"   - Added '{action.name}' to NLA")

    print(f"   Total: {added_count} animations added to NLA")

def export_rig():
    """Export the horse rig (armature only, no mesh, no animations)."""
    print("\n" + "=" * 60)
    print("EXPORTING RIG (skeleton only)")
    print("=" * 60)

    # Try to get armature by name, or fall back to first armature
    armature = select_object(OBJECT_NAMES["armature"])
    if not armature:
        print(f"   Could not find armature '{OBJECT_NAMES['armature']}', trying first armature...")
        armature = get_first_armature()
        if armature:
            select_object(armature.name)
        else:
            print("   ERROR: No armature found!")
            return False

    print(f"   Using armature: '{armature.name}'")
    print(f"   Bones: {len(armature.data.bones)}")

    # Ensure directory exists
    export_path = EXPORT_PATHS["rig"]
    export_path.parent.mkdir(parents=True, exist_ok=True)

    # Export settings for rig only
    bpy.ops.export_scene.gltf(
        filepath=str(export_path),
        export_format='GLB',
        use_selection=True,
        export_texcoords=False,
        export_normals=False,
        export_tangents=False,
        export_materials='NONE',
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=True,
        export_animations=False,  # No animations in rig file
    )

    file_size = export_path.stat().st_size
    print(f"   ✓ Exported to: {export_path}")
    print(f"   File size: {file_size / 1024:.2f} KB")

    if file_size > 500 * 1024:
        print(f"   WARNING: File size is large. Rig should be < 500 KB.")

    return True

def export_model():
    """Export the horse model (mesh only, no animations)."""
    print("\n" + "=" * 60)
    print("EXPORTING MODEL (mesh only)")
    print("=" * 60)

    # Try to get mesh by name, or fall back to first mesh
    mesh = select_object(OBJECT_NAMES["mesh"])
    if not mesh:
        print(f"   Could not find mesh '{OBJECT_NAMES['mesh']}', trying first mesh...")
        mesh = get_first_mesh()
        if mesh:
            select_object(mesh.name)
        else:
            print("   ERROR: No mesh found!")
            return False

    print(f"   Using mesh: '{mesh.name}'")
    print(f"   Vertices: {len(mesh.data.vertices)}")
    print(f"   Faces: {len(mesh.data.polygons)}")

    # Ensure directory exists
    export_path = EXPORT_PATHS["model"]
    export_path.parent.mkdir(parents=True, exist_ok=True)

    # Export settings for mesh
    bpy.ops.export_scene.gltf(
        filepath=str(export_path),
        export_format='GLB',
        use_selection=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=True,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=True,
        export_animations=False,  # No animations in model file
    )

    file_size = export_path.stat().st_size
    print(f"   ✓ Exported to: {export_path}")
    print(f"   File size: {file_size / (1024*1024):.2f} MB")

    if file_size > 20 * 1024 * 1024:
        print(f"   WARNING: File size is large. Consider optimizing textures.")

    return True

def export_animations():
    """Export the horse animations (armature with animations, no mesh)."""
    print("\n" + "=" * 60)
    print("EXPORTING ANIMATIONS (armature + animations, no mesh)")
    print("=" * 60)

    # Try to get armature by name, or fall back to first armature
    armature = select_object(OBJECT_NAMES["armature"])
    if not armature:
        print(f"   Could not find armature '{OBJECT_NAMES['armature']}', trying first armature...")
        armature = get_first_armature()
        if armature:
            select_object(armature.name)
        else:
            print("   ERROR: No armature found!")
            return False

    print(f"   Using armature: '{armature.name}'")

    # Setup NLA tracks
    if armature.animation_data:
        print("   Setting up NLA tracks...")
        setup_animations_in_nla(armature)
    else:
        print("   WARNING: No animation data found on armature!")
        return False

    # Ensure directory exists
    export_path = EXPORT_PATHS["animations"]
    export_path.parent.mkdir(parents=True, exist_ok=True)

    # Export settings for animations
    bpy.ops.export_scene.gltf(
        filepath=str(export_path),
        export_format='GLB',
        use_selection=True,
        export_texcoords=False,
        export_normals=False,
        export_tangents=False,
        export_materials='NONE',
        export_cameras=False,
        export_lights=False,
        export_apply=True,
        export_yup=True,
        export_animations=True,
        export_animation_mode='ALL_ACTIONS',
        export_nla_strips=True,
    )

    file_size = export_path.stat().st_size
    print(f"   ✓ Exported to: {export_path}")
    print(f"   File size: {file_size / (1024*1024):.2f} MB")

    return True

def main():
    """Main export function."""
    print("\n")
    print("=" * 60)
    print("HORSE ASSET EXPORT - FLEXIBLE SCRIPT")
    print("=" * 60)
    print(f"\nProject root: {PROJECT_ROOT}")
    print(f"\nConfiguration:")
    print(f"  Armature name: '{OBJECT_NAMES['armature']}'")
    print(f"  Mesh name: '{OBJECT_NAMES['mesh']}'")

    # Verify blend file is saved
    if not bpy.data.is_saved:
        print("\nWARNING: Blend file is not saved. Please save it first!")
        return

    results = {}

    # Export rig
    try:
        results['rig'] = export_rig()
    except Exception as e:
        print(f"ERROR exporting rig: {e}")
        results['rig'] = False

    # Export model
    try:
        results['model'] = export_model()
    except Exception as e:
        print(f"ERROR exporting model: {e}")
        results['model'] = False

    # Export animations
    try:
        results['animations'] = export_animations()
    except Exception as e:
        print(f"ERROR exporting animations: {e}")
        results['animations'] = False

    # Summary
    print("\n" + "=" * 60)
    print("EXPORT SUMMARY")
    print("=" * 60)
    print(f"Rig (rig-horse.glb):          {'✓ SUCCESS' if results.get('rig') else '✗ FAILED'}")
    print(f"Model (model-horse.glb):      {'✓ SUCCESS' if results.get('model') else '✗ FAILED'}")
    print(f"Animations (horse-animations): {'✓ SUCCESS' if results.get('animations') else '✗ FAILED'}")
    print("=" * 60)

    if all(results.values()):
        print("\n🎉 All exports successful! The horse is ready to use in mesh2motion.")
    else:
        print("\n⚠️  Some exports failed. Check the error messages above.")
        print("\nTIP: Run export_horse_diagnostic.py first to verify object names.")

if __name__ == "__main__":
    main()
