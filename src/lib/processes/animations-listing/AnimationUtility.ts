import { AnimationClip, Quaternion, Vector3, type KeyframeTrack, type QuaternionKeyframeTrack } from 'three'
import type { TransformedAnimationClipPair } from './interfaces/TransformedAnimationClipPair'
import { RigConfig } from '../../RigConfig'
import { SkeletonType } from '../../enums/SkeletonType'

export class AnimationUtility {
  // when we scaled the skeleton itself near the beginning, we kept track of that
  // this scaling will affect position keyframes since they expect the original skeleton scale
  // this will fix any issues with position keyframes not matching the current skeleton scale
  static apply_skeleton_scale_to_position_keyframes (animation_clips: AnimationClip[], scaleAmount: number): void {
    animation_clips.forEach((animation_clip: AnimationClip) => {
      animation_clip.tracks.forEach((track: KeyframeTrack) => {
        if (track.name.includes('.position')) {
          const values = track.values
          for (let i = 0; i < values.length; i += 3) {
            values[i] *= scaleAmount
            values[i + 1] *= scaleAmount
            values[i + 2] *= scaleAmount
          }
        }
      })
    })
  }

  static deep_clone_animation_clip (clip: AnimationClip): AnimationClip {
    const tracks = clip.tracks.map((track: KeyframeTrack) => track.clone())
    return new AnimationClip(clip.name, clip.duration, tracks)
  }

  static deep_clone_animation_clips (animation_clips: AnimationClip[]): AnimationClip[] {
    return animation_clips.map((clip: AnimationClip) => {
      return this.deep_clone_animation_clip(clip)
    })
  }

  /// Removes position tracks from animation clips, keeping only rotation tracks.
  /// @param animation_clips - The animation clips to modify.
  /// @param preserve_root_position - Whether to keep the root position track.
  static clean_track_data (animation_clips: AnimationClip[], skeleton_type: SkeletonType): void {
    animation_clips.forEach((animation_clip: AnimationClip) => {
      // remove all position nodes except root
      let rotation_tracks: KeyframeTrack[] = []

      // does the animation clip name include "RM". This indicates a root motion clip and we can keep the root position track
      const preserve_root_position: boolean = animation_clip.name.toLowerCase().endsWith('rm')

      // get position tracking bone name for normal movement (probably hips or head in the case of a snake)
      const rig_config = RigConfig.by_skeleton_type(skeleton_type)
      const position_tracking_bone_name = rig_config?.position_tracking_bone_name.toLowerCase()

      if (rig_config?.preserve_all_position_tracks === true) {
        animation_clip.tracks = animation_clip.tracks
          .filter((x: KeyframeTrack) => x.name.includes('quaternion') || x.name.includes('.position'))
        return
      }

      if (preserve_root_position) {
        rotation_tracks = animation_clip.tracks
          .filter((x: KeyframeTrack) => x.name.includes('quaternion') ||
          x.name.toLowerCase().includes(position_tracking_bone_name +  '.position') ||
          x.name.toLowerCase().includes('root.position'))
      } else {
        rotation_tracks = animation_clip.tracks
          .filter((x: KeyframeTrack) => x.name.includes('quaternion') ||
          x.name.toLowerCase().includes(position_tracking_bone_name +  '.position'))
      }

      animation_clip.tracks = rotation_tracks // update track data
      this.remove_suppressed_animation_bone_tracks(animation_clip, rig_config?.suppressed_animation_bone_names ?? [])
    })
  }

  private static remove_suppressed_animation_bone_tracks (
    animation_clip: AnimationClip,
    suppressed_bone_names: string[]
  ): void {
    if (suppressed_bone_names.length === 0) {
      return
    }

    const suppressed = new Set(suppressed_bone_names.map(name => name.toLowerCase()))
    animation_clip.tracks = animation_clip.tracks.filter((track: KeyframeTrack) => {
      const bone_name = this.bone_name_from_track_name(track.name).toLowerCase()
      return !suppressed.has(bone_name)
    })
  }

  private static bone_name_from_track_name (track_name: string): string {
    const bones_match = track_name.match(/\.bones\[("?)([^\]"]+)\1\]\./)
    if (bones_match !== null) {
      return bones_match[2]
    }

    const first_dot = track_name.indexOf('.')
    return first_dot === -1 ? track_name : track_name.slice(0, first_dot)
  }

  static apply_arm_extension_warp (animation_clips: TransformedAnimationClipPair[], percentage: number): void {
    // loop through each animation clip to update the tracks
    animation_clips.forEach((warped_clip: TransformedAnimationClipPair) => {
      warped_clip.display_animation_clip.tracks.forEach((track: KeyframeTrack) => {
        // if our name does not contain 'quaternion', we need to exit
        // since we are only modifying the quaternion tracks (e.g. L_Arm.quaternion )
        if (!track.name.includes('quaternion')) {
          return
        }

        const quaterion_track: QuaternionKeyframeTrack = track

        // if the track is an upper arm bone, then modify that
        const is_right_arm_track_match: boolean = quaterion_track.name.includes('upperarm_l')
        const is_left_arm_track_match: boolean = quaterion_track.name.includes('upperarm_r')

        if (is_right_arm_track_match || is_left_arm_track_match) {
          const new_track_values: Float32Array = quaterion_track.values.slice() // clone array

          const track_count: number = quaterion_track.times.length
          for (let i = 0; i < track_count; i++) {
            // get correct value since it is a quaternion
            const units_in_quaternions: number = 4
            const quaternion: Quaternion = new Quaternion()

            // rotate the upper arms in opposite directions to rise/lower arms
            if (is_right_arm_track_match) {
              quaternion.setFromAxisAngle(new Vector3(0, 0, -1), percentage / 100)
            }
            if (is_left_arm_track_match) {
              quaternion.setFromAxisAngle(new Vector3(0, 0, 1), percentage / 100)
            }

            // get the existing quaternion
            const existing_quaternion: Quaternion = new Quaternion(
              new_track_values[i * units_in_quaternions + 0],
              new_track_values[i * units_in_quaternions + 1],
              new_track_values[i * units_in_quaternions + 2],
              new_track_values[i * units_in_quaternions + 3]
            )

            // multiply the existing quaternion by the new quaternion
            existing_quaternion.multiply(quaternion)

            // this should change the first quaternion component of the track
            new_track_values[i * units_in_quaternions + 0] = existing_quaternion.x
            new_track_values[i * units_in_quaternions + 1] = existing_quaternion.y
            new_track_values[i * units_in_quaternions + 2] = existing_quaternion.z
            new_track_values[i * units_in_quaternions + 3] = existing_quaternion.w
          }

          track.values = new_track_values
        }
      })
    })
  }

  /**
   * Mirrors animations by swapping left and right bone tracks.
   * This swaps tracks that end with 'L' or 'R' to create mirrored animations.
   */
  static apply_animation_mirroring (animation_clips: TransformedAnimationClipPair[]): void {
    // do the swapping of the left/right tracks since we have all mirrored tracks exist now
    animation_clips.forEach((warped_clip: TransformedAnimationClipPair) => {
      const tracks = warped_clip.display_animation_clip.tracks
      const clip_name: string = warped_clip.display_animation_clip.name
      const track_swaps: Array<{ leftIndex: number, rightIndex: number, clipDetails: string }> = []

      // Find pairs of L/R tracks to swap
      for (let i = 0; i < tracks.length; i++) {
        const track = tracks[i]
        const track_name = track.name
        const mirrored_track_name = this.right_side_track_name_for_left_track(track_name)

        if (mirrored_track_name !== null) {
          const right_track_index = tracks.findIndex(t => t.name.toLowerCase() === mirrored_track_name)

          if (right_track_index !== -1) {
            track_swaps.push({ leftIndex: i, rightIndex: right_track_index, clipDetails: clip_name + ':' + track_name })
          }
        }
      }
 
      // Perform the swaps with quaternion mirroring
      track_swaps.forEach(({ leftIndex, rightIndex, clipDetails }) => {
        const left_track = tracks[leftIndex]
        const right_track = tracks[rightIndex]

        // Clone the times and values to avoid reference issues
        const left_values = left_track.values.slice()
        const right_values = right_track.values.slice()
        const left_times = left_track.times.slice()
        const right_times = right_track.times.slice()

        const is_quaternion_track = left_track.name.endsWith('.quaternion')
        const is_position_track = left_track.name.endsWith('.position')

        const mirrored_left_values = is_quaternion_track
          ? this.mirror_quaternion_track_values(left_values)
          : is_position_track
            ? this.mirror_position_track_values(left_values)
            : left_values
        const mirrored_right_values = is_quaternion_track
          ? this.mirror_quaternion_track_values(right_values)
          : is_position_track
            ? this.mirror_position_track_values(right_values)
            : right_values

        // Swap the mirrored track values and times
        left_track.values = mirrored_right_values
        left_track.times = right_times
        right_track.values = mirrored_left_values
        right_track.times = left_times
      })
    })

    this.apply_center_bone_mirroring(animation_clips)
    this.apply_hips_position_mirroring(animation_clips)
  }

  private static right_side_track_name_for_left_track (track_name: string): string | null {
    const lower_track_name = track_name.toLowerCase()
    if (lower_track_name.endsWith('_l.quaternion')) {
      return lower_track_name.replace(/_l\.quaternion$/, '_r.quaternion')
    }
    if (lower_track_name.endsWith('_l.position')) {
      return lower_track_name.replace(/_l\.position$/, '_r.position')
    }
    if (lower_track_name.endsWith('.l.quaternion')) {
      return lower_track_name.replace(/\.l\.quaternion$/, '.r.quaternion')
    }
    if (lower_track_name.endsWith('.l.position')) {
      return lower_track_name.replace(/\.l\.position$/, '.r.position')
    }
    return null
  }

  /**
   * Mirrors quaternion values by inverting X and W components for proper reflection.
   * This creates the mathematical mirror of the rotation.
   */
  private static mirror_quaternion_track_values (values: Float32Array): Float32Array {
    const mirrored_values = values.slice() // clone the array
    const units_in_quaternions = 4

    // Process each quaternion keyframe
    for (let i = 0; i < values.length; i += units_in_quaternions) {
      const quat = new Quaternion(
        values[i], // x
        values[i + 1], // y
        values[i + 2], // z
        values[i + 3] // w
      )

      // For mirroring left/right bone rotations, we invert X and W components
      // This creates the proper mirror reflection of the rotation
      quat.x = -quat.x
      quat.w = -quat.w

      // Write back the mirrored quaternion
      mirrored_values[i] = quat.x
      mirrored_values[i + 1] = quat.y
      mirrored_values[i + 2] = quat.z
      mirrored_values[i + 3] = quat.w
    }

    return mirrored_values
  }

  private static mirror_position_track_values (values: Float32Array): Float32Array {
    const mirrored_values = values.slice()
    const units_in_position = 3

    for (let i = 0; i < values.length; i += units_in_position) {
      mirrored_values[i] = -mirrored_values[i]
    }

    return mirrored_values
  }

  /**
   * Mirrors center bone rotations and hips position by inverting specific components.
   * This handles bones like spine, hips, neck, head that don't have L/R pairs.
   */
  private static apply_center_bone_mirroring (animation_clips: TransformedAnimationClipPair[]): void {
    animation_clips.forEach((warped_clip: TransformedAnimationClipPair) => {
      const tracks = warped_clip.display_animation_clip.tracks

      tracks.forEach((track: KeyframeTrack) => {
        const track_name_lower = track.name.toLowerCase()

        // Handle quaternion tracks for center bones
        if (track.name.includes('quaternion')) {
          const is_center_bone = track_name_lower.includes('spine') ||
                                track_name_lower.includes('hips') ||
                                track_name_lower.includes('pelvis') ||
                                track_name_lower.includes('neck') ||
                                track_name_lower.includes('head') ||
                                track_name_lower.includes('torso') ||
                                track_name_lower.includes('chest')

          if (!is_center_bone) { return } // mirror rotations for center aligned bones

          const values = track.values
          const units_in_quaternions = 4

          // Process each quaternion keyframe
          for (let i = 0; i < values.length; i += units_in_quaternions) {
            const quat = new Quaternion(
              values[i], // x
              values[i + 1], // y
              values[i + 2], // z
              values[i + 3] // w
            )

            // For mirroring, we need to invert the Y and Z components
            // This creates the mirror effect for center bone rotations
            quat.y = -quat.y
            quat.z = -quat.z

            // Write back the modified quaternion
            values[i] = quat.x
            values[i + 1] = quat.y
            values[i + 2] = quat.z
            values[i + 3] = quat.w
          }
        }
      })
    })
  }

  /**
   * Mirrors hips position tracks by inverting the X component.
   * This handles the hips bone position for locomotion and falling animations.
   */
  private static apply_hips_position_mirroring (animation_clips: TransformedAnimationClipPair[]): void {
    animation_clips.forEach((warped_clip: TransformedAnimationClipPair) => {
      const tracks = warped_clip.display_animation_clip.tracks

      tracks.forEach((track: KeyframeTrack) => {
        const track_name_lower = track.name.toLowerCase()

        // Handle position tracks specifically for hips
        if (track.name.includes('position') &&
        (track_name_lower.includes('hips') || track_name_lower.includes('pelvis'))) {
          const values = track.values
          const units_in_position = 3 // x, y, z

          // Process each position keyframe
          for (let i = 0; i < values.length; i += units_in_position) {
            // For mirroring hips position, we need to invert the X component
            // This creates the mirror effect for hips movement (left/right movement)
            // Y (up/down) and Z (forward/back) remain unchanged
            values[i] = -values[i] // invert X position
            // values[i + 1] unchanged (Y - up/down)
            // values[i + 2] unchanged (Z - forward/back)
          }
        }
      })
    })
  }
}
