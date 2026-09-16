"""Salidas en disco de una corrida: el log y los archivos JSON.

Mismo patrón que en `assignment-preparation`: todo lo que se imprime queda
también en `logs/`, y lo que quedó en disco se registra en un JSON.
"""

from __future__ import annotations

import json
from pathlib import Path


class Logger:
    """Escribe a stdout y, si se le da una ruta, también al log de la corrida."""

    def __init__(self, log_path: Path | None):
        self.handle = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(log_path, "a", encoding="utf-8")

    def __call__(self, message: str = ""):
        print(message)
        if self.handle:
            self.handle.write(message + "\n")
            self.handle.flush()

    def close(self):
        if self.handle:
            self.handle.close()


def load_json(path: Path, default: dict | None = None) -> dict:
    """Contenido del JSON, o `default` si el archivo falta o está corrupto.

    Un archivo ilegible no puede abortar la corrida: es un registro de apoyo, no
    la fuente de verdad. La verdad está en los repositorios clonados.
    """
    if not path.exists():
        return dict(default or {})
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return dict(default or {})
    return data if isinstance(data, dict) else dict(default or {})


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
