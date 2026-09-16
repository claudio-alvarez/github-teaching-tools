#!/usr/bin/env python3
"""Descarga los repositorios de grupo de un curso para revisarlos localmente.

Lee el mismo `course.toml` y el mismo roster que `assignment-preparation`, y
deja un clon por grupo en el directorio que indique el operador. Volver a
correrlo actualiza los clones que ya estén; no vuelve a clonar nada.

    python3 clone_repos.py --dest ~/revision/t1          # clona o actualiza
    python3 clone_repos.py --dest ~/revision/t1 --at 20/9/2026
    python3 clone_repos.py --dest ~/revision/t1 --group 7 --group 12

Al final escribe `clones.json` dentro del directorio de destino: el manifiesto
que consume la skill `preguntas-revision`. Ver README.md.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import config
import gitio
import roster_loader
import runio
from roster_loader import Group, RosterError

DATE_FORMAT = "%d/%m/%Y"  # día primero, igual que en el roster


# --- una entrada del manifiesto ---------------------------------------------


def nueva_entrada(group: Group) -> dict:
    return {
        "grupo": group.numero,
        "repo": group.repo_name,
        "url": group.repo_url,
        "ayudante": group.ayudante,
        "integrantes": [
            {"nombre": m.nombre, "github": m.github} for m in group.members
        ],
        "path": None,
        "estado": None,
        "rama": None,
        "head": None,
        "head_fecha": None,
        "head_asunto": None,
        "base": None,
        "commits": 0,
        "diff": None,
        "autores": [],
        "commits_posteriores_al_corte": 0,
        "error": None,
    }


def describir_diff(diff: dict) -> str:
    return (f"{diff['archivos']} archivo(s), "
            f"+{diff['insertadas']}/-{diff['eliminadas']} líneas")


# --- procesamiento de un grupo ----------------------------------------------


def obtener_clon(group: Group, destino: Path, opts, log) -> bool:
    """Deja el repositorio clonado y con el remoto al día. False si no se pudo.

    En dry-run informa lo que haría y no toca el disco.
    """
    esperado = f"{config.ORG}/{group.repo_name}"

    if gitio.is_repo(destino):
        url = gitio.origin_url(destino)
        if esperado.lower() not in url.lower():
            raise gitio.GitError(
                ["git", "remote"],
                f"el clon existente apunta a {url or 'ningún remoto'}, no a "
                f"{esperado}. Muévelo o usa otro --dest.",
            )
        if opts.dry_run:
            log(f"   clon        : ya existe, se actualizaría desde origin")
            return True
        if not opts.no_fetch:
            gitio.fetch(destino)
        return True

    if destino.exists() and any(destino.iterdir()):
        raise gitio.GitError(
            ["clone"],
            f"{destino} ya existe, no está vacío y no es un repositorio git.",
        )

    if opts.dry_run:
        log(f"   clon        : se clonaría {esperado} en {destino}")
        return False  # sin repo en disco no hay nada más que inspeccionar

    log(f"   clon        : clonando {esperado}…")
    gitio.clone(config.ORG, group.repo_name, destino)
    return True


def posicionar(destino: Path, opts, log, entrada: dict) -> bool:
    """Deja el clon en el commit a revisar. False si no hay nada que revisar."""
    rama = opts.ref or gitio.default_branch(destino)
    entrada["rama"] = rama

    # Una rama del remoto es lo normal; un tag o un SHA también sirven como --ref.
    punta = gitio.resolve(destino, f"origin/{rama}") or gitio.resolve(destino, rama)
    if not punta:
        raise gitio.GitError(["rev-parse"], f"no existe la referencia {rama!r}.")

    if opts.at:
        corte = f"{opts.at.isoformat()} 23:59:59"
        sha = gitio.last_commit_before(destino, punta, corte)
        if not sha:
            entrada["estado"] = "sin_commits_antes_del_corte"
            log(f"   corte       : {rama} no tiene commits anteriores al "
                f"{opts.at.strftime(DATE_FORMAT)}; no hay nada que revisar")
            return False
        entrada["commits_posteriores_al_corte"] = gitio.count_commits(
            destino, sha, punta
        )
    else:
        sha = punta

    if gitio.is_dirty(destino):
        if not opts.force:
            entrada["estado"] = "con_cambios_locales"
            log(f"   AVISO       : el clon tiene cambios locales sin commitear; "
                f"se deja como está (usa --force para descartarlos)")
            return False
        gitio.reset_hard(destino)

    # Con corte por fecha el commit casi nunca es la punta de la rama: se deja
    # HEAD desprendido para no inventar una rama local que no existe arriba.
    gitio.checkout(destino, sha, rama=None if opts.at else rama)
    return True


def inspeccionar(destino: Path, opts, entrada: dict, log) -> None:
    """Completa el manifiesto con lo que hace falta para generar preguntas."""
    head = gitio.commit_info(destino, "HEAD")
    if head is None:
        entrada["estado"] = "sin_commits"
        log("   AVISO       : el repositorio no tiene commits")
        return

    entrada["head"] = head.sha
    entrada["head_fecha"] = head.fecha_iso
    entrada["head_asunto"] = head.asunto

    base = ""
    if opts.base_ref:
        base = gitio.resolve(destino, opts.base_ref)
        if not base:
            log(f"   AVISO       : --base-ref {opts.base_ref!r} no existe en este "
                f"repo; se usa el commit inicial")
    if not base:
        # El commit inicial de un repo creado desde template es el código base.
        base = gitio.root_commit(destino)

    entrada["base"] = base
    if base and base != head.sha:
        entrada["commits"] = gitio.count_commits(destino, base)
        entrada["diff"] = gitio.diff_stat(destino, base)
        entrada["autores"] = gitio.authors(destino, base)
        log(f"   trabajo     : {entrada['commits']} commit(s) sobre el base, "
            f"{describir_diff(entrada['diff'])}")
    else:
        entrada["commits"] = 0
        entrada["diff"] = {"archivos": 0, "insertadas": 0, "eliminadas": 0}
        log("   trabajo     : el repositorio está en el código base, sin commits "
            "del grupo")


def process_group(group: Group, opts, log) -> dict:
    log("")
    log(f"── Grupo {group.numero:02d} → {group.repo_name}")

    entrada = nueva_entrada(group)
    destino = (opts.dest / group.repo_name).resolve()
    entrada["path"] = str(destino)

    existia = gitio.is_repo(destino)
    try:
        if not obtener_clon(group, destino, opts, log):
            entrada["estado"] = entrada["estado"] or (
                "se_clonaria" if opts.dry_run else "sin_clon"
            )
            return entrada

        entrada["estado"] = "actualizado" if existia else "clonado"

        if opts.dry_run:
            log("   (dry-run: no se mueve el checkout)")
            return entrada

        if not posicionar(destino, opts, log, entrada):
            # Un clon con cambios locales igual sirve para revisar: se describe
            # tal como está en disco, en vez de dejar el manifiesto en blanco.
            if entrada["estado"] == "con_cambios_locales":
                inspeccionar(destino, opts, entrada, log)
            return entrada

        inspeccionar(destino, opts, entrada, log)
        fecha = (entrada["head_fecha"] or "")[:10]
        log(f"   estado      : {entrada['rama']} @ "
            f"{(entrada['head'] or '')[:8]} ({fecha})")
        if entrada["commits_posteriores_al_corte"]:
            log(f"   corte       : {entrada['commits_posteriores_al_corte']} "
                f"commit(s) posteriores omitidos")
    except gitio.GitError as error:
        entrada["estado"] = "error"
        entrada["error"] = str(error)
        log(f"   ERROR       : {error}")

    return entrada


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Clona los repositorios de grupo de un curso para revisarlos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dest", type=Path, default=None, metavar="RUTA",
        help="directorio donde quedan los clones (por defecto, el de course.toml).",
    )
    parser.add_argument(
        "--group", type=int, action="append", metavar="N",
        help="clona solo estos grupos. Repetible. Por defecto, todos.",
    )
    parser.add_argument(
        "--ref", default=None, metavar="REF",
        help="rama o tag a revisar (por defecto, la rama principal del repo).",
    )
    parser.add_argument(
        "--at", default=None, metavar="D/M/AAAA",
        help="fecha de corte: deja cada clon en el último commit anterior.",
    )
    parser.add_argument(
        "--tarea", default=None, metavar="NOMBRE",
        help="nombre de la tarea que se está revisando; nombra el directorio de "
             "minutas. Por defecto se deduce del nombre de los repositorios.",
    )
    parser.add_argument(
        "--base-ref", default=None, metavar="REF",
        help="línea base del diff (por defecto, el commit inicial del repo, que "
             "es el código base del template).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="descarta cambios locales del clon antes de actualizarlo.",
    )
    parser.add_argument(
        "--no-fetch", action="store_true",
        help="no consulta el remoto; trabaja con lo que ya está en disco.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="muestra qué clonaría y qué actualizaría, sin tocar el disco.",
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
    return parser.parse_args(argv)


def escribir_manifiesto(entradas: list[dict], opts, log) -> Path:
    """El manifiesto es la interfaz con la skill: dónde está cada clon y qué trae."""
    manifiesto = {
        "curso": {
            "nombre": config.COURSE_NAME,
            "slug": config.COURSE_SLUG,
            "org": config.ORG,
            "course_file": str(config.COURSE_FILE),
        },
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dest": str(opts.dest),
        "ref": opts.ref or "(rama principal de cada repo)",
        "corte": opts.at.strftime(DATE_FORMAT) if opts.at else None,
        "base_ref": opts.base_ref or "(commit inicial de cada repo)",
        "tarea": opts.tarea,
        "output_dir": str(config.output_dir(opts.tarea)),
        "solucion_canonica": (
            {
                "repo": str(config.CANONICAL_REPO),
                "branch": config.CANONICAL_BRANCH,
                "base": config.CANONICAL_BASE or None,
            }
            if config.CANONICAL_REPO
            else None
        ),
        "grupos": entradas,
    }
    ruta = opts.dest / config.MANIFEST_NAME

    # Una corrida parcial (--group) no puede borrar del manifiesto a los grupos
    # que no tocó: el revisor los clonó antes y siguen ahí.
    previo = runio.load_json(ruta)
    mismo_trabajo = (
        (previo.get("curso") or {}).get("slug") == config.COURSE_SLUG
        and previo.get("tarea") == opts.tarea
    )
    if previo.get("grupos") and mismo_trabajo:
        tocados = {e["grupo"] for e in entradas}
        conservados = [e for e in previo["grupos"] if e.get("grupo") not in tocados]
        manifiesto["grupos"] = sorted(
            entradas + conservados, key=lambda e: e.get("grupo", 0)
        )
    elif previo.get("grupos"):
        log(f"\nAVISO: {ruta} traía los grupos de "
            f"{(previo.get('curso') or {}).get('slug')} / {previo.get('tarea')}; "
            f"se reemplaza. Dale un --dest propio a cada tarea.")

    runio.save_json(ruta, manifiesto)
    return ruta


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)

    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    modo = "dryrun" if opts.dry_run else "clone"
    log = runio.Logger(config.LOGS_DIR / f"{marca}-{modo}.log")
    try:
        return run(opts, log)
    finally:
        log.close()


def run(opts, log) -> int:
    # 0. Curso: define org, roster y convención de nombres de los repos.
    try:
        config.load_course(opts.course)
    except config.ConfigError as error:
        log(f"ERROR de configuración: {error}")
        return 2

    if opts.dest is None:
        opts.dest = config.CLONES_DIR
    opts.dest = Path(opts.dest).expanduser().resolve()
    if opts.roster is None:
        opts.roster = config.ROSTER_PATH
    opts.tarea = config.assignment_slug(opts.tarea)

    if opts.at:
        try:
            opts.at = datetime.strptime(opts.at, DATE_FORMAT).date()
        except ValueError:
            log(f"ERROR: fecha inválida {opts.at!r}. Formato esperado: D/M/AAAA.")
            return 2
        if opts.at > date.today():
            log(f"AVISO: la fecha de corte {opts.at.strftime(DATE_FORMAT)} es "
                f"futura; se revisará todo lo entregado hasta hoy.")

    log("=" * 72)
    log(f"{config.COURSE_NAME} · descarga de repositorios de grupo")
    log(f"Modo        : {'DRY-RUN (no toca el disco)' if opts.dry_run else 'clonar / actualizar'}")
    log(f"Organización: {config.ORG}")
    log(f"Destino     : {opts.dest}")
    log(f"Revisión    : {opts.ref or 'rama principal'}"
        f"{' hasta el ' + opts.at.strftime(DATE_FORMAT) if opts.at else ' (último commit)'}")
    log(f"Tarea       : {opts.tarea}")
    log(f"Minutas     : {config.display_path(config.output_dir(opts.tarea))}")
    log(f"Curso       : {config.display_path(config.COURSE_FILE)}")
    log(f"Roster      : {config.display_path(opts.roster)}")
    log("=" * 72)

    # 1. Herramientas --------------------------------------------------------
    faltan = gitio.require_tools(usa_gh=not opts.dry_run)
    if faltan:
        log(f"\nERROR: falta(n) en el PATH: {', '.join(faltan)}. "
            f"Instala git y GitHub CLI (`gh`) y autentícate con `gh auth login`.")
        return 2

    # 2. Roster --------------------------------------------------------------
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

    if opts.group:
        pedidos = set(opts.group)
        seleccionados = [g for g in groups if g.numero in pedidos]
        inexistentes = sorted(pedidos - {g.numero for g in seleccionados})
        if inexistentes:
            log(f"\nAVISO: no hay grupo(s) {', '.join(str(n) for n in inexistentes)} "
                f"en el roster.")
    else:
        seleccionados = list(groups)

    if not seleccionados:
        log("\nNo hay grupos que procesar.")
        return 2 if opts.group else 0

    # 3. Espacio en disco: 30 clones con historial no son gratis -------------
    if not opts.dry_run:
        opts.dest.mkdir(parents=True, exist_ok=True)
        libre_gb = shutil.disk_usage(opts.dest).free / 1024**3
        if libre_gb < 1:
            log(f"\nAVISO: quedan {libre_gb:.1f} GB libres en el destino.")

    # 4. Procesamiento -------------------------------------------------------
    entradas = []
    for group in seleccionados:
        entradas.append(process_group(group, opts, log))

    ruta_manifiesto = None
    if not opts.dry_run:
        ruta_manifiesto = escribir_manifiesto(entradas, opts, log)
        runio.save_json(config.STATE_PATH, {
            "ultima_corrida_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "curso": config.COURSE_SLUG,
            "tarea": opts.tarea,
            "dest": str(opts.dest),
            "manifiesto": str(ruta_manifiesto),
            "grupos": len(entradas),
        })

    # 5. Resumen -------------------------------------------------------------
    con_error = [e for e in entradas if e["estado"] == "error"]
    sin_trabajo = [e for e in entradas
                   if e["estado"] in ("actualizado", "clonado") and not e["commits"]]
    atencion = [e for e in entradas
                if e["estado"] in ("con_cambios_locales", "sin_commits",
                                   "sin_commits_antes_del_corte")]

    log("")
    log("=" * 72)
    log(f"Procesados  : {len(entradas)} grupo(s)")
    if opts.dry_run:
        log("Dry-run     : no se clonó ni se inspeccionó nada.")
    else:
        con_trabajo = len(entradas) - len(con_error) - len(sin_trabajo) - len(atencion)
        log(f"Con trabajo : {con_trabajo} grupo(s)")
    if sin_trabajo:
        log(f"Sin avance  : grupo(s) "
            f"{', '.join(str(e['grupo']) for e in sin_trabajo)} — están en el "
            f"código base, la minuta usará la solución canónica")
    if atencion:
        for e in atencion:
            log(f"Revisar     : grupo {e['grupo']} — {e['estado']}")
    if con_error:
        for e in con_error:
            log(f"ERROR       : grupo {e['grupo']} — {e['error']}")
    if ruta_manifiesto:
        log(f"Manifiesto  : {ruta_manifiesto}")
        log("")
        log("Siguiente paso: genera las minutas de revisión con la skill")
        log(f"  /preguntas-revision --clones {opts.dest}")
    log("=" * 72)

    return 1 if con_error else 0


if __name__ == "__main__":
    sys.exit(main())
