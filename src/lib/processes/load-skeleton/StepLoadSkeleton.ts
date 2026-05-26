import { UI } from '../../UI.ts'
import { Box3, Object3D, Vector3, type Scene, type Object3DEventMap } from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { SkeletonType, type HandSkeletonType } from '../../enums/SkeletonType.js'
import { RigConfig } from '../../RigConfig.ts'
import type GLTFResult from './interfaces/GLTFResult.ts'
import { add_origin_markers, remove_origin_markers } from './OriginMarkerManager'
import { add_preview_skeleton, remove_preview_skeleton } from './PreviewSkeletonManager.ts'
import { HandHelper } from './HandHelper.ts'

// Note: EventTarget is a built-ininterface and do not need to import it
export class StepLoadSkeleton extends EventTarget {
  private readonly loader: GLTFLoader = new GLTFLoader()
  private readonly ui: UI = UI.getInstance()
  private loaded_armature: Object3D = new Object3D()

  private _added_event_listeners: boolean = false
  private readonly _main_scene: Scene

  // used to help scale animations later
  // this is useful since position keyframes will need to be scaled
  // to prevent large offsets
  private skeleton_scale_percentage: number = 1.0

  // longest-axis size of the loaded model, set by the engine when entering this
  // step. Used to auto-fit the preset skeleton to the model on selection.
  private model_longest_dimension: number = 0

  // once the user drags the scale slider we stop overriding their value with
  // auto-fit when they switch hand options etc.
  private user_overrode_scale: boolean = false

  // this was invented since this value is stored on a DOM element
  // this helps the marketing page set the type and doesn't rely on a DOM value
  // probably could refactor this a bit to be cleaner later.
  private manual_set_skeleton_type: SkeletonType = SkeletonType.None

  public skeleton_type (): SkeletonType {
    if (this.skeleton_file_path() === SkeletonType.None) {
      return this.manual_set_skeleton_type
    }

    return this.skeleton_file_path()
  }

  public set_skeleton_type (type: SkeletonType): void {
    this.manual_set_skeleton_type = type
  }

  // The edit skeleton step will use this to scale the skeleton when loading editable skeleton
  // animations listing will use this to scale all position keyframes
  public skeleton_scale (): number {
    return this.skeleton_scale_percentage
  }

  constructor (main_scene: Scene) {
    super()
    this._main_scene = main_scene
  }

  public begin (): void {
    if (this.ui.dom_current_step_element !== null) {
      this.ui.dom_current_step_element.innerHTML = 'Load Skeleton'
    }

    if (this.ui.dom_load_skeleton_tools !== null) {
      this.ui.dom_load_skeleton_tools.style.display = 'flex'
    }

    // if we are navigating back to this step, we don't want to add the event listeners again
    if (!this._added_event_listeners) {
      this.add_event_listeners()
      this._added_event_listeners = true
    }

    // when we come back to this step, there is a good chance we already selected a skeleton
    // so just use that and load the preview right when we enter this step. Auto-fit
    // handles the first-entry case (uses model size); if the user already tuned the
    // scale, auto_fit_skeleton_to_model preserves their value.
    if (!this.has_select_skeleton_ui_option()) {
      this.auto_fit_skeleton_to_model(this.skeleton_file_path())
    }

    // Initialize hand skeleton hand options visibility
    this.toggle_ui_hand_skeleton_options()

    // add origin markers for debugging model loading issues
    add_origin_markers(this._main_scene)

    // if there is a "select skeleton" option, disable proceeding
    // putting this check here helps us if we come back to this step later
    if (this.has_select_skeleton_ui_option()) {
      this.allow_proceeding_to_next_step(false)
    } else {
      this.allow_proceeding_to_next_step(true)
    }
  }

  public regenerate_origin_markers (): void {
    add_origin_markers(this._main_scene)
  }

  public dispose (): void {
    remove_origin_markers(this._main_scene)
    remove_preview_skeleton(this._main_scene)
  }

  private skeleton_file_path (): SkeletonType {
    // get currently selected option out of the model-selection drop-down
    const skeleton_selection = this.ui.dom_skeleton_drop_type.options
    const skeleton_file: string = skeleton_selection[skeleton_selection.selectedIndex].value

    if (skeleton_file === 'select-skeleton') return SkeletonType.None

    const config = RigConfig.by_key(skeleton_file)
    if (config === undefined) {
      console.error('unknown skeleton type selected: ', skeleton_file)
      return SkeletonType.Error
    }
    return config.skeleton_type
  }

  private hand_skeleton_type (): HandSkeletonType {
    const hand_selection = this.ui.dom_hand_skeleton_selection?.options
    return hand_selection[hand_selection.selectedIndex].value as HandSkeletonType
  }

  private add_event_listeners (): void {
    // Populate the skeleton template dropdown from the central rig config
    if (this.ui.dom_skeleton_drop_type !== null) {
      RigConfig.populate_skeleton_select(this.ui.dom_skeleton_drop_type)
    }

    // Add event listener for skeleton type changes to show/hide hand options
    if (this.ui.dom_skeleton_drop_type !== null) {
      this.ui.dom_skeleton_drop_type.addEventListener('change', () => {
        // get selected value from skeleton options
        // const skeleton_selection = this.ui.dom_skeleton_drop_type.options
        // this.skeleton_t = skeleton_selection[skeleton_selection.selectedIndex].value as SkeletonType

        // hand options only apply to human skeletons, so we need to show/hide when skeleton type changes
        this.toggle_ui_hand_skeleton_options()

        // remove the "select a skeleton" option if we picked something else
        if (this.has_select_skeleton_ui_option()) {
          this.ui.dom_skeleton_drop_type?.options.remove(0)
        }

        // show the scale skeleton options and advanced settings in case they are hidden
        if (this.ui.dom_scale_skeleton_controls !== null) {
          this.ui.dom_scale_skeleton_controls.style.display = 'flex'
        }
        // load the preview skeleton, auto-fitting it to the loaded model's size.
        // auto_fit_skeleton_to_model respects a manual scale override if the user
        // already dragged the slider, and falls back to the current scale when
        // there is no model size to fit against.
        this.auto_fit_skeleton_to_model(this.skeleton_file_path())
      })
    }

    if (this.ui.dom_load_skeleton_button !== null) {
      this.ui.dom_load_skeleton_button.addEventListener('click', () => {
        if (this.ui.dom_skeleton_drop_type === null) {
          console.warn('could not find skeleton selection drop down HTML element')
          return
        }

        // add back loading information here
        const rig_file = RigConfig.rig_file_for(this.skeleton_file_path())
        if (rig_file !== undefined) {
          this.load_skeleton_file(rig_file)
        }
      })
    }// end if statement

    // when hand skeleton type changes. update the preview skeleton
    this.ui.dom_hand_skeleton_selection?.addEventListener('change', () => {
      // rebuild the preview skeleton with the new hand skeleton type
      // make sure we keep existing scale if we made a change to that
      add_preview_skeleton(this._main_scene, this.skeleton_file_path(), this.hand_skeleton_type(), this.skeleton_scale()).catch((err) => {
        console.error('error loading preview skeleton: ', err)
      })
    })

    // scale skeleton controls
    this.ui.dom_scale_skeleton_input?.addEventListener('input', (event) => {
      // a manual drag means the user is taking control of the scale; stop
      // auto-fitting on subsequent skeleton/hand changes
      this.user_overrode_scale = true
      // range sliders have rounding errors, so we round the value to avoid issues
      const new_value: number = Number((event.target as HTMLInputElement).value)
      this.update_skeleton_scale_to_value(new_value)
    })

    // reset the skeleton scale button: hand control back to auto-fit
    this.ui.dom_reset_skeleton_scale_button?.addEventListener('click', () => {
      this.user_overrode_scale = false
      this.auto_fit_skeleton_to_model(this.skeleton_file_path())
    })

  }

  private update_skeleton_scale_to_value (new_value: number): void {
    this.skeleton_scale_percentage = Number(new_value)

    // reflect the value on the slider itself (auto-fit sets this programmatically,
    // and the input event only fires on user drag, not on programmatic change)
    if (this.ui.dom_scale_skeleton_input !== null) {
      this.ui.dom_scale_skeleton_input.value = String(new_value)
    }

    const display_value: string = Math.round(new_value * 100).toString() + '%'

    if (this.ui.dom_scale_skeleton_percentage_display !== null) {
      this.ui.dom_scale_skeleton_percentage_display.textContent = display_value
    }
    add_preview_skeleton(this._main_scene, this.skeleton_file_path(), this.hand_skeleton_type(), this.skeleton_scale_percentage)
      .catch((err) => {
        console.error('error loading preview skeleton: ', err)
      })
  }

  /**
   * Called by the engine when entering this step. Records the longest dimension
   * of the loaded model so we can auto-fit the preset skeleton to it.
   */
  public set_model_size (model_longest_dimension: number): void {
    this.model_longest_dimension = model_longest_dimension
  }

  /**
   * Loads the chosen rig at scale 1, measures its longest dimension, and returns
   * the uniform scale that makes the skeleton's longest axis match the model's.
   * Returns null when we can't compute a meaningful fit (no model size known,
   * or a degenerate skeleton bounding box).
   */
  private async compute_auto_fit_scale (skeleton_type: SkeletonType): Promise<number | null> {
    if (this.model_longest_dimension <= 0) {
      return null
    }

    // add_preview_skeleton returns the loaded rig scene; render it at scale 1 so
    // the returned object's bounding box reflects the rig's native size.
    const loaded_scene = await add_preview_skeleton(
      this._main_scene, skeleton_type, this.hand_skeleton_type(), 1.0
    )

    const skeleton_box = new Box3().setFromObject(loaded_scene)
    const skeleton_size = new Vector3()
    skeleton_box.getSize(skeleton_size)
    const skeleton_longest = Math.max(skeleton_size.x, skeleton_size.y, skeleton_size.z)

    if (!isFinite(skeleton_longest) || skeleton_longest <= 0) {
      return null
    }

    const raw_fit = this.model_longest_dimension / skeleton_longest

    // keep the fit within the scale slider's range so the slider thumb and the
    // percentage display stay consistent with the applied scale
    return this.clamp_to_slider_range(raw_fit)
  }

  private clamp_to_slider_range (value: number): number {
    const slider = this.ui.dom_scale_skeleton_input
    const min = slider !== null ? Number(slider.min) : 0.1
    const max = slider !== null ? Number(slider.max) : 2.0
    return Math.min(Math.max(value, min), max)
  }

  /**
   * Auto-fit the preset skeleton to the loaded model by matching longest axes,
   * unless the user has already manually adjusted the scale. The manual slider
   * and per-joint editing remain available afterward for fine-tuning.
   */
  private auto_fit_skeleton_to_model (skeleton_type: SkeletonType): void {
    if (this.user_overrode_scale) {
      // user has taken control of the scale; don't stomp their value
      add_preview_skeleton(this._main_scene, skeleton_type, this.hand_skeleton_type(), this.skeleton_scale())
        .then(() => { this.allow_proceeding_to_next_step(true) })
        .catch((err) => { console.error('error loading preview skeleton: ', err) })
      return
    }

    this.compute_auto_fit_scale(skeleton_type)
      .then((fit_scale) => {
        if (fit_scale === null) {
          // no model size to fit against; just show the rig at current scale
          return add_preview_skeleton(this._main_scene, skeleton_type, this.hand_skeleton_type(), this.skeleton_scale())
            .then(() => undefined)
        }
        // update_skeleton_scale_to_value reloads the preview at the fit scale
        this.update_skeleton_scale_to_value(fit_scale)
        return undefined
      })
      .then(() => { this.allow_proceeding_to_next_step(true) })
      .catch((err) => { console.error('error auto-fitting skeleton: ', err) })
  }

  public load_skeleton_file (file_path: string): void {
    // load skeleton from GLB file
    this.loader.load(file_path, (gltf: GLTFResult) => {
      // traverse scene and find first bone object
      // we will go to the parent and mark that as the original armature
      let armature_found = false
      let original_armature: Object3D = new Object3D()

      gltf.scene.traverse((child: Object3D) => {
        // Note: three.js removes punctuation characters from names object names like `-` and `.` for sanitization
        // Our 3D source files will need to account fo this if we are relying on that later for parsing
        // https://discourse.threejs.org/t/avoid-dots-and-colons-being-deleted-from-models-name/15304/2
        if (child.type === 'Bone' && !armature_found) {
          armature_found = true

          if (child.parent != null) {
            original_armature = child.parent
          } else {
            console.warn('could not find armature parent while loading skeleton')
          }
        }
      })

      this.loaded_armature = original_armature.clone()
      this.loaded_armature.name = 'Loaded Armature'

      // Apply hand skeleton modifications for human skeletons
      if (this.skeleton_file_path() === SkeletonType.Human) {
        const helper = new HandHelper()
        helper.modify_hand_skeleton(this.loaded_armature, this.hand_skeleton_type())
      }

      this.loaded_armature.position.set(0, 0, 0)
      this.loaded_armature.updateWorldMatrix(true, true)

      // scale the armature to what we picked using the scale slider/preview
      this.loaded_armature.scale.set(this.skeleton_scale(), this.skeleton_scale(), this.skeleton_scale())

      this.dispatchEvent(new CustomEvent('skeletonLoaded', { detail: this.loaded_armature }))
    })
  }

  private has_select_skeleton_ui_option (): boolean {
    return this.ui.dom_skeleton_drop_type?.options[0].value === 'select-skeleton'
  }

  private allow_proceeding_to_next_step (allow: boolean): void {
    const btn = this.ui.dom_load_skeleton_button as HTMLButtonElement | null
    if (!btn) return
    btn.disabled = !allow // disable when not allowed
  }

  // returns a skeleton object that has been baked (applied) for scale
  public armature (): Object3D<Object3DEventMap> {
    return this.bake_scale_for_armature(this.loaded_armature)
  }

  // this does not mutate armature that goes in
  // bakes scale into bone positions and resets scale to 1
  private bake_scale_for_armature (armature: Object3D): Object3D {
    const scale = armature.scale.x // assumes uniform scale

    const cloned_armature: Object3D = armature.clone()

    // bake scale into all child bone positions
    if (scale !== 1) {
      cloned_armature.traverse((obj) => {
        if (obj instanceof Object3D && obj !== cloned_armature) {
          obj.position.multiplyScalar(scale)
        }
      })
      cloned_armature.scale.set(1, 1, 1)
    }

    cloned_armature.updateMatrixWorld(true)
    return cloned_armature
  }

  private toggle_ui_hand_skeleton_options (): void {
    if (this.ui.dom_skeleton_drop_type === null || this.ui.dom_hand_skeleton_options === null) {
      return
    }

    const config = RigConfig.by_skeleton_type(this.skeleton_file_path())
    if (config?.has_hand_options === true) {
      this.ui.dom_hand_skeleton_options.style.display = 'flex'
    } else {
      this.ui.dom_hand_skeleton_options.style.display = 'none'
    }
  }
}
