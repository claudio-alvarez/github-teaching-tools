#!/usr/bin/env python3
"""Reenvía las invitaciones caducadas de los repositorios de grupo ya creados.

GitHub caduca las invitaciones a colaborar a los 7 días, pero las deja en el
listado del repositorio. El alumno que no alcanzó a aceptar queda afuera y no se
arregla solo: hay que borrar la invitación vencida y emitir otra.

Esta herramienta recorre el roster del curso, compara con el estado real de cada
repositorio y solo actúa sobre quien le falta invitación:

    python3 resend_invitations.py                     # dry-run: qué falta y a quién
    python3 resend_invitations.py --apply             # reenvía (pide confirmación)
    python3 resend_invitations.py --group 4 --group 6 --apply
    python3 resend_invitations.py --course ../course.ICC4203-202620.toml

Es idempotente: a quien ya aceptó no se lo toca, y a quien tiene una invitación
vigente tampoco (salvo `--renew-pending`). No crea repositorios: eso es de
`create_repos.py`. Por defecto NO escribe nada en GitHub. Ver AGENTS.md.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import config
import github_api
import roster_loader
import runio
from roster_loader import Group, RosterError, Student


# --- el plan de la corrida ---------------------------------------------------

# Acciones que ameritan escribir. El resto del plan es informativo.
ACCIONABLES = ("reenviar", "invitar")


@dataclass
class Pendiente:
    """Un integrante al que hay que hacerle algo, o el motivo de por qué no."""

    group: Group
    member: Student
    accion: str  # reenviar | invitar | vigente | ya_colaborador | <motivo de error>
    invitacion_id: int | None = None
    creada: str = ""  # fecha de la invitación vencida, para el reporte

    @property
    def accionable(self) -> bool:
        return self.accion in ACCIONABLES


@dataclass
class PlanGrupo:
    group: Group
    repo_existe: bool
    entradas: list[Pendiente] = field(default_factory=list)
    # Personas con acceso de integrante al repo que no están en el roster.
    ajenos: list[str] = field(default_factory=list)

    @property
    def accionables(self) -> list[Pendiente]:
        return [e for e in self.entradas if e.accionable]

    @property
    def nadie_del_roster_tiene_acceso(self) -> bool:
        con_handle = [e for e in self.entradas
                      if e.accion != "sin_usuario_github"]
        return bool(con_handle) and all(e.accionable for e in con_handle)

    @property
    def sospechoso(self) -> bool:
        """El repo lo ocupa otro grupo: ningún integrante del roster tiene
        acceso y sí lo tienen personas que no están en el roster. Casi siempre
        significa que el roster no corresponde a esta organización."""
        return bool(self.ajenos) and self.nadie_del_roster_tiene_acceso


def select_groups(groups: list[Group], only: list[int] | None) -> list[Group]:
    """Por defecto, todos los grupos del roster: la caducidad no sigue fechas."""
    elegidos = [g for g in groups if g.numero in set(only)] if only else list(groups)
    return sorted(elegidos, key=lambda g: g.numero)


def plan_group(client: github_api.GitHubClient, group: Group, opts, log,
               staff: set[str]) -> PlanGrupo:
    """Diagnóstico de un grupo. Solo lecturas: no escribe nada, ni con --apply."""
    if not client.repo_exists(group.repo_name):
        log(f"── Grupo {group.numero:02d} → {group.repo_name}: el repositorio NO "
            f"existe; créalo con create_repos.py. Se omite.")
        return PlanGrupo(group=group, repo_existe=False)

    plan = PlanGrupo(group=group, repo_existe=True)
    invitaciones = client.repo_invitations(group.repo_name)
    lineas = []

    # Quién tiene acceso hoy, sin contar al equipo docente ni al dueño de la org.
    del_roster = {m.github.lower() for m in group.members_con_github}
    for colaborador in client.collaborators(group.repo_name):
        login = (colaborador.get("login") or "")
        if login.lower() in del_roster or login.lower() in staff:
            continue
        if (colaborador.get("role_name") or "") in ("admin", "maintain"):
            continue  # docencia o administración de la organización
        plan.ajenos.append(login)

    for member in group.members:
        if not member.tiene_github:
            contacto = member.email or "sin email en el roster"
            plan.entradas.append(Pendiente(group, member, "sin_usuario_github"))
            lineas.append(f"   {member.nombre} — SIN usuario de GitHub en el roster, "
                          f"no se puede invitar ({contacto})")
            continue

        estado = client.collaborator_state(group.repo_name, member.github, invitaciones)

        if estado == "collaborator":
            plan.entradas.append(Pendiente(group, member, "ya_colaborador"))
            continue  # el caso normal: no ensucia el reporte

        invitacion = client.find_invitation(group.repo_name, member.github, invitaciones)

        if estado == "expired" or (estado == "invited" and opts.renew_pending):
            creada = (invitacion.get("created_at") or "")[:10]
            plan.entradas.append(Pendiente(
                group, member, "reenviar",
                invitacion_id=invitacion["id"],
                creada=creada,
            ))
            motivo = (f"VENCIDA del {creada or 'sin fecha'} → reenviar"
                      if estado == "expired"
                      else "vigente → renovar por --renew-pending")
            lineas.append(f"   @{member.github} ({member.nombre}) — "
                          f"invitación {motivo}")
        elif estado == "invited":
            plan.entradas.append(Pendiente(group, member, "vigente"))
            lineas.append(f"   @{member.github} ({member.nombre}) — invitación "
                          f"pendiente pero aún vigente, no se toca")
        else:
            # Sin invitación ni acceso: o nunca se emitió, o alguien la rechazó.
            if not client.user_exists(member.github):
                plan.entradas.append(Pendiente(group, member, "usuario_inexistente"))
                lineas.append(f"   @{member.github} ({member.nombre}) — ese usuario "
                              f"NO existe en GitHub")
                continue
            plan.entradas.append(Pendiente(group, member, "invitar"))
            lineas.append(f"   @{member.github} ({member.nombre}) — sin invitación "
                          f"ni acceso → invitar")

    if plan.ajenos:
        lineas.append(f"   ! con acceso de integrante pero FUERA del roster: "
                      f"{', '.join('@' + a for a in plan.ajenos)}")

    if lineas:
        log(f"── Grupo {group.numero:02d} → {group.repo_name}")
        for linea in lineas:
            log(linea)

    return plan


# --- ejecución ---------------------------------------------------------------


def apply_group(client: github_api.GitHubClient, plan: PlanGrupo, log) -> dict:
    """Ejecuta las acciones del grupo. Reverifica: entre el plan y el apply el
    alumno pudo aceptar, y `ensure_collaborator` es la única puerta idempotente."""
    group = plan.group
    log("")
    log(f"── Grupo {group.numero:02d} → {config.ORG}/{group.repo_name}")

    record = {
        "grupo": group.numero,
        "repo": group.repo_name,
        "url": f"https://github.com/{config.ORG}/{group.repo_name}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": not client.apply,
        "integrantes": [],
        "errores": [],
    }

    for entrada in plan.accionables:
        member = entrada.member
        accion = client.ensure_collaborator(
            group.repo_name,
            member.github,
            config.MEMBER_PERMISSION,
            renew_pending=True,  # el plan ya decidió; acá no se vuelve a filtrar
        )

        if accion == "reenviada":
            estado = "reinvitado" if client.apply else "se_reinvitaria"
            log(f"   @{member.github:<20} invitación vencida borrada y reemitida "
                f"con permiso {config.MEMBER_PERMISSION}")
        elif accion == "invitada":
            estado = "invitado" if client.apply else "se_invitaria"
            log(f"   @{member.github:<20} invitado con permiso "
                f"{config.MEMBER_PERMISSION}")
        else:
            # Aceptó entre el diagnóstico y ahora: nada que hacer.
            estado = "ya_colaborador"
            log(f"   @{member.github:<20} ya aceptó desde el diagnóstico, se omite")

        record["integrantes"].append({
            "nombre": member.nombre,
            "github": member.github,
            "estado": estado,
        })

    return record


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Reenvía las invitaciones caducadas de los repos de grupo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="ejecuta las escrituras en GitHub. Sin este flag solo simula.",
    )
    parser.add_argument(
        "--group", type=int, action="append", metavar="N",
        help="revisa solo estos grupos (por defecto, todos). Repetible.",
    )
    parser.add_argument(
        "--renew-pending", action="store_true",
        help="también reemite las invitaciones vigentes, reiniciando su plazo de "
             "7 días. Por defecto solo se tocan las vencidas y las que faltan.",
    )
    parser.add_argument(
        "--ignore-roster-mismatch", action="store_true",
        help="continúa aunque el roster no parezca corresponder a esta "
             "organización. Úsalo solo después de revisar el diagnóstico.",
    )
    parser.add_argument(
        "--course", type=Path, default=None,
        help=f"archivo de configuración del curso (por defecto: "
             f"{config.DEFAULT_COURSE_FILE.name}).",
    )
    parser.add_argument(
        "--roster", type=Path, default=None,
        help="ruta al CSV del roster (por defecto, el que declare el curso).",
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


def confirm(pendientes: list[Pendiente]) -> bool:
    """Confirmación explícita antes de escribir en la organización (AGENTS.md §7).

    Muestra la cuenta exacta del plan, no una estimación: acá ya se sabe a
    quiénes se les va a mandar correo.
    """
    reenvios = sum(1 for p in pendientes if p.accion == "reenviar")
    nuevas = sum(1 for p in pendientes if p.accion == "invitar")
    print()
    print(f"Se van a emitir {len(pendientes)} invitación(es) en "
          f"https://github.com/{config.ORG}: {reenvios} reenvío(s) de invitaciones "
          f"vencidas y {nuevas} nueva(s). Cada una manda un correo al alumno.")
    respuesta = input("Escribe 'si' para continuar: ").strip().lower()
    return respuesta == "si"


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    modo = "apply" if opts.apply else "dryrun"
    log = runio.Logger(config.LOGS_DIR / f"{marca}-invites-{modo}.log")

    try:
        return run(opts, log)
    finally:
        log.close()


def run(opts, log) -> int:
    # 0. Curso ---------------------------------------------------------------
    try:
        config.load_course(opts.course)
    except config.ConfigError as error:
        log(f"ERROR de configuración: {error}")
        return 2

    if opts.roster is None:
        opts.roster = config.ROSTER_PATH

    log("=" * 72)
    log(f"{config.COURSE_NAME} · reenvío de invitaciones")
    log(f"Modo        : {'APLICAR CAMBIOS' if opts.apply else 'DRY-RUN (no escribe)'}")
    log(f"Organización: {config.ORG}")
    log(f"Permiso     : {config.MEMBER_PERMISSION}")
    log(f"Alcance     : "
        + (f"grupos {', '.join(str(n) for n in sorted(set(opts.group)))}"
           if opts.group else "todos los grupos del roster")
        + (" · incluye invitaciones vigentes" if opts.renew_pending else ""))
    log(f"Curso       : {config.display_path(config.COURSE_FILE)}")
    log(f"Roster      : {config.display_path(opts.roster)}")
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

    seleccionados = select_groups(groups, opts.group)
    if not seleccionados:
        log("\nNingún grupo del roster calza con --group. Nada que hacer.")
        return 0

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

    # 3. Diagnóstico (solo lecturas) -----------------------------------------
    log(f"\nRevisando {len(seleccionados)} repositorio(s) contra el roster…\n")

    staff = client.team_members()

    planes: list[PlanGrupo] = []
    fallidos: list[Group] = []
    for group in seleccionados:
        try:
            planes.append(plan_group(client, group, opts, log, staff))
        except github_api.GitHubError as error:
            log(f"── Grupo {group.numero:02d} → {group.repo_name}: ERROR {error}")
            fallidos.append(group)  # un grupo caído no aborta los siguientes

    pendientes = [e for p in planes for e in p.accionables]
    sin_repo = [p.group for p in planes if not p.repo_existe]
    problemas = [e for p in planes for e in p.entradas
                 if e.accion in ("sin_usuario_github", "usuario_inexistente")]

    # Guarda: un roster que no corresponde a esta organización se ve así —los
    # repos están ocupados por otras personas y "falta" invitar a todo el
    # roster—. Invitar en ese estado le manda correo a 30 alumnos ajenos al
    # curso, así que se detiene antes de preguntar.
    sospechosos = [p for p in planes if p.sospechoso]
    revisables = [p for p in planes if p.repo_existe]
    if sospechosos and len(sospechosos) > len(revisables) / 2:
        log("")
        log("=" * 72)
        log(f"ERROR: el roster no parece corresponder a {config.ORG}.")
        log(f"  En {len(sospechosos)} de {len(revisables)} repositorios revisados, "
            f"ningún integrante del roster tiene acceso y sí lo tienen personas "
            f"que no están en el roster.")
        log(f"  Roster usado: {config.display_path(opts.roster)}")
        log(f"  Curso       : {config.display_path(config.COURSE_FILE)}")
        log("")
        log("  Cada curso necesita su propio CSV. Declara el que corresponde en "
            "`[course] roster` de tu course.toml, o pásalo con --roster.")
        log("  Si de verdad quieres continuar: --ignore-roster-mismatch.")
        log("=" * 72)
        if not opts.ignore_roster_mismatch:
            return 2
        log("\nContinuando por --ignore-roster-mismatch.")

    if not pendientes:
        log("\n" + "=" * 72)
        log("No falta ninguna invitación: todos aceptaron o tienen una vigente.")
        if problemas:
            log(f"Quedan {len(problemas)} caso(s) que el profesor debe resolver a "
                f"mano (ver arriba: sin handle o handle inexistente).")
        log("=" * 72)
        return 1 if fallidos else 0

    log("")
    log("=" * 72)
    log(f"Faltan {len(pendientes)} invitación(es) en "
        f"{len({e.group.numero for e in pendientes})} grupo(s):")
    for entrada in pendientes:
        verbo = "reenviar" if entrada.accion == "reenviar" else "invitar"
        log(f"  grupo {entrada.group.numero:02d}  {verbo:<8} @{entrada.member.github}"
            f"  ({entrada.member.nombre})")
    log("=" * 72)

    # 4. Confirmación --------------------------------------------------------
    if not opts.apply:
        log("")
        log("  DRY-RUN: no se escribió nada en GitHub. Repite con --apply.")
        return 1 if fallidos else 0

    if opts.yes:
        log("Confirmación omitida por --yes.")
    elif not sys.stdin.isatty():
        log("ERROR: --apply requiere confirmación interactiva. Usa --yes si estás "
            "ejecutando sin terminal.")
        return 1
    elif not confirm(pendientes):
        log("\nCancelado por el usuario. No se escribió nada.")
        return 1

    # 5. Ejecución -----------------------------------------------------------
    state = runio.load_state(config.INVITATIONS_STATE_PATH)
    con_accion = [p for p in planes if p.accionables]

    for indice, plan in enumerate(con_accion):
        try:
            record = apply_group(client, plan, log)
        except github_api.GitHubError as error:
            log(f"   ERROR       : {error}")
            fallidos.append(plan.group)
            continue

        state["repos"][plan.group.repo_name] = record
        runio.save_state(config.INVITATIONS_STATE_PATH, state)

        if indice < len(con_accion) - 1:
            time.sleep(config.SLEEP_BETWEEN_REPOS)

    # 6. Resumen -------------------------------------------------------------
    log("")
    log("=" * 72)
    log("Resumen")
    log(f"  Invitaciones emitidas : {len(pendientes)}")
    log(f"  Repos tocados         : {len(con_accion)}")
    if sin_repo:
        log(f"  Sin repositorio       : {len(sin_repo)}  → "
            f"{', '.join(g.repo_name for g in sin_repo)} (usa create_repos.py)")
    if problemas:
        log(f"  A resolver a mano     : {len(problemas)}  → "
            f"{', '.join(e.member.github or e.member.nombre for e in problemas)}")
    if fallidos:
        log(f"  Fallidos              : {len(fallidos)}  → "
            f"{', '.join(g.repo_name for g in fallidos)}")
    log("")
    log("  Las invitaciones nuevas también caducan en 7 días. Avisa a los alumnos.")
    log("=" * 72)

    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
