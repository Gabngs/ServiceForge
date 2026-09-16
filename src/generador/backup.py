"""Backup de la BD objetivo — funcionalidad secundaria del programa.

Envuelve `mysqldump` como proceso hijo. Se dispara manualmente desde la GUI
(no hay scheduler acá, a diferencia de un backup manager con tareas
programadas) — normalmente antes de generar una migración o de correr
`migrate` sobre la conexión analizada.

La contraseña se pasa por la variable de entorno `MYSQL_PWD`, no como
argumento `--password=...` de línea de comandos — así no queda visible en la
lista de procesos del sistema mientras el dump corre.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Literal

from .db import ConnectionConfig

BackupScope = Literal["full", "schema", "data"]

_SCOPE_FLAGS: dict[BackupScope, list[str]] = {
    "full": [],
    "schema": ["--no-data"],
    "data": ["--no-create-info"],
}


class MysqldumpNotFoundError(RuntimeError):
    pass


class BackupFailedError(RuntimeError):
    def __init__(self, message: str, stderr: str) -> None:
        super().__init__(message)
        self.stderr = stderr


def find_mysqldump(explicit_path: str | None = None) -> str:
    if explicit_path:
        return explicit_path
    found = shutil.which("mysqldump")
    if not found:
        raise MysqldumpNotFoundError(
            "No se encontró 'mysqldump' en el PATH. Instalá el cliente de MySQL "
            "o indicá la ruta completa al ejecutable."
        )
    return found


def run_backup(
    config: ConnectionConfig,
    output_path: Path,
    *,
    scope: BackupScope = "full",
    mysqldump_path: str | None = None,
    timeout: int = 600,
    on_output: Callable[[str], None] | None = None,
) -> Path:
    """Ejecuta mysqldump y escribe el resultado en `output_path`. Retorna la ruta.

    `scope` controla qué se vuelca: "full" (estructura + datos, default),
    "schema" (solo estructura, `--no-data`) o "data" (solo datos, `--no-create-info`).

    Corre con `--verbose`: mysqldump va reportando por stderr en qué tabla está
    parado ("Retrieving table structure...", "Retrieving rows..."), línea que se
    reenvía a `on_output` si se pasa un callback — así se puede mostrar progreso
    en vivo y confirmar que efectivamente está volcando datos, no solo estructura.
    """
    if scope not in _SCOPE_FLAGS:
        raise ValueError(f"scope inválido: {scope!r} (esperado: {', '.join(_SCOPE_FLAGS)})")

    executable = find_mysqldump(mysqldump_path)

    env = os.environ.copy()
    env["MYSQL_PWD"] = config.password

    def build_command(extra: list[str] | None = None) -> list[str]:
        command = [
            executable,
            "-h", config.host,
            "-P", str(config.port),
            "-u", config.user,
            "--single-transaction",
            "--verbose",
            *_SCOPE_FLAGS[scope],
        ]
        if scope != "data":
            # Los procedimientos/funciones son esquema, no datos — no tiene sentido
            # volcarlos en un backup "solo datos".
            command.append("--routines")
        if extra:
            command.extend(extra)
        command.append(config.database)
        return command

    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _dump(command: list[str]) -> tuple[int, str]:
        stderr_lines: list[str] = []
        with output_path.open("wb") as out_file:
            process = subprocess.Popen(
                command,
                stdout=out_file,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stderr is not None
            try:
                for line in process.stderr:
                    line = line.rstrip("\n")
                    stderr_lines.append(line)
                    if on_output:
                        on_output(line)
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise
        return process.returncode, "\n".join(stderr_lines)

    returncode, stderr = _dump(build_command())

    # Clientes mysqldump 8.0+ piden por defecto information_schema.COLUMN_STATISTICS
    # (histogramas) para el dump. Servidores MySQL <8.0 o MariaDB no tienen esa tabla
    # y el dump falla con error 1109. Se reintenta desactivando esa consulta.
    if returncode != 0 and "COLUMN_STATISTICS" in stderr:
        if on_output:
            on_output("El servidor no soporta --column-statistics, reintentando sin histogramas...")
        returncode, stderr = _dump(build_command(["--column-statistics=0"]))

    if returncode != 0:
        output_path.unlink(missing_ok=True)
        raise BackupFailedError(f"mysqldump terminó con código {returncode}", stderr)

    return output_path
