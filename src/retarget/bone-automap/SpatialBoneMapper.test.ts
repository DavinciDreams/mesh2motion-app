import { describe, expect, it } from 'vitest'
import { BoneCategory, BoneSide, type BoneMetadata } from './BoneAutoMapper'
import { SpatialBoneMapper } from './SpatialBoneMapper'

function bone (name: string, position: [number, number, number]): BoneMetadata {
  return {
    name,
    normalized_name: name.toLowerCase(),
    side: BoneSide.Center,
    category: BoneCategory.Unknown,
    parent_name: null,
    world_position: position
  }
}

describe('SpatialBoneMapper', () => {
  it('detects numeric generated skeleton names', () => {
    expect(SpatialBoneMapper.is_likely_generated_skeleton([
      'Bone_0',
      'Bone_1',
      'Bone_2',
      'helper'
    ])).toBe(true)
  })

  it('maps generated bones to nearest normalized source bones', () => {
    const source_bones = [
      bone('Body', [0, 0, 0]),
      bone('Back', [0, 1, -1]),
      bone('Head', [0, 1, 1]),
      bone('IKFrontLegL', [0.5, -1, 1])
    ]
    const target_bones = [
      bone('Bone_0', [10, 0, 10]),
      bone('Bone_1', [10, 10, 0]),
      bone('Bone_2', [10, 10, 20])
    ]

    const mappings = SpatialBoneMapper.map_by_normalized_world_positions(source_bones, target_bones)

    expect(mappings.get('Bone_0')).toBe('Body')
    expect(mappings.get('Bone_1')).toBe('Back')
    expect(mappings.get('Bone_2')).toBe('Head')
    expect(Array.from(mappings.values())).not.toContain('IKFrontLegL')
  })
})
