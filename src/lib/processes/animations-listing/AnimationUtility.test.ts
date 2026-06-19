import { AnimationClip, QuaternionKeyframeTrack } from 'three'
import { describe, expect, it } from 'vitest'
import { SkeletonType } from '../../enums/SkeletonType'
import { AnimationUtility } from './AnimationUtility'

function quat_track (name: string): QuaternionKeyframeTrack {
  return new QuaternionKeyframeTrack(
    name,
    [0, 1],
    [0, 0, 0, 1, 0, 0, 0, 1]
  )
}

describe('AnimationUtility', () => {
  it('keeps fox mouth closed by removing chin animation tracks', () => {
    const clip = new AnimationClip('fox-test', 1, [
      quat_track('Head.quaternion'),
      quat_track('Chin.quaternion'),
      quat_track('Chin_Tip.quaternion'),
      quat_track('hips.position')
    ])

    AnimationUtility.clean_track_data([clip], SkeletonType.Fox)

    expect(clip.tracks.map(track => track.name)).toEqual([
      'Head.quaternion',
      'hips.position'
    ])
  })
})
