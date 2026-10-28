#!/usr/bin/env python3
"""Credenciales de base de datos y variables de despliegue, una fila por grupo.

Lee `course.toml` y el roster, y escribe en `data/` un CSV con lo que cada
grupo necesita para desplegar: el rol y la base de PostgreSQL, su contraseña,
el subdominio, el puerto de loopback y la cadena de conexión ya armada.

Es **idempotente en las contraseñas**: si el archivo de salida ya existe, las
conserva y solo genera las de los grupos que no estaban. Una contraseña nueva
para un grupo cuyo rol ya existe en el servidor deja ese despliegue sin base.

    python3 generar_credenciales_bd.py --salida credenciales-entrega3.csv
    python3 generar_credenciales_bd.py --salida credenciales-entrega3.csv --sql

`--sql` imprime además el guion de PostgreSQL que crea los roles y las bases.
No lo ejecuta: se revisa y se corre a mano en el servidor.

El resultado queda en `data/`, que no se versiona. Solo biblioteca estándar.
"""

from __future__ import annotations

import argparse
import csv
import secrets
import string
import sys
import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_COURSE_FILE = REPO_ROOT / "course.toml"
DEFAULT_ROSTER = REPO_ROOT / "roster" / "roster.csv"

COL_NOMBRE, COL_GRUPO = "Nombre", "Grupo"

# Alfanumérica a propósito: la contraseña viaja dentro de una URL de conexión y
# dentro de comillas en SQL, y un símbolo mal escapado en cualquiera de los dos
# produce un fallo que no se parece a un problema de credenciales.
ALFABETO = string.ascii_letters + string.digits
LARGO_CONTRASENA = 32

COLUMNAS = (
    "grupo",
    "group_id",
    "db_user",
    "db_password",
    "db_name",
    "host_port",
    "public_origin",
    "database_url",
)


class ErrorDatos(Exception):
    pass


def cargar_curso(ruta: Path) -> dict:
    if not ruta.exists():
        raise ErrorDatos(f"No existe {ruta}. Copia course.example.toml y complétalo.")
    with open(ruta, "rb") as handle:
        data = tomllib.load(handle)
    curso = data.get("course") or {}
    despliegue = data.get("deploy") or {}
    if not curso.get("org"):
        raise ErrorDatos(f"{ruta}: falta `course.org`.")
    faltan = [c for c in ("db_host", "db_port", "domain", "port_base", "user_prefix")
              if not despliegue.get(c)]
    if faltan:
        raise ErrorDatos(f"{ruta}: falta la sección [deploy] con {', '.join(faltan)}.")
    roster = curso.get("roster")
    return {
        "org": curso["org"],
        "roster": (REPO_ROOT / roster).resolve() if roster else DEFAULT_ROSTER,
        **despliegue,
    }


def grupos_del_roster(ruta: Path) -> list[int]:
    if not ruta.exists():
        raise ErrorDatos(f"No existe el roster {ruta}.")
    with open(ruta, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        faltan = [c for c in (COL_NOMBRE, COL_GRUPO) if c not in (reader.fieldnames or [])]
        if faltan:
            raise ErrorDatos(f"{ruta}: faltan columnas {', '.join(faltan)}.")
        numeros = set()
        for n, raw in enumerate(reader, start=2):
            grupo = (raw.get(COL_GRUPO) or "").strip()
            nombre = (raw.get(COL_NOMBRE) or "").strip()
            if not grupo and not nombre:
                continue
            if not grupo.isdigit():
                raise ErrorDatos(f"{ruta}, fila {n} ({nombre!r}): grupo inválido {grupo!r}.")
            numeros.add(int(grupo))
    if not numeros:
        raise ErrorDatos(f"{ruta}: no hay ningún grupo.")
    return sorted(numeros)


def contrasenas_existentes(destino: Path) -> dict[int, str]:
    """Lo ya emitido, para no invalidar roles que el servidor ya tiene."""
    if not destino.exists():
        return {}
    with open(destino, newline="", encoding="utf-8-sig") as handle:
        return {
            int(fila["grupo"]): fila["db_password"]
            for fila in csv.DictReader(handle)
            if (fila.get("grupo") or "").strip().isdigit() and fila.get("db_password")
        }


def fila_de_grupo(numero: int, curso: dict, contrasena: str) -> dict:
    identificador = f"{numero:02d}"
    usuario = f"{curso['user_prefix']}_grupo{identificador}"
    origen = f"https://grupo{identificador}.{curso['domain']}"
    puerto = curso["port_base"] + numero
    return {
        "grupo": numero,
        "group_id": identificador,
        "db_user": usuario,
        "db_password": contrasena,
        "db_name": usuario,
        "host_port": puerto,
        "public_origin": origen,
        "database_url": (
            f"postgresql+psycopg://{usuario}:{contrasena}"
            f"@{curso['db_host']}:{curso['db_port']}/{usuario}?sslmode=require"
        ),
    }


def guion_sql(filas: list[dict]) -> str:
    lineas = [
        "-- Roles y bases de los grupos. Revisar antes de ejecutar.",
        "-- DROP DATABASE destruye el contenido: comentar esas líneas para no perder",
        "-- lo que un grupo ya haya cargado.",
        "\\set ON_ERROR_STOP on",
        "",
    ]
    for fila in filas:
        lineas += [
            f"-- grupo {fila['group_id']}  {fila['public_origin']}",
            f"DROP DATABASE IF EXISTS {fila['db_name']};",
            f"DROP ROLE IF EXISTS {fila['db_user']};",
            f"CREATE ROLE {fila['db_user']} LOGIN PASSWORD '{fila['db_password']}';",
            f"CREATE DATABASE {fila['db_name']} OWNER {fila['db_user']};",
            "",
        ]
    return "\n".join(lineas)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--salida", required=True, metavar="ARCHIVO.csv",
                        help="nombre del CSV a escribir dentro de data/.")
    parser.add_argument("--course", type=Path, default=DEFAULT_COURSE_FILE,
                        help="archivo del curso (course.toml).")
    parser.add_argument("--roster", type=Path, default=None,
                        help="CSV del roster (por defecto, el del curso).")
    parser.add_argument("--sql", type=Path, nargs="?", const=Path("-"), metavar="ARCHIVO.sql",
                        help="escribe también el guion SQL; sin argumento, lo imprime.")
    parser.add_argument("--rotar", action="store_true",
                        help="genera contraseñas nuevas aunque ya existan. Invalida los roles del servidor.")
    opts = parser.parse_args(argv)

    try:
        curso = cargar_curso(opts.course)
        numeros = grupos_del_roster(opts.roster or curso["roster"])
        DATA_DIR.mkdir(exist_ok=True)
        destino = DATA_DIR / Path(opts.salida).name

        previas = {} if opts.rotar else contrasenas_existentes(destino)
        filas = []
        nuevas = 0
        for numero in numeros:
            contrasena = previas.get(numero)
            if not contrasena:
                contrasena = "".join(secrets.choice(ALFABETO) for _ in range(LARGO_CONTRASENA))
                nuevas += 1
            filas.append(fila_de_grupo(numero, curso, contrasena))

        with open(destino, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNAS)
            writer.writeheader()
            writer.writerows(filas)

        conservadas = len(filas) - nuevas
        print(f"Escrito {destino.relative_to(REPO_ROOT)}: {len(filas)} grupo(s), "
              f"{nuevas} contraseña(s) nueva(s), {conservadas} conservada(s).")

        if opts.sql:
            sql = guion_sql(filas)
            if str(opts.sql) == "-":
                print()
                print(sql)
            else:
                ruta_sql = DATA_DIR / Path(opts.sql).name
                ruta_sql.write_text(sql, encoding="utf-8")
                print(f"Escrito {ruta_sql.relative_to(REPO_ROOT)}.")

        print("Recuerda: data/ no se versiona, y ahí quedan contraseñas en claro.")
        return 0
    except ErrorDatos as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
