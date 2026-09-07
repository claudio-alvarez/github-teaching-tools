"""Configuración de la herramienta.

Lo específico de un curso (organización, template, team, nombres de repo, texto
del issue de bienvenida) vive en `course.toml`, no acá. Este módulo lo carga y
expone sus valores como constantes de módulo, de modo que el resto del código
haga `config.ORG` sin conocer el formato del archivo.

`load_course(path)` permite apuntar a otro curso en runtime (flag `--course`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# El curso y el roster viven en la raíz del repositorio porque los comparten
# todas las herramientas; las salidas de esta corrida, en cambio, son propias.
REPO_ROOT = BASE_DIR.parent

DEFAULT_COURSE_FILE = REPO_ROOT / "course.toml"
EXAMPLE_COURSE_FILE = REPO_ROOT / "course.example.toml"

# --- Constantes de la herramienta (no dependen del curso) --------------------

DEFAULT_ROSTER_PATH = REPO_ROOT / "roster" / "roster.csv"
ROSTER_DIR = REPO_ROOT / "roster"
STATE_PATH = BASE_DIR / "state" / "created.json"
INVITATIONS_STATE_PATH = BASE_DIR / "state" / "invitations.json"
LOGS_DIR = BASE_DIR / "logs"

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "github-classroom-repos"

REQUIRED_SCOPES = ("repo", "admin:org")

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0
SLEEP_BETWEEN_REPOS = 2.0
TEMPLATE_PROPAGATION_TIMEOUT = 30.0

VALID_PERMISSIONS = ("pull", "triage", "push", "maintain", "admin")

# --- Valores del curso (poblados por load_course) ----------------------------

COURSE_FILE: Path
COURSE_NAME: str
ORG: str
TEMPLATE_OWNER: str
TEMPLATE_REPO: str
TEAM_SLUG: str
UPSTREAM_URL: str

REPO_NAME_FORMAT: str
REPO_DESCRIPTION_FORMAT: str
REPO_PRIVATE: bool

ROSTER_PATH: Path

MEMBER_PERMISSION: str
STAFF_PERMISSION: str

WELCOME_ISSUE_ENABLED: bool
WELCOME_ISSUE_TITLE: str
WELCOME_ISSUE_BODY: str


class ConfigError(Exception):
    """`course.toml` falta o está mal formado; abortar antes de tocar GitHub."""


def _require(seccion: dict, clave: str, ruta: Path, contexto: str) -> str:
    valor = seccion.get(clave)
    if valor in (None, ""):
        raise ConfigError(f"{ruta}: falta `{contexto}.{clave}`.")
    return valor


def display_path(path: Path) -> str:
    """Ruta relativa al directorio actual si se puede; si no, absoluta.

    El curso y el roster viven en la raíz y la herramienta se corre desde su
    propio directorio, así que los mensajes deben mostrar `../course.toml` y no
    un nombre suelto que el usuario no encontraría donde está parado.
    """
    try:
        return str(Path(path).resolve().relative_to(Path.cwd()))
    except ValueError:
        import os
        return os.path.relpath(Path(path).resolve(), Path.cwd())


def load_course(path: Path | None = None) -> None:
    """Carga `course.toml` y publica sus valores como constantes del módulo."""
    global COURSE_FILE, COURSE_NAME, ORG, TEMPLATE_OWNER, TEMPLATE_REPO
    global TEAM_SLUG, UPSTREAM_URL, ROSTER_PATH
    global REPO_NAME_FORMAT, REPO_DESCRIPTION_FORMAT
    global REPO_PRIVATE, MEMBER_PERMISSION, STAFF_PERMISSION
    global WELCOME_ISSUE_ENABLED, WELCOME_ISSUE_TITLE, WELCOME_ISSUE_BODY

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
    permisos = data.get("permissions") or {}
    issue = data.get("welcome_issue") or {}

    COURSE_FILE = path
    COURSE_NAME = _require(curso, "name", path, "course")
    ORG = _require(curso, "org", path, "course")
    TEMPLATE_OWNER = curso.get("template_owner") or ORG
    TEMPLATE_REPO = _require(curso, "template_repo", path, "course")
    TEAM_SLUG = _require(curso, "team_slug", path, "course")
    UPSTREAM_URL = f"https://github.com/{TEMPLATE_OWNER}/{TEMPLATE_REPO}.git"

    # Cada curso tiene sus propios alumnos. Con dos cursos activos, un roster
    # único es un error esperando ocurrir: apuntaría las invitaciones de un
    # curso a los alumnos del otro. Por eso el curso puede declarar el suyo.
    roster = curso.get("roster")
    if roster:
        ROSTER_PATH = Path(roster)
        if not ROSTER_PATH.is_absolute():
            ROSTER_PATH = (REPO_ROOT / ROSTER_PATH).resolve()
    else:
        ROSTER_PATH = DEFAULT_ROSTER_PATH

    REPO_NAME_FORMAT = repos.get("name_format") or "grupo-{n:02d}"
    REPO_DESCRIPTION_FORMAT = repos.get("description_format") or "Grupo {n:02d}"
    REPO_PRIVATE = bool(repos.get("private", True))

    MEMBER_PERMISSION = permisos.get("members") or "push"
    STAFF_PERMISSION = permisos.get("staff") or "maintain"
    for etiqueta, permiso in (("members", MEMBER_PERMISSION), ("staff", STAFF_PERMISSION)):
        if permiso not in VALID_PERMISSIONS:
            raise ConfigError(
                f"{path}: `permissions.{etiqueta}` = {permiso!r} no es válido. "
                f"Opciones: {', '.join(VALID_PERMISSIONS)}."
            )

    WELCOME_ISSUE_ENABLED = bool(issue.get("enabled", True))
    WELCOME_ISSUE_TITLE = issue.get("title") or "Configuración inicial del repositorio"
    WELCOME_ISSUE_BODY = issue.get("body") or ""
    if WELCOME_ISSUE_ENABLED and not WELCOME_ISSUE_BODY.strip():
        raise ConfigError(
            f"{path}: `welcome_issue.enabled` es true pero `welcome_issue.body` "
            f"está vacío."
        )

    # Falla acá y no a mitad de una corrida si un formato tiene placeholders malos.
    try:
        repo_name(1)
        repo_description(1)
    except (KeyError, IndexError, ValueError) as error:
        raise ConfigError(
            f"{path}: formato de nombre o descripción inválido — {error}. "
            f"Placeholders disponibles: {{n}} y {{course_name}}."
        ) from error


def repo_name(group_number: int) -> str:
    """`1` -> `grupo-01`, según `repos.name_format`."""
    return REPO_NAME_FORMAT.format(n=group_number, course_name=COURSE_NAME)


def repo_description(group_number: int) -> str:
    return REPO_DESCRIPTION_FORMAT.format(n=group_number, course_name=COURSE_NAME)


def welcome_issue_body(group_number: int, repo: str) -> str:
    return WELCOME_ISSUE_BODY.format(
        course_name=COURSE_NAME,
        org=ORG,
        repo=repo,
        group=group_number,
        template_owner=TEMPLATE_OWNER,
        template_repo=TEMPLATE_REPO,
        upstream_url=UPSTREAM_URL,
    )


# Carga por defecto al importar. Si no existe `course.toml`, el error se levanta
# recién cuando el entrypoint llama a load_course() y puede reportarlo bien.
try:
    load_course()
except ConfigError:
    pass
