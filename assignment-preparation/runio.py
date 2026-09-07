"""Salidas en disco de una corrida: el log y el archivo de estado.

Lo comparten los dos entrypoints (`create_repos.py` y `resend_invitations.py`)
porque las dos corridas se reportan igual: todo lo que se imprime queda también
en `logs/`, y lo que se escribió en GitHub queda en un JSON de estado propio de
cada herramienta.
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


def load_state(path: Path, key: str = "repos") -> dict:
    """Estado previo, o uno vacío si el archivo falta o está corrupto.

    Un JSON ilegible no puede abortar la corrida: el estado es un registro de
    apoyo, no la fuente de verdad. La verdad se consulta a GitHub.
    """
    if not path.exists():
        return {key: {}}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {key: {}}
    data.setdefault(key, {})
    return data


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
