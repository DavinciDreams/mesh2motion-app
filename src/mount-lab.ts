import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js'

type TransformMode = 'translate' | 'rotate' | 'scale'

const loader = new GLTFLoader()
const exporter = new GLTFExporter()

const scene = new THREE.Scene()
scene.background = new THREE.Color(0x2b4353)

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.01, 100)
camera.position.set(3, 2, 4)

const renderer = new THREE.WebGLRenderer({ antialias: true })
renderer.setPixelRatio(window.devicePixelRatio)
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.shadowMap.enabled = true
document.body.appendChild(renderer.domElement)

const orbit = new OrbitControls(camera, renderer.domElement)
orbit.target.set(0, 0.8, 0)
orbit.update()

const transform = new TransformControls(camera, renderer.domElement)
transform.setMode('translate')
transform.addEventListener('dragging-changed', (event: any) => {
  orbit.enabled = !event.value
})
transform.addEventListener('objectChange', () => {
  sync_inputs_from_mount()
})
scene.add(transform)

scene.add(new THREE.HemisphereLight(0xffffff, 0x263340, 2.2))
const key_light = new THREE.DirectionalLight(0xffffff, 2.0)
key_light.position.set(3, 5, 4)
key_light.castShadow = true
scene.add(key_light)

const grid = new THREE.GridHelper(10, 20, 0x7a97aa, 0x426074)
scene.add(grid)

let animal_root: THREE.Object3D | null = null
let mount_root: THREE.Object3D | null = null

const status = element<HTMLElement>('status')
const animal_select = element<HTMLSelectElement>('animal-select')
const mount_select = element<HTMLSelectElement>('mount-select')

const transform_buttons: Record<TransformMode, HTMLButtonElement> = {
  translate: element<HTMLButtonElement>('tool-translate'),
  rotate: element<HTMLButtonElement>('tool-rotate'),
  scale: element<HTMLButtonElement>('tool-scale')
}

const position_inputs = [
  element<HTMLInputElement>('pos-x'),
  element<HTMLInputElement>('pos-y'),
  element<HTMLInputElement>('pos-z')
]
const rotation_inputs = [
  element<HTMLInputElement>('rot-x'),
  element<HTMLInputElement>('rot-y'),
  element<HTMLInputElement>('rot-z')
]
const scale_inputs = [
  element<HTMLInputElement>('scale-x'),
  element<HTMLInputElement>('scale-y'),
  element<HTMLInputElement>('scale-z')
]

function element<T extends HTMLElement> (id: string): T {
  const found = document.getElementById(id)
  if (found === null) {
    throw new Error(`Missing element #${id}`)
  }
  return found as T
}

function set_status (message: string): void {
  status.textContent = message
}

function prepare_asset (root: THREE.Object3D, name: string): THREE.Object3D {
  root.name = name
  root.traverse((child: THREE.Object3D) => {
    if ((child as THREE.Mesh).isMesh === true) {
      const mesh = child as THREE.Mesh
      mesh.castShadow = true
      mesh.receiveShadow = true
      if (Array.isArray(mesh.material)) {
        mesh.material.forEach(material => { material.side = THREE.DoubleSide })
      } else if (mesh.material !== undefined) {
        mesh.material.side = THREE.DoubleSide
      }
    }
  })
  return root
}

function frame_scene (): void {
  const box = new THREE.Box3()
  if (animal_root !== null) box.expandByObject(animal_root)
  if (mount_root !== null) box.expandByObject(mount_root)
  if (box.isEmpty()) return

  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const max_dim = Math.max(size.x, size.y, size.z, 1)
  camera.position.copy(center).add(new THREE.Vector3(max_dim * 0.9, max_dim * 0.55, max_dim * 1.2))
  orbit.target.copy(center)
  orbit.update()
}

function add_or_replace_animal (root: THREE.Object3D): void {
  if (animal_root !== null) {
    scene.remove(animal_root)
  }
  animal_root = prepare_asset(root, 'Mount Lab Animal')
  scene.add(animal_root)
  frame_scene()
}

function add_or_replace_mount (root: THREE.Object3D): void {
  if (mount_root !== null) {
    transform.detach()
    scene.remove(mount_root)
  }
  mount_root = prepare_asset(root, 'Mount Lab Mount')
  scene.add(mount_root)
  transform.attach(mount_root)
  sync_inputs_from_mount()
}

function load_url (url: string, on_load: (root: THREE.Object3D) => void): void {
  set_status(`Loading ${url.split('/').pop() ?? url}...`)
  loader.load(
    url,
    (gltf) => {
      on_load(gltf.scene)
      set_status('Ready')
    },
    undefined,
    (error) => {
      console.error(error)
      set_status(`Failed to load ${url}`)
    }
  )
}

function load_file (file: File, on_load: (root: THREE.Object3D) => void): void {
  const url = URL.createObjectURL(file)
  load_url(url, (root) => {
    URL.revokeObjectURL(url)
    on_load(root)
  })
}

function set_transform_mode (mode: TransformMode): void {
  transform.setMode(mode)
  for (const [key, button] of Object.entries(transform_buttons)) {
    button.classList.toggle('active', key === mode)
  }
}

function sync_inputs_from_mount (): void {
  if (mount_root === null) return
  const pos = mount_root.position
  const rot = mount_root.rotation
  const scale = mount_root.scale
  position_inputs[0].value = pos.x.toFixed(3)
  position_inputs[1].value = pos.y.toFixed(3)
  position_inputs[2].value = pos.z.toFixed(3)
  rotation_inputs[0].value = THREE.MathUtils.radToDeg(rot.x).toFixed(1)
  rotation_inputs[1].value = THREE.MathUtils.radToDeg(rot.y).toFixed(1)
  rotation_inputs[2].value = THREE.MathUtils.radToDeg(rot.z).toFixed(1)
  scale_inputs[0].value = scale.x.toFixed(3)
  scale_inputs[1].value = scale.y.toFixed(3)
  scale_inputs[2].value = scale.z.toFixed(3)
}

function apply_inputs_to_mount (): void {
  if (mount_root === null) return
  mount_root.position.set(
    Number(position_inputs[0].value),
    Number(position_inputs[1].value),
    Number(position_inputs[2].value)
  )
  mount_root.rotation.set(
    THREE.MathUtils.degToRad(Number(rotation_inputs[0].value)),
    THREE.MathUtils.degToRad(Number(rotation_inputs[1].value)),
    THREE.MathUtils.degToRad(Number(rotation_inputs[2].value))
  )
  mount_root.scale.set(
    Number(scale_inputs[0].value),
    Number(scale_inputs[1].value),
    Number(scale_inputs[2].value)
  )
  mount_root.updateMatrixWorld(true)
}

function download_blob (blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function export_object (object: THREE.Object3D, filename: string): void {
  exporter.parse(
    object,
    (result) => {
      const blob = result instanceof ArrayBuffer
        ? new Blob([result], { type: 'model/gltf-binary' })
        : new Blob([JSON.stringify(result)], { type: 'model/gltf+json' })
      download_blob(blob, filename)
    },
    (error) => {
      console.error(error)
      set_status('Export failed')
    },
    { binary: true }
  )
}

animal_select.addEventListener('change', () => {
  load_url(animal_select.value, add_or_replace_animal)
})

mount_select.addEventListener('change', () => {
  load_url(mount_select.value, add_or_replace_mount)
})

element<HTMLInputElement>('animal-upload').addEventListener('change', (event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file !== undefined) load_file(file, add_or_replace_animal)
})

element<HTMLInputElement>('mount-upload').addEventListener('change', (event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file !== undefined) load_file(file, add_or_replace_mount)
})

transform_buttons.translate.addEventListener('click', () => { set_transform_mode('translate') })
transform_buttons.rotate.addEventListener('click', () => { set_transform_mode('rotate') })
transform_buttons.scale.addEventListener('click', () => { set_transform_mode('scale') })

for (const input of [...position_inputs, ...rotation_inputs, ...scale_inputs]) {
  input.addEventListener('input', apply_inputs_to_mount)
}

element<HTMLButtonElement>('reset-mount').addEventListener('click', () => {
  if (mount_root === null) return
  mount_root.position.set(0, 0, 0)
  mount_root.rotation.set(0, 0, 0)
  mount_root.scale.set(1, 1, 1)
  sync_inputs_from_mount()
})

element<HTMLButtonElement>('download-mount').addEventListener('click', () => {
  if (mount_root !== null) export_object(mount_root, 'mount-aligned.glb')
})

element<HTMLButtonElement>('download-scene').addEventListener('click', () => {
  const export_group = new THREE.Group()
  export_group.name = 'mount-lab-scene'
  if (animal_root !== null) export_group.add(animal_root.clone(true))
  if (mount_root !== null) export_group.add(mount_root.clone(true))
  export_object(export_group, 'mount-lab-scene.glb')
})

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
})

function animate (): void {
  requestAnimationFrame(animate)
  renderer.render(scene, camera)
}

load_url(animal_select.value, add_or_replace_animal)
load_url(mount_select.value, add_or_replace_mount)
animate()
