#!/usr/bin/env python3
"""Arma la base de datos de mailmerge a partir del roster del curso.

Lee `course.toml` (organización y convención de nombres de repos) y el roster,
y escribe en `data/` un CSV con una fila por estudiante y las columnas que las
plantillas usan: `email`, `nombre`, `github`, `grupo`, `repo`, `url`, `ayudante`.
Opcionalmente cruza otro CSV (por ejemplo, credenciales) para agregar columnas.

    python3 roster_to_database.py --salida tarea2.csv
    python3 roster_to_database.py --salida tarea2.csv --group 4 --group 9
    python3 roster_to_database.py --salida credenciales.csv \
        --merge data/credenciales-brutas.csv --on email

El resultado queda en `data/`, que no se versiona. Solo biblioteca estándar.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_COURSE_FILE = REPO_ROOT / "course.toml"
DEFAULT_ROSTER = REPO_ROOT / "roster" / "roster.csv"

COL_NOMBRE, COL_GITHUB, COL_EMAIL, COL_GRUPO, COL_AYUDANTE = (
    "Nombre", "Usuario GitHub", "Email", "Grupo", "Ayudante")

COLUMNAS = ("email", "nombre", "github", "grupo", "repo", "url", "ayudante")


class ErrorDatos(Exception):
    pass


def cargar_curso(ruta: Path) -> dict:
    if not ruta.exists():
        raise ErrorDatos(f"No existe {ruta}. Copia course.example.toml y complétalo.")
    with open(ruta, "rb") as handle:
        data = tomllib.load(handle)
    curso = data.get("course") or {}
    repos = data.get("repos") or {}
    if not curso.get("org"):
        raise ErrorDatos(f"{ruta}: falta `course.org`.")
    roster = curso.get("roster")
    return {
        "nombre": curso.get("name", ""),
        "org": curso["org"],
        "name_format": repos.get("name_format") or "grupo-{n:02d}",
        "roster": (REPO_ROOT / roster).resolve() if roster else DEFAULT_ROSTER,
    }


def leer_roster(ruta: Path) -> list[dict]:
    if not ruta.exists():
        raise ErrorDatos(f"No existe el roster {ruta}.")
    with open(ruta, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        faltan = [c for c in (COL_NOMBRE, COL_EMAIL, COL_GRUPO) if c not in (reader.fieldnames or [])]
        if faltan:
            raise ErrorDatos(f"{ruta}: faltan columnas {', '.join(faltan)}.")
        filas = []
        for n, raw in enumerate(reader, start=2):
            nombre = (raw.get(COL_NOMBRE) or "").strip()
            grupo = (raw.get(COL_GRUPO) or "").strip()
            if not nombre and not grupo:
                continue
            if not grupo.isdigit():
                raise ErrorDatos(f"{ruta}, fila {n} ({nombre!r}): grupo inválido {grupo!r}.")
            filas.append({
                "nombre": nombre,
                "github": (raw.get(COL_GITHUB) or "").strip(),
                "email": (raw.get(COL_EMAIL) or "").strip(),
                "grupo": int(grupo),
                "ayudante": (raw.get(COL_AYUDANTE) or "").strip(),
            })
    return filas


def leer_merge(ruta: Path, clave: str) -> tuple[dict[str, dict], list[str]]:
    """CSV adicional indexado por `clave` (comparación sin mayúsculas ni espacios)."""
    if not ruta.exists():
        raise ErrorDatos(f"No existe {ruta}.")
    with open(ruta, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        campos = [c.strip() for c in (reader.fieldnames or [])]
        if clave not in campos:
            raise ErrorDatos(f"{ruta}: no tiene la columna `{clave}`. Columnas: {', '.join(campos)}.")
        indice = {}
        for raw in reader:
            fila = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            k = fila.get(clave, "").lower()
            if k:
                indice[k] = fila
    extra = [c for c in campos if c != clave]
    return indice, extra


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--salida", required=True, metavar="ARCHIVO.csv",
                        help="nombre del CSV a escribir dentro de data/.")
    parser.add_argument("--course", type=Path, default=DEFAULT_COURSE_FILE, help="archivo del curso (course.toml).")
    parser.add_argument("--roster", type=Path, default=None, help="CSV del roster (por defecto, el del curso).")
    parser.add_argument("--group", type=int, action="append", metavar="N", help="solo estos grupos. Repetible.")
    parser.add_argument("--merge", type=Path, default=None, metavar="CSV",
                        help="CSV adicional cuyas columnas se agregan a cada estudiante.")
    parser.add_argument("--on", default="email", metavar="COLUMNA",
                        help="columna del CSV adicional con la que se cruza: `email` o `github` (por defecto email).")
    parser.add_argument("--sin-email-ok", action="store_true",
                        help="no falla si un estudiante no tiene correo (la fila se omite y se avisa).")
    opts = parser.parse_args(argv)

    try:
        curso = cargar_curso(opts.course)
        filas = leer_roster(opts.roster or curso["roster"])
        if opts.group:
            filas = [f for f in filas if f["grupo"] in set(opts.group)]
        for f in filas:
            f["repo"] = curso["name_format"].format(n=f["grupo"], course_name=curso["nombre"])
            f["url"] = f"https://github.com/{curso['org']}/{f['repo']}"

        columnas = list(COLUMNAS)
        if opts.merge:
            if opts.on not in ("email", "github"):
                raise ErrorDatos("--on debe ser `email` o `github`.")
            indice, extra = leer_merge(opts.merge, opts.on)
            columnas += [c for c in extra if c not in columnas]
            sin_cruce = []
            for f in filas:
                datos = indice.get(f[opts.on].lower())
                if datos is None:
                    sin_cruce.append(f)
                else:
                    for c in extra:
                        f[c] = datos.get(c, "")
            if sin_cruce:
                print(f"AVISO: {len(sin_cruce)} estudiante(s) sin fila en {opts.merge.name} (cruce por {opts.on}):")
                for f in sin_cruce:
                    print(f"  grupo {f['grupo']:>2}  {f['nombre']}  {f[opts.on] or '(sin ' + opts.on + ')'}")

        sin_email = [f for f in filas if not f["email"]]
        if sin_email:
            print(f"AVISO: {len(sin_email)} estudiante(s) sin correo en el roster:")
            for f in sin_email:
                print(f"  grupo {f['grupo']:>2}  {f['nombre']}")
            if not opts.sin_email_ok:
                raise ErrorDatos("Completa los correos en el roster o usa --sin-email-ok para omitirlos.")
            filas = [f for f in filas if f["email"]]

        DATA_DIR.mkdir(exist_ok=True)
        destino = DATA_DIR / Path(opts.salida).name
        with open(destino, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columnas, extrasaction="ignore")
            writer.writeheader()
            for f in sorted(filas, key=lambda f: (f["grupo"], f["nombre"])):
                writer.writerow(f)
        print(f"Escrito {destino.relative_to(REPO_ROOT)}: {len(filas)} fila(s), columnas: {', '.join(columnas)}")
        print("Recuerda: data/ no se versiona. Prueba la plantilla con `mailmerge --dry-run` antes de enviar.")
        return 0
    except ErrorDatos as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
