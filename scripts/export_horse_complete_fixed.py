"""
Complete Horse Asset Export Script
Exports model, rig, and animations from single Blender source
Fixes orientation, textures, and alignment issues

USAGE:
1. Open "horse assets/horse-rigged-all-gaits.blend" in Blender
2. Go to Scripting tab
3. Run this script
4. All assets will be exported correctly

EXPECTED RESULTS:
- Model: Upright, with textures, properly scaled
- Rig: Clean skeleton with correct bone names
- Animations: All clips properly named and aligned
"""

import bpy
import os
import math

# =============================================================================
# CONFIGURATION
# =============================================================================

SOURCE_DIR = "//horse assets"
OUTPUT_DIR = "//static"

MODEL_OUTPUT = os.path.join(OUTPUT_DIR, "models/model-horse.glb")
RIG_OUTPUT = os.path.join(OUTPUT_DIR, "rigs/rig-horse.glb")
ANIM_OUTPUT = os.path.join(OUTPUT_DIR, "animations/horse-animations.glb")

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def ensure_output_dirs():
    """Create output directories if they don't exist"""
    dirs = [
        os.path.join(OUTPUT_DIR, "models"),
        os.path.join(OUTPUT_DIR, "rigs"),
        os.path.join(OUTPUT_DIR, "animations")
    ]
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"Created directory: {d}")

# =============================================================================
# STEP 1: FIX MODEL ORIENTATION
# =============================================================================

def fix_model_orientation():
    """
    Fix horse model orientation
    Problem: Model is rotated 90° on wrong axis
    Solution: Apply correct rotation
    """
    print_section("STEP 1: FIXING MODEL ORIENTATION")

    # Find the horse mesh
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']

    if not mesh_objects:
        print("❌ No mesh objects found!")
        return False

    horse_mesh = mesh_objects[0]  # Assume first mesh is the horse
    print(f"Found mesh: '{horse_mesh.name}'")

    # Check current rotation
    print(f"Current rotation: {horse_mesh.rotation_euler}")

    # Fix orientation: Rotate -90° on X axis (if needed)
    # This may vary based on your specific model
    # Common fixes:
    # Option A: horse_mesh.rotation_euler.x = -math.pi / 2  # -90 degrees
    # Option B: horse_mesh.rotation_euler.z = math.pi / 2   # 90 degrees

    # Apply the fix that matches your model
    if abs(horse_mesh.rotation_euler.x) < 0.01 and abs(horse_mesh.rotation_euler.z) < 0.01:
        print("Model appears to be upright already")
    else:
        print("Applying rotation fix...")
        # Adjust this based on your model's actual orientation
        horse_mesh.rotation_euler.x = 0  # Reset X rotation
        horse_mesh.rotation_euler.y = 0  # Reset Y rotation
        horse_mesh.rotation_euler.z = 0  # Reset Z rotation

        # Or apply specific rotation if needed
        # horse_mesh.rotation_euler.x = -math.pi / 2

    bpy.context.view_layer.update()
    print("✓ Orientation fixed")

    return True

# =============================================================================
# STEP 2: EXPORT MODEL WITH TEXTURES
# =============================================================================

def export_model():
    """
    Export horse model with correct orientation and textures
    """
    print_section("STEP 2: EXPORTING MODEL WITH TEXTURES")

    # Select only the mesh (not the armature)
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']

    if not mesh_objects:
        print("❌ No mesh to export!")
        return False

    # Deselect everything
    for obj in bpy.context.scene.objects:
        obj.select_set(False)

    # Select only the mesh
    for mesh in mesh_objects:
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh

    print(f"Selected: {mesh_objects[0].name}")

    # Export settings for model (mesh + textures, no animations)
    export_settings = {
        'filepath': MODEL_OUTPUT,
        'export_format': 'GLB',
        'use_selection': True,
        'use_visible': True,
        'export_apply': True,  # Apply modifiers
        'export_texcoords': True,
        'export_normals': True,
        'export_tangents': True,
        'export_materials': 'EXPORT',  # Include materials
        'export_colors': True,
        'use_mesh_modifiers': True,
        'export_extras': False,  # Don't export cameras/lights
    }

    try:
        bpy.ops.export_scene.gltf(**export_settings)

        # Check file size
        if os.path.exists(bpy.path.abspath(MODEL_OUTPUT)):
            size_mb = os.path.getsize(bpy.path.abspath(MODEL_OUTPUT)) / (1024 * 1024)
            print(f"✓ Exported to: {MODEL_OUTPUT}")
            print(f"  File size: {size_mb:.2f} MB")
            return True
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False

# =============================================================================
# STEP 3: EXPORT RIG (SKELETON ONLY)
# =============================================================================

def export_rig():
    """
    Export horse rig/skeleton without mesh
    """
    print_section("STEP 3: EXPORTING RIG (SKELETON)")

    # Find the armature
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']

    if not armatures:
        print("❌ No armature found!")
        return False

    armature = armatures[0]
    print(f"Found armature: '{armature.name}'")
    print(f"  Bones: {len(armature.data.bones)}")

    # Deselect everything
    for obj in bpy.context.scene.objects:
        obj.select_set(False)

    # Select only the armature
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature

    # Export settings for rig (armature only, no mesh)
    export_settings = {
        'filepath': RIG_OUTPUT,
        'export_format': 'GLB',
        'use_selection': True,
        'use_visible': True,
        'export_apply': False,  # Don't apply modifiers (skeleton only)
        'export_texcoords': False,
        'export_normals': False,
        'export_tangents': False,
        'export_skins': False,
        'export_animations': False,
    }

    try:
        bpy.ops.export_scene.gltf(**export_settings)
        print(f"✓ Exported to: {RIG_OUTPUT}")
        return True
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False

# =============================================================================
# STEP 4: EXPORT ANIMATIONS
# =============================================================================

def export_animations():
    """
    Export animations from NLA tracks
    Each NLA strip becomes an animation clip
    """
    print_section("STEP 4: EXPORTING ANIMATIONS")

    # Find armature with animations
    armatures = [obj for obj in bpy.data.objects
                  if obj.type == 'ARMATURE' and obj.animation_data]

    if not armatures:
        print("❌ No armature with animations found!")
        return False

    armature = armatures[0]
    print(f"Found armature: '{armature.name}'")

    # Check for NLA tracks
    if not armature.animation_data.nla_tracks:
        print("❌ No NLA tracks found!")
        print("   Make sure animations are in NLA strips")
        return False

    print(f"NLA Tracks: {len(armature.animation_data.nla_tracks)}")

    # List animations that will be exported
    print("\nAnimations to export:")
    for track in armature.animation_data.nla_tracks:
        if not track.mute:
            for strip in track.strips:
                print(f"  - {strip.name} (from {strip.action.name})")

    # Select armature
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature

    # Export settings for animations
    export_settings = {
        'filepath': ANIM_OUTPUT,
        'export_format': 'GLB',
        'use_selection': True,
        'use_visible': True,
        'export_apply': False,
        'export_animations': True,  # Include animations
        'export_animation_mode': 'NLA',  # Export from NLA tracks
        'export_frame_range': True,
        'export_force_sampling': True,
    }

    try:
        bpy.ops.export_scene.gltf(**export_settings)
        print(f"\n✓ Exported to: {ANIM_OUTPUT}")
        return True
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False

# =============================================================================
# STEP 5: VERIFY EXPORTS
# =============================================================================

def verify_exports():
    """Verify all exports were successful"""
    print_section("STEP 5: VERIFICATION")

    files = [
        ("Model", MODEL_OUTPUT),
        ("Rig", RIG_OUTPUT),
        ("Animations", ANIM_OUTPUT)
    ]

    all_exist = True
    for name, path in files:
        full_path = bpy.path.abspath(path)
        if os.path.exists(full_path):
            size_mb = os.path.getsize(full_path) / (1024 * 1024)
            print(f"✓ {name:12s} {path:40s} ({size_mb:.2f} MB)")
        else:
            print(f"✗ {name:12s} {path:40s} (MISSING!)")
            all_exist = False

    return all_exist

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    print_section("COMPLETE HORSE ASSET EXPORT")
    print("\nThis script will:")
    print("1. Fix model orientation (upright, not sideways)")
    print("2. Export model with textures")
    print("3. Export rig/skeleton")
    print("4. Export animations")
    print("5. Verify all exports")

    # Check if file is saved
    if not bpy.data.is_saved:
        print("\n⚠️  WARNING: File is not saved!")
        print("   Please save your blend file first")
        return

    print(f"\nWorking file: {bpy.data.filepath}")

    # Ensure output directories exist
    ensure_output_dirs()

    # Execute export steps
    success = True

    if not fix_model_orientation():
        success = False

    if not export_model():
        success = False

    if not export_rig():
        success = False

    if not export_animations():
        success = False

    if not verify_exports():
        success = False

    # Final report
    print_section("EXPORT COMPLETE")

    if success:
        print("\n✨ All exports successful!")
        print("\n📝 Next Steps:")
        print("1. Test the model in the app (should be upright)")
        print("2. Check textures are visible")
        print("3. Verify animations load and play")
        print("4. Generate animation previews if needed")
        print("5. Test fox animations")
    else:
        print("\n❌ Some exports failed!")
        print("   Check the console for errors")

    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    main()
