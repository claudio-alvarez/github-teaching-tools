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
    python3 contexto.py schema   --slug default      # o --listar

Solo biblioteca estándar y el ejecutable `git`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST_NAME = "clones.json"

# El script vive en <repo>/.claude/skills/preguntas-revision/scripts/
REPO_ROOT = Path(__file__).resolve().parents[4]
ESTADO_CLONES = REPO_ROOT / "assignment-assessment" / "state" / "clones.json"

# Los schemas de problemas (sub-partes y puntaje) viven junto a la skill. El
# nombre del archivo, en kebab-case, es el slug con el que se pide.
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
SCHEMA_DEFAULT = "default"

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


# --- schemas -----------------------------------------------------------------


def parse_frontmatter(texto: str) -> tuple[dict, str]:
    """Bloque `---` inicial con líneas `clave: valor`. Devuelve (meta, cuerpo)."""
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        return {}, texto
    meta: dict[str, str] = {}
    for i, linea in enumerate(lineas[1:], start=1):
        if linea.strip() == "---":
            return meta, "\n".join(lineas[i + 1:])
        if ":" in linea:
            clave, valor = linea.split(":", 1)
            meta[clave.strip()] = valor.strip().strip("\"'")
    return meta, texto


def tabla_partes(cuerpo: str) -> list[dict]:
    """Primera tabla markdown del cuerpo que tenga una columna `Puntos`.

    Cada fila es una sub-parte del problema: etiqueta, puntos y tipo. El resto
    del schema es prosa para el agente y no se interpreta.
    """
    lineas = cuerpo.splitlines()
    for i, linea in enumerate(lineas):
        if not linea.lstrip().startswith("|"):
            continue
        cabecera = [c.strip().lower() for c in linea.strip().strip("|").split("|")]
        if "puntos" not in cabecera:
            continue
        col_puntos = cabecera.index("puntos")
        col_parte = cabecera.index("parte") if "parte" in cabecera else 0
        col_tipo = cabecera.index("tipo") if "tipo" in cabecera else None
        partes = []
        for fila in lineas[i + 2:]:  # i+1 es la línea de guiones
            if not fila.lstrip().startswith("|"):
                break
            celdas = [c.strip() for c in fila.strip().strip("|").split("|")]
            if len(celdas) <= col_puntos:
                break
            try:
                puntos = int(celdas[col_puntos])
            except ValueError as error:
                raise ErrorContexto(
                    f"la fila `{fila.strip()}` de la tabla de sub-partes no tiene "
                    f"un entero en la columna Puntos."
                ) from error
            partes.append({
                "parte": celdas[col_parte],
                "puntos": puntos,
                "tipo": celdas[col_tipo] if col_tipo is not None else "",
            })
        return partes
    return []


def schemas_disponibles() -> list[str]:
    if not SCHEMAS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SCHEMAS_DIR.glob("*.md"))


def cargar_schema(slug: str) -> dict:
    """Lee y valida `schemas/<slug>.md`; levanta ErrorContexto si no sirve."""
    ruta = SCHEMAS_DIR / f"{slug}.md"
    if not ruta.exists():
        disponibles = ", ".join(schemas_disponibles()) or "(ninguno)"
        raise ErrorContexto(
            f"No existe el schema {slug!r} ({ruta}). Disponibles: {disponibles}."
        )
    texto = ruta.read_text(encoding="utf-8")
    meta, cuerpo = parse_frontmatter(texto)

    errores = []
    if meta.get("slug") != slug:
        errores.append(
            f"el frontmatter dice `slug: {meta.get('slug')}` y el archivo se llama "
            f"`{slug}.md`; tienen que coincidir (kebab-case)."
        )
    total: int | None
    try:
        total = int(meta.get("puntos", ""))
    except ValueError:
        total = None
        errores.append("falta `puntos` en el frontmatter, o no es un entero.")
    partes = tabla_partes(cuerpo)
    if not partes:
        errores.append("no hay una tabla de sub-partes con una columna `Puntos`.")
    suma = sum(p["puntos"] for p in partes)
    if total is not None and partes and suma != total:
        errores.append(f"las sub-partes suman {suma} y `puntos` dice {total}.")
    if errores:
        raise ErrorContexto(f"Schema {ruta} inválido:\n  - " + "\n  - ".join(errores))

    hereda = (meta.get("hereda") or "").strip() or None
    if hereda and not (SCHEMAS_DIR / f"{hereda}.md").exists():
        raise ErrorContexto(f"Schema {ruta}: hereda de `{hereda}`, que no existe en {SCHEMAS_DIR}.")
    if hereda == slug:
        raise ErrorContexto(f"Schema {ruta}: no puede heredar de sí mismo.")
    return {
        "slug": slug,
        "ruta": ruta,
        "nombre": meta.get("nombre") or slug,
        "puntos": total,
        "partes": partes,
        "texto": texto,
        "hereda": hereda,
    }


def reparto(schema: dict) -> str:
    return " · ".join(f"({p['parte']}) {p['puntos']}" for p in schema["partes"])


MARCA_PROBLEMA = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*Problema\s+(\d+)", re.M)


def problemas_marcados(ruta: Path) -> list[int]:
    """Números de problema que el docente marcó con `[x]` en la minuta."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return []
    return [int(n) for n in MARCA_PROBLEMA.findall(texto)]


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


# --- marco de función --------------------------------------------------------
#
# Un fragmento suelto («las líneas 346-368») se entiende mejor si se ve dentro de
# la función que lo contiene: la firma arriba, la llave de cierre abajo y «// ...»
# donde se omitió código. El marco se calcula con heurísticas por lenguaje; si no
# se puede determinar, el fragmento se imprime tal cual.

EXT_LLAVES = {".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".js", ".ts", ".jsx",
              ".tsx", ".go", ".rs", ".swift", ".kt", ".cs", ".m", ".S"}
EXT_PYTHON = {".py"}


def _col0(linea: str) -> bool:
    return bool(linea) and not linea[0].isspace()


def _es_firma(linea: str) -> bool:
    """Línea en columna 0 que puede formar parte de la firma de una función."""
    l = linea.strip()
    return bool(l) and not l.startswith(("}", "#", "//", "/*", "*", "{"))


def marco_llaves(lineas: list[str], desde: int, hasta: int) -> dict | None:
    """Marco para lenguajes con llaves y funciones en columna 0 (estilo C/xv6).

    Devuelve {"firma": [líneas], "apertura": n|None, "cierre": n|None,
    "sangria": str} con números de línea 1-based, o None si el rango no está
    dentro de una función reconocible.
    """
    n = len(lineas)
    # 1. ¿El rango empieza con una firma? (contiene un «{» en columna 0 antes que un «}»)
    apertura = None
    for i in range(desde, hasta + 1):
        l = lineas[i - 1]
        if _col0(l) and l.rstrip().endswith("{"):
            apertura = i
            break
        if _col0(l) and l.startswith("}"):
            break
    dentro = apertura is None
    if dentro:
        # 2. Buscar hacia arriba la llave de apertura que encierra a `desde`.
        for i in range(desde - 1, 0, -1):
            l = lineas[i - 1]
            if _col0(l) and l.startswith("}"):
                return None  # el rango está fuera de toda función
            if _col0(l) and l.rstrip().endswith("{"):
                apertura = i
                break
        if apertura is None:
            return None
    # 3. La firma: la línea de la llave si trae texto, más las líneas contiguas
    #    en columna 0 que la preceden (`void` / `scheduler(void)`).
    firma_ini = apertura
    if lineas[apertura - 1].strip() == "{":
        firma_ini = apertura - 1
        if firma_ini < 1 or not _es_firma(lineas[firma_ini - 1]):
            return None
    while firma_ini - 1 >= 1 and _es_firma(lineas[firma_ini - 2]):
        firma_ini -= 1
    # 4. La llave de cierre: primer «}» en columna 0 después de `hasta`
    #    (o dentro del rango, si ya lo incluye).
    cierre = None
    for i in range(max(hasta, apertura) + 1, n + 1):
        l = lineas[i - 1]
        if _col0(l) and l.startswith("}"):
            cierre = i
            break
        if _col0(l) and l.rstrip().endswith("{"):
            break  # empezó otra función: el rango no cerró la suya
    incluye_cierre = any(_col0(lineas[i - 1]) and lineas[i - 1].startswith("}")
                         for i in range(max(desde, apertura + 1), hasta + 1))
    primera = next((lineas[i - 1] for i in range(desde, hasta + 1) if lineas[i - 1].strip()), "  x")
    sangria = primera[:len(primera) - len(primera.lstrip())] or "  "
    return {
        "firma_ini": firma_ini, "apertura": apertura,
        "cierre": None if incluye_cierre else cierre,
        "sangria": sangria, "dentro": dentro,
    }


def marco_python(lineas: list[str], desde: int, hasta: int) -> dict | None:
    """Marco para Python: el `def`/`class` de menor sangría que precede al rango."""
    primera = next((lineas[i - 1] for i in range(desde, hasta + 1) if lineas[i - 1].strip()), None)
    if primera is None:
        return None
    sangria_rango = len(primera) - len(primera.lstrip())
    for i in range(desde - 1, 0, -1):
        l = lineas[i - 1]
        if not l.strip():
            continue
        sangria = len(l) - len(l.lstrip())
        if sangria < sangria_rango and l.lstrip().startswith(("def ", "async def ", "class ")):
            # decoradores contiguos encima
            firma_ini = i
            while firma_ini - 1 >= 1 and lineas[firma_ini - 2].strip().startswith("@"):
                firma_ini -= 1
            return {"firma_ini": firma_ini, "apertura": i, "cierre": None,
                    "sangria": " " * sangria_rango, "dentro": True}
        if sangria < sangria_rango and not l.lstrip().startswith(("#", "@", ")", "]", "}")):
            return None  # otro bloque intermedio: no es una función simple
    return None


def enmarcar(ruta: str, lineas: list[str], desde: int, hasta: int) -> tuple[list[str], str]:
    """Devuelve (líneas del fragmento enmarcado, descripción del marco)."""
    ext = ruta[ruta.rfind("."):].lower() if "." in ruta.rsplit("/", 1)[-1] else ""
    rango = lineas[desde - 1:hasta]
    if ext in EXT_PYTHON:
        marco, elipsis = marco_python(lineas, desde, hasta), "# ..."
    elif ext in EXT_LLAVES:
        marco, elipsis = marco_llaves(lineas, desde, hasta), "// ..."
    else:
        return rango, "sin marco: extensión no reconocida"
    if marco is None:
        return rango, "sin marco: el rango no está dentro de una función reconocible"

    salida: list[str] = []
    # Firma y apertura, solo la parte que el rango no trae ya.
    for i in range(marco["firma_ini"], marco["apertura"] + 1):
        if i < desde:
            salida.append(lineas[i - 1])
    if marco["dentro"] and marco["apertura"] + 1 < desde:
        salida.append(marco["sangria"] + elipsis)
    salida.extend(rango)
    if marco["cierre"] is not None:
        if marco["cierre"] > hasta + 1:
            salida.append(marco["sangria"] + elipsis)
        salida.append(lineas[marco["cierre"] - 1])
    nombre = lineas[marco["apertura"] - 1].strip()
    if nombre == "{":
        nombre = lineas[marco["apertura"] - 2].strip()
    fin = marco["cierre"] or hasta
    return salida, f"función `{nombre}` (líneas {marco['firma_ini']}-{fin})"


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
        minuta = "—"
        if salida.exists():
            marcados = problemas_marcados(salida)
            if len(marcados) == 1:
                minuta = f"ya existe · P{marcados[0]} marcado"
            elif marcados:
                minuta = f"ya existe · {len(marcados)} marcados (!)"
            else:
                minuta = "ya existe · sin marcar"
        print(f"{numero:>3}  {str(entrada.get('estado')):<20} "
              f"{entrada.get('commits', 0):>7}  {tamano:<14} "
              f"{avance:<12} {minuta}")
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
    if opts.marco:
        enmarcado, descripcion = enmarcar(opts.ruta, lineas, desde, hasta)
        print(f"# Marco: {descripcion}. Las líneas «// ...» / «# ...» no existen en el "
              f"archivo; la referencia sigue siendo la del rango {desde}-{hasta}.")
        print(f"# Pega lo siguiente tal cual dentro del bloque de código:")
        for linea in enmarcado:
            print(linea)
        return 0
    ancho = len(str(hasta))
    for numero in range(desde, hasta + 1):
        print(f"{numero:>{ancho}} | {lineas[numero - 1]}")
    return 0


def cmd_schema(opts) -> int:
    """Valida un schema y lo imprime entero, o lista los que hay."""
    if opts.listar:
        slugs = schemas_disponibles()
        if not slugs:
            print(f"No hay schemas en {SCHEMAS_DIR}.")
            return 2
        print(f"Schemas en {SCHEMAS_DIR}:")
        for slug in slugs:
            try:
                schema = cargar_schema(slug)
                print(f"  {slug:<24} {schema['puntos']:>3} pts  {reparto(schema)}"
                      f"  — {schema['nombre']}")
            except ErrorContexto as error:
                print(f"  {slug:<24} INVÁLIDO — {str(error).splitlines()[-1].strip()}")
        return 0

    schema = cargar_schema(opts.slug)
    print(f"# schema `{schema['slug']}` — {schema['nombre']} — "
          f"{schema['puntos']} puntos — {schema['ruta']}")
    print(f"# Sub-partes: {reparto(schema)}"
          + "".join(f"\n#   ({p['parte']}) {p['puntos']} pts · {p['tipo']}"
                    for p in schema["partes"]))
    print("# Válido: el slug coincide con el archivo y las sub-partes suman el total.")
    if schema.get("hereda"):
        print(f"# Hereda de `{schema['hereda']}`: sus reglas rigen en todo lo que este "
              f"schema no cambia. Se imprime después de este.")
    print()
    print(schema["texto"])
    padre = schema.get("hereda")
    while padre:
        base = cargar_schema(padre)
        print("\n" + "=" * 78)
        print(f"# schema heredado `{base['slug']}` — {base['nombre']} — {base['ruta']}")
        print("=" * 78 + "\n")
        print(base["texto"])
        padre = base.get("hereda")
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
    p_archivo.add_argument("--marco", action="store_true",
                           help="imprime el rango dentro de su función: firma, «// ...» "
                                "por lo omitido y llave de cierre, listo para pegar.")
    p_archivo.set_defaults(func=cmd_archivo)

    p_schema = sub.add_parser(
        "schema",
        help="valida e imprime un schema de problemas, o lista los disponibles.")
    p_schema.add_argument("--slug", default=SCHEMA_DEFAULT, metavar="SLUG",
                          help=f"nombre del schema, igual al archivo "
                               f"schemas/<slug>.md (por defecto {SCHEMA_DEFAULT!r}).")
    p_schema.add_argument("--listar", action="store_true",
                          help="lista los schemas disponibles y su reparto de puntos.")
    p_schema.set_defaults(func=cmd_schema)

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
