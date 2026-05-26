#!/usr/bin/env bash
set -euo pipefail

export PATH=/home/ms/.nvm/versions/node/v22.22.2/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export RIGA_NO_DRACO=1

WORK_DIR=/tank/mesh2motion-animal-kingdom
mkdir -p "$WORK_DIR/output"
cd "$WORK_DIR/input"

for mesh in model-*.glb; do
  name="${mesh%.glb}"
  dest="$WORK_DIR/output/${name}-riganything.glb"
  if [ -f "$dest" ]; then
    echo "SKIP $mesh -> $dest"
    continue
  fi

  echo "=== RIG $mesh ==="
  /tank/RigAnything/scripts/inference_blender.sh "$PWD/$mesh" 0 50000

  out="/tank/RigAnything/outputs/${name}/${name}_simplified_rig.glb"
  if [ ! -f "$out" ]; then
    out="$(find "/tank/RigAnything/outputs/${name}" -maxdepth 1 -type f -name '*_simplified_rig.glb' | sort | head -n 1)"
  fi
  if [ ! -f "$out" ]; then
    echo "MISSING $out" >&2
    exit 2
  fi

  cp "$out" "$dest"
  echo "DONE $dest"
done
