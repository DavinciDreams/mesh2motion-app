import { BoneRules } from '../../lib/BoneRules.ts'
import { type BoneMetadata } from './BoneAutoMapper.ts'

interface NormalizedBoneMetadata extends BoneMetadata {
  normalized_position: [number, number, number]
}

/**
 * Spatial fallback for generated rigs whose bones are only named Bone_0,
 * joint_0, etc. This gives the retarget flow a useful first pass that can be
 * manually corrected in the bone mapping UI.
 */
export class SpatialBoneMapper {
  static is_likely_generated_skeleton (bone_names: string[]): boolean {
    if (bone_names.length === 0) return false

    const generated_name_count = bone_names.filter(name => {
      const lower = name.toLowerCase()
      return /^bone_\d+$/.test(lower) ||
        /^joint_\d+$/.test(lower) ||
        /^bone\d+$/.test(lower) ||
        /^joint\d+$/.test(lower)
    }).length

    return generated_name_count / bone_names.length >= 0.75
  }

  static map_by_normalized_world_positions (
    source_bones: BoneMetadata[],
    target_bones: BoneMetadata[]
  ): Map<string, string> {
    const mappings = new Map<string, string>()
    const source_candidates = source_bones.filter(source_bone =>
      source_bone.world_position !== undefined &&
      source_bone.name.toLowerCase() !== 'root' &&
      !BoneRules.is_non_deforming_control_bone_name(source_bone.name) &&
      !this.is_generated_mapping_decoration_bone(source_bone.name)
    )
    const target_candidates = target_bones.filter(target_bone =>
      target_bone.world_position !== undefined
    )

    if (source_candidates.length === 0 || target_candidates.length === 0) {
      return mappings
    }

    const normalized_sources = this.normalize_positions(source_candidates)
    const normalized_targets = this.normalize_positions(target_candidates)
    const source_by_name = new Map(normalized_sources.map(source => [source.name, source]))
    const target_by_name = new Map(normalized_targets.map(target => [target.name, target]))

    for (const target_bone of normalized_targets) {
      let closest_source: NormalizedBoneMetadata | null = null
      let closest_score = Number.POSITIVE_INFINITY
      const mapped_parent_name = this.mapped_parent_source_name(target_bone, target_by_name, mappings)

      for (const source_bone of normalized_sources) {
        const distance = this.weighted_position_distance(
          source_bone.normalized_position,
          target_bone.normalized_position
        )
        const hierarchy_penalty = this.hierarchy_penalty(source_bone, mapped_parent_name, source_by_name)
        const score = distance + hierarchy_penalty

        if (score < closest_score) {
          closest_source = source_bone
          closest_score = score
        }
      }

      if (closest_source !== null) {
        mappings.set(target_bone.name, closest_source.name)
      }
    }

    return mappings
  }

  private static normalize_positions (bones: BoneMetadata[]): NormalizedBoneMetadata[] {
    const positions = bones
      .map(bone => bone.world_position)
      .filter((position): position is [number, number, number] => position !== undefined)

    const min: [number, number, number] = [
      Math.min(...positions.map(position => position[0])),
      Math.min(...positions.map(position => position[1])),
      Math.min(...positions.map(position => position[2]))
    ]
    const max: [number, number, number] = [
      Math.max(...positions.map(position => position[0])),
      Math.max(...positions.map(position => position[1])),
      Math.max(...positions.map(position => position[2]))
    ]

    const size: [number, number, number] = [
      Math.max(max[0] - min[0], 0.0001),
      Math.max(max[1] - min[1], 0.0001),
      Math.max(max[2] - min[2], 0.0001)
    ]

    return bones
      .filter((bone): bone is BoneMetadata & { world_position: [number, number, number] } =>
        bone.world_position !== undefined
      )
      .map(bone => ({
        ...bone,
        normalized_position: [
          (bone.world_position[0] - min[0]) / size[0],
          (bone.world_position[1] - min[1]) / size[1],
          (bone.world_position[2] - min[2]) / size[2]
        ]
      }))
  }

  private static weighted_position_distance (
    a: [number, number, number],
    b: [number, number, number]
  ): number {
    const dx = a[0] - b[0]
    const dy = a[1] - b[1]
    const dz = a[2] - b[2]

    return Math.sqrt((dx * dx * 0.75) + (dy * dy * 1.15) + (dz * dz * 1.25))
  }

  private static mapped_parent_source_name (
    target_bone: NormalizedBoneMetadata,
    target_by_name: Map<string, NormalizedBoneMetadata>,
    mappings: Map<string, string>
  ): string | null {
    let parent_name = target_bone.parent_name
    while (parent_name !== null) {
      const mapped_parent_name = mappings.get(parent_name)
      if (mapped_parent_name !== undefined) return mapped_parent_name
      parent_name = target_by_name.get(parent_name)?.parent_name ?? null
    }
    return null
  }

  private static hierarchy_penalty (
    source_bone: NormalizedBoneMetadata,
    mapped_parent_name: string | null,
    source_by_name: Map<string, NormalizedBoneMetadata>
  ): number {
    if (mapped_parent_name === null) return 0
    if (source_bone.name === mapped_parent_name) return 0.04
    if (source_bone.parent_name === mapped_parent_name) return -0.08

    const parent = source_by_name.get(source_bone.parent_name ?? '')
    if (parent?.parent_name === mapped_parent_name) return -0.03
    if (parent?.name === mapped_parent_name) return -0.03

    return 0.08
  }

  private static is_generated_mapping_decoration_bone (bone_name: string): boolean {
    const name = bone_name.toLowerCase()
    return name.startsWith('ear') || name.startsWith('tail')
  }
}
