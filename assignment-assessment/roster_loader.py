"""Lectura de `roster/roster.csv` para la evaluación.

Es el mismo CSV que usa `assignment-preparation` —un export de planilla, con
columnas fantasma al final y fechas chilenas `d/m/yyyy`—, pero acá se lee para
saber qué repositorios existen y quién los escribió, no para crear nada. El
código no se comparte entre los dos proyectos a propósito (ver AGENTS.md).

Este módulo se llama `roster_loader` y no `roster` para no colisionar con el
directorio `roster/` de la raíz.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import config

COL_NUMERO = "#"
COL_NOMBRE = "Nombre"
COL_GITHUB = "Usuario GitHub"
COL_EMAIL = "Email"
COL_GRUPO = "Grupo"
COL_AYUDANTE = "Ayudante"

REQUIRED_COLUMNS = (COL_NOMBRE, COL_GRUPO)


class RosterError(Exception):
    """El roster no se puede interpretar; abortar antes de clonar."""


@dataclass(frozen=True)
class Student:
    numero: str
    nombre: str
    github: str  # puede venir vacío
    grupo: int
    fila: int  # línea del CSV, para reportar errores

    # El RUT y el correo se leen pero no se almacenan: son datos sensibles y la
    # evaluación no los necesita para nada.

    @property
    def tiene_github(self) -> bool:
        return bool(self.github)


@dataclass
class Group:
    numero: int
    ayudante: str
    members: list[Student] = field(default_factory=list)

    @property
    def repo_name(self) -> str:
        return config.repo_name(self.numero)

    @property
    def repo_url(self) -> str:
        return config.repo_url(self.numero)


def _clean(value: str | None) -> str:
    """Los campos traen espacios accidentales (`LETELIER /CASTRO`)."""
    return (value or "").strip()


def load_groups(path: Path | None = None) -> tuple[list[Group], list[str]]:
    """Devuelve (grupos ordenados por número, advertencias)."""
    path = Path(path) if path else config.ROSTER_PATH
    warnings: list[str] = []
    por_grupo: dict[int, list[Student]] = {}
    ayudantes: dict[int, set[str]] = {}

    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RosterError(f"{path} está vacío.")

        faltantes = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if faltantes:
            raise RosterError(
                f"{path}: faltan columnas requeridas: {', '.join(faltantes)}"
            )

        # `fila` parte en 2 porque la 1 es el encabezado.
        for fila, raw in enumerate(reader, start=2):
            nombre = _clean(raw.get(COL_NOMBRE))
            grupo_raw = _clean(raw.get(COL_GRUPO))
            if not nombre and not grupo_raw:
                continue  # fila en blanco de la planilla

            if not grupo_raw.isdigit():
                raise RosterError(
                    f"Fila {fila} ({nombre!r}): grupo inválido {grupo_raw!r}."
                )

            grupo = int(grupo_raw)
            por_grupo.setdefault(grupo, []).append(
                Student(
                    numero=_clean(raw.get(COL_NUMERO)),
                    nombre=nombre,
                    github=_clean(raw.get(COL_GITHUB)),
                    grupo=grupo,
                    fila=fila,
                )
            )
            ayudante = _clean(raw.get(COL_AYUDANTE))
            if ayudante:
                ayudantes.setdefault(grupo, set()).add(ayudante)

    if not por_grupo:
        raise RosterError(f"{path}: no se encontró ninguna fila de alumno.")

    groups: list[Group] = []
    for numero in sorted(por_grupo):
        del_grupo = sorted(ayudantes.get(numero, ()))
        if len(del_grupo) > 1:
            warnings.append(
                f"Grupo {numero}: ayudantes distintos entre integrantes "
                f"({', '.join(del_grupo)}). Se usa {del_grupo[0]}."
            )
        groups.append(
            Group(
                numero=numero,
                ayudante=del_grupo[0] if del_grupo else "",
                members=sorted(por_grupo[numero], key=lambda s: s.nombre),
            )
        )

    numeros = [g.numero for g in groups]
    huecos = sorted(set(range(1, max(numeros) + 1)) - set(numeros))
    if huecos:
        warnings.append(
            f"Números de grupo sin integrantes en el roster: "
            f"{', '.join(str(n) for n in huecos)}."
        )

    return groups, warnings
