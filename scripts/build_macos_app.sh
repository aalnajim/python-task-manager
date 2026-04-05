#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"
ICON_SCRIPT="$ROOT_DIR/scripts/generate_app_icon.py"
ICON_FILE="$ROOT_DIR/assets/icon/python-task-manager.icns"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing .venv Python. Create the virtual environment first." >&2
  exit 1
fi

if ! "$VENV_PY" -m PyInstaller --version >/dev/null 2>&1; then
  echo "Missing PyInstaller in .venv. Install dependencies first." >&2
  exit 1
fi

cd "$ROOT_DIR"

"$VENV_PY" "$ICON_SCRIPT"

rm -rf build dist

if [[ ! -f "$ICON_FILE" ]]; then
  echo "Missing $ICON_FILE. Icon generation failed." >&2
  exit 1
fi

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --onedir
  --name "Python Task Manager"
  --icon "$ICON_FILE"
  --osx-bundle-identifier "com.aalnajim.python-task-manager"
)

"$VENV_PY" -m PyInstaller "${PYINSTALLER_ARGS[@]}" task_app/__main__.py

echo
echo "Build complete:"
echo "  $ROOT_DIR/dist/Python Task Manager.app"
