"""Auto-restart dev runner para la GUI.

PySide6 no soporta hot-reload real de widgets en caliente, así que en vez de
eso: corre `src/main.py` como subproceso, vigila el mtime de los .py/.j2 bajo
src/, y cuando detecta un cambio mata la ventana vieja y levanta una nueva —
sin tener que cerrar/reabrir el proceso wrapper a mano en cada edición.

Sin dependencias extra (solo stdlib) para no agregar watchdog a
requirements-dev.txt por un script de desarrollo.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
WATCH_SUFFIXES = {".py", ".j2"}
POLL_SECONDS = 0.75


def snapshot() -> dict[Path, float]:
    return {
        p: p.stat().st_mtime
        for p in SRC.rglob("*")
        if p.suffix in WATCH_SUFFIXES and p.is_file()
    }


def launch() -> subprocess.Popen:
    print("[dev_watch] levantando la GUI…", flush=True)
    return subprocess.Popen([sys.executable, str(SRC / "main.py")])


def main() -> None:
    proc = launch()
    last = snapshot()
    try:
        while True:
            time.sleep(POLL_SECONDS)

            if proc.poll() is not None:
                # El usuario cerró la ventana (o crasheó) — no hay nada que
                # vigilar hasta el próximo cambio detectado.
                current = snapshot()
                if current != last:
                    last = current
                    proc = launch()
                    continue
                print("[dev_watch] la ventana se cerró. Ctrl+C para salir, o guardá un cambio para relanzar.", flush=True)
                while proc.poll() is not None:
                    time.sleep(POLL_SECONDS)
                    current = snapshot()
                    if current != last:
                        last = current
                        proc = launch()
                        break
                continue

            current = snapshot()
            if current != last:
                last = current
                print("[dev_watch] cambio detectado — reiniciando…", flush=True)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                proc = launch()
    except KeyboardInterrupt:
        print("\n[dev_watch] saliendo…", flush=True)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
