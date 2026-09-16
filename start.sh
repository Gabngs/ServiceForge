#!/usr/bin/env bash
# Levanta Service-Forge en local para probar cambios sin esperar el .exe del
# workflow de CI. PySide6 no soporta hot-reload real de la ventana, así que
# por defecto corre con auto-restart (scripts/dev_watch.py): vigila los
# .py/.j2 bajo src/ y, si detecta un cambio, cierra la ventana vieja y
# levanta una nueva sola — no hace falta parar y volver a correr el script
# a mano en cada edición.
#
# Uso:
#   ./start.sh          # auto-restart al detectar cambios (recomendado)
#   ./start.sh --once    # corre una sola vez, sin vigilar cambios
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d .venv ]; then
  echo "[start.sh] no existe .venv — creándolo…"
  python -m venv .venv
fi

if [ -f .venv/Scripts/activate ]; then
  # shellcheck disable=SC1091
  source .venv/Scripts/activate   # venv creado con el python.exe de Windows
else
  # shellcheck disable=SC1091
  source .venv/bin/activate       # Linux / macOS / WSL
fi

pip install -q -r requirements-dev.txt

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

if [ "${1:-}" = "--once" ]; then
  exec python src/main.py
else
  exec python scripts/dev_watch.py
fi
