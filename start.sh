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

# En Windows, "python" puede resolver al stub de la Microsoft Store (no un
# intérprete real) aunque exista en el PATH -- probamos que ejecute antes de
# confiar en el nombre, y si no, caemos al "py launcher".
if command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
  PYTHON_BIN=python
elif command -v py >/dev/null 2>&1; then
  PYTHON_BIN=py
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  echo "[start.sh] no se encontró un intérprete de Python funcional (python/py/python3)." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "[start.sh] no existe .venv — creándolo…"
  "$PYTHON_BIN" -m venv .venv
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
