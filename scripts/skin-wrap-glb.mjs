import fs from 'node:fs'
import * as THREE from 'three'
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

globalThis.self ??= globalThis
globalThis.createImageBitmap ??= async () => ({ close () {} })
globalThis.FileReader ??= class {
  readAsArrayBuffer (blob) {
    blob.arrayBuffer().then((buffer) => {
      this.result = buffer
      this.onloadend?.()
    }).catch((error) => {
      this.error = error
      this.onerror?.(error)
    })
  }

  readAsDataURL (blob) {
    blob.arrayBuffer().then((buffer) => {
      const bytes = Buffer.from(buffer)
      this.result = `data:${blob.type || 'application/octet-stream'};base64,${bytes.toString('base64')}`
      this.onloadend?.()
    }).catch((error) => {
      this.error = error
      this.onerror?.(error)
    })
  }
}

const [rig_path, visual_path, output_path] = process.argv.slice(2)
if (rig_path === undefined || visual_path === undefined || output_path === undefined) {
  console.error('Usage: node scripts/skin-wrap-glb.mjs <rig.glb> <visual.glb> <out.glb>')
  process.exit(1)
}

async function load_glb (path) {
  const bytes = fs.readFileSync(path)
  const loader = new GLTFLoader()
  return await loader.parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '')
}

function first_skinned_mesh (root) {
  let skinned_mesh = null
  root.traverse((child) => {
    if (skinned_mesh === null && child.isSkinnedMesh === true) skinned_mesh = child
  })
  return skinned_mesh
}

function visual_meshes (root) {
  const meshes = []
  root.traverse((child) => {
    if (child.isMesh === true) meshes.push(child)
  })
  return meshes
}

function world_positions_for_mesh (mesh) {
  const positions = mesh.geometry.getAttribute('position')
  const points = []
  for (let i = 0; i < positions.count; i += 1) {
    points.push(new THREE.Vector3().fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld))
  }
  return points
}

function build_grid (points) {
  const box = new THREE.Box3().setFromPoints(points)
  const size = box.getSize(new THREE.Vector3())
  const cell_size = Math.max(size.length() / 88, 0.0001)
  const cells = new Map()

  function cell_key_for_point (point) {
    return [
      Math.floor((point.x - box.min.x) / cell_size),
      Math.floor((point.y - box.min.y) / cell_size),
      Math.floor((point.z - box.min.z) / cell_size)
    ]
  }

  function key (x, y, z) {
    return `${x},${y},${z}`
  }

  points.forEach((point, index) => {
    const [x, y, z] = cell_key_for_point(point)
    const cell_key = key(x, y, z)
    const cell = cells.get(cell_key) ?? []
    cell.push(index)
    cells.set(cell_key, cell)
  })

  function nearest_index (point) {
    const [cx, cy, cz] = cell_key_for_point(point)
    let best_index = 0
    let best_distance = Infinity

    for (let radius = 0; radius <= 10; radius += 1) {
      for (let x = cx - radius; x <= cx + radius; x += 1) {
        for (let y = cy - radius; y <= cy + radius; y += 1) {
          for (let z = cz - radius; z <= cz + radius; z += 1) {
            const cell = cells.get(key(x, y, z))
            if (cell === undefined) continue
            for (const index of cell) {
              const distance = point.distanceToSquared(points[index])
              if (distance < best_distance) {
                best_distance = distance
                best_index = index
              }
            }
          }
        }
      }
      if (Number.isFinite(best_distance)) return best_index
    }

    points.forEach((source_point, index) => {
      const distance = point.distanceToSquared(source_point)
      if (distance < best_distance) {
        best_distance = distance
        best_index = index
      }
    })
    return best_index
  }

  return { nearest_index }
}

function clone_material_without_images (material) {
  const source = Array.isArray(material) ? material[0] : material
  const color = source?.color instanceof THREE.Color ? source.color.clone() : new THREE.Color(0xcaa35f)
  return new THREE.MeshStandardMaterial({
    color,
    roughness: source?.roughness ?? 0.82,
    metalness: source?.metalness ?? 0,
    side: THREE.DoubleSide
  })
}

function copy_skin_attributes_from_nearest_source (target_mesh, source_mesh, source_points, grid) {
  const target_geometry = target_mesh.geometry.clone()
  const target_positions = target_geometry.getAttribute('position')
  const source_skin_index = source_mesh.geometry.getAttribute('skinIndex')
  const source_skin_weight = source_mesh.geometry.getAttribute('skinWeight')
  const skin_indices = new Uint16Array(target_positions.count * 4)
  const skin_weights = new Float32Array(target_positions.count * 4)

  for (let i = 0; i < target_positions.count; i += 1) {
    const world_point = new THREE.Vector3().fromBufferAttribute(target_positions, i).applyMatrix4(target_mesh.matrixWorld)
    const source_index = grid.nearest_index(world_point)
    for (let j = 0; j < 4; j += 1) {
      skin_indices[i * 4 + j] = source_skin_index.getComponent(source_index, j)
      skin_weights[i * 4 + j] = source_skin_weight.getComponent(source_index, j)
    }
  }

  return target_geometry
    .setAttribute('skinIndex', new THREE.Uint16BufferAttribute(skin_indices, 4))
    .setAttribute('skinWeight', new THREE.Float32BufferAttribute(skin_weights, 4))
}

const rig_gltf = await load_glb(rig_path)
const visual_gltf = await load_glb(visual_path)
rig_gltf.scene.updateMatrixWorld(true)
visual_gltf.scene.updateMatrixWorld(true)

const source_mesh = first_skinned_mesh(rig_gltf.scene)
if (source_mesh === null) throw new Error('No skinned mesh found in rig source')

const source_parent = source_mesh.parent
if (source_parent === null) throw new Error('Skinned mesh has no parent')

const source_points = world_positions_for_mesh(source_mesh)
const grid = build_grid(source_points)
const parent_inverse = source_parent.matrixWorld.clone().invert()

source_parent.remove(source_mesh)

for (const target_mesh of visual_meshes(visual_gltf.scene)) {
  const geometry = copy_skin_attributes_from_nearest_source(target_mesh, source_mesh, source_points, grid)
  geometry.applyMatrix4(parent_inverse.clone().multiply(target_mesh.matrixWorld))
  const skinned_mesh = new THREE.SkinnedMesh(geometry, clone_material_without_images(target_mesh.material))
  skinned_mesh.name = `${target_mesh.name || 'visual'}_skinwrapped`
  skinned_mesh.bind(source_mesh.skeleton, source_mesh.bindMatrix)
  skinned_mesh.frustumCulled = false
  source_parent.add(skinned_mesh)
}

const exporter = new GLTFExporter()
const result = await exporter.parseAsync(rig_gltf.scene, { binary: true })
fs.writeFileSync(output_path, Buffer.from(result))
console.log(`Wrote ${output_path}`)
