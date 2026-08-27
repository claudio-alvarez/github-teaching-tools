"""Lectura y validación de `roster/roster.csv`.

El CSV es un export de planilla: trae columnas fantasma al final con una tabla
lateral (leyenda de ayudantes) y fechas en formato chileno `d/m/yyyy`.
Ver AGENTS.md §3 para el detalle de las rarezas del archivo.

Este módulo se llama `roster_loader` y no `roster` para no colisionar con el
directorio `roster/`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import config

DATE_FORMAT = "%d/%m/%Y"  # día primero: 21/8/2026 es 21 de agosto

COL_NUMERO = "#"
COL_NOMBRE = "Nombre"
COL_GITHUB = "Usuario GitHub"
COL_EMAIL = "Email"
COL_GRUPO = "Grupo"
COL_TAMANO = "Tamaño Grupo"
COL_FECHA = "Fecha creación repositorio"
COL_AYUDANTE = "Ayudante"

REQUIRED_COLUMNS = (
    COL_NUMERO,
    COL_NOMBRE,
    COL_GITHUB,
    COL_GRUPO,
    COL_TAMANO,
    COL_FECHA,
)


class RosterError(Exception):
    """El roster no se puede interpretar; abortar antes de tocar GitHub."""


@dataclass(frozen=True)
class Student:
    numero: str
    nombre: str
    github: str  # puede venir vacío
    email: str  # puede venir vacío
    grupo: int
    fila: int  # línea del CSV, para reportar errores

    # El RUT se lee pero no se almacena: es dato sensible y no lo necesitamos
    # para ninguna operación de GitHub (AGENTS.md §7).

    @property
    def tiene_github(self) -> bool:
        return bool(self.github)


@dataclass
class Group:
    numero: int
    fecha_creacion: date
    ayudante: str
    tamano_declarado: int
    members: list[Student] = field(default_factory=list)

    @property
    def repo_name(self) -> str:
        return config.repo_name(self.numero)

    @property
    def description(self) -> str:
        return config.repo_description(self.numero)

    @property
    def members_con_github(self) -> list[Student]:
        return [m for m in self.members if m.tiene_github]

    @property
    def members_sin_github(self) -> list[Student]:
        return [m for m in self.members if not m.tiene_github]


def _clean(value: str | None) -> str:
    """Los campos traen espacios accidentales (`LETELIER /CASTRO`)."""
    return (value or "").strip()


def _parse_date(raw: str, fila: int) -> date:
    try:
        return datetime.strptime(raw, DATE_FORMAT).date()
    except ValueError as exc:
        raise RosterError(
            f"Fila {fila}: fecha inválida {raw!r}. Se espera formato d/m/yyyy."
        ) from exc


@dataclass(frozen=True)
class _Row:
    """Una fila del CSV ya limpia: el alumno más los metadatos de su grupo."""

    student: Student
    fecha: date
    ayudante: str
    tamano: str


def _read_rows(path: Path) -> list[_Row]:
    rows: list[_Row] = []
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
            # Las columnas fantasma del final quedan bajo la clave None (restkey)
            # o bajo la clave "" (encabezados vacíos duplicados). Se ignoran.
            nombre = _clean(raw.get(COL_NOMBRE))
            grupo_raw = _clean(raw.get(COL_GRUPO))
            if not nombre and not grupo_raw:
                continue  # fila en blanco de la planilla

            if not grupo_raw.isdigit():
                raise RosterError(
                    f"Fila {fila} ({nombre!r}): grupo inválido {grupo_raw!r}."
                )

            student = Student(
                numero=_clean(raw.get(COL_NUMERO)),
                nombre=nombre,
                github=_clean(raw.get(COL_GITHUB)),
                email=_clean(raw.get(COL_EMAIL)),
                grupo=int(grupo_raw),
                fila=fila,
            )
            rows.append(
                _Row(
                    student=student,
                    fecha=_parse_date(_clean(raw.get(COL_FECHA)), fila),
                    ayudante=_clean(raw.get(COL_AYUDANTE)),
                    tamano=_clean(raw.get(COL_TAMANO)),
                )
            )

    if not rows:
        raise RosterError(f"{path}: no se encontró ninguna fila de alumno.")
    return rows


def load_students(path: Path | None = None) -> list[Student]:
    return [row.student for row in _read_rows(path or config.ROSTER_PATH)]


def load_groups(path: Path | None = None) -> tuple[list[Group], list[str]]:
    """Devuelve (grupos ordenados por número, advertencias).

    Las advertencias son inconsistencias que no impiden operar pero que el
    profesor debe revisar. Los errores duros levantan RosterError.
    """
    path = path or config.ROSTER_PATH
    warnings: list[str] = []

    # Fecha, ayudante y tamaño se leen de cada fila —no solo de la primera del
    # grupo— para poder validar que sean consistentes entre integrantes.
    por_grupo: dict[int, list[_Row]] = {}
    for row in _read_rows(path):
        por_grupo.setdefault(row.student.grupo, []).append(row)

    groups: list[Group] = []
    for numero in sorted(por_grupo):
        entradas = por_grupo[numero]
        members = [e.student for e in entradas]

        fechas = {e.fecha for e in entradas}
        if len(fechas) > 1:
            warnings.append(
                f"Grupo {numero}: fechas de creación distintas entre integrantes "
                f"({', '.join(f.strftime(DATE_FORMAT) for f in sorted(fechas))}). "
                f"Se usa la más temprana."
            )
        fecha = min(fechas)

        ayudantes = {e.ayudante for e in entradas if e.ayudante}
        if len(ayudantes) > 1:
            warnings.append(
                f"Grupo {numero}: ayudantes distintos entre integrantes "
                f"({', '.join(sorted(ayudantes))})."
            )
        ayudante = sorted(ayudantes)[0] if ayudantes else ""

        tamanos = {e.tamano for e in entradas if e.tamano.isdigit()}
        tamano_declarado = int(sorted(tamanos)[0]) if tamanos else len(members)
        if len(tamanos) > 1:
            warnings.append(
                f"Grupo {numero}: 'Tamaño Grupo' inconsistente ({sorted(tamanos)})."
            )
        elif tamano_declarado != len(members):
            warnings.append(
                f"Grupo {numero}: 'Tamaño Grupo' declara {tamano_declarado} pero hay "
                f"{len(members)} integrante(s) en el roster."
            )

        for member in members:
            if not member.tiene_github:
                warnings.append(
                    f"Grupo {numero}: {member.nombre} (fila {member.fila}) no tiene "
                    f"usuario de GitHub en el roster; no se podrá invitar."
                )

        groups.append(
            Group(
                numero=numero,
                fecha_creacion=fecha,
                ayudante=ayudante,
                tamano_declarado=tamano_declarado,
                members=sorted(members, key=lambda s: s.nombre),
            )
        )

    numeros = [g.numero for g in groups]
    faltantes = sorted(set(range(1, max(numeros) + 1)) - set(numeros))
    if faltantes:
        warnings.append(
            f"Números de grupo sin integrantes en el roster: "
            f"{', '.join(str(n) for n in faltantes)}."
        )

    # Un mismo handle en dos grupos casi siempre es un error de tipeo en la planilla.
    vistos: dict[str, Student] = {}
    for group in groups:
        for member in group.members_con_github:
            clave = member.github.lower()
            if clave in vistos:
                warnings.append(
                    f"Usuario de GitHub {member.github!r} aparece en más de una fila "
                    f"({vistos[clave].nombre} y {member.nombre})."
                )
            else:
                vistos[clave] = member

    return groups, warnings
