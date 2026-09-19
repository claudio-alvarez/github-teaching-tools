# Skill `preparar-impresion-iet`

Arma **un solo PDF imprimible** con los enunciados del IET de todos los grupos de una
tarea, listo para impresión a doble cara y para repartir llamando grupo a grupo.
Antes comprueba, contra el roster, que **ningún estudiante quede sin enunciado**.

Es la etapa que sigue a [`preparar-iet`](../preparar-iet/), que deja un
`STATEMENT.pdf` por grupo.

```
assignment-assessment/output/<SIGLA-CURSO>/<TAREA>/
├── grupo-01/STATEMENT.pdf     ← entrada (uno por grupo)
├── grupo-02/STATEMENT.pdf
├── …
├── IET-impresion.pdf          ← salida: todos los enunciados, en orden, con copias y relleno
└── IET-impresion.md           ← salida: orden de impresión (grupo, copias, hojas)
```

## Qué hace

1. Lee el roster (`roster/roster.csv`) y agrupa a los estudiantes por número de
   grupo.
2. Para cada grupo del roster busca `grupo-XX/STATEMENT.pdf`, cuenta sus carillas y
   comprueba que los nombres de los integrantes aparezcan en la cabecera del
   enunciado.
3. **Reporta los estudiantes sin enunciado.** Si hay alguno, no genera el PDF (salvo
   `--permitir-faltantes`).
4. Concatena los enunciados en **orden ascendente de grupo**, con **una copia por
   integrante** y, cuando un enunciado tiene un número impar de carillas, una
   **página en blanco** al final de cada copia, para que a doble cara la copia
   siguiente empiece en hoja nueva.
5. Verifica que el PDF final tenga exactamente las carillas esperadas y escribe el
   manifiesto de impresión.

## Cómo se invoca

```
/preparar-impresion-iet
/preparar-impresion-iet --copias-extra 1
/preparar-impresion-iet --curso ICC3201 --tarea tarea-2
```

| Argumento | Para qué |
|---|---|
| `--curso SIGLA --tarea NOMBRE` | Otra tarea: `output/<SIGLA>/<NOMBRE>`. Por defecto, la de la última descarga. |
| `--dir DIR` | Directorio de enunciados explícito. |
| `--roster CSV` | Otro roster. Por defecto, `roster/roster.csv`. |
| `--copias N` | Copias fijas por grupo, en vez de una por integrante. |
| `--copias-extra N` | Copias adicionales por grupo (reserva). |
| `--permitir-faltantes` | Genera igual aunque falten enunciados; el manifiesto dice quiénes quedan fuera. |

## El script

```bash
# Desde la raíz del repositorio
python3 .claude/skills/preparar-impresion-iet/scripts/imprimir.py validar
python3 .claude/skills/preparar-impresion-iet/scripts/imprimir.py generar
python3 .claude/skills/preparar-impresion-iet/scripts/imprimir.py generar --copias-extra 1
```

| Subcomando | Qué hace |
|---|---|
| `validar` | Tabla por grupo del roster: integrantes, si existe el enunciado, carillas y observaciones; lista de estudiantes sin enunciado. Sale con 1 si falta alguno. |
| `generar` | Valida y, si no falta nadie, escribe `IET-impresion.pdf` e `IET-impresion.md`. |

Solo biblioteca estándar más herramientas externas por subproceso: `pdfinfo` y
`pdfunite` de poppler (`brew install poppler`) o, en su defecto, `gs` de Ghostscript
(`brew install ghostscript`), que además genera la página en blanco de relleno.

## Impresión y reparto

- Imprimir **a doble cara**. Cada copia empieza en hoja nueva gracias al relleno.
- El manifiesto `IET-impresion.md` indica, por grupo, cuántas copias y cuántas hojas;
  el orden es el del número de grupo, así que se puede repartir llamando grupo a
  grupo y tomando las hojas de arriba de la pila.
- Un grupo de dos integrantes recibe dos copias del mismo enunciado, una para cada
  uno.

## Problemas frecuentes

**«ESTUDIANTES SIN ENUNCIADO»** — a esos grupos les falta `STATEMENT.pdf`. Márcales
un problema en su `QUESTIONS.md` y corre `preparar-iet`. Si el grupo no tiene
minuta, el roster y la descarga no coinciden: revisa `clone_repos.py` y
`preguntas-revision`.

**«no aparecen en la cabecera»** — el roster cambió después de generar el enunciado.
Regenera ese grupo: `/preparar-iet --group N --rehacer`.

**«hay enunciados de grupos que no están en el roster»** — directorios de grupos
fusionados o eliminados; no se imprimen. Bórralos si ya no corresponden.

**«hace falta pdfinfo / pdfunite / gs»** — instala poppler o Ghostscript.
