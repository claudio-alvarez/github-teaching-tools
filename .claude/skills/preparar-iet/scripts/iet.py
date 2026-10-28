#!/usr/bin/env python3
"""Prepara el ítem de evaluación de tarea (IET) de cada grupo.

Lee las minutas `QUESTIONS.md` que dejó la skill `preguntas-revision`, toma el
problema que el docente marcó con `[x]` y escribe, en el directorio del grupo:

    STATEMENT.md   enunciado para los estudiantes (lápiz y papel, sin código)
    SOLUTION.md    pauta de corrección para los ayudantes
    STATEMENT.pdf  y  SOLUTION.pdf, renderizados desde los markdown

    python3 iet.py listar  [--dir DIR | --curso SIGLA --tarea T]
    python3 iet.py generar [--dir DIR] [--group N ...] [--rehacer] [--sin-pdf]
    python3 iet.py pdf     [--dir DIR] [--group N ...]        # re-renderiza los .md

Solo biblioteca estándar. El PDF se produce con un navegador Chromium en modo
headless (Google Chrome, Chromium, Brave o Edge), que se busca en el PATH y en
/Applications; sin navegador quedan los .md y se avisa.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# El script vive en <repo>/.claude/skills/preparar-iet/scripts/
REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_ROOT = REPO_ROOT / "assignment-assessment" / "output"
ESTADO_CLONES = REPO_ROOT / "assignment-assessment" / "state" / "clones.json"

MINUTA = "QUESTIONS.md"
STATEMENT = "STATEMENT.md"
SOLUTION = "SOLUTION.md"

RE_META = re.compile(r"^- \*\*(.+?):\*\* ?(.*)$")
RE_MARCA = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*Problema\s+(\d+)\s+—\s+(.+?)\s*$")
RE_PROBLEMA = re.compile(r"^### Problema (\d+) — (.+?)\s*$")
RE_SUBPARTE = re.compile(r"\*\*\((\w+)\) ([^*]+?) — (\d+) puntos\.\*\*")
RE_GRUPO_DIR = re.compile(r"grupo-(\d+)$")


class ErrorIET(Exception):
    pass


# --- lectura de la minuta ----------------------------------------------------


@dataclass
class Minuta:
    ruta: Path
    grupo: int
    meta: dict[str, str] = field(default_factory=dict)
    fallback: str = ""
    marcados: list[tuple[int, str]] = field(default_factory=list)
    candidatos: list[tuple[int, str]] = field(default_factory=list)
    problemas: dict[int, tuple[str, str]] = field(default_factory=dict)  # n -> (título, cuerpo)
    revisor: dict[int, tuple[str, str]] = field(default_factory=dict)    # n -> (refs, cuerpo)

    @property
    def elegido(self) -> int | None:
        return self.marcados[0][0] if len(self.marcados) == 1 else None

    def subpartes(self, n: int) -> list[tuple[str, str, int]]:
        cuerpo = self.problemas[n][1]
        return [(p, t.strip(), int(pts)) for p, t, pts in RE_SUBPARTE.findall(cuerpo)]


def _secciones(texto: str) -> dict[str, str]:
    """Parte el markdown por encabezados `## `. La clave '' es lo anterior al primero."""
    partes: dict[str, list[str]] = {"": []}
    actual = ""
    en_codigo = False
    for linea in texto.splitlines():
        if linea.startswith("```"):
            en_codigo = not en_codigo
        if not en_codigo and linea.startswith("## "):
            actual = linea[3:].strip()
            partes.setdefault(actual, [])
            continue
        partes.setdefault(actual, []).append(linea)
    return {k: "\n".join(v).strip("\n") for k, v in partes.items()}


def _bloques_problema(seccion: str) -> dict[int, tuple[str, str]]:
    """`### Problema N — X` -> {N: (X, cuerpo)}, respetando bloques de código."""
    bloques: dict[int, tuple[str, str]] = {}
    numero, titulo, cuerpo = None, "", []
    en_codigo = False
    for linea in seccion.splitlines():
        if linea.startswith("```"):
            en_codigo = not en_codigo
        m = RE_PROBLEMA.match(linea) if not en_codigo else None
        if m:
            if numero is not None:
                bloques[numero] = (titulo, "\n".join(cuerpo).strip("\n"))
            numero, titulo, cuerpo = int(m.group(1)), m.group(2), []
            continue
        if numero is not None:
            cuerpo.append(linea)
    if numero is not None:
        bloques[numero] = (titulo, "\n".join(cuerpo).strip("\n"))
    return bloques


def leer_minuta(ruta: Path) -> Minuta:
    texto = ruta.read_text(encoding="utf-8")
    m = RE_GRUPO_DIR.search(ruta.parent.name)
    if not m:
        raise ErrorIET(f"{ruta}: el directorio no se llama grupo-XX.")
    minuta = Minuta(ruta=ruta, grupo=int(m.group(1)))

    secciones = _secciones(texto)
    cabecera = secciones.get("", "")

    clave = None
    for linea in cabecera.splitlines():
        mm = RE_META.match(linea)
        if mm:
            clave = mm.group(1).strip()
            minuta.meta[clave] = mm.group(2).strip()
        elif clave and linea.startswith("  ") and linea.strip():
            minuta.meta[clave] += " " + linea.strip()
        else:
            clave = None
    fallback = re.search(r"^> \(Solo en el fallback\)(.*(?:\n>.*)*)", cabecera, re.M)
    if fallback:
        minuta.fallback = re.sub(r"\n> ?", " ", fallback.group(1)).strip()

    seleccion = secciones.get("Selección para la evaluación", "")
    for linea in seleccion.splitlines():
        mm = RE_MARCA.match(linea)
        if mm:
            n, titulo = int(mm.group(2)), mm.group(3)
            minuta.candidatos.append((n, titulo))
            if mm.group(1) in "xX":
                minuta.marcados.append((n, titulo))

    minuta.problemas = _bloques_problema(secciones.get("Problemas candidatos", ""))
    minuta.revisor = _bloques_problema(secciones.get("Para el revisor", ""))
    return minuta


def estado(minuta: Minuta) -> str:
    if not minuta.candidatos:
        return "sin lista de selección (formato antiguo)"
    if not minuta.marcados:
        return "sin marcar"
    if len(minuta.marcados) > 1:
        return f"{len(minuta.marcados)} marcados (!)"
    n = minuta.elegido
    if n not in minuta.problemas:
        return f"P{n} marcado pero no existe el problema"
    if n not in minuta.revisor:
        return f"P{n} marcado sin sección para el revisor"
    return f"P{n} marcado"


# --- generación de los documentos --------------------------------------------


def _cabecera(minuta: Minuta, titulo: str, extra: list[str]) -> list[str]:
    grupo = f"{minuta.grupo:02d}"
    lineas = [f"# {titulo}", ""]
    lineas.append(f"- **Curso:** {minuta.meta.get('Curso', '—')}")
    lineas.append(f"- **Tarea:** {minuta.meta.get('Tarea', '—')}")
    lineas.append(f"- **Grupo:** {grupo}")
    lineas.append(f"- **Integrantes:** {minuta.meta.get('Integrantes', '—')}")
    lineas.append(f"- **Ayudante:** {minuta.meta.get('Ayudante', '—')}")
    lineas.extend(extra)
    return lineas


def _puntaje(minuta: Minuta, n: int) -> tuple[int, str]:
    partes = minuta.subpartes(n)
    total = sum(p for _, _, p in partes)
    reparto = " · ".join(f"({e}) {p}" for e, _, p in partes)
    return total, reparto


def statement_md(minuta: Minuta, n: int) -> str:
    titulo, cuerpo = minuta.problemas[n]
    total, reparto = _puntaje(minuta, n)
    tarea = minuta.meta.get("Tarea", "tarea")
    lineas = _cabecera(
        minuta,
        f"Ítem de evaluación de tarea — {tarea} — Grupo {minuta.grupo:02d}",
        [f"- **Puntaje:** {total} puntos — {reparto}"],
    )
    lineas += [
        "",
        "**Nombre del estudiante:** ______________________________________________",
        "",
        "## Instrucciones",
        "",
        "- Este ítem se responde de manera **individual**, con lápiz y papel.",
        "- No se dispone del enunciado de la tarea ni del código del repositorio: "
        "todo lo necesario para responder está en este documento. Los requisitos de "
        "la tarea que hacen falta aparecen citados bajo «Del enunciado de la tarea».",
    ]
    if minuta.fallback:
        lineas.append(
            "- Los fragmentos de código de este problema corresponden a la **solución "
            "de referencia del curso**, no al repositorio del grupo."
        )
    else:
        lineas.append(
            "- Los fragmentos de código corresponden al repositorio entregado por su "
            "grupo, en el commit indicado junto a cada uno."
        )
    lineas += [
        "- Cada fragmento se muestra dentro de la función que lo contiene. Las líneas "
        "`// ...` marcan código omitido; la referencia `archivo:líneas` corresponde al "
        "tramo mostrado, no a las omisiones.",
        "- Cada parte indica su puntaje. Justifiquen las respuestas con referencia al "
        "código citado; en las simulaciones muestren los valores intermedios, no "
        "solo el resultado.",
        "",
        f"## Problema — {titulo}",
        "",
        cuerpo,
        "",
    ]
    return "\n".join(lineas)


def solution_md(minuta: Minuta, n: int) -> str:
    titulo, cuerpo = minuta.problemas[n]
    refs, pauta = minuta.revisor[n]
    total, reparto = _puntaje(minuta, n)
    tarea = minuta.meta.get("Tarea", "tarea")
    extra = [f"- **Puntaje:** {total} puntos — {reparto}"]
    for clave in ("Repositorio", "Commit revisado", "Schema"):
        if clave in minuta.meta:
            extra.append(f"- **{clave}:** {minuta.meta[clave]}")
    lineas = _cabecera(
        minuta,
        f"Pauta de corrección del IET — {tarea} — Grupo {minuta.grupo:02d}",
        extra,
    )
    lineas += [
        "",
        "> Documento para el equipo docente. No se entrega a los estudiantes.",
        "",
    ]
    if minuta.fallback:
        lineas += [f"> {minuta.fallback}", ""]
    lineas += [
        f"## Problema — {titulo}",
        "",
        cuerpo,
        "",
        f"## Pauta — {refs}",
        "",
        pauta,
        "",
        "## Registro de puntaje",
        "",
        "| Parte | Puntaje máximo | Puntaje obtenido |",
        "|---|---:|---:|",
    ]
    for etiqueta, tipo, puntos in minuta.subpartes(n):
        lineas.append(f"| ({etiqueta}) {tipo} | {puntos} | |")
    lineas.append(f"| **Total** | **{total}** | |")
    lineas.append("")
    return "\n".join(lineas)


# --- markdown -> html --------------------------------------------------------
#
# Conversor del subconjunto de markdown que usan las minutas: encabezados,
# párrafos, listas (con y sin casillas), bloques de código, citas, tablas,
# negritas, código en línea y enlaces. No pretende ser general.


def _inline(texto: str) -> str:
    # Los ítems de lista llegan con sus líneas de continuación unidas por «\n»;
    # una negrita o un enlace pueden cruzar ese salto, así que se normaliza antes.
    texto = " ".join(texto.split("\n"))
    partes = texto.split("`")
    salida = []
    for i, parte in enumerate(partes):
        if i % 2 == 1:
            salida.append(f"<code>{html.escape(parte)}</code>")
            continue
        parte = html.escape(parte, quote=False)
        parte = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", parte)
        parte = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", parte)
        parte = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', parte)
        salida.append(parte)
    return "".join(salida)


def _tabla(filas: list[str]) -> str:
    def celdas(fila: str) -> list[str]:
        return [c.strip() for c in fila.strip().strip("|").split("|")]

    cabecera = celdas(filas[0])
    alineacion = []
    for sep in celdas(filas[1]) if len(filas) > 1 else []:
        if sep.endswith(":") and sep.startswith(":"):
            alineacion.append("center")
        elif sep.endswith(":"):
            alineacion.append("right")
        else:
            alineacion.append("left")
    out = ["<table>", "<thead><tr>"]
    for i, c in enumerate(cabecera):
        al = alineacion[i] if i < len(alineacion) else "left"
        out.append(f'<th style="text-align:{al}">{_inline(c)}</th>')
    out.append("</tr></thead><tbody>")
    for fila in filas[2:]:
        out.append("<tr>")
        for i, c in enumerate(celdas(fila)):
            al = alineacion[i] if i < len(alineacion) else "left"
            out.append(f'<td style="text-align:{al}">{_inline(c)}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def md_a_html(md: str) -> str:
    lineas = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lineas)

    def es_item(l: str) -> re.Match | None:
        return re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", l)

    while i < n:
        linea = lineas[i]

        if not linea.strip():
            i += 1
            continue

        if linea.startswith("```"):
            lenguaje = linea[3:].strip()
            cuerpo = []
            i += 1
            while i < n and not lineas[i].startswith("```"):
                cuerpo.append(lineas[i])
                i += 1
            i += 1
            clase = f' class="lang-{html.escape(lenguaje)}"' if lenguaje else ""
            out.append(f"<pre><code{clase}>{html.escape(chr(10).join(cuerpo))}</code></pre>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", linea)
        if m:
            nivel = len(m.group(1))
            out.append(f"<h{nivel}>{_inline(m.group(2).strip())}</h{nivel}>")
            i += 1
            continue

        if re.match(r"^\s*([-*_])\s*\1\s*\1[\s\1]*$", linea):
            out.append("<hr>")
            i += 1
            continue

        if linea.startswith(">"):
            cita = []
            while i < n and lineas[i].startswith(">"):
                cita.append(re.sub(r"^> ?", "", lineas[i]))
                i += 1
            out.append(f"<blockquote>{md_a_html(chr(10).join(cita))}</blockquote>")
            continue

        if linea.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|?\s*:?-{3,}", lineas[i + 1]):
            filas = []
            while i < n and lineas[i].lstrip().startswith("|"):
                filas.append(lineas[i])
                i += 1
            out.append(_tabla(filas))
            continue

        m = es_item(linea)
        if m and not m.group(1):
            ordenada = m.group(2)[0].isdigit()
            inicio = int(m.group(2).rstrip(".")) if ordenada else 1
            items: list[str] = []
            while i < n:
                mm = es_item(lineas[i])
                if mm and not mm.group(1) and (mm.group(2)[0].isdigit() == ordenada):
                    items.append(mm.group(3))
                    i += 1
                    # líneas de continuación: sangradas, o un bloque de código sangrado
                    while i < n and lineas[i].strip() and (lineas[i].startswith("  ") or lineas[i].startswith("\t")):
                        items[-1] += "\n" + lineas[i].strip()
                        i += 1
                elif not lineas[i].strip() and i + 1 < n and es_item(lineas[i + 1]) and not es_item(lineas[i + 1]).group(1):
                    i += 1  # línea en blanco entre ítems de la misma lista
                else:
                    break
            etiqueta = "ol" if ordenada else "ul"
            # Las citas del enunciado traen reglas numeradas (4., 5.): se conserva
            # el número inicial para que «la regla 4» siga siendo la regla 4.
            atributo = f' start="{inicio}"' if ordenada and inicio != 1 else ""
            out.append(f"<{etiqueta}{atributo}>")
            for item in items:
                casilla = re.match(r"^\[( |x|X)\]\s+(.*)$", item, re.S)
                if casilla:
                    marcado = "checked" if casilla.group(1) in "xX" else ""
                    out.append(f'<li class="tarea"><input type="checkbox" disabled {marcado}> {_inline(casilla.group(2))}</li>')
                else:
                    out.append(f"<li>{_inline(item)}</li>")
            out.append(f"</{etiqueta}>")
            continue

        parrafo = []
        while i < n and lineas[i].strip() and not lineas[i].startswith(("#", "```", ">", "|")) and not (es_item(lineas[i]) and not es_item(lineas[i]).group(1)):
            parrafo.append(lineas[i].strip())
            i += 1
        if parrafo:
            out.append(f"<p>{_inline(' '.join(parrafo))}</p>")
        else:
            i += 1  # línea que no encajó en nada: no ciclar
    return "\n".join(out)


# Tamaño de página para el @page del CSS. Letter es el papel estándar donde se
# imprime hoy; A4 queda disponible con --papel a4.
PAPELES = {"letter": "Letter", "a4": "A4"}
PAPEL_DEFECTO = "letter"

CSS = """
@page { size: @PAPEL@; margin: 18mm 18mm 20mm 18mm; }
html { font-size: 10.5pt; }
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.38; color: #111;
       max-width: 100%; margin: 0; }
h1 { font-size: 1.55em; margin: 0 0 .5em; border-bottom: 1.5px solid #333; padding-bottom: .2em; }
h2 { font-size: 1.22em; margin: 1.3em 0 .5em; border-bottom: 1px solid #999; padding-bottom: .15em;
     page-break-after: avoid; }
h3 { font-size: 1.05em; margin: 1.1em 0 .4em; page-break-after: avoid; }
p { margin: .45em 0; text-align: justify; }
p:has(+ pre), p:has(+ blockquote), p:has(+ table) { break-after: avoid; page-break-after: avoid; }
ul, ol { margin: .3em 0 .5em; padding-left: 1.5em; }
li { margin: .18em 0; }
li.tarea { list-style: none; margin-left: -1.3em; }
code { font-family: Menlo, Consolas, "DejaVu Sans Mono", monospace; font-size: .86em;
       background: #f3f3f3; padding: 0 .18em; border-radius: 2px; }
pre { background: #f6f6f6; border: 1px solid #ccc; border-left: 3px solid #666; padding: .55em .7em;
      overflow-x: auto; margin: .5em 0 .8em; }
/* Un bloque largo puede partirse entre páginas: es preferible a dejar media página
   en blanco. Los cortos se protegen con orphans/widows generosos. */
pre code { orphans: 6; widows: 6; }
pre code { background: none; padding: 0; font-size: .8em; line-height: 1.32; white-space: pre; }
blockquote { margin: .6em 0; padding: .3em .9em; border-left: 3px solid #999; background: #fafafa;
             color: #222; page-break-inside: avoid; }
blockquote p { text-align: left; }
table { border-collapse: collapse; margin: .6em 0; width: 100%; page-break-inside: avoid; }
th, td { border: 1px solid #999; padding: .3em .5em; vertical-align: top; }
th { background: #eee; }
strong { font-weight: 700; }
"""


def html_documento(md: str, titulo: str, papel: str = PAPEL_DEFECTO) -> str:
    css = CSS.replace("@PAPEL@", PAPELES[papel])
    return (
        "<!DOCTYPE html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(titulo)}</title>\n<style>{css}</style>\n</head>\n<body>\n"
        f"{md_a_html(md)}\n</body>\n</html>\n"
    )


# --- html -> pdf con un navegador headless -----------------------------------

NAVEGADORES = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "brave-browser", "microsoft-edge", "chrome",
)
NAVEGADORES_MAC = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def buscar_navegador() -> str | None:
    for nombre in NAVEGADORES:
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    for ruta in NAVEGADORES_MAC:
        if Path(ruta).exists():
            return ruta
    return None


def html_a_pdf(navegador: str, html_path: Path, pdf_path: Path, espera: float = 90.0) -> None:
    """Imprime el HTML a PDF con el navegador headless.

    Chrome escribe el PDF y a veces no termina el proceso (servicios de fondo,
    sandbox del entorno). Por eso no se espera a que salga: se vigila el archivo
    y, cuando aparece y deja de crecer, se cierra el navegador.
    """
    pdf_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="iet-chrome-") as perfil:
        cmd = [
            navegador, "--headless=new", "--disable-gpu", "--no-first-run",
            "--disable-extensions", "--disable-sync", "--disable-background-networking",
            f"--user-data-dir={perfil}", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri(),
        ]
        proceso = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        inicio = time.monotonic()
        tamano_previo, estable = -1, 0
        try:
            while time.monotonic() - inicio < espera:
                if pdf_path.exists():
                    tamano = pdf_path.stat().st_size
                    estable = estable + 1 if tamano == tamano_previo and tamano > 0 else 0
                    tamano_previo = tamano
                    if estable >= 3:  # tres lecturas iguales: ~0.6 s sin crecer
                        break
                if proceso.poll() is not None:
                    break
                time.sleep(0.2)
        finally:
            if proceso.poll() is None:
                proceso.terminate()
                try:
                    proceso.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    proceso.wait(timeout=5)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        salida = ""
        try:
            salida = (proceso.stderr.read() or "").strip()[-400:]
        except (OSError, ValueError):
            pass
        raise ErrorIET(f"el navegador no produjo {pdf_path.name}: {salida or 'sin salida'}")


def render_pdf(md_path: Path, navegador: str, papel: str = PAPEL_DEFECTO) -> Path:
    md = md_path.read_text(encoding="utf-8")
    titulo = next((l[2:] for l in md.splitlines() if l.startswith("# ")), md_path.stem)
    pdf_path = md_path.with_suffix(".pdf")
    with tempfile.TemporaryDirectory(prefix="iet-html-") as tmp:
        html_path = Path(tmp) / (md_path.stem + ".html")
        html_path.write_text(html_documento(md, titulo, papel), encoding="utf-8")
        html_a_pdf(navegador, html_path, pdf_path)
    return pdf_path


# --- ubicación del directorio de la tarea ------------------------------------


def resolver_dir(opts) -> Path:
    if opts.dir:
        d = Path(opts.dir).expanduser().resolve()
    elif opts.curso and opts.tarea:
        d = OUTPUT_ROOT / opts.curso / opts.tarea
    elif opts.curso or opts.tarea:
        raise ErrorIET("Indica --curso y --tarea juntos, o --dir.")
    else:
        if not ESTADO_CLONES.exists():
            raise ErrorIET(
                f"No hay corrida previa en {ESTADO_CLONES}. Indica --curso SIGLA "
                f"--tarea NOMBRE, o --dir con el directorio de las minutas."
            )
        estado_json = json.loads(ESTADO_CLONES.read_text(encoding="utf-8"))
        manifiesto = Path(estado_json.get("manifiesto", ""))
        if not manifiesto.exists():
            raise ErrorIET(f"El manifiesto {manifiesto} ya no existe; usa --dir.")
        salida = json.loads(manifiesto.read_text(encoding="utf-8")).get("output_dir")
        if not salida:
            raise ErrorIET("El manifiesto no trae output_dir; usa --dir.")
        d = Path(salida)
    if not d.is_dir():
        raise ErrorIET(f"No existe el directorio {d}.")
    return d


def minutas_en(directorio: Path, grupos: list[int] | None) -> list[Minuta]:
    resultado = []
    for ruta in sorted(directorio.glob("grupo-*/" + MINUTA)):
        minuta = leer_minuta(ruta)
        if grupos and minuta.grupo not in grupos:
            continue
        resultado.append(minuta)
    if not resultado:
        raise ErrorIET(f"No hay minutas {MINUTA} en {directorio}/grupo-XX/.")
    return resultado


# --- subcomandos -------------------------------------------------------------


def cmd_listar(opts) -> int:
    directorio = resolver_dir(opts)
    minutas = minutas_en(directorio, opts.group)
    navegador = buscar_navegador()
    print(f"Minutas    : {directorio}")
    print(f"Navegador  : {navegador or 'NO ENCONTRADO — no se podrán generar PDF'}")
    print()
    print(f"{'Gr':>3}  {'Selección':<38} {'Título del problema elegido':<44} Archivos")
    print("-" * 110)
    for m in minutas:
        est = estado(m)
        titulo = m.problemas[m.elegido][0] if m.elegido in m.problemas else "—"
        archivos = []
        for nombre in (STATEMENT, SOLUTION, "STATEMENT.pdf", "SOLUTION.pdf"):
            if (m.ruta.parent / nombre).exists():
                archivos.append(nombre)
        print(f"{m.grupo:>3}  {est:<38} {titulo[:44]:<44} {', '.join(archivos) or '—'}")
    return 0


def cmd_generar(opts) -> int:
    directorio = resolver_dir(opts)
    minutas = minutas_en(directorio, opts.group)
    navegador = None if opts.sin_pdf else buscar_navegador()
    if not opts.sin_pdf and not navegador:
        print("AVISO: no se encontró Google Chrome, Chromium, Brave ni Edge; se escriben "
              "solo los .md. Instala uno o usa --sin-pdf para silenciar este aviso.\n")

    generados, saltados, errores = [], [], []
    for m in minutas:
        est = estado(m)
        if m.elegido is None or m.elegido not in m.problemas or m.elegido not in m.revisor:
            saltados.append((m.grupo, est))
            continue
        destino = m.ruta.parent
        existentes = [n for n in (STATEMENT, SOLUTION) if (destino / n).exists()]
        if existentes and not opts.rehacer:
            saltados.append((m.grupo, f"ya existe {', '.join(existentes)} (usa --rehacer)"))
            continue
        try:
            (destino / STATEMENT).write_text(statement_md(m, m.elegido), encoding="utf-8")
            (destino / SOLUTION).write_text(solution_md(m, m.elegido), encoding="utf-8")
            pdfs = []
            if navegador:
                for nombre in (STATEMENT, SOLUTION):
                    pdfs.append(render_pdf(destino / nombre, navegador, opts.papel).name)
            generados.append((m.grupo, m.elegido, m.problemas[m.elegido][0], pdfs))
            print(f"grupo {m.grupo:02d}: P{m.elegido} «{m.problemas[m.elegido][0]}» → "
                  f"{STATEMENT}, {SOLUTION}" + (f", {', '.join(pdfs)}" if pdfs else ""))
        except ErrorIET as error:
            errores.append((m.grupo, str(error)))
            print(f"grupo {m.grupo:02d}: ERROR — {error}")

    print()
    print(f"Generados : {len(generados)} grupo(s)")
    for grupo, motivo in saltados:
        print(f"Saltado   : grupo {grupo} — {motivo}")
    for grupo, motivo in errores:
        print(f"ERROR     : grupo {grupo} — {motivo}")
    return 1 if errores else 0


def cmd_pdf(opts) -> int:
    directorio = resolver_dir(opts)
    navegador = buscar_navegador()
    if not navegador:
        raise ErrorIET("No se encontró Google Chrome, Chromium, Brave ni Edge.")
    hechos = 0
    for ruta in sorted(directorio.glob("grupo-*/")):
        m = RE_GRUPO_DIR.search(ruta.name)
        if not m or (opts.group and int(m.group(1)) not in opts.group):
            continue
        for nombre in (STATEMENT, SOLUTION):
            md = ruta / nombre
            if md.exists():
                pdf = render_pdf(md, navegador, opts.papel)
                print(f"{pdf}")
                hechos += 1
    if not hechos:
        raise ErrorIET(f"No hay {STATEMENT}/{SOLUTION} que renderizar en {directorio}.")
    return 0


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Prepara el ítem de evaluación de tarea (IET) desde las minutas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--dir", default=None, metavar="DIR",
                         help="directorio de las minutas (output/<sigla>/<tarea>).")
    comunes.add_argument("--curso", default=None, metavar="SIGLA",
                         help="sigla del curso, con --tarea, para armar el directorio.")
    comunes.add_argument("--tarea", default=None, metavar="NOMBRE",
                         help="nombre de la tarea, con --curso.")
    comunes.add_argument("--group", type=int, action="append", metavar="N",
                         help="solo estos grupos. Repetible.")

    p = sub.add_parser("listar", parents=[comunes],
                       help="qué problema marcó el docente en cada minuta y qué archivos hay.")
    p.set_defaults(func=cmd_listar)

    p = sub.add_parser("generar", parents=[comunes],
                       help="escribe STATEMENT.md, SOLUTION.md y sus PDF.")
    p.add_argument("--rehacer", action="store_true",
                   help="sobrescribe STATEMENT.md/SOLUTION.md existentes.")
    p.add_argument("--sin-pdf", action="store_true", help="no renderiza PDF.")
    p.add_argument("--papel", choices=sorted(PAPELES), default=PAPEL_DEFECTO,
                   help=f"tamaño de página de los PDF (por defecto, {PAPEL_DEFECTO}).")
    p.set_defaults(func=cmd_generar)

    p = sub.add_parser("pdf", parents=[comunes],
                       help="re-renderiza los PDF desde los .md (tras editarlos a mano).")
    p.add_argument("--papel", choices=sorted(PAPELES), default=PAPEL_DEFECTO,
                   help=f"tamaño de página de los PDF (por defecto, {PAPEL_DEFECTO}).")
    p.set_defaults(func=cmd_pdf)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)
    try:
        return opts.func(opts)
    except ErrorIET as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
