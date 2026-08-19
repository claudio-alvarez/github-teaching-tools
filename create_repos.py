#!/usr/bin/env python3
"""Crea y configura los repositorios de grupo de un curso.

El curso se define en `course.toml`; los alumnos y sus grupos, en el CSV del
roster. Uso típico (el profesor lo ejecuta a mano en la fecha correspondiente):

    python3 create_repos.py                 # dry-run del día de hoy
    python3 create_repos.py --apply         # ejecuta de verdad (pide confirmación)
    python3 create_repos.py --date 19/8/2026 --catch-up --apply

Por defecto NO escribe nada en GitHub. Ver AGENTS.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import config
import github_api
import roster_loader
from roster_loader import DATE_FORMAT, Group, RosterError


# --- logging -----------------------------------------------------------------


class Logger:
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


# --- estado persistente ------------------------------------------------------


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"repos": {}}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {"repos": {}}
    data.setdefault("repos", {})
    return data


def save_state(path: Path, state: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


# --- selección de grupos -----------------------------------------------------


def select_groups(groups: list[Group], cutoff: date, catch_up: bool,
                  only: list[int] | None) -> list[Group]:
    if only:
        elegidos = [g for g in groups if g.numero in set(only)]
    elif catch_up:
        elegidos = [g for g in groups if g.fecha_creacion <= cutoff]
    else:
        elegidos = [g for g in groups if g.fecha_creacion == cutoff]
    # Orden ascendente de número de grupo (AGENTS.md §4).
    return sorted(elegidos, key=lambda g: g.numero)


# --- procesamiento de un grupo ----------------------------------------------


def process_group(client: github_api.GitHubClient, group: Group, opts, log) -> dict:
    log("")
    log(f"── Grupo {group.numero:02d} → {config.ORG}/{group.repo_name}")

    record = {
        "grupo": group.numero,
        "repo": group.repo_name,
        "url": f"https://github.com/{config.ORG}/{group.repo_name}",
        "fecha_creacion_roster": group.fecha_creacion.isoformat(),
        "ayudante": group.ayudante,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": not client.apply,
        "repositorio": None,
        "integrantes": [],
        "team": None,
        "issue_bienvenida": None,
        "errores": [],
    }

    # 1. Repositorio ---------------------------------------------------------
    existia = client.repo_exists(group.repo_name)
    if existia:
        log(f"   repo        : ya existe, se omite la creación")
        record["repositorio"] = "ya_existia"
    else:
        visibilidad = "privado" if config.REPO_PRIVATE else "público"
        log(f"   repo        : crear desde {config.TEMPLATE_OWNER}/"
            f"{config.TEMPLATE_REPO} ({visibilidad})")
        client.create_from_template(group.repo_name, group.description)
        client.wait_for_repo(group.repo_name)
        record["repositorio"] = "creado" if client.apply else "se_crearia"

    # En dry-run sobre un repo inexistente no hay nada que consultar: todo está
    # por hacerse. Evita 404 ruidosos al chequear colaboradores.
    repo_disponible = existia or client.apply

    # 2. Integrantes ---------------------------------------------------------
    for member in group.members:
        entrada = {"nombre": member.nombre, "github": member.github}

        if not member.tiene_github:
            entrada["estado"] = "sin_usuario_github"
            contacto = member.email or "sin email en el roster"
            log(f"   integrante  : {member.nombre} — SIN usuario de GitHub, no se "
                f"puede invitar ({contacto})")
            record["errores"].append(
                f"{member.nombre} no tiene usuario de GitHub en el roster"
            )
            record["integrantes"].append(entrada)
            continue

        if not client.user_exists(member.github):
            entrada["estado"] = "usuario_inexistente"
            log(f"   integrante  : {member.nombre} — el usuario "
                f"@{member.github} NO existe en GitHub")
            record["errores"].append(
                f"@{member.github} ({member.nombre}) no existe en GitHub"
            )
            record["integrantes"].append(entrada)
            continue

        estado = client.collaborator_state(group.repo_name, member.github) \
            if repo_disponible else "none"

        if estado == "collaborator":
            entrada["estado"] = "ya_colaborador"
            log(f"   integrante  : @{member.github} ya es colaborador")
        elif estado == "invited":
            entrada["estado"] = "invitacion_pendiente"
            log(f"   integrante  : @{member.github} ya tiene invitación pendiente")
        else:
            client.add_collaborator(
                group.repo_name, member.github, config.MEMBER_PERMISSION
            )
            entrada["estado"] = "invitado" if client.apply else "se_invitaria"
            log(f"   integrante  : invitar a @{member.github} "
                f"({member.nombre}) con permiso {config.MEMBER_PERMISSION}")

        record["integrantes"].append(entrada)

    # 3. Team staff ----------------------------------------------------------
    actual = client.team_repo_permission(group.repo_name) if repo_disponible else None
    if actual == opts.staff_permission:
        log(f"   team        : @{config.ORG}/{config.TEAM_SLUG} ya tiene "
            f"{opts.staff_permission}")
        record["team"] = "sin_cambios"
    else:
        detalle = f" (tenía {actual})" if actual else ""
        client.add_team_to_repo(group.repo_name, opts.staff_permission)
        log(f"   team        : dar {opts.staff_permission} a @{config.ORG}/"
            f"{config.TEAM_SLUG}{detalle}")
        record["team"] = "actualizado" if client.apply else "se_actualizaria"

    # 4. Issue de bienvenida con las instrucciones de upstream ---------------
    if opts.welcome_issue:
        ya_existe = (
            client.issue_exists(group.repo_name, config.WELCOME_ISSUE_TITLE)
            if repo_disponible
            else False
        )
        if ya_existe:
            log("   issue       : el issue de bienvenida ya existe")
            record["issue_bienvenida"] = "ya_existia"
        else:
            body = config.welcome_issue_body(group.numero, group.repo_name)
            client.create_issue(group.repo_name, config.WELCOME_ISSUE_TITLE, body)
            log(f"   issue       : crear «{config.WELCOME_ISSUE_TITLE}» con las "
                f"instrucciones de upstream")
            record["issue_bienvenida"] = "creado" if client.apply else "se_crearia"
    else:
        record["issue_bienvenida"] = "omitido"

    return record


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Crea los repositorios de grupo de un curso desde un template.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="ejecuta las escrituras en GitHub. Sin este flag solo simula.",
    )
    parser.add_argument(
        "--date", metavar="D/M/AAAA",
        help="fecha de corte (por defecto, hoy).",
    )
    parser.add_argument(
        "--catch-up", action="store_true",
        help="incluye grupos con fecha anterior a la de corte, no solo los de ese día.",
    )
    parser.add_argument(
        "--group", type=int, action="append", metavar="N",
        help="procesa solo estos grupos, ignorando la fecha. Repetible.",
    )
    parser.add_argument(
        "--staff-permission", default=None, choices=config.VALID_PERMISSIONS,
        help="permiso del team docente (por defecto, el de course.toml).",
    )
    parser.add_argument(
        "--no-welcome-issue", dest="welcome_issue", action="store_false",
        help="no crea el issue con las instrucciones de upstream.",
    )
    parser.add_argument(
        "--course", type=Path, default=None,
        help=f"archivo de configuración del curso (por defecto: "
             f"{config.DEFAULT_COURSE_FILE.name}).",
    )
    parser.add_argument(
        "--roster", type=Path, default=config.ROSTER_PATH,
        help="ruta al CSV del roster.",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="omite la confirmación interactiva (para uso no interactivo).",
    )
    parser.add_argument(
        "--skip-scope-check", action="store_true",
        help="no valida los scopes del token antes de empezar.",
    )
    return parser.parse_args(argv)


def confirm(groups: list[Group], opts, log) -> bool:
    """Confirmación explícita antes de escribir en la organización (AGENTS.md §7)."""
    if opts.yes:
        log("Confirmación omitida por --yes.")
        return True
    if not sys.stdin.isatty():
        log("ERROR: --apply requiere confirmación interactiva. Usa --yes si estás "
            "ejecutando sin terminal.")
        return False

    total_invitaciones = sum(len(g.members_con_github) for g in groups)
    print()
    print(f"Se van a crear/configurar {len(groups)} repositorio(s) en "
          f"https://github.com/{config.ORG} e invitar a {total_invitaciones} "
          f"estudiante(s). Esto es visible para terceros.")
    respuesta = input("Escribe 'si' para continuar: ").strip().lower()
    return respuesta == "si"


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    modo = "apply" if opts.apply else "dryrun"
    log = Logger(config.LOGS_DIR / f"{marca}-{modo}.log")

    try:
        return run(opts, log)
    finally:
        log.close()


def run(opts, log) -> int:
    # 0. Curso: define org, template, team y convenciones de nombre.
    try:
        config.load_course(opts.course)
    except config.ConfigError as error:
        log(f"ERROR de configuración: {error}")
        return 2

    # Los defaults que dependen del curso se resuelven recién ahora.
    if opts.staff_permission is None:
        opts.staff_permission = config.STAFF_PERMISSION
    opts.welcome_issue = opts.welcome_issue and config.WELCOME_ISSUE_ENABLED

    if opts.date:
        try:
            cutoff = datetime.strptime(opts.date, DATE_FORMAT).date()
        except ValueError:
            log(f"ERROR: fecha inválida {opts.date!r}. Formato esperado: D/M/AAAA.")
            return 2
    else:
        cutoff = date.today()

    log("=" * 72)
    log(f"{config.COURSE_NAME} · creación de repositorios de grupo")
    log(f"Modo        : {'APLICAR CAMBIOS' if opts.apply else 'DRY-RUN (no escribe)'}")
    log(f"Organización: {config.ORG}")
    log(f"Template    : {config.TEMPLATE_OWNER}/{config.TEMPLATE_REPO}")
    log(f"Fecha corte : {cutoff.strftime(DATE_FORMAT)}"
        f"{' (incluye anteriores)' if opts.catch_up else ''}")
    log(f"Curso       : {config.COURSE_FILE}")
    log(f"Roster      : {opts.roster}")
    log("=" * 72)

    # 1. Roster --------------------------------------------------------------
    try:
        groups, warnings = roster_loader.load_groups(opts.roster)
    except (RosterError, FileNotFoundError) as error:
        log(f"ERROR de roster: {error}")
        return 2

    log(f"\nRoster: {sum(len(g.members) for g in groups)} alumnos en "
        f"{len(groups)} grupos.")
    if warnings:
        log(f"\nAdvertencias del roster ({len(warnings)}):")
        for warning in warnings:
            log(f"  ! {warning}")

    seleccionados = select_groups(groups, cutoff, opts.catch_up, opts.group)
    if not seleccionados:
        log(f"\nNo hay grupos con fecha {cutoff.strftime(DATE_FORMAT)}. Nada que hacer.")
        return 0

    log(f"\nGrupos a procesar ({len(seleccionados)}):")
    for group in seleccionados:
        integrantes = ", ".join(
            f"@{m.github}" if m.tiene_github else f"{m.nombre} (sin GitHub)"
            for m in group.members
        )
        log(f"  {group.numero:02d} → {group.repo_name}  "
            f"[{group.fecha_creacion.strftime(DATE_FORMAT)}]  {integrantes}")

    # 2. Token y scopes ------------------------------------------------------
    try:
        token = github_api.get_token()
    except RuntimeError as error:
        log(f"\nERROR de autenticación: {error}")
        return 2

    client = github_api.GitHubClient(token, apply=opts.apply, log=log)

    if not opts.skip_scope_check:
        try:
            faltantes = client.check_scopes()
        except github_api.GitHubError as error:
            log(f"\nERROR validando el token: {error}")
            return 2
        if faltantes:
            log(f"\nERROR: al token le faltan los scopes: {', '.join(faltantes)}.")
            log(f"Ejecuta:  gh auth refresh -h github.com -s {','.join(faltantes)}")
            return 2

    # 3. Confirmación --------------------------------------------------------
    if opts.apply and not confirm(seleccionados, opts, log):
        log("\nCancelado por el usuario. No se escribió nada.")
        return 1

    # 4. Procesamiento -------------------------------------------------------
    state = load_state(config.STATE_PATH)
    ok, con_errores, fallidos = [], [], []

    for indice, group in enumerate(seleccionados):
        try:
            record = process_group(client, group, opts, log)
        except github_api.GitHubError as error:
            log(f"   ERROR       : {error}")
            fallidos.append(group)
            if opts.apply:
                state["repos"][group.repo_name] = {
                    "grupo": group.numero,
                    "repo": group.repo_name,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "errores": [str(error)],
                }
                save_state(config.STATE_PATH, state)
            continue  # un grupo caído no aborta los siguientes (AGENTS.md §4)

        if record["errores"]:
            con_errores.append(group)
        else:
            ok.append(group)

        if opts.apply:
            state["repos"][group.repo_name] = record
            save_state(config.STATE_PATH, state)

        if opts.apply and indice < len(seleccionados) - 1:
            time.sleep(config.SLEEP_BETWEEN_REPOS)

    # 5. Resumen -------------------------------------------------------------
    log("")
    log("=" * 72)
    log("Resumen")
    log(f"  Completos          : {len(ok)}")
    log(f"  Con advertencias   : {len(con_errores)}"
        + (f"  → {', '.join(g.repo_name for g in con_errores)}" if con_errores else ""))
    log(f"  Fallidos           : {len(fallidos)}"
        + (f"  → {', '.join(g.repo_name for g in fallidos)}" if fallidos else ""))
    if not opts.apply:
        log("")
        log("  DRY-RUN: no se escribió nada en GitHub. Repite con --apply.")
    log("=" * 72)

    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
