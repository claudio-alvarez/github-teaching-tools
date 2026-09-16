#!/usr/bin/env python3
"""Extrae, para un grupo, el contexto que hace falta para escribir preguntas.

Lo consume la skill `preguntas-revision`: en vez de que el agente ande leyendo
repositorios enteros, este script le entrega un digesto compacto —enunciado,
archivos tocados y diff contra el código base— y le dice si el avance del grupo
alcanza para preguntar sobre su propio código o si hay que caer en la solución
canónica.

    python3 contexto.py listar   [--clones DIR]
    python3 contexto.py grupo    [--clones DIR] --group 7 [--max-lineas 400]
    python3 contexto.py canonica --repo RUTA --branch solucion [--base main]
    python3 contexto.py archivo  --group 7 --ruta src/router.py --desde 11 --hasta 19

Solo biblioteca estándar y el ejecutable `git`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

MANIFEST_NAME = "clones.json"

# El script vive en <repo>/.claude/skills/preguntas-revision/scripts/
REPO_ROOT = Path(__file__).resolve().parents[4]
ESTADO_CLONES = REPO_ROOT / "assignment-assessment" / "state" / "clones.json"

# Archivos que no cuentan como "avance del grupo": documentación, datos,
# dependencias y todo lo que suele venir generado o copiado.
EXT_NO_CODIGO = {
    ".md", ".txt", ".rst", ".pdf", ".csv", ".tsv", ".json", ".lock", ".xml",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip", ".jar",
    ".ttf", ".woff", ".woff2", ".mp3", ".mp4", ".pbxproj", ".xcworkspacedata",
    ".plist", ".gradle", ".properties", ".cfg", ".ini", ".toml", ".yaml", ".yml",
}
DIRS_NO_CODIGO = (
    "node_modules/", "vendor/", "dist/", "build/", ".venv/", "venv/",
    "Pods/", "target/", "__pycache__/", ".idea/", ".gradle/", "migrations/",
    "coverage/", "public/assets/", ".next/", "Carthage/",
)
# Nombres de archivo que son configuración del proyecto, no lógica del grupo.
NOMBRES_NO_CODIGO = {
    "package-lock.json", "yarn.lock", "Gemfile.lock", "poetry.lock",
    "Package.resolved", ".gitignore", ".gitattributes", "LICENSE",
}

MIN_LINEAS_CODIGO = 30  # umbral por defecto del veredicto de avance


class ErrorContexto(Exception):
    pass


# --- git ---------------------------------------------------------------------


def git(repo: Path, args: list[str], check: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo)] + args,
        capture_output=True, text=True, timeout=300,
    )
    if check and result.returncode != 0:
        raise ErrorContexto(
            f"git {' '.join(args[:3])}… falló en {repo}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout


def root_commit(repo: Path, rev: str = "HEAD") -> str:
    salida = git(repo, ["rev-list", "--max-parents=0", rev]).split()
    return salida[-1] if salida else ""


# --- clasificación de archivos ----------------------------------------------


def es_codigo(ruta: str) -> bool:
    p = ruta.replace("\\", "/")
    if any(d in p for d in DIRS_NO_CODIGO):
        return False
    nombre = p.rsplit("/", 1)[-1]
    if nombre in NOMBRES_NO_CODIGO:
        return False
    punto = nombre.rfind(".")
    ext = nombre[punto:].lower() if punto > 0 else ""
    return ext not in EXT_NO_CODIGO


def ruta_destino(ruta: str) -> str:
    """Nombre actual del archivo cuando git reporta un renombre.

    Con `-M`, numstat escribe `src/{viejo.py => nuevo.py}` o `viejo.py => nuevo.py`;
    esa cadena no existe en el árbol y no sirve para filtrar el diff.
    """
    if " => " not in ruta:
        return ruta
    if "{" in ruta and "}" in ruta:
        antes, resto = ruta.split("{", 1)
        medio, despues = resto.split("}", 1)
        return antes + medio.split(" => ")[-1] + despues
    return ruta.split(" => ")[-1]


def numstat(repo: Path, base: str, head: str) -> list[dict]:
    """Archivos tocados entre base y head, con líneas +/- y si son código."""
    salida = git(repo, ["diff", "--numstat", "-M", f"{base}..{head}"])
    archivos = []
    for linea in salida.splitlines():
        partes = linea.split("\t")
        if len(partes) != 3:
            continue
        mas, menos, ruta = partes
        ruta = ruta_destino(ruta)
        binario = mas == "-"
        archivos.append({
            "ruta": ruta,
            "insertadas": 0 if binario else int(mas),
            "eliminadas": 0 if binario else int(menos),
            "binario": binario,
            "codigo": (not binario) and es_codigo(ruta),
        })
    return sorted(archivos, key=lambda a: a["insertadas"], reverse=True)


def veredicto(archivos: list[dict], minimo: int) -> dict:
    """¿Alcanza el avance para preguntar sobre el código del propio grupo?

    Cuenta líneas, no ideas: es una primera criba. La skill la confirma leyendo
    el diff, porque 200 líneas copiadas del enunciado no son avance y 25 líneas
    con el núcleo del algoritmo sí lo son.
    """
    codigo = [a for a in archivos if a["codigo"]]
    lineas = sum(a["insertadas"] for a in codigo)
    suficiente = lineas >= minimo or (len(codigo) >= 2 and lineas >= minimo // 2)
    return {
        "archivos_codigo": len(codigo),
        "lineas_codigo": lineas,
        "umbral": minimo,
        "suficiente": suficiente,
    }


# --- manifiesto --------------------------------------------------------------


def cargar_manifiesto(clones: Path | None) -> tuple[Path, dict]:
    if clones is None:
        if not ESTADO_CLONES.exists():
            raise ErrorContexto(
                "No se indicó --clones y no hay corrida previa registrada en "
                f"{ESTADO_CLONES}. Corre antes:\n"
                "  cd assignment-assessment && python3 clone_repos.py --dest RUTA"
            )
        estado = json.loads(ESTADO_CLONES.read_text(encoding="utf-8"))
        clones = Path(estado.get("dest", ""))

    clones = Path(clones).expanduser()
    ruta = clones if clones.name == MANIFEST_NAME else clones / MANIFEST_NAME
    if not ruta.exists():
        raise ErrorContexto(
            f"No existe {ruta}. Ese archivo lo escribe `clone_repos.py`; "
            f"corre la descarga antes de generar preguntas."
        )
    return ruta, json.loads(ruta.read_text(encoding="utf-8"))


def buscar_grupo(manifiesto: dict, numero: int) -> dict:
    for entrada in manifiesto.get("grupos", []):
        if entrada.get("grupo") == numero:
            return entrada
    disponibles = ", ".join(
        str(g.get("grupo")) for g in manifiesto.get("grupos", [])
    )
    raise ErrorContexto(
        f"El manifiesto no tiene al grupo {numero}. Grupos disponibles: {disponibles}."
    )


def ruta_salida(manifiesto: dict, numero: int) -> Path:
    """`<output>/<sigla-curso>/<tarea>/grupo-XX/QUESTIONS.md`.

    El nivel de la tarea separa las revisiones de un mismo curso a lo largo del
    semestre. El manifiesto ya trae el directorio resuelto; lo de abajo es para
    manifiestos viejos, anteriores a ese campo.
    """
    salida = manifiesto.get("output_dir")
    if salida:
        base = Path(salida)
    else:
        curso = (manifiesto.get("curso") or {}).get("slug") or "curso"
        base = (REPO_ROOT / "assignment-assessment" / "output" / curso
                / (manifiesto.get("tarea") or "tarea"))
    return base / f"grupo-{numero:02d}" / "QUESTIONS.md"


# --- impresión ---------------------------------------------------------------


def imprimir_diff(repo: Path, base: str, head: str, archivos: list[dict],
                  max_lineas: int, max_total: int) -> None:
    total = 0
    for archivo in archivos:
        if not archivo["codigo"]:
            continue
        if total >= max_total:
            print(f"\n[…corte: se alcanzó el máximo de {max_total} líneas de diff. "
                  f"Usa `git -C {repo} diff {base[:8]}..{head[:8]} -- RUTA` para el resto.]")
            break
        salida = git(repo, ["diff", "-U6", "-M", f"{base}..{head}", "--",
                            archivo["ruta"]])
        lineas = salida.splitlines()
        print(f"\n===== DIFF {archivo['ruta']} "
              f"(+{archivo['insertadas']}/-{archivo['eliminadas']}) =====")
        for linea in lineas[:max_lineas]:
            print(linea)
        if len(lineas) > max_lineas:
            print(f"[…{len(lineas) - max_lineas} líneas más en este archivo. "
                  f"Léelo completo con Read: {repo / archivo['ruta']}]")
        total += min(len(lineas), max_lineas)


def enunciado(repo: Path) -> Path | None:
    """El enunciado de la tarea es el README.md de la raíz del repo."""
    for nombre in ("README.md", "README.MD", "readme.md", "README"):
        candidato = repo / nombre
        if candidato.exists():
            return candidato
    return None


# --- subcomandos -------------------------------------------------------------


def cmd_listar(opts) -> int:
    ruta, manifiesto = cargar_manifiesto(opts.clones)
    curso = manifiesto.get("curso", {})
    print(f"Manifiesto : {ruta}")
    print(f"Curso      : {curso.get('nombre')}  (slug: {curso.get('slug')})")
    print(f"Tarea      : {manifiesto.get('tarea') or '(no registrada)'}")
    print(f"Clones     : {manifiesto.get('dest')}")
    print(f"Revisión   : {manifiesto.get('ref')}"
          + (f" · corte {manifiesto['corte']}" if manifiesto.get("corte") else ""))
    print(f"Salida     : {manifiesto.get('output_dir')}")
    canonica = manifiesto.get("solucion_canonica")
    if canonica:
        print(f"Canónica   : {canonica.get('repo')} @ {canonica.get('branch')}")
    else:
        print("Canónica   : no declarada en course.toml "
              "(pásala con --repo/--branch al usar el fallback)")
    print()
    print(f"{'Gr':>3}  {'Estado':<20} {'Commits':>7}  {'Arch/+líneas':<14} "
          f"{'Avance':<12} QUESTIONS.md")
    print("-" * 82)
    for entrada in manifiesto.get("grupos", []):
        numero = entrada.get("grupo")
        repo = Path(entrada.get("path") or "")
        diff = entrada.get("diff") or {}
        avance = "—"
        if repo.exists() and entrada.get("base") and entrada.get("head"):
            archivos = numstat(repo, entrada["base"], entrada["head"])
            v = veredicto(archivos, opts.min_lineas)
            avance = "suficiente" if v["suficiente"] else "INSUFICIENTE"
        elif entrada.get("estado") == "error":
            avance = "sin clon"
        salida = ruta_salida(manifiesto, numero)
        tamano = f"{diff.get('archivos', 0)}/+{diff.get('insertadas', 0)}"
        print(f"{numero:>3}  {str(entrada.get('estado')):<20} "
              f"{entrada.get('commits', 0):>7}  {tamano:<14} "
              f"{avance:<12} {'ya existe' if salida.exists() else '—'}")
    return 0


def cmd_grupo(opts) -> int:
    _, manifiesto = cargar_manifiesto(opts.clones)
    entrada = buscar_grupo(manifiesto, opts.group)
    repo = Path(entrada.get("path") or "")
    if not repo.exists():
        raise ErrorContexto(
            f"El clon del grupo {opts.group} no está en {repo}. "
            f"Estado registrado: {entrada.get('estado')} "
            f"({entrada.get('error') or 'sin error'})."
        )

    curso = manifiesto.get("curso", {})
    base = entrada.get("base") or root_commit(repo)
    head = entrada.get("head") or git(repo, ["rev-parse", "HEAD"]).strip()

    print("=" * 78)
    print(f"GRUPO {opts.group:02d} · {entrada.get('repo')} · {curso.get('nombre')}"
          f" · {manifiesto.get('tarea') or 'tarea sin nombre'}")
    print("=" * 78)
    print(f"Clon        : {repo}")
    integrantes = ", ".join(
        f"{m['nombre']} (@{m['github']})" if m.get("github") else m["nombre"]
        for m in entrada.get("integrantes", []))
    print(f"Integrantes : {integrantes or '(sin datos en el roster)'}")
    print(f"Ayudante    : {entrada.get('ayudante') or '—'}")
    print(f"Rama        : {entrada.get('rama')}   HEAD: {head[:8]} "
          f"({(entrada.get('head_fecha') or '')[:10]}) {entrada.get('head_asunto') or ''}")
    print(f"Base        : {base[:8]} (código entregado por el equipo docente)")
    print(f"Commits     : {entrada.get('commits', 0)} sobre el base")
    autores = entrada.get("autores") or []
    if autores:
        print("Autores     : " + ", ".join(
            f"{a['autor']} ({a['commits']})" for a in autores))
    if entrada.get("commits_posteriores_al_corte"):
        print(f"Corte       : {entrada['commits_posteriores_al_corte']} commit(s) "
              f"posteriores al corte quedaron fuera")
    print(f"Salida      : {ruta_salida(manifiesto, opts.group)}")

    doc = enunciado(repo)
    print(f"Enunciado   : {doc if doc else 'NO HAY README.md EN LA RAÍZ'}")

    if not base or base == head:
        print("\nVEREDICTO   : INSUFICIENTE — el repositorio está en el código base, "
              "sin trabajo del grupo. Usa la solución canónica.")
        return 0

    archivos = numstat(repo, base, head)
    v = veredicto(archivos, opts.min_lineas)

    print()
    print("--- ARCHIVOS TOCADOS SOBRE EL BASE " + "-" * 42)
    for a in archivos:
        marca = "código" if a["codigo"] else ("binario" if a["binario"] else "otro")
        print(f"  +{a['insertadas']:<5} -{a['eliminadas']:<5} [{marca:<7}] {a['ruta']}")
    print()
    print(f"VEREDICTO   : {'suficiente' if v['suficiente'] else 'INSUFICIENTE'} — "
          f"{v['archivos_codigo']} archivo(s) de código, +{v['lineas_codigo']} "
          f"líneas (umbral {v['umbral']}).")
    if not v["suficiente"]:
        print("              Confírmalo leyendo el diff: si no hay lógica propia "
              "sobre la que preguntar, usa la solución canónica.")

    if opts.solo_resumen:
        return 0

    print()
    print("--- DIFF CONTRA EL CÓDIGO BASE " + "-" * 46)
    imprimir_diff(repo, base, head, archivos, opts.max_lineas, opts.max_total)
    return 0


def cmd_canonica(opts) -> int:
    repo = Path(opts.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        raise ErrorContexto(f"{repo} no es un repositorio git.")

    rama = git(repo, ["rev-parse", "--verify", "--quiet",
                      f"{opts.branch}^{{commit}}"]).strip()
    if not rama:
        rama = git(repo, ["rev-parse", "--verify", "--quiet",
                          f"origin/{opts.branch}^{{commit}}"]).strip()
    if not rama:
        raise ErrorContexto(
            f"La rama {opts.branch!r} no existe en {repo}. "
            f"Ramas: {' '.join(git(repo, ['branch', '-a', '--format=%(refname:short)']).split())}"
        )

    if opts.base:
        base = git(repo, ["rev-parse", "--verify", "--quiet",
                          f"{opts.base}^{{commit}}"]).strip()
        if not base:
            raise ErrorContexto(f"La base {opts.base!r} no existe en {repo}.")
        # Contra el punto en que la solución se separó del base, no contra su punta.
        fusion = git(repo, ["merge-base", base, rama]).strip()
        base = fusion or base
    else:
        base = root_commit(repo, rama)

    print("=" * 78)
    print(f"SOLUCIÓN CANÓNICA · {repo.name} · rama {opts.branch}")
    print("=" * 78)
    print(f"Repositorio : {repo}")
    print(f"Rama        : {opts.branch} @ {rama[:8]}")
    print(f"Base        : {base[:8]}"
          f"{' (' + opts.base + ')' if opts.base else ' (commit inicial)'}")

    doc = None
    contenido = git(repo, ["show", f"{rama}:README.md"])
    if contenido.strip():
        doc = f"git -C {repo} show {opts.branch}:README.md"
    print(f"Enunciado   : {doc or 'no hay README.md en esa rama'}")

    archivos = numstat(repo, base, rama)
    print()
    print("--- ARCHIVOS DE LA SOLUCIÓN " + "-" * 49)
    for a in archivos:
        marca = "código" if a["codigo"] else ("binario" if a["binario"] else "otro")
        print(f"  +{a['insertadas']:<5} -{a['eliminadas']:<5} [{marca:<7}] {a['ruta']}")

    if opts.solo_resumen:
        return 0

    print()
    print("--- DIFF DE LA SOLUCIÓN CONTRA EL BASE " + "-" * 38)
    imprimir_diff(repo, base, rama, archivos, opts.max_lineas, opts.max_total)
    return 0


def cmd_archivo(opts) -> int:
    """Imprime un archivo con números de línea, para citar rangos exactos."""
    if opts.group is not None:
        _, manifiesto = cargar_manifiesto(opts.clones)
        entrada = buscar_grupo(manifiesto, opts.group)
        repo = Path(entrada.get("path") or "")
        ref = entrada.get("head") or "HEAD"
        etiqueta = f"grupo {opts.group:02d} · {entrada.get('repo')}"
    elif opts.repo:
        repo = Path(opts.repo).expanduser().resolve()
        ref = opts.branch or "HEAD"
        etiqueta = f"{repo.name} · {ref}"
    else:
        raise ErrorContexto("Indica --group N o --repo RUTA [--branch RAMA].")

    if not (repo / ".git").exists():
        raise ErrorContexto(f"{repo} no es un repositorio git.")

    # Se lee del commit revisado, no del árbol de trabajo: si alguien editó el
    # clon, los números de línea que cites tienen que ser los del commit citado.
    contenido = git(repo, ["show", f"{ref}:{opts.ruta}"])
    origen = f"{ref[:8]}:{opts.ruta}"
    if not contenido:
        en_disco = repo / opts.ruta
        if not en_disco.exists():
            raise ErrorContexto(
                f"{opts.ruta} no existe en {ref[:8]} ni en el árbol de trabajo de {repo}."
            )
        contenido = en_disco.read_text(encoding="utf-8", errors="replace")
        origen = f"{opts.ruta} (árbol de trabajo; no está en {ref[:8]})"

    lineas = contenido.splitlines()
    desde = max(1, opts.desde or 1)
    hasta = min(len(lineas), opts.hasta or len(lineas))
    if desde > len(lineas):
        raise ErrorContexto(
            f"{opts.ruta} tiene {len(lineas)} líneas; --desde {desde} queda fuera."
        )

    print(f"# {etiqueta} — {origen} — líneas {desde}-{hasta} de {len(lineas)}")
    print(f"# Cita este fragmento como `{opts.ruta}:{desde}-{hasta}`")
    ancho = len(str(hasta))
    for numero in range(desde, hasta + 1):
        print(f"{numero:>{ancho}} | {lineas[numero - 1]}")
    return 0


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Contexto de un grupo para generar preguntas de revisión.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--clones", type=Path, default=None, metavar="DIR",
                         help="directorio de clones o ruta a clones.json "
                              "(por defecto, el de la última descarga).")
    comunes.add_argument("--min-lineas", type=int, default=MIN_LINEAS_CODIGO,
                         metavar="N",
                         help=f"líneas de código nuevas bajo las cuales el avance "
                              f"se considera insuficiente (por defecto {MIN_LINEAS_CODIGO}).")

    salida = argparse.ArgumentParser(add_help=False)
    salida.add_argument("--max-lineas", type=int, default=400, metavar="N",
                        help="máximo de líneas de diff por archivo (400).")
    salida.add_argument("--max-total", type=int, default=3000, metavar="N",
                        help="máximo de líneas de diff en total (3000).")
    salida.add_argument("--solo-resumen", action="store_true",
                        help="no imprime el diff, solo el resumen y el veredicto.")

    p_listar = sub.add_parser("listar", parents=[comunes],
                              help="tabla de todos los grupos descargados.")
    p_listar.set_defaults(func=cmd_listar)

    p_grupo = sub.add_parser("grupo", parents=[comunes, salida],
                             help="digesto de un grupo: metadatos, archivos y diff.")
    p_grupo.add_argument("--group", type=int, required=True, metavar="N")
    p_grupo.set_defaults(func=cmd_grupo)

    p_canon = sub.add_parser("canonica", parents=[salida],
                             help="digesto de la solución canónica (fallback).")
    p_canon.add_argument("--repo", required=True, metavar="RUTA",
                         help="repositorio local con la solución.")
    p_canon.add_argument("--branch", required=True, metavar="RAMA",
                         help="rama que contiene la solución.")
    p_canon.add_argument("--base", default=None, metavar="REF",
                         help="rama o commit del código base (por defecto, el "
                              "commit inicial del repositorio).")
    p_canon.set_defaults(func=cmd_canonica)

    p_archivo = sub.add_parser(
        "archivo", parents=[comunes],
        help="imprime un archivo con números de línea, para citar rangos exactos.")
    p_archivo.add_argument("--group", type=int, default=None, metavar="N",
                           help="grupo del manifiesto al que pertenece el archivo.")
    p_archivo.add_argument("--repo", default=None, metavar="RUTA",
                           help="repositorio suelto (p. ej. el de la solución "
                                "canónica), en vez de --group.")
    p_archivo.add_argument("--branch", default=None, metavar="RAMA",
                           help="rama o commit del que leer, con --repo.")
    p_archivo.add_argument("--ruta", required=True, metavar="ARCHIVO",
                           help="ruta del archivo dentro del repositorio.")
    p_archivo.add_argument("--desde", type=int, default=None, metavar="N")
    p_archivo.add_argument("--hasta", type=int, default=None, metavar="N")
    p_archivo.set_defaults(func=cmd_archivo)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)
    try:
        return opts.func(opts)
    except ErrorContexto as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
