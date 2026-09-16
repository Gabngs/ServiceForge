"""Service-Forge: motor de generación de boilerplate backend/frontend."""

import subprocess
from pathlib import Path


def _detect_version() -> str:
    """Resuelve la versión sin tener que escribirla a mano en cada release.

    Orden de prioridad:
    1. `_version.py` generado por CI al construir el `.exe` de un tag `v*`
       (ver .github/workflows/build-exe.yml) — el binario final no tiene
       `.git` adentro, así que no puede usar `git describe`.
    2. `git describe` contra el repo local — para correr desde código fuente
       (`start.sh`, `python src/main.py`) siempre refleja el tag/commit
       actual, incluyendo si hay cambios sin commitear (`-dirty`).
    3. Si ninguna de las dos funciona (repo sin tags, sin git instalado),
       un valor de último recurso.
    """
    try:
        from ._version import __version__ as pinned  # type: ignore[import-not-found]

        return pinned
    except ImportError:
        pass

    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().lstrip("v")
    except (OSError, subprocess.SubprocessError):
        pass

    return "0.0.0-dev"


__version__ = _detect_version()
