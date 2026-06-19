import { describe, expect, it } from 'vitest'
import { Bone, MathUtils, Quaternion, Vector3 } from 'three'
import { StepEditSkeleton } from './StepEditSkeleton'

function add_bone (name: string, position: [number, number, number], parent?: Bone): Bone {
  const bone = new Bone()
  bone.name = name
  bone.position.set(position[0], position[1], position[2])

  if (parent !== undefined) {
    parent.add(bone)
  }

  return bone
}

describe('StepEditSkeleton limb rotation baking', () => {
  it('turns a rotated limb into descendant joint positions while restoring the root rotation', () => {
    const step = new StepEditSkeleton()
    const chest = add_bone('chest', [0, 0, 0])
    const neck = add_bone('neck', [0, 1, 0], chest)
    const head = add_bone('head', [0, 1, 0], neck)
    const face = add_bone('face', [0, 0.5, 0], head)
    chest.updateMatrixWorld(true)

    const neck_start_quaternion = neck.quaternion.clone()
    const head_start = head.getWorldPosition(new Vector3())
    const face_start = face.getWorldPosition(new Vector3())

    step.begin_limb_rotation_drag(neck)
    neck.quaternion.multiply(new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), MathUtils.degToRad(-90)))
    neck.updateWorldMatrix(true, true)
    step.bake_limb_rotation_drag(neck)

    const head_end = head.getWorldPosition(new Vector3())
    const face_end = face.getWorldPosition(new Vector3())

    expect(neck.quaternion.angleTo(neck_start_quaternion)).toBeCloseTo(0, 5)
    expect(head_end.x).toBeCloseTo(1, 5)
    expect(head_end.y).toBeCloseTo(1, 5)
    expect(face_end.x).toBeCloseTo(1.5, 5)
    expect(face_end.y).toBeCloseTo(1, 5)
    expect(head_end.distanceTo(head_start)).toBeGreaterThan(0.9)
    expect(face_end.distanceTo(face_start)).toBeGreaterThan(1.4)
  })
})
