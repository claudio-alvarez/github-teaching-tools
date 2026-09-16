"""Configuración de la herramienta de evaluación.

Lo específico de un curso (organización, convención de nombres de repos, roster,
solución canónica) vive en `course.toml`, en la raíz del repositorio, no acá.
Este módulo lo carga y expone sus valores como constantes, igual que hace
`assignment-preparation` con el suyo; el código no se comparte entre proyectos.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# El curso y el roster viven en la raíz porque los comparten las dos
# herramientas; las salidas de esta corrida son propias de este directorio.
REPO_ROOT = BASE_DIR.parent

DEFAULT_COURSE_FILE = REPO_ROOT / "course.toml"
EXAMPLE_COURSE_FILE = REPO_ROOT / "course.example.toml"

DEFAULT_ROSTER_PATH = REPO_ROOT / "roster" / "roster.csv"
LOGS_DIR = BASE_DIR / "logs"
STATE_PATH = BASE_DIR / "state" / "clones.json"

# Nombre del manifiesto que queda dentro del directorio de clones. Es la
# interfaz entre `clone_repos.py` y la skill de preguntas de revisión.
MANIFEST_NAME = "clones.json"

# --- Valores del curso (poblados por load_course) ----------------------------

COURSE_FILE: Path
COURSE_NAME: str
COURSE_SLUG: str
ORG: str
TEMPLATE_OWNER: str
TEMPLATE_REPO: str
ROSTER_PATH: Path
REPO_NAME_FORMAT: str

CLONES_DIR: Path
OUTPUT_DIR: Path
ASSIGNMENT_SLUG: str
CANONICAL_REPO: Path | None
CANONICAL_BRANCH: str
CANONICAL_BASE: str


class ConfigError(Exception):
    """`course.toml` falta o está mal formado; abortar antes de clonar nada."""


def _require(seccion: dict, clave: str, ruta: Path, contexto: str) -> str:
    valor = seccion.get(clave)
    if valor in (None, ""):
        raise ConfigError(f"{ruta}: falta `{contexto}.{clave}`.")
    return valor


def display_path(path: Path) -> str:
    """Ruta relativa al directorio actual si se puede; si no, absoluta."""
    absoluta = Path(path).resolve()
    try:
        return str(absoluta.relative_to(Path.cwd()))
    except ValueError:
        pass
    relativa = os.path.relpath(absoluta, Path.cwd())
    # Una ruta a varios niveles hacia arriba se lee peor que la absoluta.
    return relativa if relativa.count("..") <= 2 else str(absoluta)


def _resolve(valor: str, base: Path) -> Path:
    """Expande `~`, variables de entorno y rutas relativas contra `base`."""
    path = Path(os.path.expandvars(str(valor))).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _slug_from_name(name: str) -> str:
    """`ICC3201-202620 · Bases de Datos` -> `ICC3201-202620`.

    El slug nombra el directorio de salida, así que tiene que ser corto y sin
    espacios. Si el curso no declara uno, se toma el primer token del nombre.
    """
    primero = re.split(r"[\s·|/]+", name.strip())[0]
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "-", primero).strip("-")
    return limpio or "curso"


# Palabras con las que termina el nombre de un repo de grupo y que, por lo tanto,
# no forman parte del nombre de la tarea.
_PALABRAS_DE_GRUPO = {"grupo", "grupos", "group", "groups", "equipo", "team", "g"}


def _slug_from_repo_format(fmt: str) -> str:
    """`tarea-1-grupo-{n:02d}` -> `tarea-1`.

    El nombre de los repositorios suele traer la tarea adelante, así que sirve
    de default razonable para el directorio de salida. Si el formato es solo
    `grupo-{n}`, no hay nada que extraer y devuelve cadena vacía.
    """
    literal = fmt.split("{", 1)[0]
    partes = [p for p in re.split(r"[-_. ]+", literal) if p]
    while partes and partes[-1].lower() in _PALABRAS_DE_GRUPO:
        partes.pop()
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "-", "-".join(partes)).strip("-")
    return limpio


def assignment_slug(explicito: str | None = None) -> str:
    """Nombre de la tarea que da nombre al directorio de minutas.

    Orden: lo que pase el operador, lo que declare `course.toml`, lo que se
    pueda deducir del nombre de los repositorios, y `tarea` como último recurso.
    """
    for candidato in (explicito, ASSIGNMENT_SLUG,
                      _slug_from_repo_format(REPO_NAME_FORMAT)):
        if candidato:
            limpio = re.sub(r"[^A-Za-z0-9._-]+", "-", str(candidato).strip()).strip("-")
            if limpio:
                return limpio
    return "tarea"


def output_dir(tarea: str | None = None) -> Path:
    """`output/<sigla-curso>/<tarea>/`, donde van las minutas de cada grupo.

    Un curso usa esta herramienta varias veces al semestre, contra tareas
    distintas: sin el nivel de la tarea, la segunda corrida pisaría a la primera.
    """
    return OUTPUT_DIR / COURSE_SLUG / assignment_slug(tarea)


def load_course(path: Path | None = None) -> None:
    """Carga `course.toml` y publica sus valores como constantes del módulo."""
    global COURSE_FILE, COURSE_NAME, COURSE_SLUG, ORG
    global TEMPLATE_OWNER, TEMPLATE_REPO, ROSTER_PATH, REPO_NAME_FORMAT
    global CLONES_DIR, OUTPUT_DIR, ASSIGNMENT_SLUG
    global CANONICAL_REPO, CANONICAL_BRANCH, CANONICAL_BASE

    path = Path(path) if path else DEFAULT_COURSE_FILE
    if not path.exists():
        raise ConfigError(
            f"No existe {display_path(path)}. Crea el archivo copiando la "
            f"plantilla:\n"
            f"  cp {display_path(EXAMPLE_COURSE_FILE)} {display_path(path)}"
        )

    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: TOML inválido — {error}") from error

    curso = data.get("course") or {}
    repos = data.get("repos") or {}
    evaluacion = data.get("assessment") or {}

    COURSE_FILE = path
    COURSE_NAME = _require(curso, "name", path, "course")
    COURSE_SLUG = curso.get("slug") or _slug_from_name(COURSE_NAME)
    ORG = _require(curso, "org", path, "course")
    TEMPLATE_OWNER = curso.get("template_owner") or ORG
    TEMPLATE_REPO = curso.get("template_repo") or ""

    roster = curso.get("roster")
    ROSTER_PATH = _resolve(roster, REPO_ROOT) if roster else DEFAULT_ROSTER_PATH

    REPO_NAME_FORMAT = repos.get("name_format") or "grupo-{n:02d}"

    # Los clones traen código de alumnos y pueden ser muchos gigabytes: el
    # operador decide dónde viven. `course.toml` fija el default del curso y
    # `--dest` manda por sobre él.
    clones = evaluacion.get("clones") or f"clones/{COURSE_SLUG}"
    CLONES_DIR = _resolve(clones, BASE_DIR)

    salida = evaluacion.get("output") or "output"
    OUTPUT_DIR = _resolve(salida, BASE_DIR)

    # La misma herramienta se corre varias veces en un curso, contra tareas
    # distintas: el nombre de la tarea separa las minutas de cada una.
    ASSIGNMENT_SLUG = (evaluacion.get("assignment") or "").strip()

    canonico = evaluacion.get("canonical_repo")
    CANONICAL_REPO = _resolve(canonico, REPO_ROOT) if canonico else None
    CANONICAL_BRANCH = evaluacion.get("canonical_branch") or ""
    CANONICAL_BASE = evaluacion.get("canonical_base") or ""

    if CANONICAL_REPO and not CANONICAL_BRANCH:
        raise ConfigError(
            f"{path}: `assessment.canonical_repo` está definido pero falta "
            f"`assessment.canonical_branch` (la rama con la solución)."
        )

    # Falla acá y no a mitad de una corrida si el formato tiene placeholders malos.
    try:
        repo_name(1)
    except (KeyError, IndexError, ValueError) as error:
        raise ConfigError(
            f"{path}: `repos.name_format` inválido — {error}. "
            f"Placeholders disponibles: {{n}} y {{course_name}}."
        ) from error


def repo_name(group_number: int) -> str:
    """`1` -> `grupo-01`, según `repos.name_format`. El mismo nombre que creó
    `assignment-preparation`: por eso el formato se lee del mismo archivo."""
    return REPO_NAME_FORMAT.format(n=group_number, course_name=COURSE_NAME)


def repo_url(group_number: int) -> str:
    return f"https://github.com/{ORG}/{repo_name(group_number)}"


# Carga por defecto al importar. Si no existe `course.toml`, el error se levanta
# recién cuando el entrypoint llama a load_course() y puede reportarlo bien.
try:
    load_course()
except ConfigError:
    pass
