import { describe, expect, it } from 'vitest'
import { Bone } from 'three'
import { BoneCategory, BoneClassifier } from './BoneClassifier'

function bone_named (name: string): Bone {
  const bone = new Bone()
  bone.name = name
  return bone
}

describe('BoneClassifier', () => {
  it('keeps face controls out of torso smoothing', () => {
    const classifier = new BoneClassifier([
      bone_named('Head'),
      bone_named('Chin'),
      bone_named('mouth_upper'),
      bone_named('mouth_lower_tip'),
      bone_named('neck'),
      bone_named('spine')
    ])

    expect(classifier.get_category(0)).toBe(BoneCategory.Extremity)
    expect(classifier.get_category(1)).toBe(BoneCategory.Extremity)
    expect(classifier.get_category(2)).toBe(BoneCategory.Extremity)
    expect(classifier.get_category(3)).toBe(BoneCategory.Extremity)
    expect(classifier.get_category(4)).toBe(BoneCategory.Extremity)
    expect(classifier.get_category(5)).toBe(BoneCategory.Torso)
  })
})
