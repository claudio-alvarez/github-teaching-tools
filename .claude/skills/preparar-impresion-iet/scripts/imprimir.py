#!/usr/bin/env python3
"""Arma el PDF único e imprimible con los enunciados del IET de todos los grupos.

Recorre los `STATEMENT.pdf` de `output/<sigla>/<tarea>/grupo-XX/` en orden
ascendente de grupo, rellena con una página en blanco los enunciados de número
impar de carillas (impresión a doble cara: cada copia empieza en hoja nueva) y
repite cada enunciado tantas veces como integrantes tenga el grupo en el roster.
Antes valida que todo estudiante del roster tenga enunciado.

    python3 imprimir.py validar [--dir DIR | --curso SIGLA --tarea T] [--roster CSV]
    python3 imprimir.py generar [--dir DIR] [--roster CSV] [--copias N | --copias-extra N]
                                [--salida IET-impresion.pdf] [--permitir-faltantes]

Solo biblioteca estándar más herramientas externas por subproceso: `pdfinfo` y
`pdfunite` (poppler) o, en su defecto, `gs` (Ghostscript), que también produce
la página en blanco.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# El script vive en <repo>/.claude/skills/preparar-impresion-iet/scripts/
REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_ROOT = REPO_ROOT / "assignment-assessment" / "output"
ESTADO_CLONES = REPO_ROOT / "assignment-assessment" / "state" / "clones.json"
ROSTER_DEFAULT = REPO_ROOT / "roster" / "roster.csv"

STATEMENT_PDF = "STATEMENT.pdf"
STATEMENT_MD = "STATEMENT.md"
SALIDA_PDF = "IET-impresion.pdf"
SALIDA_MD = "IET-impresion.md"
RE_GRUPO_DIR = re.compile(r"^grupo-(\d+)$")

COL_NOMBRE, COL_GRUPO, COL_GITHUB = "Nombre", "Grupo", "Usuario GitHub"


class ErrorImpresion(Exception):
    pass


# --- ubicación --------------------------------------------------------------


def resolver_dir(opts) -> Path:
    if opts.dir:
        d = Path(opts.dir).expanduser().resolve()
    elif opts.curso and opts.tarea:
        d = OUTPUT_ROOT / opts.curso / opts.tarea
    elif opts.curso or opts.tarea:
        raise ErrorImpresion("Indica --curso y --tarea juntos, o --dir.")
    else:
        if not ESTADO_CLONES.exists():
            raise ErrorImpresion(f"No hay corrida previa en {ESTADO_CLONES}. Indica --curso SIGLA --tarea NOMBRE, o --dir.")
        manifiesto = Path(json.loads(ESTADO_CLONES.read_text(encoding="utf-8")).get("manifiesto", ""))
        if not manifiesto.exists():
            raise ErrorImpresion(f"El manifiesto {manifiesto} ya no existe; usa --dir.")
        salida = json.loads(manifiesto.read_text(encoding="utf-8")).get("output_dir")
        if not salida:
            raise ErrorImpresion("El manifiesto no trae output_dir; usa --dir.")
        d = Path(salida)
    if not d.is_dir():
        raise ErrorImpresion(f"No existe el directorio {d}.")
    return d


# --- roster -----------------------------------------------------------------


@dataclass
class Estudiante:
    nombre: str
    github: str
    grupo: int


def leer_roster(ruta: Path) -> list[Estudiante]:
    if not ruta.exists():
        raise ErrorImpresion(f"No existe el roster {ruta}.")
    with open(ruta, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or COL_NOMBRE not in reader.fieldnames or COL_GRUPO not in reader.fieldnames:
            raise ErrorImpresion(f"{ruta}: se esperan las columnas `{COL_NOMBRE}` y `{COL_GRUPO}`.")
        alumnos = []
        for fila, raw in enumerate(reader, start=2):
            nombre = (raw.get(COL_NOMBRE) or "").strip()
            grupo = (raw.get(COL_GRUPO) or "").strip()
            if not nombre and not grupo:
                continue
            if not grupo.isdigit():
                raise ErrorImpresion(f"{ruta}, fila {fila} ({nombre!r}): grupo inválido {grupo!r}.")
            alumnos.append(Estudiante(nombre, (raw.get(COL_GITHUB) or "").strip(), int(grupo)))
    if not alumnos:
        raise ErrorImpresion(f"{ruta}: no hay filas de alumnos.")
    return alumnos


# --- herramientas PDF -------------------------------------------------------


def herramientas() -> dict:
    return {n: shutil.which(n) for n in ("pdfinfo", "pdfunite", "gs")}


def contar_paginas(pdf: Path, tools: dict) -> int:
    if tools["pdfinfo"]:
        salida = subprocess.run([tools["pdfinfo"], str(pdf)], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", salida, re.M)
        if m:
            return int(m.group(1))
    if tools["gs"]:
        salida = subprocess.run(
            [tools["gs"], "-q", "-dNODISPLAY", "-dNOSAFER", "-c", f"({pdf}) (r) file runpdfbegin pdfpagecount = quit"],
            capture_output=True, text=True).stdout.strip()
        if salida.isdigit():
            return int(salida)
    raise ErrorImpresion(f"No pude contar las páginas de {pdf}: hace falta `pdfinfo` (poppler) o `gs`.")


def tamano_pagina(pdf: Path, tools: dict) -> tuple[float, float]:
    """Ancho y alto en puntos de la primera página, para que la hoja en blanco calce."""
    if tools["pdfinfo"]:
        salida = subprocess.run([tools["pdfinfo"], str(pdf)], capture_output=True, text=True).stdout
        m = re.search(r"^Page size:\s+([\d.]+) x ([\d.]+)", salida, re.M)
        if m:
            return float(m.group(1)), float(m.group(2))
    return 595.0, 842.0  # A4


def pagina_en_blanco(destino: Path, ancho: float, alto: float, tools: dict) -> Path:
    if not tools["gs"]:
        raise ErrorImpresion("Hace falta `gs` (Ghostscript) para generar la página en blanco de relleno.")
    cmd = [tools["gs"], "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite", f"-sOutputFile={destino}",
           "-c", f"<< /PageSize [{ancho:.2f} {alto:.2f}] >> setpagedevice showpage"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not destino.exists():
        raise ErrorImpresion(f"gs no pudo crear la página en blanco: {(r.stderr or r.stdout).strip()[-300:]}")
    return destino


def concatenar(partes: list[Path], destino: Path, tools: dict) -> None:
    if tools["pdfunite"]:
        r = subprocess.run([tools["pdfunite"], *map(str, partes), str(destino)], capture_output=True, text=True)
    elif tools["gs"]:
        r = subprocess.run([tools["gs"], "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                            f"-sOutputFile={destino}", *map(str, partes)], capture_output=True, text=True)
    else:
        raise ErrorImpresion("Hace falta `pdfunite` (poppler) o `gs` para concatenar.")
    if r.returncode != 0 or not destino.exists():
        raise ErrorImpresion(f"La concatenación falló: {(r.stderr or r.stdout).strip()[-300:]}")


# --- validación -------------------------------------------------------------


@dataclass
class Grupo:
    numero: int
    integrantes: list[Estudiante] = field(default_factory=list)
    pdf: Path | None = None
    md: Path | None = None
    paginas: int = 0
    sin_nombre: list[str] = field(default_factory=list)


def armar_grupos(directorio: Path, alumnos: list[Estudiante], tools: dict) -> tuple[list[Grupo], list[int]]:
    por_grupo: dict[int, Grupo] = {}
    for a in alumnos:
        por_grupo.setdefault(a.grupo, Grupo(a.grupo)).integrantes.append(a)
    for g in por_grupo.values():
        d = directorio / f"grupo-{g.numero:02d}"
        pdf, md = d / STATEMENT_PDF, d / STATEMENT_MD
        if pdf.exists() and pdf.stat().st_size > 0:
            g.pdf = pdf
            g.paginas = contar_paginas(pdf, tools)
        if md.exists():
            g.md = md
            texto = md.read_text(encoding="utf-8")
            g.sin_nombre = [a.nombre for a in g.integrantes if a.nombre not in texto]
    # directorios con enunciado que no corresponden a ningún grupo del roster
    huerfanos = []
    for d in directorio.glob("grupo-*"):
        m = RE_GRUPO_DIR.match(d.name)
        if m and int(m.group(1)) not in por_grupo and (d / STATEMENT_PDF).exists():
            huerfanos.append(int(m.group(1)))
    return [por_grupo[k] for k in sorted(por_grupo)], sorted(huerfanos)


def informe_validacion(grupos: list[Grupo], huerfanos: list[int], log) -> tuple[list[Estudiante], int]:
    faltantes: list[Estudiante] = []
    avisos = 0
    log(f"{'Gr':>3}  {'Integrantes':>11}  {'STATEMENT.pdf':<14} {'Carillas':>8}  Observaciones")
    log("-" * 78)
    for g in grupos:
        obs = []
        if g.pdf is None:
            faltantes.extend(g.integrantes)
            obs.append("FALTA EL ENUNCIADO")
        elif g.md is None:
            obs.append("sin STATEMENT.md para comprobar la cabecera")
            avisos += 1
        elif g.sin_nombre:
            obs.append("no aparecen en la cabecera: " + "; ".join(g.sin_nombre))
            avisos += 1
        log(f"{g.numero:>3}  {len(g.integrantes):>11}  {'sí' if g.pdf else '—':<14} {g.paginas if g.pdf else '—':>8}  {'; '.join(obs)}")
    if huerfanos:
        log(f"\nAVISO: hay enunciados de grupos que no están en el roster (no se imprimen): "
            f"{', '.join(str(h) for h in huerfanos)}.")
        avisos += 1
    if faltantes:
        log("\nESTUDIANTES SIN ENUNCIADO:")
        for a in faltantes:
            log(f"  grupo {a.grupo:>2}  {a.nombre}" + (f"  (@{a.github})" if a.github else ""))
    return faltantes, avisos


# --- subcomandos -------------------------------------------------------------


def cmd_validar(opts) -> int:
    directorio = resolver_dir(opts)
    tools = herramientas()
    alumnos = leer_roster(Path(opts.roster) if opts.roster else ROSTER_DEFAULT)
    print(f"Enunciados : {directorio}")
    print(f"Roster     : {opts.roster or ROSTER_DEFAULT}  ({len(alumnos)} estudiantes)")
    print(f"Herramientas: " + ", ".join(f"{k}={'sí' if v else 'NO'}" for k, v in tools.items()))
    print()
    grupos, huerfanos = armar_grupos(directorio, alumnos, tools)
    faltantes, avisos = informe_validacion(grupos, huerfanos, print)
    print(f"\nEstudiantes sin enunciado: {len(faltantes)} de {len(alumnos)}. Avisos: {avisos}.")
    return 1 if faltantes else 0


def cmd_generar(opts) -> int:
    directorio = resolver_dir(opts)
    tools = herramientas()
    alumnos = leer_roster(Path(opts.roster) if opts.roster else ROSTER_DEFAULT)
    grupos, huerfanos = armar_grupos(directorio, alumnos, tools)
    faltantes, _ = informe_validacion(grupos, huerfanos, print)
    if faltantes and not opts.permitir_faltantes:
        print(f"\nNo se genera el PDF: {len(faltantes)} estudiante(s) sin enunciado. "
              f"Genera los que faltan con `preparar-iet`, o usa --permitir-faltantes para imprimir igual el resto.")
        return 1

    salida = directorio / (opts.salida or SALIDA_PDF)
    con_pdf = [g for g in grupos if g.pdf]
    if not con_pdf:
        raise ErrorImpresion("Ningún grupo tiene STATEMENT.pdf; no hay nada que imprimir.")
    ancho, alto = tamano_pagina(con_pdf[0].pdf, tools)

    filas = []
    total_paginas = 0
    with tempfile.TemporaryDirectory(prefix="iet-impresion-") as tmp:
        blanco = pagina_en_blanco(Path(tmp) / "blanco.pdf", ancho, alto, tools)
        partes: list[Path] = []
        for g in con_pdf:
            copias = opts.copias if opts.copias else len(g.integrantes) + (opts.copias_extra or 0)
            relleno = g.paginas % 2
            for _ in range(copias):
                partes.append(g.pdf)
                if relleno:
                    partes.append(blanco)
            paginas_grupo = copias * (g.paginas + relleno)
            total_paginas += paginas_grupo
            filas.append((g.numero, len(g.integrantes), copias, g.paginas, relleno, paginas_grupo))
        concatenar(partes, salida, tools)

    paginas_reales = contar_paginas(salida, tools)
    if paginas_reales != total_paginas:
        raise ErrorImpresion(f"El PDF final tiene {paginas_reales} páginas y se esperaban {total_paginas}.")

    # manifiesto de impresión, para quien reparta las hojas
    lineas = [f"# Orden de impresión del IET — {directorio.name}", "",
              f"- **Archivo:** `{salida.name}`", f"- **Impresión:** doble cara; cada copia empieza en hoja nueva.",
              f"- **Copias:** " + ("una por integrante del roster" if not opts.copias else f"{opts.copias} por grupo")
              + (f", más {opts.copias_extra} extra por grupo" if opts.copias_extra else "") + ".",
              f"- **Total:** {total_paginas} carillas = {total_paginas // 2} hojas, {sum(f[2] for f in filas)} copias, {len(filas)} grupos.", "",
              "| Grupo | Integrantes | Copias | Carillas por copia | Relleno | Carillas | Hojas |", "|---:|---:|---:|---:|:---:|---:|---:|"]
    acumulado = 0
    for numero, n, copias, paginas, relleno, pg in filas:
        acumulado += pg
        lineas.append(f"| {numero:02d} | {n} | {copias} | {paginas} | {'sí' if relleno else 'no'} | {pg} | {pg // 2} |")
    lineas += ["", f"Las copias van en orden ascendente de grupo; el grupo 01 empieza en la hoja 1 y "
               f"el último termina en la hoja {total_paginas // 2}."]
    if faltantes:
        lineas += ["", "**Estudiantes sin enunciado (no incluidos):** " + "; ".join(f"{a.nombre} (grupo {a.grupo})" for a in faltantes)]
    (directorio / SALIDA_MD).write_text("\n".join(lineas) + "\n", encoding="utf-8")

    print(f"\nPDF        : {salida}  ({paginas_reales} carillas, {paginas_reales // 2} hojas a doble cara)")
    print(f"Copias     : {sum(f[2] for f in filas)} en {len(filas)} grupos, en orden ascendente")
    print(f"Orden      : {directorio / SALIDA_MD}")
    return 0


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="PDF único e imprimible con los enunciados del IET.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--dir", default=None, metavar="DIR", help="directorio de los enunciados (output/<sigla>/<tarea>).")
    comunes.add_argument("--curso", default=None, metavar="SIGLA", help="sigla del curso, con --tarea.")
    comunes.add_argument("--tarea", default=None, metavar="NOMBRE", help="nombre de la tarea, con --curso.")
    comunes.add_argument("--roster", default=None, metavar="CSV", help=f"roster del curso (por defecto {ROSTER_DEFAULT.relative_to(REPO_ROOT)}).")

    p = sub.add_parser("validar", parents=[comunes], help="comprueba que todo estudiante del roster tenga enunciado.")
    p.set_defaults(func=cmd_validar)

    p = sub.add_parser("generar", parents=[comunes], help="arma el PDF único, ordenado por grupo, con relleno y copias.")
    p.add_argument("--copias", type=int, default=None, metavar="N", help="copias fijas por grupo (por defecto, una por integrante).")
    p.add_argument("--copias-extra", type=int, default=None, metavar="N", help="copias adicionales por grupo, además de una por integrante.")
    p.add_argument("--salida", default=None, metavar="ARCHIVO", help=f"nombre del PDF (por defecto {SALIDA_PDF}).")
    p.add_argument("--permitir-faltantes", action="store_true", help="genera el PDF aunque falten enunciados.")
    p.set_defaults(func=cmd_generar)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)
    try:
        return opts.func(opts)
    except ErrorImpresion as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
