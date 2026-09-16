"""Preferencias persistidas del programa (tema, etc.) — no confundir con la
configuración de conexión a la BD objetivo, que nunca se persiste con la
contraseña en texto plano y vive solo en memoria durante la sesión.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_THEME = "dark"
VALID_THEMES = ("dark", "light")


@dataclass
class Settings:
    theme: str = DEFAULT_THEME  # "dark" | "light"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or default_settings_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        theme = data.get("theme", DEFAULT_THEME)
        if theme not in VALID_THEMES:
            theme = DEFAULT_THEME
        return cls(theme=theme)

    def save(self, path: Path | None = None) -> None:
        path = path or default_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def default_settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ServiceForge" / "settings.json"
